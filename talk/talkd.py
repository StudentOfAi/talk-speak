#!/usr/bin/env python3
"""talkd — hold-space dictation daemon for macOS (talk-speak).

Always ARMED, in EVERY app: mic closed. Hold SPACE to talk; the mic opens only
while held. Release -> transcribe -> typed wherever the keyboard focus is
(terminal, browser, Docs, Notes, Mail...), no Enter. A quick tap of space
(< PTT_MIN_HOLD) is passed through as a normal space. Any space-down while
`say` is speaking cuts the speech off. No wake word, no claps, no window gate.

Controlled by `talk-speak talk ...`. Every file lives in $TALK_SPEAK_HOME
(default ~/.talk-speak): talk.log, talk.pid, talk.health.json, talk.cfg, talk.vocab.
Runs as a child of ~/Applications/talk-speak.app (the signed stub launchd runs),
which owns the Microphone / Accessibility / Input Monitoring grants.
Supervised by launchd (KeepAlive) — no Terminal, no watchdog.
"""
import os, sys, time, json, queue, subprocess, re, threading
from collections import deque
from datetime import datetime

import numpy as np
import sounddevice as sd

VERSION = "3.0.2"                # keep in sync with the VERSION file (CI checks)
STATE = os.environ.get("TALK_SPEAK_HOME") or os.path.expanduser("~/.talk-speak")
LAUNCHD_LABEL = "com.studentofai.talk-speak"


def _p(name: str) -> str:
    """Path of a state file under STATE."""
    return os.path.join(STATE, name)


SR = 16000
BLOCK = 480                      # 30 ms blocks
LOG = _p("talk.log")

PTT_KEYCODE = 49                 # space
PTT_MIN_HOLD = 0.30              # shorter than this = a normal space keypress
PTT_MAX_HOLD = 90.0
TYPING_GUARD_S = 0.40            # a space within this long after another key = normal typing, not PTT
# Streaming: transcribe each phrase at a silence boundary while you keep talking,
# so release-to-text latency is ~one segment instead of the whole hold.
STREAMING = True               # segment at pauses while talking; False = one whole-buffer pass
SEG_SILENCE_S = 0.7             # only a clear pause ends a phrase (short gaps garble on cut)
SEG_MIN_SPEECH_S = 1.6         # never cut a segment shorter than this (tiny clips hallucinate)
SEG_MAX_S = 12.0               # force-cut unbroken speech so latency stays bounded
SEG_RMS = 0.006                # absolute floor for "silence" (adaptive threshold can't go below this)
SEG_NOISE_MULT = 2.2           # a block is speech if louder than (rolling noise floor * this)
SEG_NOISE_WIN = 100            # blocks (~3s) used to estimate the noise floor adaptively
MAGIC = 0x7A1C                   # tags key events we post ourselves so the tap passes them

# optional overrides: JSON at $TALK_SPEAK_HOME/talk.cfg, e.g. {"PTT_MIN_HOLD": 0.25}
INPUT_DEVICE = None              # substring of the input device name; None = system default input
HISTORY = True                   # {"HISTORY": false} keeps no transcript log at all
try:
    import json
    with open(_p("talk.cfg")) as _f:
        for _k, _v in json.load(_f).items():
            if _k.isupper():
                globals()[_k] = _v
except FileNotFoundError:
    pass
except Exception as _e:
    print("talk.cfg ignored: %r" % _e, file=sys.stderr)

audio_q: "queue.Queue[np.ndarray]" = queue.Queue()
ptt_q: "queue.Queue[str]" = queue.Queue()
_model = None
_model_lock = threading.Lock()
state = {"armed": True, "ptt_down": False, "last_key_ts": 0.0, "down_ts": 0.0}

# ---------------------------------------------------------------- health / self-healing
# The safety property: the key tap holds the spacebar hostage ONLY while audio is
# proven healthy. If the mic dies, /talk degrades to a no-op and typing is untouched.
HEALTH_FILE = _p("talk.health.json")
PTT_FLAG = _p("talk.ptt")        # exists only while space is held; other mic apps can mute on it


def ptt_flag_set():
    """Tell other mic apps that talk-speak owns the mic right now."""
    try:
        with open(PTT_FLAG, "w") as f:
            f.write("%.3f\n" % time.time())
    except Exception as e:
        log("ptt flag set failed: %r" % e)


def ptt_flag_clear():
    try:
        os.unlink(PTT_FLAG)
    except FileNotFoundError:
        pass
    except Exception as e:
        log("ptt flag clear failed: %r" % e)
DEAD_RMS = 1e-4          # a capture quieter than this delivered no signal at all
DEAD_STRIKES = 2         # consecutive dead captures before degrading
HEAL_INTERVAL_S = 20.0   # how often to retry the mic while degraded
HEAL_BEFORE_RESTART = 6  # failed heals before the daemon re-execs itself
RESTART_WINDOW_S = 1800  # self-restarts are rate-limited inside this window
RESTART_MAX = 3          # ...to this many, then we stop and ask for hands
HEARTBEAT_S = 10.0

health = {
    "audio_ok": True,        # <- the tap reads this; False = space is never swallowed
    "state": "OK",
    "consec_dead": 0,
    "heal_attempts": 0,
    "healed": 0,
    "restarts": [],          # epoch seconds of recent self-restarts
    "last_ok": None,
    "last_error": None,
    "degraded_since": None,
    "backend": None,
    "started": time.time(),
}
health_lock = threading.Lock()
heal_now = threading.Event()

try:                                   # second pass: health knobs are overridable too
    with open(_p("talk.cfg")) as _f:
        for _k, _v in json.load(_f).items():
            if _k.isupper():
                globals()[_k] = _v
except Exception:
    pass


def notify(title, msg):
    """Best-effort desktop notification; never raises."""
    try:
        subprocess.run(["osascript", "-e",
                        'display notification %s with title %s' % (json.dumps(msg), json.dumps(title))],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def degrade(reason):
    """Mic is not delivering audio. Free the spacebar and start healing."""
    state["ptt_down"] = False      # the tap passes everything while degraded, so the
                                   # keyup never reaches the up-branch: a stuck flag here
                                   # gates the healer off forever (wedged 2026-09-03 → 09-04)
    with health_lock:
        if not health["audio_ok"]:
            return
        health["audio_ok"] = False
        health["state"] = "DEGRADED"
        health["last_error"] = reason
        health["degraded_since"] = time.time()
        health["heal_attempts"] = 0
    log("DEGRADED: %s — spacebar released to normal typing, healing in background" % reason)
    play("Basso")
    notify("/talk degraded", "Mic not delivering audio. Spacebar types normally. Healing...")
    heal_now.set()


def recover(how):
    with health_lock:
        was = health["audio_ok"]
        health["audio_ok"] = True
        health["state"] = "OK"
        health["consec_dead"] = 0
        health["heal_attempts"] = 0
        health["degraded_since"] = None
        health["last_error"] = None
        if not was:
            health["healed"] += 1
    if not was:
        log("RECOVERED via %s — push-to-talk armed again" % how)
        play("Glass")
        notify("/talk recovered", "Mic is back. Hold space to dictate.")


def audio_sample(peak_rms, blocks, held):
    """Feed one hold's measured energy to the health model."""
    if held < PTT_MIN_HOLD:
        return
    if blocks == 0 or peak_rms < DEAD_RMS:
        with health_lock:
            health["consec_dead"] += 1
            n = health["consec_dead"]
        log("capture delivered no signal (blocks=%d peak_rms=%.6f) strike %d/%d"
            % (blocks, peak_rms, n, DEAD_STRIKES))
        if n >= DEAD_STRIKES:
            degrade("%d consecutive captures with no audio" % n)
    else:
        with health_lock:
            health["consec_dead"] = 0
            health["last_ok"] = time.time()


def reset_portaudio():
    """Tear PortAudio down and back up: re-enumerates devices and clears a wedged
    CoreAudio client without restarting the process."""
    try:
        sd._terminate()
    except Exception as e:
        log("portaudio terminate: %r" % e)
    time.sleep(0.4)
    sd._initialize()


def audio_probe(seconds=0.4):
    """Open the mic and confirm blocks actually arrive. Returns (ok, detail)."""
    try:
        drain_queue(audio_q)
        st = open_stream()
    except Exception as e:
        return False, "open failed: %r" % e
    try:
        deadline = time.time() + seconds + 1.0
        got = 0
        peak = 0.0
        while time.time() < deadline and got < int(seconds * SR / BLOCK):
            try:
                c = audio_q.get(timeout=0.3)
            except queue.Empty:
                break
            got += 1
            peak = max(peak, float(np.sqrt((c ** 2).mean())))
        if got == 0:
            return False, "stream opened but delivered 0 blocks"
        if peak < DEAD_RMS:
            return False, "delivered %d blocks of pure zeros" % got
        return True, "%d blocks, peak_rms=%.5f" % (got, peak)
    finally:
        try:
            st.stop(); st.close()
        except Exception:
            pass
        drain_queue(audio_q)


def self_restart(why):
    """Re-exec this daemon in place: a brand new CoreAudio client, same pid lineage
    (so Terminal's Accessibility grant is kept). Rate-limited."""
    now = time.time()
    with health_lock:
        health["restarts"] = [t for t in health["restarts"] if now - t < RESTART_WINDOW_S]
        if len(health["restarts"]) >= RESTART_MAX:
            log("self-restart suppressed (%d in the last %dmin) — needs hands: replug the microphone"
                % (len(health["restarts"]), RESTART_WINDOW_S // 60))
            notify("/talk needs you", "Mic still dead after %d restarts. Unplug and replug the microphone."
                   % RESTART_MAX)
            speak("Voice input needs you. Please replug the microphone.")
            return False
        health["restarts"].append(now)
        restarts = list(health["restarts"])
    write_health(extra={"restarts": restarts, "restarting": why})
    log("self-restarting (%s) — attempt %d in this window" % (why, len(restarts)))
    try:
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__),
                                  "--restarts", json.dumps(restarts)])
    except Exception as e:
        log("execv failed: %r" % e)
        return False
    return True


def healer():
    """While degraded, keep trying to bring the mic back; escalate if it won't."""
    while True:
        heal_now.wait(timeout=HEAL_INTERVAL_S)
        heal_now.clear()
        with health_lock:
            degraded = not health["audio_ok"]
        if not degraded:
            continue
        if state.get("ptt_down"):
            continue                      # don't fight a hold in progress
        with health_lock:
            health["heal_attempts"] += 1
            attempt = health["heal_attempts"]
        ok, detail = audio_probe()
        if ok:
            recover("probe after %d attempt(s): %s" % (attempt, detail))
            continue
        log("heal attempt %d failed: %s" % (attempt, detail))
        if attempt == 1 or attempt % 3 == 0:
            log("resetting portaudio")
            try:
                reset_portaudio()
            except Exception as e:
                log("portaudio reset failed: %r" % e)
            ok, detail = audio_probe()
            if ok:
                recover("portaudio reset: %s" % detail)
                continue
        if attempt >= HEAL_BEFORE_RESTART:
            self_restart("mic dead after %d heal attempts" % attempt)


def write_health(extra=None):
    try:
        with health_lock:
            d = dict(health)
        d["pid"] = os.getpid()
        d["ts"] = time.time()
        d["uptime_s"] = round(time.time() - d["started"], 1)
        if extra:
            d.update(extra)
        tmp = HEALTH_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, HEALTH_FILE)
    except Exception as e:
        log("health write failed: %r" % e)


# ---------------------------------------------------------------- TCC grants
_IOKIT = "/System/Library/Frameworks/IOKit.framework/IOKit"
_LISTEN = 1                       # kIOHIDRequestTypeListenEvent


def grants() -> dict:
    """What macOS has granted THIS process. Meaningful inside the app the stub spawned;
    a Terminal process asking gets Terminal's answer, which is why doctor reads the health file."""
    out = {"microphone": "unknown", "accessibility": None, "input_monitoring": "unknown"}
    try:
        from AVFoundation import AVCaptureDevice
        out["microphone"] = {0: "not determined", 1: "restricted", 2: "denied", 3: "authorized"}.get(
            AVCaptureDevice.authorizationStatusForMediaType_("soun"), "unknown")
    except Exception as e:
        log("microphone grant probe unavailable: %r" % e)
    try:
        from ApplicationServices import AXIsProcessTrusted
        out["accessibility"] = bool(AXIsProcessTrusted())
    except Exception as e:
        log("accessibility grant probe unavailable: %r" % e)
    try:
        import ctypes
        iokit = ctypes.cdll.LoadLibrary(_IOKIT)
        iokit.IOHIDCheckAccess.restype, iokit.IOHIDCheckAccess.argtypes = ctypes.c_uint32, [ctypes.c_uint32]
        out["input_monitoring"] = {0: "granted", 1: "denied", 2: "unknown"}.get(iokit.IOHIDCheckAccess(_LISTEN), "unknown")
    except Exception as e:
        log("input monitoring grant probe unavailable: %r" % e)
    return out


def request_grants():
    """First start: raise the three system prompts, each with an Open System Settings button."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception as e:
        log("accessibility prompt unavailable: %r" % e)
    try:
        import ctypes
        iokit = ctypes.cdll.LoadLibrary(_IOKIT)
        iokit.IOHIDRequestAccess.restype, iokit.IOHIDRequestAccess.argtypes = ctypes.c_bool, [ctypes.c_uint32]
        iokit.IOHIDRequestAccess(_LISTEN)
    except Exception as e:
        log("input monitoring prompt unavailable: %r" % e)
    try:
        from AVFoundation import AVCaptureDevice
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            "soun", lambda ok: log("microphone access %s" % ("granted" if ok else "denied")))
    except Exception as e:
        log("microphone prompt unavailable: %r" % e)


def grants_from_health(d: dict):
    """(ok, detail) for doctor, from the daemon's own report in talk.health.json."""
    g = (d or {}).get("grants")
    if not g:
        return False, "unknown until the daemon runs (talk-speak talk on)"
    mic, ax, im = g.get("microphone"), g.get("accessibility"), g.get("input_monitoring")
    detail = "microphone %s, accessibility %s, input monitoring %s" % (mic, "granted" if ax else "denied", im)
    return (mic == "authorized" and bool(ax) and im == "granted"), detail


def heartbeat():
    while True:
        g = grants()
        with health_lock:
            health["grants"] = g
        write_health()
        with health_lock:
            wedged = (not health["audio_ok"] and health["heal_attempts"] == 0
                      and health["degraded_since"] is not None
                      and time.time() - health["degraded_since"] > 60.0)
        if wedged:                    # healer never fired (ptt_down gate or lost wakeup)
            state["ptt_down"] = False
            heal_now.set()
            log("heartbeat: degraded >60s with 0 heal attempts — unsticking healer")
        time.sleep(HEARTBEAT_S)


def supervised(fn, name):
    """Run fn forever; a crash is logged and the thread is restarted, never fatal."""
    def wrapper():
        backoff = 1.0
        while True:
            try:
                fn()
                log("thread %s returned; restarting in %.0fs" % (name, backoff))
            except Exception as e:
                log("thread %s crashed: %r — restarting in %.0fs" % (name, e, backoff))
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
    t = threading.Thread(target=wrapper, name=name, daemon=True)
    t.start()
    return t



def log(msg):
    with open(LOG, "a") as f:
        f.write("%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


# ---------------------------------------------------------------- whisper
MLX_REPO = _p("models/whisper-large-v3-turbo")   # `talk-speak talk warm` fetches it
MLX_WEIGHTS_BYTES = 1613977612                      # a partial download must not be loaded
MLX_SHA256 = {   # mlx-community/whisper-large-v3-turbo at main, from the Hub API on 2026-09-09; {} skips the check
    "config.json": "b34fc29e4e11e0a25e812775dd67f4dd16fc2c8eb43d28ae25ff7d660ecb6379",
    "weights.safetensors": "951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6",
}
_backend = None                                     # "mlx" | "cpu"


def mlx_ready() -> bool:
    try:
        return os.path.getsize(os.path.join(MLX_REPO, "weights.safetensors")) >= MLX_WEIGHTS_BYTES \
            and os.path.exists(os.path.join(MLX_REPO, "config.json"))
    except OSError:
        return False


def get_backend() -> str:
    """Pick the transcription backend once: MLX on the GPU, CPU whisper as fallback."""
    global _model, _backend
    with _model_lock:
        if _backend is None:
            try:
                if not mlx_ready():
                    raise RuntimeError("local MLX weights missing or incomplete")
                import mlx_whisper                    # noqa: F401
                _backend = "mlx"
                log("backend: mlx (%s)" % MLX_REPO)
            except Exception as e:
                _backend = "cpu"
                log("mlx unavailable (%r) — using CPU whisper small" % e)
        if _backend == "cpu" and _model is None:
            import whisper
            log("loading whisper small model...")
            _model = whisper.load_model("small")
            log("model loaded")
    return _backend


def get_model():                                     # kept: older callers/selftest use it
    get_backend()
    return _model


def warm_up():
    """First real dictation shouldn't pay the model load."""
    try:
        if get_backend() == "mlx":
            import mlx_whisper
            mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32),
                                   path_or_hf_repo=MLX_REPO, language="en")
            log("mlx model warm")
        with health_lock:
            health["backend"] = get_backend()
    except Exception as e:
        log("warm-up failed: %r" % e)


def transcribe(samples: np.ndarray, app: str = "", prompt_extra: str = "") -> str:
    audio = samples.astype(np.float32)
    prompt = vocab_prompt(app)
    if prompt_extra:                                       # rolling context across stream segments
        prompt = (prompt + " " + prompt_extra)[-MAX_PROMPT_CHARS:]
    if get_backend() == "mlx":
        import mlx_whisper
        try:
            result = mlx_whisper.transcribe(audio, path_or_hf_repo=MLX_REPO, language="en",
                                            initial_prompt=prompt,
                                            condition_on_previous_text=False)
            return result["text"].strip()
        except Exception as e:                        # never lose a dictation to a backend fault
            log("mlx transcribe failed (%r) — using CPU whisper for this one" % e)
            global _backend
            with _model_lock:
                _backend = "cpu"
    result = get_model().transcribe(audio, language="en", fp16=False, initial_prompt=prompt,
                                    condition_on_previous_text=False)
    return result["text"].strip()


HALLUCINATION_RE = re.compile(r"(you|thank you|thanks|bye|\W*)")

# Vocabulary whisper should spell correctly; passed as the dictation prompt.
# Lives in $TALK_SPEAK_HOME/talk.vocab so it can be edited without touching this file.
VOCAB_FILE = _p("talk.vocab")
MAX_PROMPT_CHARS = 850                 # whisper truncates the prompt at ~224 tokens
CODE_APPS = {"Terminal", "iTerm2", "Visual Studio Code", "Code", "Cursor", "Xcode",
             "Warp", "Ghostty", "Alacritty", "kitty", "WezTerm"}
_vocab = {"mtime": None, "general": "", "code": "", "corrections": []}


def parse_vocab(text: str) -> dict:
    """[general] words always sent to whisper; [code] added in terminals and editors;
    [corrections] lines `regex => replacement`, case-insensitive, run after the built-ins."""
    section, buf, corrections = "general", {"general": [], "code": []}, []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            buf.setdefault(section, [])
            continue
        if section == "corrections":
            if " => " not in line:
                log("vocab: correction without ' => ' skipped: %r" % line)
                continue
            pat, repl = line.split(" => ", 1)
            try:
                corrections.append((re.compile(pat.strip(), re.I), repl.strip()))
            except re.error as e:
                log("vocab: bad correction regex %r skipped (%s)" % (pat.strip(), e))
            continue
        buf.setdefault(section, []).append(line)
    return {"general": ", ".join(buf["general"]), "code": ", ".join(buf["code"]),
            "corrections": corrections}


def load_vocab() -> dict:
    """Re-read talk.vocab when it changes; no restart needed."""
    try:
        mtime = os.path.getmtime(VOCAB_FILE)
    except OSError:
        return _vocab
    if mtime == _vocab["mtime"]:
        return _vocab
    try:
        with open(VOCAB_FILE) as f:
            parsed = parse_vocab(f.read())
        _vocab.update(mtime=mtime, **parsed)
        log("vocab reloaded (%d general / %d code chars, %d corrections)"
            % (len(_vocab["general"]), len(_vocab["code"]), len(_vocab["corrections"])))
    except Exception as e:
        log("vocab load failed (%r) — keeping previous" % e)
    return _vocab


def vocab_prompt(app: str = "") -> str:
    """General vocabulary, plus the code list when a terminal or editor has focus."""
    v = load_vocab()
    parts = [v["general"]]
    if app in CODE_APPS and v["code"]:
        parts.append(v["code"])
    prompt = "; ".join(p for p in parts if p)
    return prompt[-MAX_PROMPT_CHARS:]   # whisper keeps the tail, so trim from the front

# Built-in fix-ups: mechanics only. Name corrections belong in talk.vocab [corrections].
CORRECTIONS = [
    (r"[,.]?\s*(?:\bdot\b[,.]?\s*){3,}", "..."),               # spoken "dot dot dot"(+) → ...
    (r"\bscreen[\s-]*server\b", "screensaver"),                 # never a real phrase in dictation
    (r"\bhot[\s-]*key\b", "hotkey"),
    (r"\bslash[\s,.:;]+([A-Za-z][\w-]*)", r"/\1"),              # "slash talk" / "slash, mouse" -> /talk /mouse
]

# Applied only when a terminal or editor has focus, where these readings are near-certain.
CORRECTIONS_CODE = [
    (r"\bevent\s+tab\b", "event tap"),
    (r"\btalk[td]?\s+(file|daemon|log|process)\b", r"talkd \1"),
]


TRAILING_PUNCT = ".!?,;:"


# Spoken punctuation: "dot" / "comma" / "question mark" / "exclamation mark"
# become real characters. Runs AFTER the "dot dot dot" ellipsis rule so three
# or more spoken dots still collapse to " ...".
_SPOKEN_PUNCT_RE = re.compile(
    r"\s*\b(question\s+mark|exclamation\s+(?:mark|point)|period|dot|comma)\b\s*([.,!?]?)", re.I)
_SPOKEN_PUNCT_CHAR = {"question mark": "?", "period": ".", "dot": ".", "comma": ","}


def spoken_punct(text: str) -> str:
    def repl(m):
        word = m.group(1).lower()
        ch = _SPOKEN_PUNCT_CHAR.get(word, "!")
        pre = text[:m.start()].rstrip()
        post = text[m.end():].lstrip()
        prev_ch = pre[-1] if pre else ""
        next_ch = post[:1]
        tight = (ch == "." and prev_ch and next_ch                 # "gmail dot com" -> gmail.com
                 and (prev_ch.islower() or prev_ch.isdigit())
                 and (next_ch.islower() or next_ch.isdigit()))
        if tight:
            return ch
        return ch + " " if post else ch        # spoken mark absorbs whisper's trailing stop
    return _SPOKEN_PUNCT_RE.sub(repl, text)


def apply_corrections(text: str, user_rules=(), app: str = "") -> str:
    """Built-in mechanics, code-context rules, then the user's [corrections] from talk.vocab."""
    for pattern, replacement in CORRECTIONS + (CORRECTIONS_CODE if app in CODE_APPS else []):
        text = re.sub(pattern, replacement, text, flags=re.I)
    for pattern, replacement in user_rules:
        text = pattern.sub(replacement, text)
    return text


def clean_transcript(text: str, app: str = "") -> str:
    stripped = text.strip().lower().rstrip(".!?")
    if stripped in ("dot", "period"):                      # a whole utterance that IS punctuation
        return "."
    if HALLUCINATION_RE.fullmatch(stripped):
        return ""
    text = " ".join(text.split())
    text = apply_corrections(text, load_vocab()["corrections"], app)
    text = spoken_punct(text)
    # glued punctuation: "anywhere.I'm" -> "anywhere. I'm"; leaves 3.5 and google.com alone
    text = re.sub(r"([.!?])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([,;:])([A-Za-z])", r"\1 \2", text)
    text = text.strip()
    if text.startswith("/"):                               # a voice slash-command line: no trailing period
        return re.sub(r"[.!?,;:]+$", "", text)
    # no auto-added final stop: punctuation is additive — the user says "dot"/"period"
    # (or whisper writes one); the daemon never appends marks that were not spoken.
    return text                        # NO trailing space: see continuation_prefix()


# ---------------------------------------------------------------- macOS glue
def play(sound):
    subprocess.Popen(["afplay", "/System/Library/Sounds/%s.aiff" % sound],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def speak(text):
    rate = open(_p("speak.rate")).read().strip() if os.path.exists(_p("speak.rate")) else "195"
    voice_f = _p("speak.voice")
    cmd = ["say", "-r", rate]
    if os.path.exists(voice_f):
        v = open(voice_f).read().strip()
        if v:
            cmd += ["-v", v]
    subprocess.run(cmd + [text])


def frontmost():
    """Frontmost app name + focused window title, in-process.

    NSWorkspace + the AX API: no Automation consent (System Events), no
    subprocess, ~0 ms instead of the AppleScript probe's ~100 ms per press.
    Falls back to the AppleScript probe if the pyobjc frameworks are missing."""
    try:
        from AppKit import NSWorkspace
        from ApplicationServices import (AXUIElementCreateApplication,
                                         AXUIElementCopyAttributeValue,
                                         kAXFocusedWindowAttribute,
                                         kAXTitleAttribute)
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None, None
        name = app.localizedName() or ""
        win = ""
        try:
            axapp = AXUIElementCreateApplication(app.processIdentifier())
            w, err = AXUIElementCopyAttributeValue(axapp, kAXFocusedWindowAttribute, None)
            if w is not None:
                t, _ = AXUIElementCopyAttributeValue(w, kAXTitleAttribute, None)
                if t is not None:
                    win = str(t)
        except Exception:
            pass                                   # window title is optional metadata
        return name, win
    except Exception as e:
        log("frontmost fast path unavailable (%r) — using AppleScript" % e)
        return _frontmost_osascript()


def _frontmost_osascript():
    script = ('tell application "System Events"\n'
              'set p to first application process whose frontmost is true\n'
              'set appName to name of p\n'
              'set winName to ""\n'
              # keyboard-focused window first (z-order 'front window' can be a stale phantom on another Space)
              'try\nset winName to value of attribute "AXTitle" of (value of attribute "AXFocusedWindow" of p)\nend try\n'
              'if winName is "" then\ntry\nset winName to name of front window of p\nend try\nend if\n'
              'return appName & "\\n" & winName\nend tell')
    try:
        out = subprocess.run(["osascript", "-e", script], capture_output=True,
                             text=True, timeout=15)
        if out.returncode != 0:
            log("frontmost check failed: %s" % out.stderr.strip())
            return None, None
        parts = out.stdout.rstrip("\n").split("\n")
        return parts[0], parts[1] if len(parts) > 1 else ""
    except Exception as e:
        log("frontmost check error: %r" % e)
        return None, None


def type_text(text: str) -> bool:
    """Post the transcript as MAGIC-tagged Unicode key events.

    Not AppleScript `keystroke`: other filter taps ahead of ours (Siri and
    SiriNCService register two, with multi-second worst-case latency) delay
    events long enough that a `state["typing"]` time window can close before
    our own spaces reach the tap — they were then eaten as push-to-talk.
    MAGIC tags each event by identity, so the tap passes it whatever the delay.
    """
    if not text:
        return False
    import Quartz
    CHUNK = 16                        # CGEventKeyboardSetUnicodeString is capped in practice
    try:
        for i in range(0, len(text), CHUNK):
            part = text[i:i + CHUNK]
            for down in (True, False):
                ev = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
                if ev is None:
                    log("keystroke failed: could not create key event")
                    return False
                Quartz.CGEventKeyboardSetUnicodeString(ev, len(part), part)
                Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGEventSourceUserData, MAGIC)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.02)          # let the target app's run loop consume each chunk
    except Exception as e:
        log("keystroke failed (Accessibility permission?): %r" % e)
        return False
    return True


# ---------------------------------------------------------------- audio
def _callback(indata, frames, t, status):
    audio_q.put(indata[:, 0].copy())


def pick_input_device(wanted, devices):
    """Index of the first input device whose name contains `wanted` (case-insensitive).
    None = let PortAudio use the system default input."""
    if not wanted:
        return None
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0 and wanted.lower() in str(d.get("name", "")).lower():
            return i
    log("INPUT_DEVICE %r not found — using the system default input" % wanted)
    return None


def open_stream():
    kw = {}
    dev = pick_input_device(INPUT_DEVICE, sd.query_devices())
    if dev is not None:
        kw["device"] = dev
    s = sd.InputStream(samplerate=SR, blocksize=BLOCK, channels=1,
                       dtype="float32", callback=_callback, **kw)
    s.start()
    return s


def drain_queue(q):
    while not q.empty():
        try: q.get_nowait()
        except queue.Empty: break


# ---------------------------------------------------------------- key tap
def ptt_decision(is_down, keycode, flags, user_data, mod_mask, now):
    """The whole push-to-talk interception rule, in one testable place.

    Returns: "pass" (hand the key on untouched) | "down" (swallow, start PTT)
             | "up" (swallow, end PTT) | "eat" (swallow, autorepeat)
             | "tap" (swallow, hand the space back inline — quick tap).

    Three safety rules live here, in priority order. All of them err towards
    giving the user their spacebar back — /talk failing must cost nothing.
    """
    if keycode != PTT_KEYCODE:
        if is_down and user_data != MAGIC:
            state["last_key_ts"] = now          # remember YOU are typing (our own
        return "pass"                           # transcript must not arm the guard)
    # SAFETY 1 — a Space carrying cmd/opt/ctrl/fn is somebody's hotkey
    # (option-space = ChatGPT, cmd-space = Spotlight), never push-to-talk.
    if flags & mod_mask:
        if state["ptt_down"]:                   # modifier pressed mid-hold: close it out
            state["ptt_down"] = False
            ptt_q.put("up")
        return "pass"
    if user_data == MAGIC:
        return "pass"                           # a space we re-posted ourselves
    if state.get("typing"):
        return "pass"                           # spaces inside our own typed transcript
    # SAFETY 2 — the mic is not delivering audio. Never hold the spacebar hostage
    # for a daemon that cannot hear; typing must be completely unaffected.
    if not health["audio_ok"]:
        return "pass"
    if is_down:
        if state["ptt_down"]:
            return "eat"                        # autorepeat while held
        # SAFETY 3 — a space that lands amid active typing is just a space.
        if now - state["last_key_ts"] < TYPING_GUARD_S:
            return "pass"
        if state["armed"]:
            state["down_ts"] = now
            return "down"
        return "pass"
    if state["ptt_down"]:
        # A quick tap must get its space back INSTANTLY, inside this callback.
        # Round-tripping through the worker queue (pkill + frontmost() ≈ 150 ms)
        # re-posts the space AFTER the next letters you already typed — mid-word.
        # Measured 2026-09-04: that late-space insertion was the typing bug.
        state["ptt_down"] = False
        if now - state.get("down_ts", now) < PTT_MIN_HOLD:
            return "tap"
        return "up"
    return "pass"


def start_key_tap():
    """Global keyboard tap. Swallows SPACE while ARMED (push-to-talk), in every app."""
    import Quartz
    from Quartz import (CGEventTapCreate, kCGSessionEventTap, kCGHeadInsertEventTap,
                        kCGEventTapOptionDefault, CGEventGetIntegerValueField,
                        kCGKeyboardEventKeycode, kCGKeyboardEventAutorepeat,
                        kCGEventSourceUserData, CFMachPortCreateRunLoopSource,
                        CFRunLoopAddSource, CFRunLoopGetCurrent, kCFRunLoopCommonModes,
                        CFRunLoopRun, CGEventTapEnable)
    KEYDOWN, KEYUP = 10, 11
    # Space carrying one of these is somebody's hotkey, not push-to-talk:
    # ⌥Space = ChatGPT launcher, ⌘Space = Spotlight, ⌃/fn+Space = Siri / input source.
    MOD_MASK = (Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskAlternate
                | Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskSecondaryFn)

    def cb(proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            log("event tap disabled by system — re-enabling")
            CGEventTapEnable(tap, True)
            return event
        try:
            act = ptt_decision(etype == KEYDOWN,
                               CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode),
                               Quartz.CGEventGetFlags(event),
                               CGEventGetIntegerValueField(event, kCGEventSourceUserData),
                               MOD_MASK, time.time())
        except Exception as e:
            # a bug in the decision must never cost the user their keyboard
            log("tap decision error (passing key through): %r" % e)
            return event
        if act == "pass":
            return event
        if act == "down":
            state["ptt_down"] = True
            ptt_q.put("down")
        elif act == "tap":
            post_space()                        # back instantly, before the next keystroke
            ptt_q.put("tap")                    # worker: abort the pending hold, no transcript
        elif act == "up":
            state["ptt_down"] = False
            ptt_q.put("up")
        return None

    tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionDefault,
                           (1 << KEYDOWN) | (1 << KEYUP), cb, None)
    if tap is None:
        log("FATAL: could not create key tap (Input Monitoring / Accessibility)")
        return False
    src = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)
    log("key tap active (space = push-to-talk while armed)")
    CFRunLoopRun()
    return True


def post_space():
    """Re-post a real space for a quick tap that was swallowed."""
    import Quartz
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, PTT_KEYCODE, down)
        Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGEventSourceUserData, MAGIC)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


# ---------------------------------------------------------------- states
def record_hold():
    """Mic open only while space is held. Returns (samples, seconds_held)."""
    t0 = time.time()
    stream = open_stream()
    chunks = []
    try:
        while True:
            try:
                c = audio_q.get(timeout=0.2)
                chunks.append(c)
            except queue.Empty:
                pass
            try:
                if ptt_q.get_nowait() == "up":
                    break
            except queue.Empty:
                pass
            if time.time() - t0 > PTT_MAX_HOLD:
                log("push-to-talk hit max hold; stopping")
                break
    finally:
        stream.stop(); stream.close()
        drain_queue(audio_q)
    held = time.time() - t0
    return (np.concatenate(chunks) if chunks else np.zeros(0, np.float32)), held


def _rms(a: np.ndarray) -> float:
    return float(np.sqrt(np.mean(a * a))) if a.size else 0.0


def segment_stream(get_chunk, is_up, t0, app):
    """Consume audio chunks while the key is held, transcribing each phrase at a
    silence boundary in a background worker; return (joined_text, seconds_held).
    `get_chunk()` yields the next audio chunk or None; `is_up()` reports release.
    Segments cut at real pauses (clean word boundaries) so there is nothing to
    de-duplicate. A hold shorter than PTT_MIN_HOLD returns ('', held) untranscribed
    (a normal space tap). Falls back to one whole-buffer pass if streaming is empty."""
    seg_q: "queue.Queue" = queue.Queue()
    results, prev = {}, {"text": ""}

    def worker():
        while True:
            item = seg_q.get()
            if item is None:
                seg_q.task_done(); return
            idx, seg = item
            try:
                txt = transcribe(seg, app, prompt_extra=prev["text"])
            except Exception as e:
                log("stream seg %d failed: %r" % (idx, e)); txt = ""
            if txt and HALLUCINATION_RE.fullmatch(txt.strip().lower().rstrip(".!?")):
                txt = ""                                   # a fragment that whisper hallucinated
            if txt:
                results[idx] = txt; prev["text"] = txt
            seg_q.task_done()

    wt = threading.Thread(target=worker, daemon=True); wt.start()

    SIL = int(SEG_SILENCE_S * SR); MIN = int(SEG_MIN_SPEECH_S * SR); MAX = int(SEG_MAX_S * SR)
    all_chunks, seg_chunks = [], []
    seg_len = silence = idx = 0
    seg_voiced = False
    floor_win: "deque[float]" = deque(maxlen=SEG_NOISE_WIN)   # rolling RMS for the noise floor

    def emit():
        nonlocal seg_chunks, seg_len, silence, seg_voiced, idx
        if seg_voiced and seg_chunks:                      # skip all-silence segments
            seg_q.put((idx, np.concatenate(seg_chunks))); idx += 1
        seg_chunks, seg_len, silence, seg_voiced = [], 0, 0, False

    while True:
        c = get_chunk()
        if c is not None:
            all_chunks.append(c); seg_chunks.append(c); seg_len += len(c)
            r = _rms(c); floor_win.append(r)
            # silence threshold adapts to THIS mic's noise floor (a fixed cutoff fails
            # when the room hiss is louder than the constant — which it usually is).
            thresh = max(SEG_RMS, min(floor_win) * SEG_NOISE_MULT)
            if r < thresh:
                silence += len(c)
            else:
                silence = 0; seg_voiced = True
            if STREAMING and ((seg_len >= MIN and silence >= SIL) or seg_len >= MAX):
                emit()
        if is_up():
            break
        if time.time() - t0 > PTT_MAX_HOLD:
            log("push-to-talk hit max hold; stopping"); break

    t_up = time.time()                                     # key released here
    held = t_up - t0
    if held < PTT_MIN_HOLD:                                # a quick tap: it was just a space
        seg_q.put(None); seg_q.join()
        return "", held, t_up
    emit()                                                 # flush the final phrase
    seg_q.put(None); seg_q.join()                          # only the final phrase is still pending
    text = " ".join(results[i] for i in sorted(results)).strip()
    if not text and all_chunks:                            # fallback: one whole-buffer pass
        text = transcribe(np.concatenate(all_chunks), app)
    return text, held, t_up


def check_trigger(trigger_file):
    """`talk-speak talk typetest` drops a file; run the keystroke permission probe."""
    if not os.path.exists(trigger_file):
        return
    try: content = open(trigger_file).read().strip()
    except Exception: content = ""
    os.unlink(trigger_file)
    if content == "typetest":
        r = subprocess.run(["osascript",
                            "-e", 'tell application "System Events" to keystroke "x"',
                            "-e", 'tell application "System Events" to key code 51'],
                           capture_output=True, text=True, timeout=20)
        log("typetest result: %s%s" % ("OK" if r.returncode == 0 else "FAILED — ",
                                       r.stderr.strip()))
    elif content == "degrade":
        # fault injection: prove the safety property on the live daemon without
        # unplugging anything. The healer will probe and recover on its own.
        degrade("fault injected by `talk-speak talk simulate-failure`")
    elif content == "heal":
        heal_now.set()
        log("heal requested")
    else:
        log("trigger %r ignored (typetest|degrade|heal)" % content)


HISTORY_FILE = _p("talk.history.jsonl")


def record_history(text, app, win, held, elapsed):
    if not HISTORY:
        return
    try:
        with open(HISTORY_FILE, "a") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                                "app": app, "window": win, "held": round(held, 2),
                                "transcribe": round(elapsed, 2), "text": text}) + "\n")
    except Exception as e:
        log("history write failed: %r" % e)


CONTINUATION_S = 120.0   # two dictations further apart than this are not one thought


def continuation_prefix(app, win):
    """Return " " when this dictation continues the previous one.

    Consecutive dictations must not glue together, but the separator must not be
    a TRAILING space on the earlier one — that is visible in the prompt and
    doubles up against anything already there. So it goes on the FRONT of the
    continuation instead, and only when we are genuinely continuing: same field,
    recent, and nothing typed by the user in between (their own spacing wins).
    """
    last = state.get("last_typed_ts", 0.0)
    if not last:
        return ""
    if (app, win) != state.get("last_typed_where"):
        return ""
    if time.time() - last > CONTINUATION_S:
        return ""
    if state.get("last_key_ts", 0.0) > last:
        return ""
    return " "


def handle_ptt():
    ptt_flag_set()                # other mic apps mute until we clear this
    try:
        _handle_ptt()
    finally:
        ptt_flag_clear()


def _handle_ptt():
    subprocess.run(["pkill", "-x", "say"], stdout=subprocess.DEVNULL)   # space cuts my voice off
    app, win = frontmost()                     # ~100ms; known up front so segments use the right vocab
    app = app or ""
    t0 = time.time()
    stream = None
    last_err = None
    for _ in range(3):                        # transient PortAudio -9986 usually clears
        try:                                  # on a second open; don't degrade on one bad read
            stream = open_stream()
            break
        except Exception as e:
            last_err = e
            time.sleep(0.3)
    if stream is None:
        # opening the mic failed outright — definitive, degrade on the first strike
        degrade("mic would not open: %r" % last_err)
        state["ptt_down"] = False             # the keyup passes through now; a stuck flag
        post_space()                          # would wedge the healer (2026-09-03). Give the space back.
        return

    energy = {"peak": 0.0, "blocks": 0}

    def get_chunk():
        try:
            c = audio_q.get(timeout=0.2)
        except queue.Empty:
            return None
        energy["blocks"] += 1
        r = float(np.sqrt((c ** 2).mean()))
        if r > energy["peak"]:
            energy["peak"] = r
        return c

    up = {"v": False, "tap": False}
    def is_up():
        if up["v"]:
            return True
        try:
            ev = ptt_q.get_nowait()
            if ev in ("up", "tap"):
                up["v"] = True
                up["tap"] = (ev == "tap")     # callback already re-posted the space
        except queue.Empty:
            pass
        return up["v"]

    try:
        # phrases transcribe in the background AS you talk; on release only the
        # last phrase is left, so this returns almost immediately.
        text, held, t_up = segment_stream(get_chunk, is_up, t0, app)
    finally:
        try:
            stream.stop(); stream.close()
        except Exception as e:
            log("stream close: %r" % e)
        drain_queue(audio_q)

    audio_sample(energy["peak"], energy["blocks"], held)

    if held < PTT_MIN_HOLD or up["tap"]:
        if not up["tap"]:
            post_space()                      # it was just a space
        return                                # tap: space was re-posted in the callback
    log("push-to-talk released after %.1fs" % held)
    said = clean_transcript(text, app)
    elapsed = time.time() - t_up              # true release -> ready latency (the streaming win)
    log("dictation: %r -> %r (%.1fs after release)" % (said, (app, win), elapsed))
    if said:
        said = continuation_prefix(app, win) + said
    if said and type_text(said):
        state["last_typed_ts"] = time.time()
        state["last_typed_where"] = (app, win)
        play("Glass"); log("typed OK")
        record_history(said, app, win, held, elapsed)
    else:
        play("Basso")
        if not said:
            post_space()                      # silent hold: never hold the spacebar hostage
            log("silent hold — space re-posted")


def armed_session(trigger_file):
    """ARMED forever: mic closed; space-hold = talk; space-down cuts `say` off."""
    state["armed"] = True
    drain_queue(ptt_q)
    log("ARMED: hold space to talk (always on, no wake word)")
    try:
        while True:
            try:
                ev = ptt_q.get(timeout=1.0)
            except queue.Empty:
                check_trigger(trigger_file)
                continue
            if ev != "down":
                continue
            try:
                handle_ptt()
            except Exception as e:                    # never let one bad hold kill the daemon
                log("ptt error (recovered): %r" % e)
                state["ptt_down"] = False
                drain_queue(ptt_q); drain_queue(audio_q)
                if "PortAudio" in type(e).__name__ or "PortAudio" in repr(e):
                    degrade("PortAudio error: %r" % e)   # definitive: free the spacebar now
                else:
                    play("Basso")
    finally:
        state["armed"] = False
        state["ptt_down"] = False


def run():
    try:
        os.setsid()          # drop the controlling tty: Terminal windows close without "terminate?" prompts
    except OSError as e:
        log("setsid skipped: %r" % e)
    log("talkd v%s started (pid %d)" % (VERSION, os.getpid()))
    try:                            # the daemon owns its pidfile now (launchd is the supervisor)
        with open(_p("talk.pid"), "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log("pidfile write failed: %r" % e)
    request_grants()             # first start on a new Mac: the three permission prompts
    with health_lock:
        health["grants"] = grants()
    ptt_flag_clear()             # a daemon that died mid-hold must not mute other apps forever
    # carry the self-restart ledger across an exec so the rate limit survives a restart
    if "--restarts" in sys.argv:
        try:
            with health_lock:
                health["restarts"] = json.loads(sys.argv[sys.argv.index("--restarts") + 1])
        except Exception as e:
            log("restart ledger unreadable: %r" % e)

    # Preflight. If the mic is already dead we start DEGRADED, so a daemon that
    # cannot hear never takes the spacebar hostage.
    ok, detail = False, "not probed"
    for attempt in range(3):        # a device released by a previous daemon can
        try:                        # take a moment; don't degrade on one bad read
            ok, detail = audio_probe()
        except Exception as e:
            ok, detail = False, "probe raised %r" % e
        if ok:
            break
        if attempt < 2:
            log("preflight probe %d/3 failed (%s) — retrying" % (attempt + 1, detail))
            time.sleep(1.5)
    if ok:
        log("preflight audio OK (%s)" % detail)
        with health_lock:
            health["last_ok"] = time.time()
    else:
        degrade("preflight: %s" % detail)
    write_health()

    threading.Thread(target=warm_up, daemon=True).start()
    supervised(start_key_tap, "keytap")
    supervised(healer, "healer")
    supervised(heartbeat, "heartbeat")

    trigger = _p("talk.trigger")
    backoff = 1.0
    while True:                       # the main loop itself is not allowed to die
        try:
            armed_session(trigger)
            backoff = 1.0
        except Exception as e:
            log("armed_session crashed: %r — restarting in %.0fs" % (e, backoff))
            write_health(extra={"last_crash": repr(e)})
            state["ptt_down"] = False
            drain_queue(ptt_q); drain_queue(audio_q)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


# ---------------------------------------------------------------- tools
def selftest():
    ok = True
    get_model(); print("whisper small: loaded")
    import Quartz
    tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                  Quartz.kCGEventTapOptionDefault, 1 << 10,
                                  lambda p, t, e, r: e, None)
    print("key tap permission:", "OK" if tap else "DENIED"); ok &= tap is not None
    app, win = frontmost()
    print("frontmost now: app=%r window=%r (no gate: dictation types here)" % (app, win))
    sys.exit(0 if ok else 1)


def levels(seconds=10):
    print("talk while this runs... (%ds)" % seconds)
    stream = open_stream()
    try:
        for _ in range(seconds):
            peak = rms = 0.0
            for _ in range(int(SR / BLOCK)):
                c = audio_q.get()
                peak = max(peak, float(np.abs(c).max()))
                rms = max(rms, float(np.sqrt((c ** 2).mean())))
            print("peak=%.3f rms=%.3f %s" % (peak, rms, "#" * int(min(peak, 1.0) * 50)))
    finally:
        stream.stop(); stream.close()
    sys.exit(0)


def doctor():
    """Full preflight. Every dependency /talk needs, checked and named.
    Exit 0 = healthy. Anything that fails prints what to do about it."""
    checks, fails = [], 0

    def chk(name, fn, fix=""):
        nonlocal fails
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, "%s: %s" % (type(e).__name__, e)
        checks.append((ok, name, detail, fix if not ok else ""))
        if not ok:
            fails += 1
        return ok

    def _imports():
        missing = []
        for m in ("numpy", "sounddevice", "Quartz", "mlx_whisper"):
            try:
                __import__(m)
            except Exception as e:
                missing.append("%s (%s)" % (m, type(e).__name__))
        return (not missing), ("all present" if not missing else "MISSING: " + ", ".join(missing))

    def _weights():
        try:
            return (mlx_ready(), MLX_REPO)
        except Exception as e:
            return False, repr(e)

    def _device():
        ins = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
        if not ins:
            return False, "no input devices at all"
        return True, ", ".join(repr(d["name"]) for d in ins)

    def _health():
        try:
            return json.load(open(HEALTH_FILE))
        except Exception:
            return {}

    def _capture():                # the daemon's own verdict: doctor never opens the mic itself
        d = _health()
        if not d:
            return False, "unknown until the daemon runs"
        return bool(d.get("audio_ok")), ("healthy" if d.get("audio_ok") else "DEAD: %s" % d.get("last_error"))

    def _grants():
        return grants_from_health(_health())

    def _paths():
        bad = []
        for f in (LOG, HEALTH_FILE, HISTORY_FILE):
            d = os.path.dirname(f)
            if not os.path.isdir(d) or not os.access(d, os.W_OK):
                bad.append(d)
        return (not bad), ("writable" if not bad else "NOT writable: " + ", ".join(bad))

    def _cfg():
        f = _p("talk.cfg")
        if not os.path.exists(f):
            return True, "none (defaults)"
        try:
            return True, "parsed: %s" % json.load(open(f))
        except Exception as e:
            return False, "INVALID JSON: %s" % e

    def _agent():
        r = subprocess.run(["launchctl", "print", "gui/%d/%s" % (os.getuid(), LAUNCHD_LABEL)],
                           capture_output=True, text=True, timeout=15)
        ok = r.returncode == 0 and "state = running" in r.stdout
        return ok, ("launchd agent running" if ok else "not running (talk-speak talk on)")

    def _daemon():
        if not os.path.exists(HEALTH_FILE):
            return False, "no heartbeat file (daemon never ran this version)"
        d = json.load(open(HEALTH_FILE))
        age = time.time() - d.get("ts", 0)
        alive = False
        try:
            os.kill(int(d["pid"]), 0)
            alive = True
        except Exception:
            pass
        detail = "pid %s %s, state=%s, heartbeat %.0fs old, healed %sx" % (
            d.get("pid"), "alive" if alive else "DEAD", d.get("state"), age, d.get("healed"))
        return (alive and age < 90), detail

    chk("python deps", _imports, "%s/venv/bin/pip install -r requirements.txt (from the talk-speak clone)" % STATE)
    chk("mlx weights", _weights, "talk-speak talk warm (CPU 'small' fallback still works without it)")
    chk("input device", _device, "plug a microphone in, or set INPUT_DEVICE in talk.cfg")
    chk("mic capture", _capture, "talk-speak talk on; if it stays DEAD: replug the microphone, or: sudo killall coreaudiod")
    chk("permissions", _grants, "System Settings > Privacy & Security: grant talk-speak Microphone, Accessibility, Input Monitoring "
        "(open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone', ...?Privacy_Accessibility, ...?Privacy_ListenEvent)")
    chk("paths writable", _paths, "check %s permissions" % STATE)
    chk("talk.cfg", _cfg, "fix or delete %s" % _p("talk.cfg"))
    chk("launchd agent", _agent, "talk-speak talk on (bootstraps %s)" % LAUNCHD_LABEL)
    chk("daemon heartbeat", _daemon, "talk-speak talk on")

    w = max(len(n) for _, n, _, _ in checks)
    print("talk-speak doctor  v%s" % VERSION)
    print("-" * (w + 40))
    for ok, name, detail, fix in checks:
        print("%s  %-*s  %s" % ("PASS" if ok else "FAIL", w, name, detail))
        if fix:
            print("      %s-> %s" % (" " * w, fix))
    print("-" * (w + 40))
    print("%d/%d passed" % (len(checks) - fails, len(checks)))
    sys.exit(0 if fails == 0 else 1)


def sha256_of(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_weights() -> bool:
    """Every file in MLX_SHA256 must hash right; a mismatch is moved aside as *.bad so
    mlx_ready() stops seeing it and the CPU fallback takes over. Fails closed."""
    bad = []
    for name, want in MLX_SHA256.items():
        dest = os.path.join(MLX_REPO, name)
        if not os.path.exists(dest) or sha256_of(dest) != want:
            bad.append(name)
    for name in bad:
        dest = os.path.join(MLX_REPO, name)
        if os.path.exists(dest):
            os.replace(dest, dest + ".bad")
    if bad:
        print("CHECKSUM MISMATCH: %s moved aside as *.bad; run warm again" % ", ".join(bad))
    return not bad


def warm_weights() -> bool:
    """Fetch the MLX weights with resumable curl, then verify them against pinned hashes."""
    base = "https://huggingface.co/mlx-community/whisper-large-v3-turbo/resolve/main/"
    os.makedirs(MLX_REPO, exist_ok=True)
    if mlx_ready():
        print("mlx weights already present in %s; verifying checksums" % MLX_REPO)
        return verify_weights() if MLX_SHA256 else True
    print("fetching whisper-large-v3-turbo (%.2f GB) into %s" % (MLX_WEIGHTS_BYTES / 1e9, MLX_REPO))
    for name, want in (("config.json", 1), ("weights.safetensors", MLX_WEIGHTS_BYTES)):
        dest = os.path.join(MLX_REPO, name)
        if os.path.exists(dest) and os.path.getsize(dest) >= want:
            continue
        for attempt in range(1, 6):
            r = subprocess.run(["curl", "-L", "-C", "-", "--speed-limit", "40000", "--speed-time", "25",
                                "--progress-bar", "-o", dest, base + name])
            if r.returncode == 0:
                break
            print("retry %d/5 for %s" % (attempt, name))
        else:
            print("FAILED to fetch %s" % name)
            return False
    if MLX_SHA256 and not verify_weights():
        return False
    ok = mlx_ready()
    print("mlx weights %s" % ("ready" if ok else "INCOMPLETE — run warm again"))
    return ok


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(VERSION); sys.exit(0)
    if "--warm" in sys.argv:
        sys.exit(0 if warm_weights() else 1)
    if "--doctor" in sys.argv:
        doctor()
    if "--selftest" in sys.argv:
        selftest()
    if "--levels" in sys.argv:
        levels()
    try:
        run()
    except Exception as e:
        log("fatal: %r" % e)
        write_health(extra={"fatal": repr(e)})
        raise

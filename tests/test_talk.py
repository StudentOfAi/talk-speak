#!/usr/bin/env python
"""talk-speak daemon test suite. Run: talk-speak talk selfcheck (or <venv>/bin/python tests/test_talk.py)

Covers the three safety rules and the self-healing state machine. The rule that
matters most: /talk failing must never cost the user their spacebar.
"""
import importlib.util, os, sys, time, types, tempfile

os.environ["TALK_SPEAK_HOME"] = tempfile.mkdtemp()   # never touch the real state dir

DAEMON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "talk", "talkd.py")

def load():
    spec = importlib.util.spec_from_loader("talkd", loader=None)
    m = types.ModuleType("talkd")
    m.__file__ = DAEMON
    src = open(DAEMON).read()
    # strip the __main__ block so importing never starts a daemon
    src = src.split('if __name__ == "__main__":')[0]
    exec(compile(src, DAEMON, "exec"), m.__dict__)
    return m

t = load()
MODS = t.__dict__.get("_MOD_MASK_TEST")
import Quartz
MOD = (Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskAlternate
       | Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskSecondaryFn)
SPACE, LETTER = t.PTT_KEYCODE, 4

results = []
def check(name, got, want):
    ok = got == want
    results.append((ok, name, "got %r want %r" % (got, want)))
    return ok

def reset(audio_ok=True, armed=True, ptt_down=False, typing=False, last_key=0.0,
          down_ts=0.0):
    t.state.update({"armed": armed, "ptt_down": ptt_down, "last_key_ts": last_key,
                    "typing": typing, "down_ts": down_ts})
    t.health["audio_ok"] = audio_ok
    t.drain_queue(t.ptt_q)

NOW = 10_000.0

# ---- SAFETY 1: modifier chords are never swallowed
for name, fl in [("option+space (ChatGPT)", Quartz.kCGEventFlagMaskAlternate),
                 ("command+space (Spotlight)", Quartz.kCGEventFlagMaskCommand),
                 ("control+space", Quartz.kCGEventFlagMaskControl),
                 ("fn+space", Quartz.kCGEventFlagMaskSecondaryFn)]:
    reset()
    check("SAFETY1 %s passes through" % name,
          t.ptt_decision(True, SPACE, fl, 0, MOD, NOW), "pass")

reset()
check("SAFETY1 plain space still arms PTT",
      t.ptt_decision(True, SPACE, 0, 0, MOD, NOW), "down")
reset()
check("SAFETY1 shift+space still arms PTT (shift is not a hotkey modifier)",
      t.ptt_decision(True, SPACE, Quartz.kCGEventFlagMaskShift, 0, MOD, NOW), "down")
# modifier arriving mid-hold must close the hold, not wedge it
reset(ptt_down=True)
t.ptt_decision(True, SPACE, Quartz.kCGEventFlagMaskCommand, 0, MOD, NOW)
check("SAFETY1 modifier mid-hold clears ptt_down", t.state["ptt_down"], False)

# ---- SAFETY 2: dead mic => spacebar is never held hostage
reset(audio_ok=False)
check("SAFETY2 space passes through while audio is dead",
      t.ptt_decision(True, SPACE, 0, 0, MOD, NOW), "pass")
reset(audio_ok=False)
check("SAFETY2 keyup passes through while audio is dead",
      t.ptt_decision(False, SPACE, 0, 0, MOD, NOW), "pass")

# ---- SAFETY 3: typing guard
reset(last_key=NOW - 0.1)
check("SAFETY3 space 0.1s after a letter is a space",
      t.ptt_decision(True, SPACE, 0, 0, MOD, NOW), "pass")
reset(last_key=NOW - 5.0)
check("SAFETY3 space after a pause arms PTT",
      t.ptt_decision(True, SPACE, 0, 0, MOD, NOW), "down")

# ---- our own re-posted space is not re-intercepted
reset()
check("re-posted space passes through",
      t.ptt_decision(True, SPACE, 0, t.MAGIC, MOD, NOW), "pass")
reset(typing=True)
check("spaces inside our typed transcript pass through",
      t.ptt_decision(True, SPACE, 0, 0, MOD, NOW), "pass")

# ---- normal keys always pass and update the typing clock
reset()
check("letter passes through", t.ptt_decision(True, LETTER, 0, 0, MOD, NOW), "pass")
check("letter updates typing clock", t.state["last_key_ts"], NOW)

# ---- autorepeat while held is eaten, release ends the hold
reset(ptt_down=True)
check("autorepeat eaten", t.ptt_decision(True, SPACE, 0, 0, MOD, NOW), "eat")
reset(ptt_down=True)
check("release ends hold", t.ptt_decision(False, SPACE, 0, 0, MOD, NOW), "up")

# ---- quick taps return the space INSTANTLY in the callback (the late-space fix:
# a worker round-trip re-posted the space after the next letters, mid-word)
reset(ptt_down=True, down_ts=NOW - 0.1)
check("quick tap returns 'tap'", t.ptt_decision(False, SPACE, 0, 0, MOD, NOW), "tap")
check("quick tap clears ptt_down", t.state["ptt_down"], False)
reset(ptt_down=True, down_ts=NOW - 0.4)
check("hold past threshold returns 'up'", t.ptt_decision(False, SPACE, 0, 0, MOD, NOW), "up")
reset(ptt_down=False, down_ts=NOW)
check("keyup with no hold passes through",
      t.ptt_decision(False, SPACE, 0, 0, MOD, NOW), "pass")

# ---- health model: dead captures degrade, live captures clear the strikes
t.play = lambda *a: None
t.notify = lambda *a: None
t.speak = lambda *a: None
t.log = lambda *a: None
t.health.update({"audio_ok": True, "consec_dead": 0})
t.audio_sample(0.0, 0, 2.0)
check("1 dead capture does not degrade yet", t.health["audio_ok"], True)
t.audio_sample(0.0, 0, 2.0)
check("2 dead captures degrade", t.health["audio_ok"], False)

t.health.update({"audio_ok": True, "consec_dead": 1})
t.audio_sample(0.02, 50, 2.0)
check("a live capture clears the strike count", t.health["consec_dead"], 0)

t.health.update({"audio_ok": True, "consec_dead": 0})
t.audio_sample(0.0, 0, 0.1)          # a quick tap is a space, not evidence
check("a sub-threshold tap is not counted as evidence", t.health["consec_dead"], 0)

# ---- degrade/recover transitions
t.health.update({"audio_ok": True, "healed": 0})
t.degrade("test")
check("degrade sets DEGRADED", t.health["state"], "DEGRADED")
check("degrade frees the spacebar", t.health["audio_ok"], False)
t.recover("test")
check("recover sets OK", t.health["state"], "OK")
check("recover counts the heal", t.health["healed"], 1)

# ---- audio_probe reports failure instead of raising, when the mic will not open
orig = t.open_stream
t.open_stream = lambda: (_ for _ in ()).throw(RuntimeError("device gone"))
ok, detail = t.audio_probe(0.1)
check("probe reports a dead device without raising", (ok, "device gone" in detail), (False, True))
t.open_stream = orig

# ---- self-restart is rate limited so a dead dongle cannot cause a reboot loop
t.health["restarts"] = [time.time()] * t.RESTART_MAX
t.os = os
check("self_restart refuses past the rate limit", t.self_restart("test"), False)

# ---- transcripts carry NO trailing space
for name, raw, want in [
    ("plain sentence", "That was fantastic work", "That was fantastic work"),
    ("already punctuated", "Can you hear me?", "Can you hear me?"),
    ("slash command", "/mouse on.", "/mouse on"),
    ("slash command bare", "/talk", "/talk"),
]:
    got = t.clean_transcript(raw, "Terminal")
    check("no trailing space: %s" % name, got, want)
    check("no trailing space: %s (endswith)" % name, got.endswith(" "), False)

# ---- spoken punctuation: additive — a mark lands only when he says it
for name, raw, want in [
    ("domain joins tight, no stray stop", "attach it to gmail dot com", "attach it to gmail.com"),
    ("digits join tight", "chrome 2 dot 0", "chrome 2.0"),
    ("sentence dot", "I want to add a dot", "I want to add a."),
    ("whisper trailing stop absorbed", "I want to add a dot.", "I want to add a."),
    ("comma spaced", "downloads comma control button", "downloads, control button"),
    ("comma not doubled", "pause comma", "pause,"),
    ("question mark", "did it work question mark", "did it work?"),
    ("spoken mark wins over whisper mark", "did it work question mark.", "did it work?"),
    ("exclamation point", "nice exclamation point", "nice!"),
    ("dotfiles untouched", "check the dotfiles", "check the dotfiles"),
    ("bare dot is a dot", "Dot", "."),
    ("whisper punctuation untouched", "ok. then we go", "ok. then we go"),
    ("ellipsis rule survives", "wait dot dot dot", "wait..."),
]:
    check("spoken punct: %s" % name, t.clean_transcript(raw, "Terminal"), want)
check("screensaver mishear corrected",
      t.clean_transcript("screen server hotkey", "Terminal"), "screensaver hotkey")

# ---- the separator moves to the FRONT of a genuine continuation
def set_typed(app, win, ago, keyed_ago=None):
    now = time.time()
    state = t.state
    state["last_typed_ts"] = now - ago
    state["last_typed_where"] = (app, win)
    state["last_key_ts"] = 0.0 if keyed_ago is None else now - keyed_ago

set_typed("Terminal", "w1", 2.0)
check("continuation in the same field gets a leading space",
      t.continuation_prefix("Terminal", "w1"), " ")
set_typed("Terminal", "w1", 2.0)
check("a different window starts clean",
      t.continuation_prefix("Terminal", "w2"), "")
set_typed("Terminal", "w1", t.CONTINUATION_S + 10)
check("an old dictation is not a continuation",
      t.continuation_prefix("Terminal", "w1"), "")
set_typed("Terminal", "w1", 5.0, keyed_ago=1.0)   # user typed after our transcript
check("if the user typed since, their spacing wins",
      t.continuation_prefix("Terminal", "w1"), "")
t.state["last_typed_ts"] = 0.0
check("the very first dictation gets no leading space",
      t.continuation_prefix("Terminal", "w1"), "")

# ---- our own typed characters must not arm the typing guard
reset(last_key=0.0)
t.ptt_decision(True, LETTER, 0, t.MAGIC, MOD, NOW)      # a char WE typed
check("our own transcript does not arm the typing guard", t.state["last_key_ts"], 0.0)
reset(last_key=0.0)
t.ptt_decision(True, LETTER, 0, 0, MOD, NOW)           # a char HE typed
check("his typing does arm the typing guard", t.state["last_key_ts"], NOW)
# ...so a hold right after a transcript lands still dictates
reset(last_key=0.0)
t.ptt_decision(True, LETTER, 0, t.MAGIC, MOD, NOW)
check("space right after our transcript still arms PTT",
      t.ptt_decision(True, SPACE, 0, 0, MOD, NOW + 0.05), "down")

# ---- push-to-talk flag: other mic apps mute on it while space is held
import tempfile
t.PTT_FLAG = os.path.join(tempfile.mkdtemp(), "talk.ptt")
t.ptt_flag_clear()
check("clearing an absent PTT flag is harmless", os.path.exists(t.PTT_FLAG), False)
t.ptt_flag_set()
check("PTT flag exists while space is held", os.path.exists(t.PTT_FLAG), True)
t.ptt_flag_clear()
check("PTT flag is gone after release", os.path.exists(t.PTT_FLAG), False)

# ---- v3 public release: state dir, vocab corrections, device knob, history gate, grants
check("STATE honours TALK_SPEAK_HOME", t.STATE, os.environ["TALK_SPEAK_HOME"])
check("LOG lives under STATE", t.LOG, os.path.join(t.STATE, "talk.log"))
check("VOCAB_FILE lives under STATE", t.VOCAB_FILE, os.path.join(t.STATE, "talk.vocab"))
v = t.parse_vocab("[general]\nfoo\n[corrections]\nkim+i => Kimi\nopen\\s+claw => OpenClaw\n")
check("vocab [general] parsed", v["general"], "foo")
check("vocab [corrections] parsed", [r.pattern for r, _ in v["corrections"]], ["kim+i", "open\\s+claw"])
check("user corrections run after built-ins", t.apply_corrections("slash talk to kimmi", v["corrections"]), "/talk to Kimi")
check("no user corrections = built-ins only", t.apply_corrections("dot dot dot", []), "...")
bad = t.parse_vocab("[corrections]\nno arrow here\n( => broken\n")
check("bad correction lines are skipped, not fatal", bad["corrections"], [])
devs = [{"name": "MacBook Pro Microphone", "max_input_channels": 1},
        {"name": "USB Audio", "max_input_channels": 1},
        {"name": "Speakers", "max_input_channels": 0}]
check("INPUT_DEVICE substring picks the index", t.pick_input_device("usb", devs), 1)
check("INPUT_DEVICE None = system default", t.pick_input_device(None, devs), None)
check("INPUT_DEVICE with no match = system default", t.pick_input_device("nope", devs), None)
check("INPUT_DEVICE never picks an output-only device", t.pick_input_device("speakers", devs), None)
t.HISTORY, t.HISTORY_FILE = False, os.path.join(tempfile.mkdtemp(), "talk.history.jsonl")
t.record_history("hi", "Notes", "", 1.0, 0.5)
check("HISTORY false writes nothing", os.path.exists(t.HISTORY_FILE), False)
t.HISTORY = True
t.record_history("hi", "Notes", "", 1.0, 0.5)
check("HISTORY true appends one line", open(t.HISTORY_FILE).read().count("\n"), 1)
ok_all = {"grants": {"microphone": "authorized", "accessibility": True, "input_monitoring": "granted"}}
check("grants: all granted", t.grants_from_health(ok_all),
      (True, "microphone authorized, accessibility granted, input monitoring granted"))
check("grants: unknown until the daemon runs", t.grants_from_health({})[0], False)
check("grants: one denied fails", t.grants_from_health({"grants": {"microphone": "denied", "accessibility": True, "input_monitoring": "granted"}})[0], False)

# ---- model download integrity
_hf = os.path.join(tempfile.mkdtemp(), "abc"); open(_hf, "wb").write(b"abc")
check("sha256_of hashes file content", t.sha256_of(_hf),
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
check("pinned weight hashes are 64-hex", all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in t.MLX_SHA256.values()), True)

# ---- report
fails = [r for r in results if not r[0]]
w = max(len(n) for _, n, _ in results)
for ok, name, detail in results:
    print("%s  %-*s  %s" % ("PASS" if ok else "FAIL", w, name, "" if ok else detail))
print("-" * (w + 12))
print("%d/%d passed" % (len(results) - len(fails), len(results)))
sys.exit(1 if fails else 0)

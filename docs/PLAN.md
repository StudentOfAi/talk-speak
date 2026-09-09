# talk-speak v3.0.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the private hold-space dictation daemon and the spoken-replies engine into one public repo, `StudentOfAi/talk-speak`, that reproduces this Mac's setup on any Apple Silicon Mac with `git clone`, `./install.sh` and the one-time permission clicks. **This Mac's live install is not modified by any task** (the author, 2026-09-09: "don't mess with mine, I like it, simply push the experience I have").

**Architecture:** One state directory `~/.talk-speak/` holds the venv, the daemon, the speak engine, hooks and all flags. A tiny signed Swift stub `talk-speak.app` is what launchd runs; it spawns the Python daemon as a child so the app's TCC grants cover it. One CLI `talk-speak` with `talk` and `speak` subcommands; the Claude Code skills `/talk` and `/speak` call it. Harness adapters are 20-line hooks that pipe the finished reply into `speak-text.sh`.

**Tech Stack:** Python 3.14 (venv), mlx-whisper 0.4.3 + openai-whisper 20250625 fallback, sounddevice 0.5.6, pyobjc 12.2.2 (Quartz, Cocoa, ApplicationServices, AVFoundation), Swift 6.2 (`swiftc`, no Xcode), Bash, launchd, `security`/`codesign`, GitHub Actions `macos-latest`.

**Spec:** `docs/PRD.md` (same repo). Read it first; every requirement id below (T8, S5, ...) points there.

## Global Constraints

- Name is `talk-speak` everywhere: repo, CLI, app, `com.studentofai.talk-speak` (bundle id and launchd label), `~/.talk-speak/`. The word "claude" may appear only in `skills/`, in `speak/claude-code/` (the harness is called Claude Code), and in the `CLAUDE_SPEAK=off` compatibility env.
- macOS 14 or newer on Apple Silicon; tested on 26.1. No `sudo` anywhere.
- Every path derives from `STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"` (Bash) or `STATE = os.environ.get("TALK_SPEAK_HOME", os.path.expanduser("~/.talk-speak"))` (Python). No literal `~/.claude/`, absolute home paths, usernames or personal names in shipped files.
- Tests run with `$STATE/venv/bin/python -m unittest discover -s tests -v`; the suite must stay green after every task (64 today).
- Scripts pass `shellcheck` with no warnings. Commits are conventional (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `ci:`).
- Never delete a user file: installs back up before replacing (`<file>.replaced-<timestamp>`), uninstall moves state aside only with `--purge`.
- The installer never edits shell rc files and never runs `tccutil`.

---

## File map

| Path | Responsibility |
|---|---|
| `bin/talk-speak` | the CLI: `talk` and `speak` subcommand dispatch, state paths, launchd control |
| `talk/talkd.py` | the daemon (moved from `bin/claude-talkd.py`) |
| `talk/app/Stub.swift`, `talk/app/Info.plist.tmpl`, `talk/app/build.sh` | the signed stub |
| `talk/launchagent.plist.tmpl` | KeepAlive agent for the stub |
| `talk/talk.cfg.example`, `talk/talk.vocab.example` | generic seeds |
| `speak/speak-text.sh`, `speak/speak-prune.sh` | the engine |
| `speak/claude-code/{speak-last.sh,speak-session-end.sh,last-reply.py}` | Claude Code hooks |
| `speak/adapters/{hermes,kimi,claw,dst}/` | reference adapters, each with `README.md` and the config snippet |
| `lib/identity.sh` | create/find the local signing identity |
| `lib/hooks.py` | idempotent `settings.json` merger |
| `install.sh` | install, `--dry-run`, `--uninstall [--purge]` |
| `skills/talk/SKILL.md`, `skills/speak/SKILL.md` | Claude Code skills |
| `tests/test_talk.py` (exists), `tests/test_speak.py`, `tests/test_hooks.py`, `tests/test_cli.py` | unit tests |
| `docs/` | PRD, this plan, PERMISSIONS, SETUP, TROUBLESHOOTING, ACCEPTANCE |
| `.github/workflows/ci.yml` | tests, shellcheck, stub compile, dry-run |

Runtime layout `~/.talk-speak/`: `venv/`, `talkd.py`, `models/whisper-large-v3-turbo/`, `bin/` (engine + hooks copies), `talk.{cfg,vocab,log,err,out,pid,health.json,history.jsonl,disabled,ptt,trigger}`, `speak.{on,rate,voice,session,replay,env}`, `speaking`, `last-reply.txt`, `last-reply.replay.txt`, `speak.muted/`, `speak.alive/`, `repo` (text file holding the clone path).

---

### Task 1: Rename the repo and lay out the tree

**Files:** `git clone ~/Projects/claude-talk ~/Projects/talk-speak` (history kept, the original and its `selfcheck` path untouched), branch `v3-talk-speak`; `git mv` files into the map above; `git rm` the dead watchdog model (`bin/claude-talk-watchdog.sh`, `bin/claude-talk-relaunch.command`, `launchagents/`); add `LICENSE` (MIT, (c) 2026 StudentOfAi), `requirements.txt`, `.gitignore` additions (`build/`, `*.replaced-*`, `.venv/`).

**Interfaces:** Produces the paths every later task uses.

- [x] Step 1: `git clone ~/Projects/claude-talk ~/Projects/talk-speak && cd ~/Projects/talk-speak && git checkout -b v3-talk-speak && git remote remove origin`
- [x] Step 2: `git mv bin/claude-talkd.py talk/talkd.py`, `git mv config/talk.cfg.example talk/`, `git mv config/talk.vocab.example talk/`, `git mv docs/SKILL.md skills/talk/SKILL.md`, `git rm bin/claude-talk-watchdog.sh bin/claude-talk-relaunch.command launchagents/com.clawd.claude-talk-watchdog.plist.tmpl`. Keep `bin/claude-talk` until Task 5 replaces it.
- [x] Step 3: write `requirements.txt`:

```
mlx==0.32.2
mlx-whisper==0.4.3
openai-whisper==20250625
numpy==2.4.6
sounddevice==0.5.6
pyobjc-core==12.2.2
pyobjc-framework-Cocoa==12.2.2
pyobjc-framework-Quartz==12.2.2
pyobjc-framework-ApplicationServices==12.2.2
pyobjc-framework-AVFoundation==12.2.2
```

- [x] Step 4: `tests/test_talk.py` loads the daemon by path; point it at `talk/talkd.py`. Run: `/opt/homebrew/Cellar/openai-whisper/20250625_6/libexec/bin/python -m unittest discover -s tests` → 64 pass.
- [x] Step 5: commit `refactor: lay out talk-speak tree, drop the watchdog model`.

---

### Task 2: The signed stub, proven against the live install

**Files:** create `talk/app/Stub.swift`, `talk/app/Info.plist.tmpl`, `talk/app/build.sh`, `talk/launchagent.plist.tmpl`, `lib/identity.sh`.

**Interfaces:**
- `lib/identity.sh` exports `IDENTITY="talk-speak Local Dev"`, `identity_exists`, `identity_create` (uses `/usr/bin/openssl`, imports with `-T /usr/bin/codesign`, trusts with `add-trusted-cert -p codeSign`).
- `talk/app/build.sh [--identity NAME] [--bundle-id ID] [--out DIR]` produces `DIR/<name>.app`, signed, version from `VERSION`. Defaults: identity from `lib/identity.sh`, bundle id `com.studentofai.talk-speak`, out `build/`.
- The stub spawns `$STATE/venv/bin/python $STATE/talkd.py` with `TALK_SPEAK_HOME` set, exits 0 silently if `$STATE/talk.disabled` exists, forwards SIGTERM/SIGINT/SIGHUP to the child, exits with the child's status.

- [x] Step 1: `talk/app/Stub.swift`

```swift
// talk-speak stub: the process launchd runs. It owns the Microphone,
// Accessibility and Input Monitoring grants (TCC keys them to this bundle's
// signature) and spawns the Python daemon as a child so the grants cover it.
import Foundation

let env = ProcessInfo.processInfo.environment
let home = env["HOME"] ?? FileManager.default.homeDirectoryForCurrentUser.path
let state = env["TALK_SPEAK_HOME"] ?? "\(home)/.talk-speak"
let fm = FileManager.default

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write("talk-speak: \(msg)\n".data(using: .utf8)!)
    exit(0)   // exit 0 on purpose: KeepAlive(SuccessfulExit=false) must not spin on a config error
}

if fm.fileExists(atPath: "\(state)/talk.disabled") { exit(0) }   // `talk off` wins over KeepAlive

let python = "\(state)/venv/bin/python"
let daemon = "\(state)/talkd.py"
for p in [python, daemon] where !fm.fileExists(atPath: p) { fail("missing \(p) (run install.sh)") }

let child = Process()
child.executableURL = URL(fileURLWithPath: python)
child.arguments = [daemon]
var childEnv = env
childEnv["TALK_SPEAK_HOME"] = state
child.environment = childEnv
child.standardOutput = FileHandle.standardOutput   // launchd routes these to talk.out / talk.err
child.standardError = FileHandle.standardError

let signals = DispatchQueue(label: "talk-speak.signals")
var sources: [DispatchSourceSignal] = []
for sig in [SIGTERM, SIGINT, SIGHUP] {
    signal(sig, SIG_IGN)
    let s = DispatchSource.makeSignalSource(signal: sig, queue: signals)
    s.setEventHandler { if child.isRunning { child.terminate() } }
    s.resume()
    sources.append(s)
}
child.terminationHandler = { p in exit(p.terminationStatus) }
do { try child.run() } catch { fail("cannot spawn \(python): \(error)") }
dispatchMain()
```

- [x] Step 2: `talk/app/Info.plist.tmpl` with `__BUNDLE_ID__`, `__NAME__`, `__VERSION__` placeholders; keys: CFBundleExecutable, CFBundleIdentifier, CFBundleName, CFBundlePackageType APPL, CFBundleShortVersionString, LSUIElement true, LSMinimumSystemVersion 14.0, NSMicrophoneUsageDescription ("talk-speak records only while you hold the spacebar."), NSAppleEventsUsageDescription ("talk-speak shows notifications and, as a fallback, asks which window is focused.").
- [x] Step 3: `lib/identity.sh` (the spike from the PRD decision log, parameterised by `IDENTITY`); `talk/app/build.sh`: `swiftc -O Stub.swift -o "$APP/Contents/MacOS/$NAME"`, render the plist with `sed`, `codesign --force --sign "$IDENTITY" --identifier "$BUNDLE_ID" "$APP"`, `codesign --verify --verbose=2 "$APP"`, print `codesign -d -r- "$APP"`.
- [x] Step 4: `talk/launchagent.plist.tmpl`: Label `__LABEL__`, ProgramArguments `__HOME__/Applications/__NAME__.app/Contents/MacOS/__NAME__`, RunAtLoad true, KeepAlive `{SuccessfulExit: false}`, ThrottleInterval 10, StandardOutPath `__STATE__/talk.out`, StandardErrorPath `__STATE__/talk.err`.
- [x] Step 5: **Proof in a sandbox, the live install untouched.** Build into `build/` with a throwaway identity (`--identity "talk-speak-test Local Dev"`, deleted afterwards). Run the stub by hand with `TALK_SPEAK_HOME=<sandbox>` where the sandbox holds a fake `venv/bin/python` (symlink to the system python3) and a fake `talkd.py` that prints its env, writes a heartbeat file every second and exits 0 on SIGTERM. Expected: the child sees `TALK_SPEAK_HOME`, heartbeats appear, SIGTERM to the stub ends both processes within 2 s, `talk.disabled` present makes the stub exit 0 without spawning. The real daemon is never started outside the running install (two event taps would fight over the spacebar).
- [x] Step 6: commit `feat: signed stub with source, build script, launchd template`.

---

### Task 3: Generalise the daemon

**Files:** modify `talk/talkd.py`; extend `tests/test_talk.py`.

**Interfaces (produced):**
- `STATE` constant; every former `~/.claude/...` literal becomes `os.path.join(STATE, ...)` (10 sites: talk.cfg, talk.vocab, talk.log, talk.pid, talk.health.json, talk.history.jsonl, talk.ptt, talk.trigger, speak.rate, speak.voice). `PTT_FLAG`, `MLX_REPO` (default `STATE/models/whisper-large-v3-turbo`), `INPUT_DEVICE` (`None` = system default; substring match on `sd.query_devices()` names), `HISTORY` (`True`), `LAUNCHD_LABEL = "com.studentofai.talk-speak"` are module constants, so `talk.cfg` overrides them for free.
- `load_vocab()` returns `{"general": str, "code": str, "corrections": [(re.Pattern, str)]}`; a `[corrections]` section holds `regex => replacement` lines; `apply_corrections(text, rules)` runs built-in generic rules then user rules.
- `grants()` returns `{"microphone": str, "accessibility": bool, "input_monitoring": str}` using `AVCaptureDevice.authorizationStatusForMediaType_("soun")` (0 notDetermined, 1 restricted, 2 denied, 3 authorized), `AXIsProcessTrusted()`, and `IOHIDCheckAccess(1)` via ctypes (0 granted, 1 denied, 2 unknown). `request_grants()` calls `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})`, `IOHIDRequestAccess(1)` and `AVCaptureDevice.requestAccessForMediaType_completionHandler_` once at daemon start, so first start raises the three system prompts. The health file gains a `grants` key; doctor reads grants from the health file (the daemon runs inside the app; a Terminal process cannot see the app's grants) and prints the `open x-apple.systempreferences:com.apple.preference.security?Privacy_<Pane>` link for each missing one.
- `--warm` fetches `config.json` and `weights.safetensors` from `https://huggingface.co/mlx-community/whisper-large-v3-turbo/resolve/main/` with `curl -L -C - --speed-limit 40000 --speed-time 25` retried up to 5 times, prints the size first (1.61 GB measured).

- [x] Step 1: tests first (add to `tests/test_talk.py`, same exec-loader pattern the file already uses):

```python
def test_vocab_corrections_section_parsed():
    v = mod.parse_vocab("[general]\nfoo\n[corrections]\nkim+i => Kimi\nopen\\s+claw => OpenClaw\n")
    assert v["general"] == "foo"
    assert [r.pattern for r, _ in v["corrections"]] == ["kim+i", "open\\s+claw"]

def test_user_corrections_applied_after_builtin():
    rules = mod.parse_vocab("[corrections]\nkimmy => Kimi\n")["corrections"]
    assert mod.apply_corrections("slash talk to kimmy", rules) == "/talk to Kimi"

def test_bad_correction_line_is_skipped_not_fatal():
    v = mod.parse_vocab("[corrections]\nno arrow here\n( => broken\n")
    assert v["corrections"] == []

def test_state_dir_from_env(monkeypatch_env):   # helper sets TALK_SPEAK_HOME then re-execs the module
    assert mod.STATE == monkeypatch_env and mod.LOG == os.path.join(monkeypatch_env, "talk.log")

def test_history_off_writes_nothing(tmp_state):
    mod.HISTORY = False; mod.record_history("hi", app="Notes", win="", held=1.0, secs=0.5)
    assert not os.path.exists(os.path.join(tmp_state, "talk.history.jsonl"))

def test_input_device_substring_selects_index():
    devs = [{"name": "MacBook Pro Microphone", "max_input_channels": 1}, {"name": "USB Audio", "max_input_channels": 1}]
    assert mod.pick_input_device("usb", devs) == 1
    assert mod.pick_input_device(None, devs) is None
    assert mod.pick_input_device("nope", devs) is None   # falls back to default, logs
```

- [x] Step 2: run → the new tests fail with `AttributeError`.
- [x] Step 3: implement `STATE`, `parse_vocab` (split out of `load_vocab`, which keeps file IO and mtime caching), `apply_corrections`, `pick_input_device`, `record_history` gate, `grants`/`request_grants`, health `grants`, doctor rows, `--warm`. Remove the personal rules from `CORRECTIONS` (Kimi, clawdsites, gigscout, OpenClaw, Hermes) and the "USB mic dongle" wording (say "the input device"). Rename the docstring and log strings.
- [x] Step 4: run the whole suite → 64 + 6 pass. `grep -n 'claude\|clawd\|dongle\|\.claude/' talk/talkd.py` → only the `CLAUDE_SPEAK` line, if any.
- [x] Step 5: commit `feat(talk): state dir, corrections in vocab, device knob, grant probes, warm`.

---

### Task 4: Speak engine, hooks and adapters into the repo

**Files:** create `speak/speak-text.sh`, `speak/speak-prune.sh`, `speak/claude-code/{speak-last.sh,speak-session-end.sh,last-reply.py}`, `speak/adapters/hermes/{speak.sh,session-end.sh,README.md}`, `speak/adapters/kimi/{kimi-speak.sh,kimi-last-reply.py,README.md}`, `speak/adapters/claw/{reply,README.md}`, `speak/adapters/dst/{speak.mjs,README.md}`, `tests/test_speak.py`, fixture `tests/fixtures/transcript.jsonl`.

**Interfaces:**
- Engine contract (unchanged in behaviour): text on stdin or `$1`; `STATE=${TALK_SPEAK_HOME:-$HOME/.talk-speak}`; exits 0 silently when `$STATE/speak.on` is absent or `CLAUDE_SPEAK=off` or `TALK_SPEAK=off`; sources `$STATE/speak.env` if present (optional `SPEAKING_FLAG`, `SAY_BIN`); writes `$STATE/last-reply.txt`; touches `$STATE/speaking` (or `$SPEAKING_FLAG`) while `say` runs; never kills a live replay.
- Adapter contract (documented in `docs/SETUP.md`): read session id → stamp `$STATE/speak.alive/<id>` → move `$STATE/speak.muted/PENDING` to `<id>` → exit 0 if `$STATE/speak.muted/<id>` exists → pipe final reply text into `$STATE/bin/speak-text.sh` → exit 0, print nothing (Hermes prints `{}`).
- `last-reply.py <transcript.jsonl>` prints the last assistant text, markdown stripped, a trailing `-word` signature line removed.

- [x] Step 1: `tests/test_speak.py` (subprocess-based; a fake `say` on PATH records its argv to `$TMP/say.log`):

```python
class SpeakEngine(unittest.TestCase):
    def setUp(self): self.state = tempfile.mkdtemp(); self.fake_bin = make_fake_say(self.state)
    def run_engine(self, text, env=None):
        e = {**os.environ, "TALK_SPEAK_HOME": self.state, "PATH": self.fake_bin + ":" + os.environ["PATH"], **(env or {})}
        return subprocess.run(["bash", ENGINE], input=text, text=True, env=e, capture_output=True)
    def test_off_says_nothing(self):
        self.run_engine("hello"); self.assertFalse(os.path.exists(self.state + "/say.log"))
    def test_on_calls_say_with_rate_and_voice(self):
        touch(self.state, "speak.on"); write(self.state, "speak.rate", "180"); write(self.state, "speak.voice", "Samantha")
        self.run_engine("hello"); wait_for(self.state + "/say.log")
        self.assertIn("-r 180", read(self.state, "say.log")); self.assertIn("-v Samantha", read(self.state, "say.log"))
        self.assertEqual(read(self.state, "last-reply.txt").strip(), "hello")
    def test_env_off_wins_over_flag(self):
        touch(self.state, "speak.on"); self.run_engine("hello", {"TALK_SPEAK": "off"})
        self.assertFalse(os.path.exists(self.state + "/say.log"))
    def test_speaking_flag_cleared_after_say(self):
        touch(self.state, "speak.on"); self.run_engine("hello"); wait_for(self.state + "/say.log")
        time.sleep(0.3); self.assertFalse(os.path.exists(self.state + "/speaking"))

class LastReply(unittest.TestCase):
    def test_strips_markdown_and_signature(self):
        out = subprocess.run([PY, LAST_REPLY, FIXTURE], capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "Done. code block omitted. See the file. link")
    def test_ignores_non_assistant_lines(self): ...

class Prune(unittest.TestCase):
    def test_mute_without_heartbeat_is_removed(self): ...   # touch speak.muted/abc, no speak.alive/abc → gone
    def test_fresh_heartbeat_keeps_mute(self): ...
    def test_pending_survives_prune(self): ...
```

- [x] Step 2: run → fails (files missing).
- [x] Step 3: copy the six live files in, replace every `$HOME/.claude` with `$STATE`, `captions.mute` with `${SPEAKING_FLAG:-$STATE/speaking}`, `~/.claude/tools/speak-text.sh` with `$STATE/bin/speak-text.sh`; generalise the signature strip in `last-reply.py` to `re.sub(r"\n?-[a-z]{2,12}\s*$", "", t)`; add the `speak.env` source line and `TALK_SPEAK=off`. Adapters: same substitutions; each `README.md` carries the exact config snippet measured on this Mac (Hermes `hooks.post_llm_call` + `on_session_end`, Kimi `[[hooks]] event = "Stop"`, Claw `$CLAW_REPLY` hook path, dst `cordis.patch.yml` mount) and "verified 2026-09-09 on this machine's versions".
- [x] Step 4: run → pass. `shellcheck speak/*.sh speak/claude-code/*.sh speak/adapters/*/*.sh` clean.
- [x] Step 5: commit `feat(speak): engine, Claude Code hooks and four adapters under one state dir`.

---

### Task 5: The CLI

**Files:** create `bin/talk-speak`; `git rm bin/claude-talk`; create `tests/test_cli.py`.

**Interfaces:**
- `talk-speak talk on|off|toggle|restart|ensure|status|health|doctor|version|log [N]|test|levels|typetest|simulate-failure|heal|selfcheck|warm`
- `talk-speak speak on|off|toggle|status|again|stop|rate N|voice NAME|mute [ID]|unmute [ID|all]|muted`
- `talk-speak doctor` = talk doctor then speak status; `talk-speak version`; `talk-speak paths` prints STATE, app, plist, repo.
- Constants at the top: `STATE`, `NAME=talk-speak`, `LABEL=com.studentofai.talk-speak`, `APP="$HOME/Applications/$NAME.app"`, `PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"`, `DAEMON="$STATE/talkd.py"`, `PY="$STATE/venv/bin/python"`; `selfcheck` reads the clone path from `$STATE/repo`.

- [x] Step 1: `tests/test_cli.py` drives `speak` state with `TALK_SPEAK_HOME` in a temp dir and a fake `say`: `on` creates `speak.on`; `toggle` twice returns to the start; `mute` creates `speak.muted/PENDING` and speaks the "Muted" line; `mute abc` creates `speak.muted/abc`; `unmute all` empties the dir; `muted` lists; `rate 150` writes `speak.rate`; `status` reports ON with rate and voice; `talk status` with no pidfile prints `talk: OFF`; unknown subcommand prints usage and exits 2.
- [x] Step 2: run → fails. Step 3: write the CLI by merging `bin/claude-talk` and `~/bin/claude-speak` under two `case` blocks; `launchctl` calls unchanged apart from the label. Step 4: tests pass; `shellcheck bin/talk-speak` clean. Step 5: commit `feat: talk-speak CLI with talk and speak subcommands`.

---

### Task 6: Hook merger

**Files:** create `lib/hooks.py`, `tests/test_hooks.py`.

**Interfaces:** `python3 lib/hooks.py add|remove <settings.json> <state-dir>`; `add` appends `Stop` → `bash <state>/bin/speak-last.sh` (timeout 10) and `SessionEnd` → `bash <state>/bin/speak-session-end.sh` (timeout 5) unless an entry whose command contains `<state>/bin/` already exists; `remove` drops exactly those entries and any now-empty event list; both back up to `settings.json.bak-<ts>` before writing, write with `indent=2`, exit 1 and write nothing on invalid JSON; a missing file is created as `{"hooks": {...}}`.

- [x] Step 1: tests: add-then-add is byte-identical; add-then-remove leaves other hooks untouched (fixture with the PostToolUse hook this Mac has); remove on a file without our entries is a no-op with no backup; invalid JSON → exit 1, file unchanged; missing file → created.
- [x] Step 2: fail. Step 3: implement (~60 lines, `json` + `shutil` only). Step 4: pass. Step 5: commit `feat: idempotent Claude Code hook merger`.

---

### Task 7: The installer

**Files:** rewrite `install.sh`; `talk/talk.cfg.example` stays `{}` (every knob is documented in `docs/SETUP.md`), `talk/talk.vocab.example` (generic dev vocabulary only, done in Task 3); the two `SKILL.md` files the installer copies are written here.

**Interfaces:** `./install.sh [--dry-run] [--no-start] [--no-cpu-fallback] [--identity NAME] [--uninstall [--purge]]`; steps 1 to 10 in order, each printed as `[n/10] ...`; every write goes through `run()` so `--dry-run` prints `would:` lines; `$STATE/repo` records the clone path; step 9 starts the daemon (which raises the three system prompts itself), step 10 prints the permissions table with deep links and runs doctor. No interactive waits.

- [x] Step 1: write it; `shellcheck install.sh` clean.
- [x] Step 2: `./install.sh --dry-run` from the repo prints ten steps and creates nothing (`find ~/.talk-speak` before/after identical).
- [x] Step 3: (done with the real HOME and `TALK_SPEAK_HOME/BIN/APP_DIR/LAUNCH_AGENTS/CLAUDE_DIR` overrides instead of a fake HOME: macOS evaluates a self-signed identity's trust through HOME-relative settings, so a fake HOME hides the identity from `codesign`) `./install.sh --no-start --identity "talk-speak-test Local Dev"` on this Mac: everything lands under the sandbox (venv, app, plist file, `bin`, `.claude/skills`, `.claude/settings.json`), the LaunchAgent is written but not bootstrapped, the throwaway identity is deleted afterwards. Expected: venv created (record wall time and size), `HOME=<sandbox> bin/talk-speak talk doctor` reports deps PASS, weights FAIL until `warm`, grants "unknown until the daemon runs". The real home directory is not touched: `find ~ -newer <marker> -maxdepth 2` shows nothing outside the repo and the sandbox.
- [x] Step 4: `./install.sh --uninstall --dry-run` lists exactly the reverse. Step 5: commit `feat: install.sh v3 (venv, identity, app, agent, hooks, skills)`.

---

### Task 8: Docs, skills, CI

**Files:** `README.md` (rewrite), `docs/PERMISSIONS.md`, `docs/SETUP.md`, `docs/TROUBLESHOOTING.md`, `docs/ACCEPTANCE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `skills/talk/SKILL.md`, `skills/speak/SKILL.md`, `.github/workflows/ci.yml`.

- [x] Step 1: skills: `/talk` runs `~/bin/talk-speak talk $ARGUMENTS` (empty → `toggle`); `/speak` runs `~/bin/talk-speak speak $ARGUMENTS` with the session-id rule for `mute`/`unmute`; "report the one output line, nothing else".
- [x] Step 2: README per PRD 5.7 (GIF placeholder path `docs/demo.gif`, to be recorded by the author); PERMISSIONS = PRD 5.5 table; TROUBLESHOOTING = one row per doctor line and per Basso; ACCEPTANCE = PRD section 2 as a dated checklist.
- [x] Step 3: `ci.yml`: `macos-latest`, `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, `.venv/bin/python -m unittest discover -s tests -v`, `brew install shellcheck && shellcheck $(git ls-files '*.sh' bin/talk-speak)`, `swiftc -O talk/app/Stub.swift -o /tmp/stub`, `CI=1 ./install.sh --dry-run`.
- [x] Step 4: `grep -rn 'claude\|clawd\|the author\|/Users/' --exclude-dir=.git .` shows only the allowed sites. Step 5: commit `docs: README, permissions, setup, troubleshooting, acceptance; ci: tests + shellcheck + stub build`.

---

### Task 9: Publish

- [x] Step 1: `gh repo create StudentOfAi/talk-speak --private --source . --push` (private first; the author flips to public after reading the README on GitHub). Done 2026-09-09.
- [x] Step 2: CI green on the first push (run 34331587449).
- [x] Step 3: tag `v3.0.0` and write the release notes from `CHANGELOG.md`.
- [ ] Step 4: the author runs the README on the next Mac (his call when); the timed result goes into `docs/ACCEPTANCE.md`. Until then the first-boot grant flow (three prompts from the stub) is **unverified**, and the README says so.

---

## Self-review against the PRD

- Coverage: T1 to T7 unchanged behaviour (Task 3 keeps the 64 tests green), T8 Task 7, T9/T10/T11 Task 2, T12/T13/T14/T15 Task 3, T16 Task 5, T17 Tasks 3 to 5; S1 to S4 Task 4, S5 Task 6, S6 Task 4 READMEs + SETUP.md, S7 Task 4, S8 Task 8; 5.5 Task 8 PERMISSIONS + Task 3 doctor; 5.6 Task 7; 5.7 and 5.8 Task 8; gaps 1 to 13 mapped except gap 12 (the zshrc line on this Mac, left alone by the author's instruction: "don't mess with mine").
- Placeholders: the README GIF is the one deliberate placeholder and is the author's to record.
- Names used consistently: `STATE`, `TALK_SPEAK_HOME`, `com.studentofai.talk-speak`, `talk-speak Local Dev`, `$STATE/bin/speak-text.sh`, `parse_vocab`, `apply_corrections`, `pick_input_device`, `grants`, `request_grants`.

# PRD: talk-speak (hold-space dictation + spoken replies for macOS agent harnesses)

Status: v1.0, 2026-09-09. Describes release v3.0.1 of
https://github.com/StudentOfAi/talk-speak as shipped. Owner: StudentOfAi.

Purpose: take a private, working hold-space dictation + spoken-replies setup
and make it a public repo that reproduces the same setup on any Apple Silicon
Mac with one clone, one install script and a short, known list of one-time
permission clicks.

Every number in this document was measured on 2026-09-09, on the author's Mac
mini (M4, macOS 26.1) or on the GitHub `macos-latest` runner, unless marked
"unverified". The implementation plan that produced the repo is
[PLAN.md](PLAN.md); the checklist for a fresh Mac is [ACCEPTANCE.md](ACCEPTANCE.md).

---

## 1. Validate

**What does this do that a simpler thing can't?**
macOS Dictation needs a per-app trigger and never interrupts spoken output.
Paid dictation apps type text but do not close the loop with an agent harness.
This does one loop nothing off the shelf does: hold space in any app to talk,
release to type, every finished reply from every harness is read aloud with one
per-session mute, and pressing space cuts the speech off. All local: Whisper on
the Apple GPU, macOS `say`, no cloud, no API key.

**Who is it for?**
A developer on a Mac who runs terminal AI harnesses (Claude Code first; Hermes,
Kimi Code, Claw and dst also wired) and wants to talk instead of type and hear
replies while looking elsewhere. First concrete user: the author's second Mac.
Second: anyone who reads the README.

**What does it replace?**
A paid dictation app, and the hours it took to hand-build the signed stub and
the permissions dance, which could not be repeated before this repo existed
because the stub's source had been lost.

**Proof it is needed.**
The private version is used daily (every transcript since 2026-08-31 is in its
history file; the daemon was up and healthy while this was written). The pain
was reproducibility, not desire.

**Narrowest version.**
A repo that reproduces the setup on a second Mac: `git clone`, `./install.sh`,
the clicks in section 5.5, `doctor` 9/9. The installer wires Claude Code; the
other four harness adapters ship as files plus a config snippet each.

**Still matters in 6 months?** Yes, for as long as terminal harnesses are the
daily driver.

Validate passes.

---

## 2. Define: what finished looks like

Finished = a person with only the README, on an Apple Silicon Mac they have not
set up before, can do all of the following:

| # | Check | Status 2026-09-09 |
|---|---|---|
| 1 | Clone, run `./install.sh`, complete the one-time clicks in section 5.5 | installer verified in a sandbox (every target directory redirected, 38 s); the three first-start prompts **unverified** |
| 2 | Run `talk-speak talk doctor` and see `9/9 passed` | 4/9 before the daemon runs, as designed; 9/9 **unverified** on a fresh Mac |
| 3 | Open Notes, hold space, say one sentence, release: the sentence appears, no trailing space; a second dictation is separated by exactly one space | spacing rules unit-tested (81 daemon checks); live dictation through the installed app **unverified** |
| 4 | Tap space in a YouTube tab: the video pauses (tap passes through) | tap rule unit-tested; live **unverified** |
| 5 | In Claude Code: `/speak on`, the next reply is spoken; `/speak mute` silences that session only; space-down cuts speech | engine, transcript reader and mute contract unit-tested (35 tests); live **unverified** |
| 6 | `./install.sh --uninstall` leaves no app, no LaunchAgent, no hooks in `settings.json`, no CLI; state survives unless `--purge` | verified in the sandbox, including `--purge` removing the signing identity |

Measured target: clone to first dictation in 15 minutes or less, excluding the
model download (1.61 GB MLX large-v3-turbo; the CPU `small` fallback works
until it lands). The time on a fresh Mac has not been recorded yet.

---

## 3. Evaluate: how finished is tested

| Check | How | Where | Last result |
|---|---|---|---|
| Daemon rules | `<venv>/bin/python tests/test_talk.py`: the three fail-open spacebar rules, healing state machine, spoken punctuation, continuation spacing, vocab corrections, device knob, history gate, grant report | local, CI | 81/81 |
| Speak, hooks, CLI | `python3 -m unittest tests.test_speak tests.test_hooks tests.test_cli` | local, CI | 35/35 |
| Scripts | `shellcheck -x` on every `.sh`, the CLI and the Claw hook | local, CI | clean |
| Stub | `swiftc -O talk/app/Stub.swift` | local, CI | compiles (64 KB arm64) |
| Version | `VERSION` equals `talkd.py --version` | CI | equal |
| Installer | `./install.sh --dry-run` and `--uninstall --dry-run` print the plan and write nothing | local, CI | clean, home untouched |
| Pinned deps | `python3 -m venv` + `pip install -r requirements.txt` on a fresh venv | local, CI | 18 s with a warm cache, 16 to 32 s cold, 1.3 GB |
| Sandboxed install | `./install.sh --no-start` with every target directory redirected and a throwaway identity, then `--uninstall --purge` | local, before the tag | see ACCEPTANCE.md |
| Stub behaviour | run the compiled stub against a fake daemon: environment, SIGTERM forwarding, `talk.disabled`, missing venv | local | all four paths correct |
| Clean room | the README on a Mac that has never run it: prompts, 9/9, live dictation, spoken replies, uninstall | manual | **not run yet** |

TCC grants cannot be exercised in CI. The clean-room run is the only test of
the permission flow, and it is still open.

---

## 4. Scope

**In (v3.x):** macOS on Apple Silicon (MLX backend) with CPU whisper fallback;
talk daemon, CLI, signed app stub with source, KeepAlive LaunchAgent; speak
engine, Claude Code Stop and SessionEnd hooks, transcript-to-speech cleaner;
`/talk` and `/speak` skills; adapters for Hermes, Kimi Code, Claw and dst as
files plus config snippets; installer, uninstaller, doctor; docs; CI.

**Out:** Windows and Linux. Wake word. A GUI. Voice cloning. Any coupling to a
specific captions or listener app (the flag files stay generic). A key other
than space in the UI (`PTT_KEYCODE` in `talk.cfg` already allows it).

---

## 5. Requirements as shipped

### 5.1 Layout

```
talk-speak/
  README.md  LICENSE (MIT)  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  VERSION
  requirements.txt            pinned deps, measured working on macOS 26.1 / Apple Silicon
  install.sh                  install | --dry-run | --no-start | --no-cpu-fallback | --identity NAME | --uninstall [--purge]
  bin/talk-speak              one CLI: `talk` and `speak` subcommands, `doctor`, `version`, `paths`
  lib/identity.sh             self-signed code-signing identity, created by script
  lib/hooks.py                idempotent settings.json merger for the Claude Code hooks
  talk/talkd.py               the daemon
  talk/app/Stub.swift  Info.plist.tmpl  build.sh     the signed stub and its build
  talk/launchagent.plist.tmpl                          KeepAlive agent, passes TALK_SPEAK_HOME
  talk/talk.cfg.example  talk.vocab.example           generic seeds
  speak/speak-text.sh  speak-prune.sh                 the engine and the mute pruner
  speak/claude-code/speak-last.sh  speak-session-end.sh  last-reply.py
  speak/adapters/hermes/  kimi/  claw/  dst/          each: hook file(s) + README with the config snippet
  skills/talk/SKILL.md  skills/speak/SKILL.md
  tests/test_talk.py  test_speak.py  test_hooks.py  test_cli.py  fixtures/
  docs/PRD.md  PLAN.md  PERMISSIONS.md  SETUP.md  TROUBLESHOOTING.md  ACCEPTANCE.md
  .github/workflows/ci.yml
```

Installed layout: `~/.talk-speak/` (venv, daemon copy, models, `bin/` engine and
hooks, all flags and logs), `~/Applications/talk-speak.app`,
`~/Library/LaunchAgents/com.studentofai.talk-speak.plist`, `~/bin/talk-speak`,
`~/.claude/skills/{talk,speak}` and two hook entries in `~/.claude/settings.json`.
Every target directory is overridable (`TALK_SPEAK_HOME`, `TALK_SPEAK_BIN`,
`TALK_SPEAK_APP_DIR`, `TALK_SPEAK_LAUNCH_AGENTS`, `TALK_SPEAK_CLAUDE_DIR`,
`TALK_SPEAK_IDENTITY`).

### 5.2 Naming (decision D1)

Anthropic's Claude Code legal page says third parties may state that a tool
works with Claude Code but may not use "Claude Code" or "Anthropic" as part of
their own product, feature or company name
(https://docs.anthropic.com/en/docs/claude-code/legal-and-compliance). The
private names (`claude-talk`, `claude-speak`, `claude-talkd`) did exactly that
and also collided with existing repos.

Name: `talk-speak`, free on GitHub on 2026-09-09. Repo `StudentOfAi/talk-speak`,
CLI `talk-speak` (bare `talk` and `speak` already exist on macOS and Homebrew),
app `talk-speak.app`, bundle id and launchd label `com.studentofai.talk-speak`,
state dir `~/.talk-speak/`, identity `talk-speak Local Dev`. The word "claude"
appears only where the harness is named: `skills/`, `speak/claude-code/`, the
`CLAUDE_SPEAK=off` compatibility variable. The skills `/talk` and `/speak` are
commands inside Claude Code, not product names.

### 5.3 Talk

Behaviour carried over unchanged (all covered by `tests/test_talk.py`):

- T1 Hold space in any app records; a tap under 0.30 s passes through as a
  space; any space with ⌘ ⌥ ⌃ or fn passes through.
- T2 Release types the transcript as tagged CGEvent Unicode key events into the
  focused field; no trailing space; a genuine continuation gets one leading
  space.
- T3 Space-down kills `say`.
- T4 Fail-open: space is intercepted only while audio is proven healthy;
  degrade, heal ladder, rate-limited self-restart, heartbeat file,
  `simulate-failure`.
- T5 MLX large-v3-turbo on Apple Silicon, CPU `small` fallback; streaming
  segmentation on pauses.
- T6 `talk.cfg` JSON overrides any uppercase constant; `talk.vocab` hot
  reloads; `[code]` list when a terminal or editor is frontmost.
- T7 A flag file exists while space is held so other mic apps can mute.

Changes made for the public release:

- T8 Interpreter: the installer builds `~/.talk-speak/venv` from
  `requirements.txt` (pinned: mlx 0.32.2, mlx-whisper 0.4.3, openai-whisper
  20250625, numpy 2.4.6, sounddevice 0.5.6, pyobjc 12.2.2). The stub runs that
  interpreter. A Homebrew upgrade cannot break dictation.
- T9 Stub: `talk/app/Stub.swift` (43 lines) spawns the daemon as a child with
  `TALK_SPEAK_HOME` set, exits 0 quietly when `talk.disabled` exists or the
  venv is missing (so KeepAlive does not spin), forwards SIGTERM, SIGINT and
  SIGHUP to the child, exits with the child's status. No hardcoded paths.
  `build.sh` stamps the version from `VERSION` and signs with the local
  identity. The daemon must be a child, not an exec: TCC attributes a child to
  its responsible parent, which is how the app's grants reach Python.
- T10 Signing identity: `lib/identity.sh` creates a self-signed code-signing
  certificate with `/usr/bin/openssl` and `security`, no Keychain Access clicks
  (Homebrew OpenSSL 3 writes a PKCS12 that `security import` rejects). Grants
  are keyed to bundle id + certificate, so the same identity signs every
  rebuild and grants survive upgrades. `--purge` removes it.
- T11 LaunchAgent: KeepAlive template with `EnvironmentVariables.TALK_SPEAK_HOME`
  (added in 3.0.1; without it a custom state dir never started). The old
  Terminal-child watchdog files are gone. The installer never edits shell rc
  files.
- T12 Corrections: the daemon keeps mechanics only (spoken punctuation,
  "slash x", "dot dot dot", two mishears). Name corrections live in a
  `[corrections]` section of `talk.vocab` as `regex => replacement`, hot
  reloaded. The example vocab ships generic developer vocabulary.
- T13 Doctor names each grant (Microphone via `AVCaptureDevice`, Accessibility
  via `AXIsProcessTrusted`, Input Monitoring via `IOHIDCheckAccess`) from the
  daemon's own report in `talk.health.json`, with the System Settings deep link
  for each. The daemon raises the three prompts itself on first start.
- T14 `INPUT_DEVICE` knob (substring of the device name); default is the system
  input. No message assumes a USB dongle.
- T15 `talk.history.jsonl` on by default, `{"HISTORY": false}` turns it off;
  README and SECURITY.md say audio and text never leave the machine.
- T16 `selfcheck` finds the test suite through `~/.talk-speak/repo`, written by
  the installer.
- T17 State directory `~/.talk-speak/` (`TALK_SPEAK_HOME` overrides), one
  `STATE` constant in every script. Nothing of the product lives under
  `~/.claude/` except the two skills and the two hook entries, which is where
  Claude Code looks. The author's own Mac stays on its private layout (D2).

### 5.4 Speak

Behaviour carried over unchanged (covered by `tests/test_speak.py` and
`tests/test_cli.py`):

- S1 Engine: reply text on stdin or as one argument; `say` with rate and voice
  files; global `speak.on` flag; `TALK_SPEAK=off` or `CLAUDE_SPEAK=off` for
  headless runners; writes `last-reply.txt`; never kills a running `again`
  replay; a `speaking` flag exists while talking; a newer reply cuts off the
  engine's own previous one only.
- S2 CLI: on, off, toggle, status (warns when output is muted or at zero),
  again, stop, rate, voice, mute, unmute, muted.
- S3 Session-scoped mute: `PENDING` is written by `mute`; the next hook to fire
  claims it for its session id; each hook stamps an alive file per turn; a mute
  dies with its session (end hook) or 90 minutes after the last heartbeat.
- S4 Claude Code: the Stop hook extracts the last assistant text from the
  transcript JSONL and strips code blocks, inline code, links, tables, markdown
  marks and a trailing `-word` signature; the SessionEnd hook clears the mute.

Changes made for the public release:

- S5 Hook installer: `lib/hooks.py add|remove` merges the two hooks into
  `settings.json` idempotently (backup first, other hooks untouched, running
  twice changes nothing, removes exactly its own entries, exit 1 and no write
  on invalid JSON).
- S6 Adapter contract, written once in SETUP.md: read the session id, stamp
  alive, claim `PENDING`, exit if muted, pipe the final reply text to
  `~/.talk-speak/bin/speak-text.sh`, exit 0 and print nothing. Hermes, Kimi
  Code, Claw and dst are the reference implementations, each with the config
  snippet measured on the author's builds on 2026-09-09. The installer wires
  Claude Code only (D3).
- S7 `TALK_SPEAK=off` added; `CLAUDE_SPEAK=off` still works.
- S8 Both skills rewritten for the launchd model; the installer copies them to
  `~/.claude/skills/`.

### 5.5 Permissions: the one-time clicks

All grants go to the signed `talk-speak.app`, never to Terminal, because the
app is what launchd runs.

| # | Grant | Who gets it | Why | When macOS asks | Verify |
|---|---|---|---|---|---|
| 1 | Microphone | talk-speak.app | capture while space is held | first daemon start | Privacy & Security > Microphone |
| 2 | Accessibility | talk-speak.app | event tap on the space key, posting keystrokes, reading the focused window title | first daemon start | Privacy & Security > Accessibility |
| 3 | Input Monitoring | talk-speak.app | session event tap on current macOS | first daemon start; takes effect after `talk-speak talk restart` | Privacy & Security > Input Monitoring |
| 4 | Background item | the LaunchAgent | launchd runs the stub at login and keeps it alive | `launchctl bootstrap` triggers the "Background Items Added" notice; leave it on | Login Items & Extensions |
| 5 | Automation to System Events | Terminal | only the `typetest` probe uses `osascript` | only if you run `typetest` | Privacy & Security > Automation |
| 6 | Keychain: use the signing key | `codesign` | the identity is imported pre-authorised for `codesign`; a prompt here is unexpected | first `build.sh`, if at all | Keychain Access |

Normal operation needs rows 1 to 4: three privacy toggles plus one
acknowledgement. Rows 5 and 6 are conditional. Nothing needs `sudo`. Known
recovery for a cached keystroke denial: the user runs
`tccutil reset PostEvent com.studentofai.talk-speak` themselves; the installer
never runs it.

### 5.6 Install flow

`./install.sh`, ten printed steps, each idempotent, no interactive waits:

1. Preflight: Apple Silicon, macOS 14 or newer, Homebrew, Homebrew python3 3.11
   or newer, `swiftc` from the Command Line Tools. Stops with the fix on the
   first miss.
2. `~/.talk-speak/venv` from `requirements.txt` (`--no-cpu-fallback` skips
   openai-whisper and torch).
3. The signing identity, created if absent.
4. Build and sign the stub into `~/Applications/talk-speak.app`.
5. Render and write the LaunchAgent.
6. Daemon copy, `VERSION`, the CLI into `~/bin` (prints the PATH line if
   missing, never edits rc files), `~/.talk-speak/repo`.
7. Speak engine and hooks into `~/.talk-speak/bin`, skills into
   `~/.claude/skills`, hooks merged into `settings.json`.
8. Seed `talk.cfg`, `talk.vocab`, `speak.on` only if absent.
9. Start the daemon (`--no-start` skips; the daemon raises the three prompts).
10. Print the permissions table with deep links and run `doctor`.

`--dry-run` prints every write as a `would:` line and writes nothing.
`--uninstall` reverses 4 to 7 and the CLI, leaves state; `--purge` also removes
`~/.talk-speak` and the identity. Any file it replaces is backed up as
`<file>.replaced-<timestamp>`.

### 5.7 Docs

README (what it does, the design rule, install, the permissions table,
commands, configure, other harnesses, privacy, limits, uninstall, tests);
PERMISSIONS.md (section 5.5 plus recovery); SETUP.md (layout, adapter contract,
every daemon knob with its default); TROUBLESHOOTING.md (one row per doctor
line, then symptoms); ACCEPTANCE.md (section 2 as a dated checklist);
CHANGELOG, CONTRIBUTING, SECURITY. The README's demo GIF is a placeholder
comment until the author records one. No screenshots.

### 5.8 CI

GitHub Actions on `macos-latest`, Python 3.14: venv from the pins, the 81
daemon checks, the 35 unit tests, `shellcheck`, the stub compile, the VERSION
check, `./install.sh --dry-run`. Green on every push since the first.

---

## 6. Gaps found and how each was closed

| # | Gap (found 2026-09-09) | Closed by |
|---|---|---|
| 1 | The signed stub's Swift source did not exist on disk | `talk/app/Stub.swift`, rewritten from the binary's observable behaviour and verified against a fake daemon |
| 2 | Installer, plist template and skill described the deprecated Terminal-child watchdog | installer v3, KeepAlive agent template, both skills rewritten; watchdog files removed |
| 3 | Interpreter pinned to one Homebrew Cellar path in two places | own venv with pinned `requirements.txt` |
| 4 | The whole speak side (11 files, 5 harnesses) lived outside the repo; hooks were hand-edited into `settings.json` | `speak/`, `lib/hooks.py`, adapters with snippets |
| 5 | Names infringed the Claude Code trademark rule and collided on GitHub | `talk-speak` everywhere (5.2) |
| 6 | Personal data in the vocab example, `CORRECTIONS`, README and tests | generic example vocab; corrections moved to `talk.vocab`; names removed from shipped files (see D6 for history) |
| 7 | `selfcheck` hardcoded one machine's repo path | `~/.talk-speak/repo` |
| 8 | Bundle version 2.2.0 vs daemon 2.3.0 | `VERSION` is the single source; CI checks it against the daemon; `build.sh` stamps the bundle |
| 9 | No LICENSE, CHANGELOG, CI, CONTRIBUTING, SECURITY | all present |
| 10 | Model download size documented nowhere | README, `warm` prints it (1.61 GB) |
| 11 | Messages assumed a USB dongle; no device knob | `INPUT_DEVICE`, wording fixed |
| 12 | A shell rc line from the old model on the author's Mac | left alone on purpose (D2) |
| 13 | Docs said 27 tests; the suite had 64 | 81 checks + 35 tests, counts in README and CI |
| 14 | 3.0.1: LaunchAgent did not pass `TALK_SPEAK_HOME`; a custom state dir never started | `EnvironmentVariables` in the template; stub verified with and without the variable |
| 15 | 3.0.1: `--uninstall` failed when the state dir did not exist | guarded; reproduced then re-run to exit 0 |
| 16 | 3.0.1: the PRD described the pre-release state; PLAN.md carried a personal name | this document; PLAN.md scrubbed |

---

## 7. Decisions

- D1 Name `talk-speak` (decided 2026-09-09 by the author).
- D2 State dir `~/.talk-speak/`, nothing Claude-named; the author's own Mac is
  **not** migrated, restarted or re-granted by any step (decided 2026-09-09:
  "don't mess with mine, simply push the experience I have").
- D3 Ship all five harness integrations; the installer wires Claude Code only.
- D4 Publish under `StudentOfAi`, MIT, private until the author flips it.
- D5 Transcript history on by default with an off switch.
- D6 **Open, the author's call:** the git history before the rename still
  contains the private vocab example (a first name, three place names, private
  project names) and one absolute home path. The working tree is clean; the
  history is not. Before flipping public, either squash to a single root commit
  and re-create the release tag on it, or accept that the old commits are
  readable. The squash is one force-push; the exact commands are in the
  release notes for v3.0.1 and in the session that shipped it.

---

## 8. Verified and not verified

Verified on 2026-09-09: everything in section 3 except the clean-room row;
the sandboxed install and purge in ACCEPTANCE.md; the stub's four paths; the
signing spike (identity by script, no dialogs, designated requirement
`identifier + certificate leaf`); no private email in any commit; the author's
live install untouched throughout (daemon up, no `~/.talk-speak`, no second
identity, no second agent).

Not verified, needs a person and a Mac that has never run it: the three
first-start prompts, `doctor` 9/9, live dictation through the installed app,
spoken replies through the installed hooks, `/speak mute` scoping across two
sessions, and the clone-to-first-dictation time. ACCEPTANCE.md is the checklist;
the result goes into its Runs table.

---

## Decision log

- 2026-09-09: PRD drafted from the live install. Name check: `talkspeak` and
  `talk-speak` free on GitHub; `heldspace` and `hold2talk` each had one
  zero-star repo; `claude-talk` and `claude-speak` taken and trademark-bound.
  The author chose `talk-speak`.
- 2026-09-09: signing spike passed. `/usr/bin/openssl` (LibreSSL) makes a
  PKCS12 that `security import -T /usr/bin/codesign` accepts;
  `security add-trusted-cert -p codeSign` needs no dialog; `codesign` signs
  without a prompt; designated requirement = `identifier` + `certificate leaf`,
  so grants survive rebuilds with the same identity. Homebrew OpenSSL 3 PKCS12
  fails to import (MAC verification).
- 2026-09-09: the stub spawns the daemon as a child and forwards SIGTERM, not
  exec: TCC attributes a child to its responsible parent.
- 2026-09-09: sandbox lesson. Faking `HOME` hides a self-signed identity from
  `codesign` (trust settings are HOME-relative), so the sandbox run redirects
  every target directory individually and keeps the real HOME and keychain.
  `grep -q` in a pipeline under `set -o pipefail` makes a found identity look
  missing; scripts pin `/usr/bin/grep ... >/dev/null`.
- 2026-09-09: v3.0.0 pushed private, CI green, release created. Validation pass
  the same day found gaps 14 to 16; v3.0.1.

# talk-speak

Hold **space** anywhere on macOS, talk, release: your words are typed into whatever has keyboard focus. Terminal, browser, Docs, Notes, Mail, any app. And every reply your AI harness finishes is read aloud, from Claude Code, Hermes, Kimi Code, Claw or dst, with one shared mute per session. Pressing space cuts the speech off.

All local. Whisper large-v3-turbo on the Apple GPU (MLX), macOS `say` for speech. No cloud, no API key, no wake word, no window gate, no Enter pressed for you.

<!-- demo GIF: docs/demo.gif (hold, talk, release, spoken reply) -->

## Install

Apple Silicon Mac, macOS 14 or newer (tested on 26.1), Homebrew, Command Line Tools.

```bash
git clone https://github.com/StudentOfAi/talk-speak.git
cd talk-speak
./install.sh
```

`install.sh` prints ten steps: a Python venv with pinned deps in `~/.talk-speak/venv`, a self-signed code-signing identity (no Keychain clicks), the signed `~/Applications/talk-speak.app`, a launchd agent, the `talk-speak` CLI in `~/bin`, the speak engine and Claude Code hooks, then it starts the daemon. `./install.sh --dry-run` shows the plan without writing anything. No `sudo`. It never edits your shell rc files.

Then the **one-time clicks**. macOS asks three times, all for "talk-speak", the signed app launchd runs:

| # | Grant | Why |
|---|---|---|
| 1 | Microphone | records only while you hold the spacebar |
| 2 | Accessibility | sees the spacebar, types the transcript, reads the focused window title |
| 3 | Input Monitoring | the session-wide key tap (restart the daemon after granting: `talk-speak talk restart`) |

A "Background Items Added" notice is launchd registering the agent; leave it enabled. Missed a prompt? System Settings > Privacy & Security > the pane > enable "talk-speak". Details, deep links and recovery in [docs/PERMISSIONS.md](docs/PERMISSIONS.md).

Finally, `talk-speak talk warm` fetches the 1.6 GB MLX weights (resumable). Until then the CPU `small` model is used, which works but is slower and sloppier with names.

`talk-speak doctor` checks all of it, nine lines, each failure naming its fix.

## Use

- Hold space, talk, release. The text lands in the focused field, no trailing space; a second dictation is separated by exactly one space.
- A quick tap of space is a space. Space with ⌘ ⌥ ⌃ or fn is never touched (Spotlight, launchers). Space within 0.4 s of other typing is typing.
- Say "dot", "comma", "question mark" for punctuation; "slash talk" becomes `/talk`.
- Spoken replies are on. `talk-speak speak mute` silences the current session only; `talk-speak speak off` silences everything; space-down cuts speech off.
- In Claude Code: `/talk` and `/speak` (installed as skills) run the same commands.

## The design rule

> Dictation failing must never cost you your spacebar.

The key tap swallows space only while audio is proven healthy. Three fail-open rules, all unit-tested:

1. A space carrying ⌘ ⌥ ⌃ or fn passes straight through.
2. If the mic is not delivering audio, space is never intercepted.
3. A space within 0.4 s of another keystroke is a space (your keystrokes only; the daemon's own output is tagged and ignored).

If the mic dies mid-session the daemon degrades (spacebar freed, notification), heals itself (re-probe every 20 s, re-init CoreAudio, then a rate-limited self-restart), and tells you out loud when it needs a replug. Heartbeat and grants are in `~/.talk-speak/talk.health.json`; `talk-speak talk simulate-failure` proves the property on the live daemon.

## Commands

```
talk-speak talk  on | off | toggle | restart | status | doctor | warm | log [N] | levels | typetest | simulate-failure | selfcheck
talk-speak speak on | off | toggle | status | mute [ID] | unmute [ID|all] | muted | again | stop | rate N | voice NAME
talk-speak doctor | version | paths
```

## Configure

- `~/.talk-speak/talk.vocab`: words whisper should spell your way (`[general]`, `[code]` for terminals and editors) and `[corrections]` as `regex => replacement`. Reloaded on save.
- `~/.talk-speak/talk.cfg`: JSON overrides for any knob of the daemon (`PTT_MIN_HOLD`, `TYPING_GUARD_S`, `INPUT_DEVICE`, `HISTORY`, `PTT_KEYCODE`, ...). The full list is in [docs/SETUP.md](docs/SETUP.md).
- `talk-speak speak rate 180`, `talk-speak speak voice Samantha`.

## Other harnesses

The Claude Code hooks are installed for you. Hermes, Kimi Code, Claw and dst adapters are in [`speak/adapters/`](speak/adapters/), each a ~20-line hook plus the config snippet. Any harness can join: read the session id, stamp alive, claim a pending mute, pipe the finished reply into `~/.talk-speak/bin/speak-text.sh`. The contract is in [docs/SETUP.md](docs/SETUP.md).

## Privacy

Audio is transcribed on your Mac and never leaves it. Every transcript is appended to `~/.talk-speak/talk.history.jsonl` with the app and window it went to, which is how you debug a mishear; set `{"HISTORY": false}` in `talk.cfg` to keep nothing. While the spacebar is held, `~/.talk-speak/talk.ptt` exists, and while a reply is being spoken `~/.talk-speak/speaking` exists, so other always-on listeners on your Mac can mute themselves.

## Known limits

- macOS on Apple Silicon only. The stub, the event tap and `say` are macOS; MLX is Apple GPU.
- Holding space in a game or a video player records. Taps still pass through.
- If CoreAudio wedges at the device level, no process can fix it: `sudo killall coreaudiod` or replug the mic. The daemon says so instead of failing quietly.
- Secure text fields (password prompts) refuse posted keystrokes: you hear Basso, nothing is typed.

## Uninstall

```bash
./install.sh --uninstall          # app, agent, hooks, skills, CLI; keeps ~/.talk-speak
./install.sh --uninstall --purge  # also ~/.talk-speak and the signing identity
```

## Tests

```bash
~/.talk-speak/venv/bin/python tests/test_talk.py          # 81 checks: the safety rules, healing, vocab, grants
python3 -m unittest tests.test_speak tests.test_hooks tests.test_cli
```

MIT. Built by [StudentOfAi](https://github.com/StudentOfAi). Works with Claude Code, Hermes, Kimi Code, Claw and dst; not affiliated with any of them.

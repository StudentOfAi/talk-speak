# Setup details

## Layout

| Path | What |
|---|---|
| `~/.talk-speak/venv/` | Python with the pinned deps (`requirements.txt`) |
| `~/.talk-speak/talkd.py` | the daemon, a copy of `talk/talkd.py` |
| `~/.talk-speak/models/whisper-large-v3-turbo/` | MLX weights (`talk-speak talk warm`) |
| `~/.talk-speak/bin/` | speak engine, prune, Claude Code hooks, transcript readers |
| `~/.talk-speak/talk.cfg`, `talk.vocab` | your config and vocabulary |
| `~/.talk-speak/talk.log`, `talk.err`, `talk.out`, `talk.health.json`, `talk.history.jsonl` | daemon output |
| `~/.talk-speak/speak.on`, `speak.rate`, `speak.voice`, `speak.muted/`, `speak.alive/`, `last-reply.txt` | speak state |
| `~/Applications/talk-speak.app` | the signed stub launchd runs |
| `~/Library/LaunchAgents/com.studentofai.talk-speak.plist` | KeepAlive agent |
| `~/bin/talk-speak` | the CLI |
| `~/.claude/skills/talk`, `~/.claude/skills/speak` | Claude Code skills; hooks are merged into `~/.claude/settings.json` |

Set `TALK_SPEAK_HOME` to move the state dir. The installer also honours `TALK_SPEAK_BIN`, `TALK_SPEAK_APP_DIR`, `TALK_SPEAK_LAUNCH_AGENTS`, `TALK_SPEAK_CLAUDE_DIR` and `TALK_SPEAK_IDENTITY`.

## Harness adapters

The engine is `~/.talk-speak/bin/speak-text.sh`: reply text on stdin, it honours the global `speak.on` flag, rate and voice, writes `last-reply.txt`, and never interrupts a `speak again` replay. Any "reply finished" hook can feed it. The per-session mute contract, in order:

1. Read the session id from the hook payload (fall back to a stable per-harness key).
2. Stamp `~/.talk-speak/speak.alive/<id>` (an empty file).
3. If `~/.talk-speak/speak.muted/PENDING` exists, rename it to `<id>` (that session asked to be muted). If `UNMUTE-PENDING` exists, delete it and `<id>`.
4. If `~/.talk-speak/speak.muted/<id>` exists, exit 0 silently.
5. Pipe the final reply text into the engine. Exit 0, print nothing (or whatever "no-op" your harness expects).

A session-end hook deletes `speak.muted/<id>` and `speak.alive/<id>`; without one, a mute expires 90 minutes after the last heartbeat. Headless runs are silenced with `TALK_SPEAK=off` (or `CLAUDE_SPEAK=off`) in the environment.

Reference adapters, each with its config snippet: [`speak/adapters/hermes`](../speak/adapters/hermes/README.md), [`speak/adapters/kimi`](../speak/adapters/kimi/README.md), [`speak/adapters/claw`](../speak/adapters/claw/README.md), [`speak/adapters/dst`](../speak/adapters/dst/README.md). The installer wires Claude Code only.

Optional `~/.talk-speak/speak.env` (sourced by the engine): `SPEAKING_FLAG=/path` to move the "speaking now" flag file, `SAY_BIN=/path` to use another `say`-compatible speaker.

## Daemon knobs (`~/.talk-speak/talk.cfg`, JSON)

Any uppercase constant of `talkd.py` can be overridden, for example `{"PTT_MIN_HOLD": 0.25, "INPUT_DEVICE": "USB", "HISTORY": false}`. Defaults:

| Knob | Default | Meaning |
|---|---|---|
| `SR` | `16000` |  |
| `BLOCK` | `480` | 30 ms blocks |
| `PTT_KEYCODE` | `49` | space |
| `PTT_MIN_HOLD` | `0.30` | shorter than this = a normal space keypress |
| `PTT_MAX_HOLD` | `90.0` |  |
| `TYPING_GUARD_S` | `0.40` | a space within this long after another key = normal typing, not PTT |
| `STREAMING` | `True` | segment at pauses while talking; False = one whole-buffer pass |
| `SEG_SILENCE_S` | `0.7` | only a clear pause ends a phrase (short gaps garble on cut) |
| `SEG_MIN_SPEECH_S` | `1.6` | never cut a segment shorter than this (tiny clips hallucinate) |
| `SEG_MAX_S` | `12.0` | force-cut unbroken speech so latency stays bounded |
| `SEG_RMS` | `0.006` | absolute floor for "silence" (adaptive threshold can't go below this) |
| `SEG_NOISE_MULT` | `2.2` | a block is speech if louder than (rolling noise floor * this) |
| `SEG_NOISE_WIN` | `100` | blocks (~3s) used to estimate the noise floor adaptively |
| `INPUT_DEVICE` | `None` | substring of the input device name; None = system default input |
| `HISTORY` | `True` | {"HISTORY": false} keeps no transcript log at all |
| `PTT_FLAG` | `_p("talk.ptt")` | exists only while space is held; other mic apps can mute on it |
| `DEAD_RMS` | `1e-4` | a capture quieter than this delivered no signal at all |
| `DEAD_STRIKES` | `2` | consecutive dead captures before degrading |
| `HEAL_INTERVAL_S` | `20.0` | how often to retry the mic while degraded |
| `HEAL_BEFORE_RESTART` | `6` | failed heals before the daemon re-execs itself |
| `RESTART_WINDOW_S` | `1800` | self-restarts are rate-limited inside this window |
| `RESTART_MAX` | `3` | ...to this many, then we stop and ask for hands |
| `HEARTBEAT_S` | `10.0` |  |
| `MLX_REPO` | `_p("models/whisper-large-v3-turbo")` | `talk-speak talk warm` fetches it |
| `MAX_PROMPT_CHARS` | `850` | whisper truncates the prompt at ~224 tokens |
| `CONTINUATION_S` | `120.0` | two dictations further apart than this are not one thought |

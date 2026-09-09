---
name: speak
description: Toggle spoken replies. /speak (toggle) · /speak on · /speak off · /speak mute (mute THIS session only) · /speak unmute · /speak muted (list) · /speak again (re-read the last reply) · /speak stop · /speak rate 180 · /speak voice Samantha. When on, every finished reply is read aloud via macOS `say`.
---
Run exactly one shell command and report its one-line output, nothing else:

`~/bin/talk-speak speak $ARGUMENTS`

If $ARGUMENTS is empty, run `~/bin/talk-speak speak toggle`.

Scoped mutes (global speech stays ON, only the target goes quiet):
- `/speak mute` or `/speak unmute` with no id: supply THIS session's id yourself. It is the UUID path component before `/scratchpad` in your scratchpad directory (e.g. `.../<session-uuid>/scratchpad`). Run `~/bin/talk-speak speak mute <session-uuid>`.
- With an explicit id (`/speak mute <uuid>`), pass it through as-is.
- Headless runners (LaunchAgents calling `claude -p`) are silenced with `TALK_SPEAK=off` (or `CLAUDE_SPEAK=off`) in the environment of the call, not with mute.

Do not add commentary beyond the command's output line (the line itself will be spoken if speech is on).

How it works: the Claude Code `Stop` hook (`~/.talk-speak/bin/speak-last.sh`) extracts the last reply from the transcript and pipes it to the shared engine `~/.talk-speak/bin/speak-text.sh`, which owns the on/off flag, rate, voice, `last-reply.txt` and replay protection. Other harnesses feed the same engine through the adapters in the talk-speak repo (`speak/adapters/`), so `/speak on|off|rate|voice|again` govern all of them.

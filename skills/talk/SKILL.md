---
name: talk
description: Toggle voice input. /talk (toggle) · /talk on · /talk off · /talk status · /talk doctor · /talk log · /talk warm. Hold SPACE in ANY app to talk (the mic opens only while held); release → the transcript is typed wherever the keyboard focus is, without Enter. Space also cuts off any spoken reply.
---
Run exactly one shell command and report its one-line output, nothing else:

`~/bin/talk-speak talk $ARGUMENTS`

If $ARGUMENTS is empty, run `~/bin/talk-speak talk toggle`.

Notes:
- The daemon runs inside the signed `~/Applications/talk-speak.app` under launchd (KeepAlive). `off` writes `~/.talk-speak/talk.disabled`, which survives reboots; `on` clears it.
- Debug: `status` (state, backend, grants), `doctor` (9-point preflight, each failure names its fix), `log [N]`, `levels` (live meter), `typetest`, `simulate-failure`.
- Config: `~/.talk-speak/talk.cfg` (JSON; any uppercase constant of talkd.py). Vocabulary and `[corrections]` in `~/.talk-speak/talk.vocab`, reloaded on save.
- If keystrokes are refused everywhere ("not allowed to send keystrokes (1002)"), the user runs `tccutil reset PostEvent com.studentofai.talk-speak` themselves. Never run tccutil for them.

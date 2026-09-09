#!/bin/bash
# Claude Code `SessionEnd` hook: the session died, its mute dies with it.
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
SID=$(cat | /usr/bin/python3 -c 'import sys,json; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)
[ -n "$SID" ] || exit 0
rm -f "$STATE/speak.muted/$SID" "$STATE/speak.alive/$SID"
exit 0

#!/bin/bash
# Claude Code `SessionEnd` hook: the session died, its mute dies with it.
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
SID=$(cat | /usr/bin/python3 -c 'import sys,json; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)
case "$SID" in ''|.|..|*[!A-Za-z0-9._-]*) SID="";; esac   # a session id is a path component: letters, digits, dot, dash, underscore
[ -n "$SID" ] || exit 0
rm -f "$STATE/speak.muted/$SID" "$STATE/speak.alive/$SID"
exit 0

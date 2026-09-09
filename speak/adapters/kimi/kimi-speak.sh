#!/bin/sh
# Kimi Code `Stop` hook: speak the finished reply through the shared engine.
# Must always exit 0 and print nothing (exit 2 = block; stdout JSON = injected context).
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
PAYLOAD=$(cat)
MUT="$STATE/speak.muted"
SID=$(printf '%s' "$PAYLOAD" | /usr/bin/python3 -c '
import sys, json
try: print(json.load(sys.stdin).get("session_id", ""))
except Exception: pass' 2>/dev/null)
case "$SID" in ''|.|..|*[!A-Za-z0-9._-]*) SID="";; esac   # a session id is a path component: letters, digits, dot, dash, underscore
if [ -n "$SID" ]; then
  printf '%s' "$SID" > "$STATE/speak.session"
  mkdir -p "$STATE/speak.alive"; : > "$STATE/speak.alive/$SID"
  [ -f "$MUT/PENDING" ] && mv -f "$MUT/PENDING" "$MUT/$SID"
  [ -f "$MUT/UNMUTE-PENDING" ] && rm -f "$MUT/UNMUTE-PENDING" "$MUT/$SID"
  [ -f "$MUT/$SID" ] && exit 0
fi
printf '%s' "$PAYLOAD" | /usr/bin/python3 "$STATE/bin/kimi-last-reply.py" 2>/dev/null \
  | bash "$STATE/bin/speak-text.sh" >/dev/null 2>&1
exit 0

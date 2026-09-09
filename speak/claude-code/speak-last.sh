#!/bin/bash
# Claude Code `Stop` hook: speak the reply that just finished.
# Stdin is the hook JSON (session_id, transcript_path). The session-mute contract:
# stamp alive, claim a PENDING mute for this session, stay silent if muted.
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
INPUT=$(cat)
[ "$TALK_SPEAK" = "off" ] && exit 0
[ "$CLAUDE_SPEAK" = "off" ] && exit 0   # headless runners (`claude -p` from a LaunchAgent) stay silent
SID=$(printf '%s' "$INPUT" | /usr/bin/python3 -c 'import sys,json; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)
case "$SID" in ''|.|..|*[!A-Za-z0-9._-]*) SID="";; esac   # a session id is a path component: letters, digits, dot, dash, underscore
MUT="$STATE/speak.muted"
if [ -n "$SID" ]; then
  printf '%s' "$SID" > "$STATE/speak.session"
  mkdir -p "$STATE/speak.alive"; : > "$STATE/speak.alive/$SID"
  [ -f "$MUT/PENDING" ] && mv -f "$MUT/PENDING" "$MUT/$SID"
  [ -f "$MUT/UNMUTE-PENDING" ] && rm -f "$MUT/UNMUTE-PENDING" "$MUT/$SID"
  [ -f "$MUT/$SID" ] && exit 0   # per-session mute (`talk-speak speak mute`)
fi
[ -f "$STATE/speak.on" ] || exit 0
TRANSCRIPT=$(printf '%s' "$INPUT" | /usr/bin/python3 -c 'import sys,json; print(json.load(sys.stdin).get("transcript_path",""))' 2>/dev/null)
[ -f "$TRANSCRIPT" ] || exit 0
/usr/bin/python3 "$STATE/bin/last-reply.py" "$TRANSCRIPT" 2>/dev/null | bash "$STATE/bin/speak-text.sh"
exit 0

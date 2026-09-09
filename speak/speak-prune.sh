#!/bin/bash
# speak-prune.sh — a session mute dies when the session dies.
# Every speak hook stamps $STATE/speak.alive/<key> on each turn, so a live session keeps
# its heartbeat fresh. Precise death: the harness's session-end hook deletes the mute.
# Fallback: no heartbeat for 90 minutes = the session is gone.
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
A="$STATE/speak.alive"
M="$STATE/speak.muted"
mkdir -p "$A" "$M"
for f in "$M"/*; do
  [ -f "$f" ] || continue
  k=$(basename "$f")
  case "$k" in PENDING|UNMUTE-PENDING) continue;; esac
  if [ ! -f "$A/$k" ] || [ -z "$(find "$A/$k" -mmin -90 2>/dev/null)" ]; then
    rm -f "$f" "$A/$k"
  fi
done
find "$M" -maxdepth 1 -name 'PENDING' -mmin +60 -delete 2>/dev/null
find "$M" -maxdepth 1 -name 'UNMUTE-PENDING' -mmin +60 -delete 2>/dev/null
exit 0

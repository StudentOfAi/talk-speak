#!/bin/bash
# speak-text.sh — the shared speech engine every harness's "reply finished" hook feeds.
#   some-hook | speak-text.sh          reply text on stdin
#   speak-text.sh "reply text"         or as one argument
# Honours: $STATE/speak.on (global toggle); TALK_SPEAK=off or CLAUDE_SPEAK=off (headless runners);
#          $STATE/speak.rate, $STATE/speak.voice; $STATE/speak.env (optional overrides:
#          SPEAKING_FLAG, SAY_BIN). Never kills a `speak again` replay in progress.
# Writes $STATE/last-reply.txt so `talk-speak speak again` works from any harness, and
# $STATE/speak.pid while speaking so a newer reply can cut the older one off.
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
[ "$TALK_SPEAK" = "off" ] && exit 0
[ "$CLAUDE_SPEAK" = "off" ] && exit 0
# shellcheck disable=SC1091
[ -f "$STATE/speak.env" ] && . "$STATE/speak.env"
SPEAKING_FLAG="${SPEAKING_FLAG:-$STATE/speaking}"
SAY_BIN="${SAY_BIN:-say}"
bash "$STATE/bin/speak-prune.sh" 2>/dev/null
[ -f "$STATE/speak.on" ] || exit 0
if [ -n "$1" ]; then TEXT="$1"; else TEXT=$(cat); fi
[ -n "$(printf '%s' "$TEXT" | tr -d '[:space:]')" ] || exit 0
printf '%s\n' "$TEXT" > "$STATE/last-reply.txt"
RATE=$(cat "$STATE/speak.rate" 2>/dev/null || echo 195)
case "$RATE" in ''|*[!0-9]*) RATE=195;; esac         # digits only; anything else is the default
VOICE=$(cat "$STATE/speak.voice" 2>/dev/null)
# The background speaker reads these from its environment. Nothing read from a file is
# ever spliced into shell text: a quote in speak.voice is a quote, not code.
export STATE RATE VOICE SAY_BIN SPEAKING_FLAG
# shellcheck disable=SC2329   # invoked indirectly through `declare -f`
say_file() {
  # the flag exists while we speak: an always-on listener can ignore the assistant's own voice
  touch "$SPEAKING_FLAG"
  if [ -n "$VOICE" ]; then "$SAY_BIN" -v "$VOICE" -r "$RATE" -f "$STATE/last-reply.txt" &
  else "$SAY_BIN" -r "$RATE" -f "$STATE/last-reply.txt" & fi
  echo $! > "$STATE/speak.pid"
  wait $!
  rm -f "$SPEAKING_FLAG" "$STATE/speak.pid"
}
REPLAY="$STATE/speak.replay"
RP=$(cat "$REPLAY" 2>/dev/null); case "$RP" in ''|*[!0-9]*) RP=0;; esac; export RP
if [ "$RP" != 0 ] && kill -0 "$RP" 2>/dev/null; then
  [ "$TEXT" = "speaking last reply" ] && exit 0
  nohup bash -c "while kill -0 \"\$RP\" 2>/dev/null; do sleep 1; done; $(declare -f say_file); say_file" >/dev/null 2>&1 &
  exit 0
fi
rm -f "$REPLAY"
[ -f "$STATE/speak.pid" ] && kill "$(cat "$STATE/speak.pid")" 2>/dev/null   # a newer reply supersedes the older one
nohup bash -c "$(declare -f say_file); say_file" >/dev/null 2>&1 &
exit 0

#!/usr/bin/env bash
# Hermes `post_llm_call` shell hook: speak the finished reply through the shared engine.
# Session contract: PENDING / UNMUTE-PENDING resolve to this session id (falling back to
# hermes-<platform>); the mute then lives for this session only. Prints `{}` (no injected context).
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
payload=$(cat)
MUT="$STATE/speak.muted"
platform=$(printf '%s' "$payload" | jq -r '.extra.platform // .platform // "hermes"')
sid=$(printf '%s' "$payload" | jq -r '.session_id // .extra.session_id // empty')
KEY="${sid:-hermes-$platform}"
printf '%s' "$KEY" > "$STATE/speak.session"
mkdir -p "$STATE/speak.alive"; : > "$STATE/speak.alive/$KEY"
if [ -f "$MUT/PENDING" ]; then mv -f "$MUT/PENDING" "$MUT/$KEY"; fi
if [ -f "$MUT/UNMUTE-PENDING" ]; then rm -f "$MUT/UNMUTE-PENDING" "$MUT/$KEY"; fi
[ -f "$MUT/$KEY" ] && { printf '{}\n'; exit 0; }
printf '%s' "$payload" | jq -r '.extra.assistant_response // empty' \
  | perl -0777 -pe 's/```.*?```/ code block omitted. /gs; s/`([^`]*)`/$1/g; s/\[([^\]]+)\]\([^)]+\)/$1/g; s|https?://\S+|link|g; s/[#*_>~]+//g' \
  | bash "$STATE/bin/speak-text.sh"
printf '{}\n'

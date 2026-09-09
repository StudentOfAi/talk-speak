#!/usr/bin/env bash
# Hermes `on_session_end` hook: the session died, its mute dies with it.
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
payload=$(cat)
sid=$(printf '%s' "$payload" | jq -r '.session_id // .extra.session_id // empty')
[ -n "$sid" ] || { printf '{}\n'; exit 0; }
rm -f "$STATE/speak.muted/$sid" "$STATE/speak.alive/$sid"
printf '{}\n'

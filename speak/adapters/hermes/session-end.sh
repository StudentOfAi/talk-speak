#!/usr/bin/env bash
# Hermes `on_session_end` hook: the session died, its mute dies with it.
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
payload=$(cat)
sid=$(printf '%s' "$payload" | jq -r '.session_id // .extra.session_id // empty')
case "$sid" in ''|.|..|*[!A-Za-z0-9._-]*) sid="";; esac   # a session id is a path component: letters, digits, dot, dash, underscore
[ -n "$sid" ] || { printf '{}\n'; exit 0; }
rm -f "$STATE/speak.muted/$sid" "$STATE/speak.alive/$sid"
printf '{}\n'

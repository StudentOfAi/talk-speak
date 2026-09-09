#!/bin/bash
# install.sh — talk-speak for macOS on Apple Silicon: hold-space dictation + spoken replies.
#   ./install.sh                       install or upgrade (idempotent)
#   ./install.sh --dry-run             print every step, write nothing
#   ./install.sh --no-start            install without starting the daemon (verification runs)
#   ./install.sh --no-cpu-fallback     MLX only: skip openai-whisper (and torch); run `talk-speak talk warm` after
#   ./install.sh --identity NAME       signing identity to create/use (default "talk-speak Local Dev")
#   ./install.sh --uninstall [--purge] remove app, agent, hooks, skills, CLI; --purge also removes ~/.talk-speak and the identity
# No sudo. Never edits shell rc files. Never runs tccutil. Backs up any file it replaces.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="talk-speak"
LABEL="com.studentofai.$NAME"
STATE="${TALK_SPEAK_HOME:-$HOME/.talk-speak}"
# every target directory can be overridden (used by the sandboxed verification run)
BIN="${TALK_SPEAK_BIN:-$HOME/bin}"
APP="${TALK_SPEAK_APP_DIR:-$HOME/Applications}/$NAME.app"
LA="${TALK_SPEAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"; PLIST="$LA/$LABEL.plist"
CLAUDE="${TALK_SPEAK_CLAUDE_DIR:-$HOME/.claude}"; SETTINGS="$CLAUDE/settings.json"
# shellcheck source=lib/identity.sh
source "$SRC/lib/identity.sh"
DRY=0; UNINSTALL=0; PURGE=0; NOSTART=0; CPU=1
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1;;
    --uninstall) UNINSTALL=1;;
    --purge) PURGE=1;;
    --no-start) NOSTART=1;;
    --no-cpu-fallback) CPU=0;;
    --identity) IDENTITY="$2"; shift;;
    -h|--help) sed -n '2,9p' "$0"; exit 0;;
    *) echo "unknown option: $1"; exit 2;;
  esac
  shift
done
step() { printf '\n[%s/10] %s\n' "$1" "$2"; }
run() { if [ "$DRY" = 1 ]; then echo "  would: $*"; else "$@"; fi; }
install_file() {   # src dst [mode]: never clobber a local edit without keeping a copy
  if [ -f "$2" ] && ! cmp -s "$1" "$2"; then
    run cp "$2" "$2.replaced-$(date +%Y%m%d_%H%M%S)"; echo "  backed up $2"
  fi
  run cp "$1" "$2"
  [ -n "${3:-}" ] && run chmod "$3" "$2"
  return 0
}
render() {   # template dest: fill __APP__ __STATE__ __LABEL__ __NAME__
  if [ "$DRY" = 1 ]; then echo "  would: render $1 -> $2"; return 0; fi
  sed -e "s#__APP__#$APP#g" -e "s#__STATE__#$STATE#g" -e "s#__LABEL__#$LABEL#g" -e "s#__NAME__#$NAME#g" "$1" > "$2"
}

# ---------------------------------------------------------------- uninstall
if [ "$UNINSTALL" = 1 ]; then
  echo "Uninstalling $NAME$( [ "$DRY" = 1 ] && echo ' (dry run)')..."
  [ -d "$STATE" ] && run touch "$STATE/talk.disabled"   # nothing to disable if the state dir never existed
  run launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  run rm -f "$PLIST"
  [ -d "$APP" ] && run rm -rf "$APP"
  [ -f "$SETTINGS" ] && run python3 "$SRC/lib/hooks.py" remove "$SETTINGS" "$STATE"
  for s in talk speak; do   # only skills we installed (they name talk-speak)
    if [ -f "$CLAUDE/skills/$s/SKILL.md" ] && /usr/bin/grep -q "talk-speak" "$CLAUDE/skills/$s/SKILL.md"; then run rm -rf "$CLAUDE/skills/$s"; fi
  done
  run rm -f "$BIN/$NAME"
  if [ "$PURGE" = 1 ]; then
    case "$STATE" in ""|/|"$HOME"|"$HOME/") echo "refusing to remove '$STATE' (TALK_SPEAK_HOME must be a directory of its own)"; exit 1;; esac
    run rm -rf "$STATE"
    run identity_delete
    echo "Removed everything, including $STATE and the '$IDENTITY' signing identity."
  else
    echo "Removed. Your state (vocab, config, logs, venv, models) was LEFT in $STATE; --purge removes it."
  fi
  exit 0
fi

echo "$NAME $(tr -d '[:space:]' < "$SRC/VERSION")  ->  $STATE$( [ "$DRY" = 1 ] && echo '   (dry run: nothing will be written)')"

# ---------------------------------------------------------------- 1 preflight
step 1 "preflight"
fail=0
chk() { if "$2"; then echo "  ok:   $1"; else echo "  FAIL: $1 -> $3"; fail=1; fi; }
is_arm() { [ "$(uname -m)" = "arm64" ]; }
macos14() { [ "$(sw_vers -productVersion | cut -d. -f1)" -ge 14 ]; }
has_brew() { command -v brew >/dev/null; }
has_py() { PY3="$(brew --prefix 2>/dev/null)/bin/python3"; [ -x "$PY3" ] && "$PY3" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; }
has_swift() { command -v swiftc >/dev/null && xcode-select -p >/dev/null 2>&1; }
chk "Apple Silicon" is_arm "talk-speak needs an M-series Mac (MLX)"
chk "macOS 14 or newer" macos14 "update macOS"
chk "Homebrew" has_brew "install from https://brew.sh"
chk "Homebrew python3 >= 3.11" has_py "brew install python"
chk "Swift compiler (Command Line Tools)" has_swift "xcode-select --install"
[ "$fail" = 0 ] || { echo "fix the FAIL lines above, then run install.sh again"; exit 1; }

# ---------------------------------------------------------------- 2 venv
step 2 "python venv with pinned deps -> $STATE/venv"
run mkdir -p "$STATE/bin" "$STATE/models"
[ -x "$STATE/venv/bin/python" ] || run "$PY3" -m venv "$STATE/venv"
REQ="$SRC/requirements.txt"
if [ "$CPU" = 0 ]; then REQ="$(mktemp)"; /usr/bin/grep -v '^openai-whisper' "$SRC/requirements.txt" > "$REQ"; fi
t0=$SECONDS
run "$STATE/venv/bin/pip" install -q --disable-pip-version-check -r "$REQ"
[ "$DRY" = 1 ] || echo "  deps installed in $((SECONDS - t0)) s ($(du -sh "$STATE/venv" | cut -f1))"

# ---------------------------------------------------------------- 3 identity
step 3 "code-signing identity '$IDENTITY' (self-signed, login keychain, no clicks)"
if identity_exists; then echo "  ok: already present"; else run identity_create; fi

# ---------------------------------------------------------------- 4 app
step 4 "build + sign $APP"
if [ "$DRY" = 1 ]; then echo "  would: $SRC/talk/app/build.sh --identity '$IDENTITY' --out $SRC/build; would: copy to $APP"
else
  "$SRC/talk/app/build.sh" --identity "$IDENTITY" --out "$SRC/build" | /usr/bin/grep -E 'built|designated'
  mkdir -p "$(dirname "$APP")"
  rm -rf "$APP"; cp -R "$SRC/build/$NAME.app" "$APP"
fi

# ---------------------------------------------------------------- 5 launchd agent
step 5 "LaunchAgent $PLIST"
run mkdir -p "$LA"
render "$SRC/talk/launchagent.plist.tmpl" "$PLIST"

# ---------------------------------------------------------------- 6 daemon + CLI
step 6 "daemon -> $STATE/talkd.py, CLI -> $BIN/$NAME"
run mkdir -p "$BIN"
install_file "$SRC/talk/talkd.py" "$STATE/talkd.py" 755
install_file "$SRC/bin/$NAME" "$BIN/$NAME" 755
install_file "$SRC/VERSION" "$STATE/VERSION"
if [ "$DRY" = 1 ]; then echo "  would: write $STATE/repo = $SRC"; else printf '%s\n' "$SRC" > "$STATE/repo"; fi
case ":$PATH:" in *":$BIN:"*) ;; *) echo "  NOTE: $BIN is not on your PATH. Add to your shell rc:  export PATH=\"\$HOME/bin:\$PATH\"";; esac

# ---------------------------------------------------------------- 7 speak engine, hooks, skills
step 7 "speak engine + Claude Code hooks -> $STATE/bin, settings.json, skills"
for f in speak/speak-text.sh speak/speak-prune.sh speak/claude-code/speak-last.sh speak/claude-code/speak-session-end.sh \
         speak/claude-code/last-reply.py speak/adapters/kimi/kimi-last-reply.py; do
  install_file "$SRC/$f" "$STATE/bin/$(basename "$f")" 755
done
run mkdir -p "$CLAUDE/skills/talk" "$CLAUDE/skills/speak"
install_file "$SRC/skills/talk/SKILL.md" "$CLAUDE/skills/talk/SKILL.md"
install_file "$SRC/skills/speak/SKILL.md" "$CLAUDE/skills/speak/SKILL.md"
run python3 "$SRC/lib/hooks.py" add "$SETTINGS" "$STATE"

# ---------------------------------------------------------------- 8 seeds
step 8 "seed config (only files that do not exist yet)"
[ -f "$STATE/talk.cfg" ]   || install_file "$SRC/talk/talk.cfg.example" "$STATE/talk.cfg"
[ -f "$STATE/talk.vocab" ] || install_file "$SRC/talk/talk.vocab.example" "$STATE/talk.vocab"
[ -f "$STATE/speak.on" ]   || run touch "$STATE/speak.on"     # spoken replies are on by default; `talk-speak speak off`

# ---------------------------------------------------------------- 9 start
step 9 "start the daemon"
if [ "$DRY" = 1 ] || [ "$NOSTART" = 1 ]; then echo "  skipped ($( [ "$DRY" = 1 ] && echo dry-run || echo --no-start )); later: $NAME talk on"
else "$BIN/$NAME" talk on || true; fi

# ---------------------------------------------------------------- 10 permissions + doctor
step 10 "permissions (one-time clicks) + doctor"
cat <<TABLE
  macOS asks three times, all for "$NAME" (the signed app launchd runs). Click Allow on each:
    1. Microphone         records only while you hold the spacebar
    2. Accessibility      sees the spacebar, types the transcript, reads the focused window title
    3. Input Monitoring   the session-wide key tap (needs a restart after granting)
  Missed a prompt? System Settings > Privacy & Security > (that pane) > enable "$NAME", then:  $NAME talk restart
  Deep links:  open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone'
               open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
               open 'x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent'
  A "Background Items Added" notice is launchd registering the agent: leave it enabled.
TABLE
[ "$DRY" = 1 ] || "$BIN/$NAME" talk doctor || true
cat <<NEXT

Next:
  $NAME talk warm        fetch the MLX whisper weights (1.6 GB, resumable); until then the CPU model is used
  hold SPACE anywhere, talk, release: the text lands in the focused field
  $NAME speak status     spoken replies are ON; mute one session with:  $NAME speak mute
NEXT

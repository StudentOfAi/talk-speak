#!/usr/bin/env python3
"""lib/hooks.py — add or remove talk-speak's Claude Code hooks in settings.json, idempotently.

    python3 lib/hooks.py add    <settings.json> <state-dir>
    python3 lib/hooks.py remove <settings.json> <state-dir>

Ours are the entries whose command mentions "<state-dir>/bin/". Everything else in the
file is left as it was (re-serialised with indent=2). A timestamped backup is written
before any change. Exit 0 = done or nothing to do, 1 = invalid JSON (file untouched),
2 = usage."""
import json
import os
import shutil
import sys
import time


def our_entries(state):
    return {
        "Stop": {"hooks": [{"type": "command", "command": "bash %s/bin/speak-last.sh" % state, "timeout": 10}]},
        "SessionEnd": {"hooks": [{"type": "command", "command": "bash %s/bin/speak-session-end.sh" % state, "timeout": 5}]},
    }


def is_ours(entry, marker):
    return isinstance(entry, dict) and any(
        marker in str(h.get("command", "")) for h in entry.get("hooks", []) if isinstance(h, dict))


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save(path, data):
    if os.path.exists(path):
        shutil.copy2(path, "%s.bak-%s" % (path, time.strftime("%Y%m%d_%H%M%S")))
    else:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def add(data, state):
    marker = "%s/bin/" % state
    hooks = data.setdefault("hooks", {})
    changed = False
    for event, entry in our_entries(state).items():
        lst = hooks.setdefault(event, [])
        if not any(is_ours(e, marker) for e in lst):
            lst.append(entry)
            changed = True
    return changed


def remove(data, state):
    marker = "%s/bin/" % state
    hooks = data.get("hooks") or {}
    changed = False
    for event in list(hooks):
        kept = [e for e in hooks[event] if not is_ours(e, marker)]
        if len(kept) != len(hooks[event]):
            changed = True
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    return changed


def main(argv):
    if len(argv) != 4 or argv[1] not in ("add", "remove"):
        print(__doc__)
        return 2
    op, path, state = argv[1], argv[2], argv[3].rstrip("/")
    try:
        data = load(path)
    except ValueError as e:
        print("hooks: %s is not valid JSON (%s); nothing written" % (path, e))
        return 1
    changed = add(data, state) if op == "add" else remove(data, state)
    if changed:
        save(path, data)
        print("hooks: %s done in %s" % (op, path))
    else:
        print("hooks: nothing to %s in %s" % (op, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

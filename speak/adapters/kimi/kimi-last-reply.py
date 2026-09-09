#!/usr/bin/python3
"""Print the last assistant reply of a Kimi Code session.

Reads the Stop-hook JSON payload on stdin (needs session_id), resolves the
session directory via ~/.kimi-code/session_index.jsonl and returns the text
parts of the final step in agents/main/wire.jsonl. Prints nothing on any error.
"""
import json
import os
import sys
import time

HOME = os.path.expanduser("~/.kimi-code")


def session_dir(session_id: str) -> str:
    found = ""
    with open(os.path.join(HOME, "session_index.jsonl")) as index:
        for line in index:
            record = json.loads(line)
            if record.get("sessionId") == session_id:
                found = record.get("sessionDir", "")
    return found


def last_reply(wire_path: str) -> str:
    parts = []
    with open(wire_path) as wire:
        for line in wire:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "context.append_loop_event":
                continue
            event = record.get("event") or {}
            if event.get("type") == "step.begin":
                parts = []
            elif event.get("type") == "content.part":
                part = event.get("part") or {}
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
    return "".join(parts).strip()


def main() -> None:
    try:
        session_id = json.load(sys.stdin)["session_id"]
        wire = os.path.join(session_dir(session_id), "agents", "main", "wire.jsonl")
        if not os.path.isfile(wire):
            return
        time.sleep(0.15)  # the final text record is fsynced just before Stop fires
        print(last_reply(wire))
    except Exception:
        return


if __name__ == "__main__":
    main()

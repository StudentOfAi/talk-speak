# Hermes adapter

Copy `speak.sh` and `session-end.sh` to `~/.hermes/agent-hooks/`, `chmod +x` them, and add to `~/.hermes/config.yaml`:

```yaml
hooks:
  post_llm_call:
    - command: ~/.hermes/agent-hooks/speak.sh
      timeout: 10
  on_session_end:
    - command: ~/.hermes/agent-hooks/session-end.sh
      timeout: 5
```

Hermes asks once to approve each shell hook (it records the approval in `~/.hermes/shell-hooks-allowlist.json`, keyed on the script's mtime, so re-approve after editing). Needs `jq` and `perl` on PATH. Every platform (cli, tui, gateway, desktop, messaging, cron) speaks; mute per session with `talk-speak speak mute`.

Verified 2026-09-09 on the Hermes build installed on the author's Mac.

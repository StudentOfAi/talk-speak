# Kimi Code adapter

Copy `kimi-speak.sh` to `~/bin/` (`chmod +x`) and `kimi-last-reply.py` to `~/.talk-speak/bin/`, then add to `~/.kimi-code/config.toml`:

```toml
[[hooks]]
event = "Stop"
command = "~/bin/kimi-speak.sh"
timeout = 10
```

`kimi-last-reply.py` resolves the session id through `~/.kimi-code/session_index.jsonl` and reads the last step's text parts from `agents/main/wire.jsonl`; the 150 ms sleep is deliberate (the final record is flushed just before `Stop` fires).

Verified 2026-09-09 on the Kimi Code build installed on the author's Mac.

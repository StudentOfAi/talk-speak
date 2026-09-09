# dst (cordis) adapter

Copy `speak.mjs` next to your profile's `cordis.patch.yml` (for example `~/.dsh/profiles/dsh-tui/`) and mount it:

```yaml
- insert:
    - id: speak-reply
      name: ./speak.mjs
```

It listens on the `session/event` bus, keeps the last `assistant/message` text of the turn and pipes it to the engine at `turn/end` when the reason is `completed`. Subagents (delegation depth > 0) stay silent.

Verified 2026-09-09 on the dst build installed on the author's Mac.

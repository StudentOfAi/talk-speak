# Claw adapter

Copy `reply` to `~/.claw/hooks/reply` and `chmod +x` it. Claw runs that path (or `$CLAW_REPLY_HOOK`) after every interactive reply with the final text in `$CLAW_REPLY`; one-shot `-p` runs stay silent by design. This relies on the `run_reply_hook` patch in the author's Claw build; upstream Claw may need the same three-line patch.

Verified 2026-09-09 on the author's patched Claw build.

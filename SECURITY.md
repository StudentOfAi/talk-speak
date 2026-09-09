# Security

talk-speak runs a key tap and posts keystrokes, so it is worth a careful look. Everything runs locally: audio never leaves the machine, transcripts are only written to `~/.talk-speak/talk.history.jsonl` (off with `{"HISTORY": false}`), and the only network call is the optional model download from Hugging Face in `talk-speak talk warm`.

Report a vulnerability privately through GitHub's "Report a vulnerability" on this repository rather than a public issue.

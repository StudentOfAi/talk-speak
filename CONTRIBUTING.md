# Contributing

- Run the tests before a pull request: `~/.talk-speak/venv/bin/python tests/test_talk.py` and `python3 -m unittest tests.test_speak tests.test_hooks tests.test_cli`. CI runs them on macOS plus `shellcheck` and a compile of the stub.
- The rule every change is measured against: dictation failing must never cost the user their spacebar. A change to `ptt_decision`, the healer or the key tap needs a test in `tests/test_talk.py`.
- Keep it small. The stub is ~40 lines on purpose; mechanics go in the daemon, names go in `talk.vocab`.
- No hardcoded home paths; everything derives from `TALK_SPEAK_HOME`.
- Conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `ci:`.

# Changelog

## 3.0.2 (2026-09-09): security pass

- The speak engine and `speak again` no longer splice the voice and rate files into shell text; the values reach `say` as arguments. A quote in `speak.voice` was shell before. `speak rate` takes digits only and `speak voice` a plain voice name.
- Every hook accepts a session id only as a plain path component (letters, digits, dot, dash, underscore).
- `talk-speak talk warm` verifies the model files against pinned SHA-256 hashes and moves a mismatch aside as `*.bad`, so the CPU fallback takes over instead of a bad file loading.
- `--uninstall --purge` refuses to remove `/` or the home directory.
- CI actions pinned to commit SHAs; CodeQL (Python) runs on every push; a `tempfile.mktemp` in a test replaced with `mkstemp`.

## 3.0.1 (2026-09-09): validation pass

- The launchd agent passes `TALK_SPEAK_HOME` to the stub. Before, an install with a custom state dir never started: the stub looked in `~/.talk-speak`, found no venv and exited.
- `install.sh --uninstall` no longer fails when the state dir does not exist (a second uninstall, or one after `--purge`).
- The PRD describes the repo as shipped; personal names are out of the docs.

## 3.0.0 (2026-09-09): public release as talk-speak

- One repo, one state dir (`~/.talk-speak`), one CLI (`talk-speak talk ...`, `talk-speak speak ...`).
- The signed stub has source (`talk/app/Stub.swift`) and a build script; the installer creates the signing identity by script.
- Own Python venv with pinned deps; a Homebrew upgrade can no longer break dictation.
- Name corrections live in `talk.vocab [corrections]`; the code keeps mechanics only.
- `INPUT_DEVICE` and `HISTORY` knobs; `talk-speak talk warm` fetches the MLX weights.
- The daemon reports its Microphone, Accessibility and Input Monitoring grants and raises the prompts on first start; doctor reads that report.
- Speak engine, Claude Code hooks and the Hermes, Kimi Code, Claw and dst adapters ship in the repo; hooks are merged into `settings.json` idempotently.
- A newer spoken reply cuts off the engine's own previous one, not every `say` on the machine.
- 81 daemon checks plus 35 unit tests; CI on macOS.

## 2.3.0 (2026-09-06)

- A flag file exists while the spacebar is held so other mic apps can mute.

## 2.1.0 (2026-09-02)

- No trailing space on transcripts; the separator moves to the front of a continuation.
- The daemon's own keystrokes no longer arm the typing guard.

## 2.0.0 (2026-09-02)

- Fail-open spacebar: space is intercepted only while audio is proven healthy.
- Self-healing: degrade, re-probe, re-init CoreAudio, rate-limited self-restart, spoken hand-off.
- `doctor`, `status`, `health`, `simulate-failure`, `selfcheck`; first export to a repo.

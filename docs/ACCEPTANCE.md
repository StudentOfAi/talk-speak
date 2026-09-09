# Acceptance

Finished means a person with only the README, on an Apple Silicon Mac they have not set up before, can do all of this. Record every run: date, machine, macOS, times.

| # | Check | How |
|---|---|---|
| 1 | Clone, `./install.sh`, the one-time clicks | ten steps print, three prompts appear on first start |
| 2 | `talk-speak talk doctor` | `9/9 passed` |
| 3 | Hold space in Notes, say one sentence, release | the sentence appears, no trailing space; a second dictation is separated by one space |
| 4 | Tap space in a YouTube tab | the video pauses (tap passes through) |
| 5 | Claude Code: `/speak on`, a reply | spoken; `/speak mute` silences that session only, another session still speaks; space-down cuts speech |
| 6 | `./install.sh --uninstall` | no app, no agent, no hooks in `settings.json`, no CLI; `~/.talk-speak` kept unless `--purge` |

Target: clone to first dictation in 15 minutes or less, excluding the model download.

## Runs

### 2026-09-09, author's Mac mini M4, macOS 26.1: sandboxed install (not a fresh machine)

Run with every target directory redirected into a sandbox so the author's live install stayed untouched.

| Item | Result |
|---|---|
| `./install.sh --no-start` wall time | 38 s |
| venv with pinned deps, fresh download | 16 to 32 s, 1.3 GB |
| app signature | `identifier "com.studentofai.talk-speak" and certificate leaf = H"..."` |
| hooks merged into a fresh `settings.json` | Stop + SessionEnd, nothing else touched |
| daemon checks inside the new venv (`talk-speak talk selfcheck`) | 81/81 |
| doctor before the daemon runs | 4/9 (deps, device, paths, cfg PASS; weights, capture, permissions, agent, heartbeat FAIL as designed) |
| `--uninstall --purge` | app, agent, CLI, hooks, skills, state and identity all gone |

Not verified in this run (needs a fresh Mac and a person clicking): the three first-start prompts, `9/9`, live dictation, spoken replies through the installed hooks, checks 3 to 5 above. The stub's spawn, environment, SIGTERM forwarding, disabled-flag and missing-venv paths were verified separately with a fake daemon.

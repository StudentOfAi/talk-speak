# Troubleshooting

Start with `talk-speak talk doctor`. One row per line of its output, then the symptoms people actually report.

| Doctor line | FAIL means | Fix |
|---|---|---|
| python deps | the venv is missing a package | `~/.talk-speak/venv/bin/pip install -r requirements.txt` from the clone |
| mlx weights | the 1.6 GB MLX model is not there yet; CPU `small` is used meanwhile | `talk-speak talk warm` (resumable) |
| input device | macOS lists no input device | plug in a mic, or set `"INPUT_DEVICE": "name substring"` in `talk.cfg` |
| mic capture | the daemon's last probe delivered no signal | `talk-speak talk restart`; still DEAD: replug the mic, or `sudo killall coreaudiod` |
| permissions | the daemon reports a missing grant | grant talk-speak in the named pane, then `talk-speak talk restart` ([PERMISSIONS.md](PERMISSIONS.md)) |
| paths writable | `~/.talk-speak` is not writable | fix ownership or `TALK_SPEAK_HOME` |
| talk.cfg | invalid JSON | fix or delete `~/.talk-speak/talk.cfg` |
| launchd agent | the agent is not loaded | `talk-speak talk on` |
| daemon heartbeat | no fresh `talk.health.json` | `talk-speak talk on`, then `talk-speak talk log 50` |

## Symptoms

- **Holding space types nothing and eats the space.** The mic is dead and the daemon should have degraded. `talk-speak talk status` shows `audio: DEAD`; `talk-speak talk off` restores the spacebar instantly; then restart, replug, or `sudo killall coreaudiod`. Triage order: `talk-speak talk restart` first (a wedged CoreAudio client inside the daemon), replug only if a fresh process also fails.
- **Spaces vanish while typing fast.** The typing guard treats a space within `TYPING_GUARD_S` (0.4 s) of another key as typing. Raise it in `talk.cfg` if you type in bursts.
- **⌥Space or ⌘Space stopped working.** They never should: any modifier passes through. Check `talk-speak talk log` for the chord; a third-party tap ahead of ours can still eat it.
- **The transcript arrived without spaces** ("workinghereornot"). Another event tap with high latency (Siri registers two) delayed our own key events. The daemon posts tagged Unicode events for exactly this reason; report it with `talk-speak talk log 50`.
- **Basso, nothing typed.** The focused field refused posted keystrokes (a secure password field) or the transcript was empty (a hallucination filtered out).
- **"not allowed to send keystrokes (1002)" everywhere.** A cached denial. You run `tccutil reset PostEvent com.studentofai.talk-speak`, then `talk-speak talk restart`.
- **Input Monitoring is granted but doctor still says denied.** Restart the daemon; the grant applies to new processes.
- **Replies speak into silence.** `talk-speak speak status` reports output muted or at zero and prints the `osascript` fix.
- **A session keeps speaking after `speak mute`.** The mute is claimed by the next hook that fires; if two harnesses reply at once the wrong one can claim `PENDING`. Mute by id: `talk-speak speak muted`, then `talk-speak speak mute <id>`.
- **Nothing starts after a reboot.** `~/.talk-speak/talk.disabled` exists (left by `talk off`); `talk-speak talk on` clears it.
- **It stopped after a Homebrew upgrade.** It should not any more: the deps live in `~/.talk-speak/venv`, not in Homebrew's whisper. Run doctor.
- **Every dictation is empty and `talk.out` shows `PaMacCore (AUHAL) ... Error`.** The daemon's CoreAudio client wedged; `talk-speak talk restart` clears it.

## Where to look

`~/.talk-speak/talk.log` (every hold, transition and error, with the app and window that received the text), `talk.err` and `talk.out` (the process's stderr/stdout), `talk.health.json` (state, audio, backend, grants, heals, restarts), `talk.history.jsonl` (transcripts with timings). `talk-speak talk levels` is a live meter; `talk-speak talk typetest` fires the keystroke probe; `talk-speak talk simulate-failure` proves the spacebar comes back when the mic dies.

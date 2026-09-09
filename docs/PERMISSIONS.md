# Permissions: the one-time clicks

Everything is granted to **`talk-speak.app`** (`com.studentofai.talk-speak`), the small signed stub launchd runs. It spawns the Python daemon as a child, and macOS attributes the child to its responsible parent, so the app's grants cover the daemon. Nothing is granted to Terminal.

The grants are keyed to (bundle id + signing certificate). The installer creates a self-signed identity named `talk-speak Local Dev` once and signs every rebuild with it, so upgrades keep the grants. Ad-hoc signing would change identity on every build and re-prompt each time.

| # | Grant | Who | Why | When macOS asks | Verify |
|---|---|---|---|---|---|
| 1 | Microphone | talk-speak | capture while space is held | first daemon start | Privacy & Security > Microphone |
| 2 | Accessibility | talk-speak | event tap on the space key, posting keystrokes, reading the focused window title | first daemon start | Privacy & Security > Accessibility |
| 3 | Input Monitoring | talk-speak | session event tap on current macOS | first daemon start | Privacy & Security > Input Monitoring |
| 4 | Background item | the LaunchAgent | launchd starts the stub at login and keeps it alive | `launchctl bootstrap` triggers a "Background Items Added" notice; leave it on | Login Items & Extensions |
| 5 | Automation to System Events | Terminal | only the `typetest` probe uses `osascript` | only if you run `talk-speak talk typetest` | Privacy & Security > Automation |
| 6 | Keychain: use the signing key | `codesign` | first signature with the new identity may ask to allow keychain access | first `build.sh` | Keychain Access |

Normal operation needs rows 1 to 4: three privacy toggles plus one acknowledgement. Rows 5 and 6 are conditional. Nothing needs `sudo`.

The daemon raises prompts 1 to 3 itself on its first start. Input Monitoring takes effect after the process restarts: `talk-speak talk restart`.

Deep links to the panes:

```bash
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone'
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent'
```

`talk-speak talk doctor` reads the daemon's own report of the three grants from `~/.talk-speak/talk.health.json` (a Terminal process asking macOS would get Terminal's answer, not the app's).

## Recovery

- Keystrokes refused everywhere ("not allowed to send keystrokes (1002)"): a denial got cached. Run `tccutil reset PostEvent com.studentofai.talk-speak` yourself, then `talk-speak talk restart` and grant again. The installer never runs `tccutil`.
- Granted Input Monitoring but the tap is still denied: restart the daemon. macOS applies that grant to new processes only.
- Renamed or re-signed the app with a different identity: all three grants must be redone once. Keep the identity.

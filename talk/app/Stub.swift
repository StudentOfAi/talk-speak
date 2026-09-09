// talk-speak stub: the process launchd runs. It owns the Microphone, Accessibility
// and Input Monitoring grants (macOS keys them to this bundle's signature) and
// spawns the Python daemon as a child, so the grants cover the daemon too.
// ~40 lines on purpose: everything else lives in talkd.py.
import Foundation

let env = ProcessInfo.processInfo.environment
let home = env["HOME"] ?? FileManager.default.homeDirectoryForCurrentUser.path
let state = env["TALK_SPEAK_HOME"] ?? "\(home)/.talk-speak"
let fm = FileManager.default

func quit(_ msg: String) -> Never {
    FileHandle.standardError.write("talk-speak: \(msg)\n".data(using: .utf8)!)
    exit(0)   // exit 0 on purpose: KeepAlive(SuccessfulExit=false) must not spin on a config error
}

if fm.fileExists(atPath: "\(state)/talk.disabled") { exit(0) }   // `talk off` wins over KeepAlive

let python = "\(state)/venv/bin/python"
let daemon = "\(state)/talkd.py"
for p in [python, daemon] where !fm.fileExists(atPath: p) { quit("missing \(p) (run install.sh)") }

let child = Process()
child.executableURL = URL(fileURLWithPath: python)
child.arguments = [daemon]
var childEnv = env
childEnv["TALK_SPEAK_HOME"] = state
child.environment = childEnv
child.standardOutput = FileHandle.standardOutput   // launchd routes these to talk.out / talk.err
child.standardError = FileHandle.standardError

let signals = DispatchQueue(label: "talk-speak.signals")
var sources: [DispatchSourceSignal] = []
for sig in [SIGTERM, SIGINT, SIGHUP] {
    signal(sig, SIG_IGN)
    let s = DispatchSource.makeSignalSource(signal: sig, queue: signals)
    s.setEventHandler { if child.isRunning { child.terminate() } }
    s.resume()
    sources.append(s)
}
child.terminationHandler = { p in exit(p.terminationStatus) }
do { try child.run() } catch { quit("cannot spawn \(python): \(error)") }
dispatchMain()

"""talk-speak CLI: speak state machine and talk status, in a sandbox state dir.
Deliberately does not exercise off/stop/toggle: they `pkill -x say` for real.
Run: python3 -m unittest tests.test_cli"""
import os, stat, subprocess, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "talk-speak")


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="talk-speak-cli.")
        fake = os.path.join(self.state, "fakebin"); os.makedirs(fake)
        self.log = os.path.join(self.state, "say.log")
        with open(os.path.join(fake, "say"), "w") as f:
            f.write('#!/bin/bash\necho "$@" >> "$FAKE_SAY_LOG"\n')
        os.chmod(os.path.join(fake, "say"), stat.S_IRWXU)
        self.env = {**os.environ, "TALK_SPEAK_HOME": self.state, "FAKE_SAY_LOG": self.log,
                    "PATH": fake + ":" + os.environ["PATH"]}

    def run_cli(self, *args):
        r = subprocess.run([CLI, *args], env=self.env, capture_output=True, text=True)
        return r.returncode, r.stdout.strip()

    def path(self, *p):
        return os.path.join(self.state, *p)

    def wait_log(self, seconds=2.0):
        end = time.time() + seconds
        while time.time() < end and not os.path.exists(self.log):
            time.sleep(0.05)
        return open(self.log).read() if os.path.exists(self.log) else ""


class Speak(Sandbox):
    def test_on_creates_flag(self):
        rc, out = self.run_cli("speak", "on")
        self.assertEqual((rc, out), (0, "speak: ON")); self.assertTrue(os.path.exists(self.path("speak.on")))

    def test_rate_and_voice_files(self):
        self.run_cli("speak", "rate", "150"); self.run_cli("speak", "voice", "Samantha")
        self.assertEqual(open(self.path("speak.rate")).read().strip(), "150")
        self.assertEqual(open(self.path("speak.voice")).read().strip(), "Samantha")
        self.run_cli("speak", "voice"); self.assertFalse(os.path.exists(self.path("speak.voice")))

    def test_status_reports_rate_and_voice(self):
        self.run_cli("speak", "on"); self.run_cli("speak", "rate", "150"); self.run_cli("speak", "voice", "Samantha")
        rc, out = self.run_cli("speak", "status")
        self.assertEqual(rc, 0); self.assertIn("speak: ON (rate 150, voice Samantha)", out)

    def test_status_off(self):
        rc, out = self.run_cli("speak", "status"); self.assertIn("speak: OFF", out)

    def test_mute_without_id_queues_pending_and_says_so(self):
        rc, out = self.run_cli("speak", "mute")
        self.assertEqual(rc, 0); self.assertIn("muting this session", out)
        self.assertTrue(os.path.exists(self.path("speak.muted", "PENDING")))
        self.assertIn("Muted", self.wait_log())

    def test_mute_with_id_then_list_then_unmute(self):
        self.run_cli("speak", "mute", "abc123")
        self.assertTrue(os.path.exists(self.path("speak.muted", "abc123")))
        rc, out = self.run_cli("speak", "muted"); self.assertIn("muted: abc123", out)
        self.run_cli("speak", "unmute", "abc123")
        self.assertFalse(os.path.exists(self.path("speak.muted", "abc123")))
        rc, out = self.run_cli("speak", "muted"); self.assertIn("no muted sessions", out)

    def test_unmute_all_clears_everything(self):
        self.run_cli("speak", "mute", "a"); self.run_cli("speak", "mute", "b"); self.run_cli("speak", "unmute", "all")
        self.assertEqual(os.listdir(self.path("speak.muted")), [])

    def test_unmute_without_id_queues_unmute_pending(self):
        self.run_cli("speak", "mute"); self.run_cli("speak", "unmute")
        self.assertFalse(os.path.exists(self.path("speak.muted", "PENDING")))
        self.assertTrue(os.path.exists(self.path("speak.muted", "UNMUTE-PENDING")))

    def test_again_replays_last_reply(self):
        with open(self.path("last-reply.txt"), "w") as f:
            f.write("previous reply\n")
        rc, out = self.run_cli("speak", "again")
        self.assertEqual((rc, out), (0, "speaking last reply"))
        self.assertIn("last-reply.replay.txt", self.wait_log())

    def test_unknown_subcommand_is_usage(self):
        rc, out = self.run_cli("speak", "bogus"); self.assertEqual(rc, 2); self.assertIn("usage", out)


class Talk(Sandbox):
    def test_status_off_without_pidfile(self):
        rc, out = self.run_cli("talk", "status"); self.assertEqual((rc, out), (0, "talk: OFF"))

    def test_status_ignores_a_dead_pid(self):
        with open(self.path("talk.pid"), "w") as f:
            f.write("999999")
        rc, out = self.run_cli("talk", "status"); self.assertEqual(out, "talk: OFF")

    def test_unknown_subcommand_is_usage(self):
        rc, out = self.run_cli("talk", "bogus"); self.assertEqual(rc, 2); self.assertIn("usage", out)


class Top(Sandbox):
    def test_paths_prints_state(self):
        rc, out = self.run_cli("paths"); self.assertEqual(rc, 0); self.assertIn(self.state, out)

    def test_version_matches_file(self):
        rc, out = self.run_cli("version")
        self.assertEqual(out, open(os.path.join(ROOT, "VERSION")).read().strip())

    def test_no_args_is_usage(self):
        rc, out = self.run_cli(); self.assertEqual(rc, 2); self.assertIn("usage", out)


if __name__ == "__main__":
    unittest.main()

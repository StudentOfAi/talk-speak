"""speak engine, Claude Code transcript reader and prune. Run: python3 -m unittest tests.test_speak"""
import os, shutil, stat, subprocess, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "speak", "speak-text.sh")
PRUNE = os.path.join(ROOT, "speak", "speak-prune.sh")
LAST = os.path.join(ROOT, "speak", "claude-code", "last-reply.py")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "transcript.jsonl")


def make_state():
    """A sandbox state dir with the engine installed under bin/ and a fake `say` on PATH."""
    state = tempfile.mkdtemp(prefix="talk-speak-test.")
    os.makedirs(os.path.join(state, "bin"))
    for f in (ENGINE, PRUNE):
        shutil.copy(f, os.path.join(state, "bin"))
    fake = os.path.join(state, "fakebin"); os.makedirs(fake)
    say = os.path.join(fake, "say")
    with open(say, "w") as f:
        f.write('#!/bin/bash\necho "$@" >> "$FAKE_SAY_LOG"\nsleep 0.3\n')
    os.chmod(say, stat.S_IRWXU)
    return state, fake


def wait_for(path, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        if os.path.exists(path):
            return True
        time.sleep(0.05)
    return False


class Engine(unittest.TestCase):
    def setUp(self):
        self.state, self.fake = make_state()
        self.log = os.path.join(self.state, "say.log")

    def run_engine(self, text, extra_env=None):
        env = {**os.environ, "TALK_SPEAK_HOME": self.state, "FAKE_SAY_LOG": self.log,
               "PATH": self.fake + ":" + os.environ["PATH"]}
        env.pop("TALK_SPEAK", None); env.pop("CLAUDE_SPEAK", None)
        env.update(extra_env or {})
        return subprocess.run(["bash", ENGINE], input=text, text=True, env=env, capture_output=True)

    def touch(self, name, content=""):
        with open(os.path.join(self.state, name), "w") as f:
            f.write(content)

    def test_off_says_nothing(self):
        self.run_engine("hello"); time.sleep(0.3)
        self.assertFalse(os.path.exists(self.log))

    def test_on_calls_say_with_rate_and_voice_and_records_reply(self):
        self.touch("speak.on"); self.touch("speak.rate", "180"); self.touch("speak.voice", "Samantha")
        self.run_engine("hello there")
        self.assertTrue(wait_for(self.log))
        line = open(self.log).read()
        self.assertIn("-r 180", line); self.assertIn("-v Samantha", line)
        self.assertEqual(open(os.path.join(self.state, "last-reply.txt")).read(), "hello there\n")

    def test_env_off_wins_over_flag(self):
        self.touch("speak.on")
        self.run_engine("hello", {"TALK_SPEAK": "off"}); time.sleep(0.3)
        self.assertFalse(os.path.exists(self.log))
        self.run_engine("hello", {"CLAUDE_SPEAK": "off"}); time.sleep(0.3)
        self.assertFalse(os.path.exists(self.log))

    def test_blank_text_is_ignored(self):
        self.touch("speak.on"); self.run_engine("  \n "); time.sleep(0.3)
        self.assertFalse(os.path.exists(self.log))

    def test_speaking_flag_exists_while_saying_then_clears(self):
        self.touch("speak.on"); self.run_engine("hello")
        self.assertTrue(wait_for(os.path.join(self.state, "speaking")))
        self.assertTrue(wait_for(self.log))
        time.sleep(0.6)
        self.assertFalse(os.path.exists(os.path.join(self.state, "speaking")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "speak.pid")))

    def test_speak_env_overrides_flag_path(self):
        self.touch("speak.on"); custom = os.path.join(self.state, "custom.flag")
        self.touch("speak.env", 'SPEAKING_FLAG="%s"\n' % custom)
        self.run_engine("hello")
        self.assertTrue(wait_for(custom)); self.assertTrue(wait_for(self.log))


class LastReply(unittest.TestCase):
    def test_last_assistant_text_markdown_stripped_signature_removed(self):
        out = subprocess.run(["/usr/bin/python3", LAST, FIXTURE], capture_output=True, text=True).stdout
        self.assertIn("Done", out); self.assertIn("code block omitted", out)
        self.assertNotIn("```", out); self.assertNotIn("http", out); self.assertNotIn("**", out)
        self.assertNotIn("|", out); self.assertIn("1, 2", out)
        self.assertFalse(out.rstrip().endswith("-code")); self.assertNotIn("Working on it", out)

    def test_hyphenated_words_survive_signature_strip(self):
        fd, p = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
        with open(p, "w") as f:
            f.write('{"type":"assistant","message":{"content":[{"type":"text","text":"It is self-hosted"}]}}\n')
        out = subprocess.run(["/usr/bin/python3", LAST, p], capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "It is self-hosted")


class Prune(unittest.TestCase):
    def setUp(self):
        self.state, _ = make_state()
        self.mut = os.path.join(self.state, "speak.muted"); self.alive = os.path.join(self.state, "speak.alive")
        os.makedirs(self.mut); os.makedirs(self.alive)

    def prune(self):
        subprocess.run(["bash", PRUNE], env={**os.environ, "TALK_SPEAK_HOME": self.state}, check=True)

    def test_mute_without_heartbeat_is_removed(self):
        open(os.path.join(self.mut, "abc"), "w").close(); self.prune()
        self.assertFalse(os.path.exists(os.path.join(self.mut, "abc")))

    def test_fresh_heartbeat_keeps_mute(self):
        open(os.path.join(self.mut, "abc"), "w").close(); open(os.path.join(self.alive, "abc"), "w").close(); self.prune()
        self.assertTrue(os.path.exists(os.path.join(self.mut, "abc")))

    def test_stale_heartbeat_removes_mute(self):
        open(os.path.join(self.mut, "abc"), "w").close(); a = os.path.join(self.alive, "abc"); open(a, "w").close()
        old = time.time() - 100 * 60; os.utime(a, (old, old)); self.prune()
        self.assertFalse(os.path.exists(os.path.join(self.mut, "abc")))

    def test_pending_survives_prune(self):
        open(os.path.join(self.mut, "PENDING"), "w").close(); self.prune()
        self.assertTrue(os.path.exists(os.path.join(self.mut, "PENDING")))


if __name__ == "__main__":
    unittest.main()

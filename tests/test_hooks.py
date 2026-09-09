"""lib/hooks.py: idempotent add/remove of talk-speak's hooks in Claude Code settings.json.
Run: python3 -m unittest tests.test_hooks"""
import glob, json, os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "lib", "hooks.py")
STATE = "/Users/someone/.talk-speak"
FIXTURE = {
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"]},
    "hooks": {
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "bash ~/.claude/tools/track.sh"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "bash ~/other/stop.sh", "timeout": 3}]}],
    },
}


class Hooks(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "settings.json")
        with open(self.path, "w") as f:
            json.dump(FIXTURE, f, indent=2)

    def run_hooks(self, op, path=None):
        return subprocess.run(["python3", HOOKS, op, path or self.path, STATE], capture_output=True, text=True)

    def read(self):
        return json.load(open(self.path))

    def backups(self):
        return glob.glob(self.path + ".bak-*")

    def test_add_appends_ours_and_keeps_everything_else(self):
        self.assertEqual(self.run_hooks("add").returncode, 0)
        d = self.read()
        self.assertEqual(d["model"], "opus"); self.assertEqual(d["permissions"], FIXTURE["permissions"])
        self.assertEqual(d["hooks"]["PostToolUse"], FIXTURE["hooks"]["PostToolUse"])
        stop = d["hooks"]["Stop"]
        self.assertEqual(stop[0], FIXTURE["hooks"]["Stop"][0])                 # the foreign Stop hook stays first
        self.assertEqual(stop[1]["hooks"][0]["command"], "bash %s/bin/speak-last.sh" % STATE)
        self.assertEqual(stop[1]["hooks"][0]["timeout"], 10)
        self.assertEqual(d["hooks"]["SessionEnd"][0]["hooks"][0]["command"], "bash %s/bin/speak-session-end.sh" % STATE)
        self.assertEqual(len(self.backups()), 1)

    def test_add_twice_changes_nothing(self):
        self.run_hooks("add"); before = open(self.path).read()
        r = self.run_hooks("add")
        self.assertEqual(r.returncode, 0); self.assertIn("nothing to add", r.stdout)
        self.assertEqual(open(self.path).read(), before); self.assertEqual(len(self.backups()), 1)

    def test_remove_restores_the_others(self):
        self.run_hooks("add"); r = self.run_hooks("remove")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.read()["hooks"], FIXTURE["hooks"])                # SessionEnd gone, foreign Stop kept

    def test_remove_when_absent_is_a_noop_without_backup(self):
        r = self.run_hooks("remove")
        self.assertEqual(r.returncode, 0); self.assertIn("nothing to remove", r.stdout)
        self.assertEqual(self.backups(), []); self.assertEqual(self.read(), FIXTURE)

    def test_invalid_json_exits_1_and_writes_nothing(self):
        with open(self.path, "w") as f:
            f.write("{ not json")
        r = self.run_hooks("add")
        self.assertEqual(r.returncode, 1); self.assertEqual(open(self.path).read(), "{ not json"); self.assertEqual(self.backups(), [])

    def test_missing_file_is_created_with_only_ours(self):
        p = os.path.join(self.dir, "new", "settings.json")
        r = self.run_hooks("add", p)
        self.assertEqual(r.returncode, 0)
        d = json.load(open(p))
        self.assertEqual(sorted(d["hooks"]), ["SessionEnd", "Stop"]); self.assertEqual(list(d), ["hooks"])

    def test_bad_usage_exits_2(self):
        r = subprocess.run(["python3", HOOKS, "frobnicate"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()

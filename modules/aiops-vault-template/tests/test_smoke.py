import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class SmokeTests(unittest.TestCase):
    def test_example_jsonl_parses(self):
        path = ROOT / "maintenance-log.example.jsonl"
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 1)
        for line in lines:
            obj = json.loads(line)
            self.assertIn("summary", obj)
            self.assertNotIn("SECRET", json.dumps(obj))

    def test_cli_check_on_repo_examples(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            subprocess.check_call([sys.executable, str(ROOT / "scripts" / "install.py"), "--vault", str(vault), "--agent", "none"])
            out = subprocess.check_output([sys.executable, str(vault / "scripts" / "aiops.py"), "check"], cwd=vault, text=True)
            self.assertIn("check passed", out)


    def test_installed_absolute_script_detects_own_vault(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            subprocess.check_call([sys.executable, str(ROOT / "scripts" / "install.py"), "--vault", str(vault), "--agent", "none"])
            out = subprocess.check_output([sys.executable, str(vault / "scripts" / "aiops.py"), "check"], cwd=ROOT, text=True)
            self.assertIn("check passed", out)
            self.assertNotIn("WARN", out)

    def test_cli_slice_commands(self):
        env = os.environ.copy()
        env["AIOPS_ROOT"] = str(ROOT)
        out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "aiops.py"), "resources", "--section", "Service Inventory"], env=env, text=True)
        self.assertIn("example-api", out)
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "aiops.py"), "service", "example-api"], env=env, text=True, stdout=subprocess.PIPE)
        self.assertEqual(out.returncode, 0)
        self.assertIn("example-api", out.stdout)

    def test_cli_fuzzy_service_lookup(self):
        env = os.environ.copy()
        env["AIOPS_ROOT"] = str(ROOT)
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "aiops.py"), "service", "example api docker"], env=env, text=True, stdout=subprocess.PIPE)
        self.assertEqual(out.returncode, 0)
        self.assertIn("example-api", out.stdout)
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "aiops.py"), "service", "notesweb systemd"], env=env, text=True, stdout=subprocess.PIPE)
        self.assertEqual(out.returncode, 0)
        self.assertIn("notes-web", out.stdout)
        out = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "aiops.py"),
                "service",
                "帮我看看那个 example api 的历史遗留问题有没有解决",
            ],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
        )
        self.assertEqual(out.returncode, 0)
        self.assertIn("example-api", out.stdout)

    def test_cli_log_query(self):
        env = os.environ.copy()
        env["AIOPS_ROOT"] = str(ROOT)
        out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "aiops.py"), "log", "--query", "example maintenance", "--summary"], env=env, text=True)
        self.assertIn("example", out.lower())

if __name__ == "__main__":
    unittest.main()

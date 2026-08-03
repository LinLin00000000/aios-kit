from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("aios_doctor_cli", CLI)
assert SPEC and SPEC.loader
AIOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AIOS)


def tree_fingerprint(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class DoctorJsonCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-doctor-test-")
        self.home = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for key in (
            "AIOS_ROOT",
            "AIOS_HOME",
            "AIOS_AGENT_SKILLS_DIR",
            "AIOS_SKILLS_DIR",
            "HERMES_HOME",
            "PYTHONPYCACHEPREFIX",
        ):
            env.pop(key, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )

    def test_json_contract_is_versioned_compact_read_only_and_exit_aligned(self) -> None:
        before = tree_fingerprint(self.home)
        first = self.run_cli("doctor", "--json")
        second = self.run_cli("doctor", "--json")
        after = tree_fingerprint(self.home)

        self.assertIn(first.returncode, (0, 1), first.stderr)
        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        self.assertEqual(first.stdout.count("\n"), 1)
        self.assertNotIn("\n", first.stdout[:-1])
        self.assertEqual(before, after, "doctor must not create or mutate instance files")

        payload = json.loads(first.stdout)
        self.assertEqual(set(payload), {"checks", "ok", "problems", "schema", "version"})
        self.assertEqual(payload["schema"], "aios.doctor.v1")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["ok"], first.returncode == 0)
        self.assertEqual([check["id"] for check in payload["checks"]], ["instance", "skillpack", "assets"])
        for check in payload["checks"]:
            self.assertEqual(set(check), {"id", "messages", "ok"})
            self.assertIsInstance(check["ok"], bool)
            self.assertIsInstance(check["messages"], list)
            self.assertTrue(all(isinstance(message, str) for message in check["messages"]))
        assets_messages = next(check["messages"] for check in payload["checks"] if check["id"] == "assets")
        isolated_asset = str(self.home / "projects" / "lins-living-loop")
        self.assertTrue(any(isolated_asset in message for message in assets_messages))
        self.assertEqual(bool(payload["problems"]), not payload["ok"])
        for problem in payload["problems"]:
            self.assertEqual(set(problem), {"check", "code", "message"})
            self.assertEqual(problem["code"], "doctor_failed")
            self.assertIn(problem["check"], {"instance", "skillpack", "assets"})

    def test_healthy_isolated_instance_returns_zero_with_no_problems(self) -> None:
        required = (
            self.home / "aios" / "config",
            self.home / "aios" / "vault" / "ops" / "projects",
            self.home / "aios" / "work",
            self.home / "aios" / "skills",
            self.home / ".agents" / "skills",
            self.home / "aios" / "modules" / "lins-living-loop",
            self.home / "aios" / "state",
            self.home / "aios" / "logs",
            self.home / "aios" / "cache",
        )
        for path in required:
            path.mkdir(parents=True, exist_ok=True)
        (self.home / "aios" / "modules" / "lins-living-loop" / "SKILL.md").write_text(
            "---\nname: lins-living-loop\n---\n", encoding="utf-8"
        )
        fake_bin = self.home / "bin"
        fake_bin.mkdir()
        for command in ("node", "npx"):
            executable = fake_bin / command
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
        before = tree_fingerprint(self.home)

        cp = self.run_cli(
            "doctor",
            "--json",
            extra_env={"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")},
        )

        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(cp.stderr, "")
        payload = json.loads(cp.stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["problems"], [])
        self.assertTrue(all(check["ok"] for check in payload["checks"]))
        self.assertEqual(before, tree_fingerprint(self.home))

    def test_default_human_output_keeps_existing_sections_and_exit_behavior(self) -> None:
        first = self.run_cli("doctor")
        second = self.run_cli("doctor")

        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        self.assertEqual(
            [line for line in first.stdout.splitlines() if line.startswith("==")],
            ["== instance ==", "== skillpack ==", "== assets =="],
        )
        self.assertFalse(first.stdout.lstrip().startswith("{"))


class DoctorRedactionTests(unittest.TestCase):
    def test_central_redaction_removes_url_credentials_assignments_and_provider_keys(self) -> None:
        sensitive = "".join(("credential", "-value"))
        provider_value = "".join(("sk", "-", "A" * 24))
        query_name = "_".join(("access", "token"))
        assignment_name = "".join(("pass", "word"))
        raw = "\n".join(
            (
                f"origin: https://oauth2:{sensitive}@example.invalid/repo.git?{query_name}={sensitive}",
                f"{assignment_name}={sensitive}",
                f"provider: {provider_value}",
            )
        )

        redacted = AIOS.redact_output(raw, [])

        self.assertNotIn(sensitive, redacted)
        self.assertNotIn(provider_value, redacted)
        self.assertNotIn("oauth2:", redacted)
        self.assertIn("https://example.invalid/repo.git?***REDACTED***", redacted)
        self.assertGreaterEqual(redacted.count("***REDACTED***"), 3)

    def test_assignment_key_requires_sensitive_suffix_before_operator(self) -> None:
        safe_keys = (
            "aios-secret-management", "secret_id", "token_budget", "password_policy",
            "passwordless_mode", "credential_type", "authorization_scheme", "api_key_path",
            "private_key_path", "tokenizer_type",
        )
        sensitive_keys = (
            "api_key", "openai_api_key", "access-key", "privateKey", "AWS_SECRET_ACCESS_KEY",
            "secret_key", "secret_value", "secret-material", "access_token", "refreshToken",
            "auth-token", "bearer_token", "github_token", "token", "password", "passwd",
            "passphrase", "client_secret", "clientSecret", "secret", "credential",
            "credentials", "authorization",
        )
        markers = [f"synthetic-{index}-marker" for index in range(len(sensitive_keys))]
        safe_lines = [f"{key}: /srv/{key}/public" for key in safe_keys]
        raw = "\n".join(
            safe_lines
            + [f"{key}={marker}" for key, marker in zip(sensitive_keys, markers)]
            + [f"token_budget: github_token={markers[-1]}"]
        )

        redacted = AIOS.redact_output(raw, [])

        for line in safe_lines:
            self.assertIn(line, redacted)
        for key, marker in zip(sensitive_keys, markers):
            self.assertIn(f"{key}=***REDACTED***", redacted)
            self.assertNotIn(marker, redacted)
        self.assertIn("token_budget: github_token=***REDACTED***", redacted)

    def test_assets_human_doctor_redacts_configured_and_observed_git_output(self) -> None:
        sensitive = "".join(("fixture", "-credential"))
        provider_value = "".join(("sk", "-", "B" * 24))
        query_name = "_".join(("refresh", "token"))
        configured = f"https://oauth2:{sensitive}@example.invalid/repo.git?{query_name}={sensitive}"
        observed = f"https://user:{sensitive}@example.invalid/other.git?{query_name}={sensitive}"

        with tempfile.TemporaryDirectory(prefix="aios-doctor-assets-") as raw:
            asset_path = Path(raw)
            runs = [
                subprocess.CompletedProcess([], 0, stdout=observed + "\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout=f"## branch-{provider_value}\n", stderr=""),
            ]
            output = io.StringIO()
            with (
                patch.object(AIOS, "assets_manifest_path", return_value=ROOT / "manifests" / "local-assets.json"),
                patch.object(
                    AIOS,
                    "load_assets",
                    return_value={
                        "assets": [
                            {
                                "id": "fixture",
                                "kind": "repository",
                                "canonical_path": str(asset_path),
                                "remote": configured,
                            }
                        ]
                    },
                ),
                patch.object(AIOS.subprocess, "run", side_effect=runs),
                contextlib.redirect_stdout(output),
            ):
                with self.assertRaises(SystemExit) as stopped:
                    AIOS.assets_doctor(argparse.Namespace())

        self.assertEqual(stopped.exception.code, 1)
        rendered = output.getvalue()
        self.assertNotIn(sensitive, rendered)
        self.assertNotIn(provider_value, rendered)
        self.assertNotIn("oauth2:", rendered)
        self.assertIn("https://example.invalid/other.git?***REDACTED***", rendered)
        self.assertIn("https://example.invalid/repo.git?***REDACTED***", rendered)


class DoctorAdversarialPublicCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-doctor-public-")
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_cli_fixture(self, root: Path, assets: list[dict[str, str]] | None = None) -> Path:
        scripts = root / "scripts"
        manifests = root / "manifests"
        scripts.mkdir(parents=True)
        manifests.mkdir()
        shutil.copy2(CLI, scripts / "aios.py")
        shutil.copy2(ROOT / "scripts" / "aios_promotion.py", scripts / "aios_promotion.py")
        (root / "skillpack.yaml").write_text(
            "defaults:\n  state_dir: ~/aios/vault/ops/state/aios-kit\nexternal: []\nfirst_party: []\n",
            encoding="utf-8",
        )
        self.write_assets(root, assets or [])
        return root

    def write_assets(self, fixture_root: Path, assets: list[dict[str, str]]) -> None:
        (fixture_root / "manifests" / "local-assets.local.json").write_text(
            json.dumps({"assets": assets}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def prepare_healthy_home(self, home: Path) -> Path:
        required = (
            home / "aios" / "config",
            home / "aios" / "vault" / "ops" / "projects",
            home / "aios" / "work",
            home / "aios" / "skills",
            home / ".agents" / "skills",
            home / "aios" / "modules" / "lins-living-loop",
            home / "aios" / "state",
            home / "aios" / "logs",
            home / "aios" / "cache",
        )
        for path in required:
            path.mkdir(parents=True, exist_ok=True)
        (home / "aios" / "modules" / "lins-living-loop" / "SKILL.md").write_text(
            "---\nname: lins-living-loop\n---\n", encoding="utf-8"
        )
        fake_bin = home / "bin"
        fake_bin.mkdir()
        for command in ("node", "npx"):
            self.write_executable(fake_bin / command, "#!/bin/sh\nexit 0\n")
        return fake_bin

    @staticmethod
    def write_executable(path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def clean_env(self, home: Path, fake_bin: Path | None = None) -> dict[str, str]:
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("GIT_") or key in {
                "AIOS_ROOT",
                "AIOS_HOME",
                "AIOS_AGENT_SKILLS_DIR",
                "AIOS_SKILLS_DIR",
                "HERMES_HOME",
                "PYTHONPYCACHEPREFIX",
            }:
                env.pop(key, None)
        env["HOME"] = str(home)
        env["XDG_CONFIG_HOME"] = str(home / ".config")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if fake_bin is not None:
            env["PATH"] = str(fake_bin) + os.pathsep + os.environ.get("PATH", "")
        return env

    def run_public_cli(
        self,
        fixture_root: Path,
        home: Path,
        *args: str,
        fake_bin: Path,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.clean_env(home, fake_bin)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(fixture_root / "scripts" / "aios.py"), "--home", str(home), *args],
            cwd=fixture_root,
            text=True,
            capture_output=True,
            env=env,
        )

    def git(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        cp = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            env={
                **self.clean_env(self.base / "git-setup-home"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            },
        )
        self.assertEqual(cp.returncode, 0, f"git {' '.join(args)} failed:\n{cp.stdout}\n{cp.stderr}")
        return cp

    def init_repo(self, repo: Path, remote: str) -> Path:
        repo.mkdir(parents=True)
        self.git(repo, "init", "--quiet")
        tracked = repo / "tracked.txt"
        tracked.write_text("fixture\n", encoding="utf-8")
        self.git(repo, "add", "tracked.txt")
        self.git(
            repo,
            "-c",
            "user.name=AIOS Doctor Fixture",
            "-c",
            "user.email=doctor-fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        )
        self.git(repo, "remote", "add", "origin", remote)
        return tracked

    def test_public_cli_redacts_adversarial_assets_in_json_and_human_modes(self) -> None:
        fixture_root = self.make_cli_fixture(self.base / "redaction-cli")
        home = self.base / "redaction-home"
        fake_bin = self.prepare_healthy_home(home)
        repo = home / "projects" / "redaction"
        ftp_secret = "".join(("ftp", "-userinfo-marker"))
        ftp_remote = (
            f"ftp://fixture-user:{ftp_secret}@safe.example/safe/repo.git"
            f"?access_token={ftp_secret}#fragment-{ftp_secret}"
        )
        self.init_repo(repo, ftp_remote)

        bearer_one = "".join(("bearer", "-marker-one"))
        bearer_two = "".join(("bearer", "-marker-two"))
        quoted_json = "".join(("quoted", "-json-marker"))
        quoted_yaml = "".join(("quoted", "-yaml-marker"))
        provider_value = "".join(("sk", "-", "C" * 24))
        ordinary = "ordinary-non-secret-marker"
        safe_uris = [
            f"{scheme}://safe.example/safe/path"
            for scheme in ("ftp", "http", "https", "ssh", "git")
        ]
        self.write_assets(
            fixture_root,
            [
                {
                    "id": "credential-uri",
                    "kind": "repository",
                    "canonical_path": "~/projects/redaction",
                    "remote": ftp_remote,
                },
                {
                    "id": f"Authorization: Bearer {bearer_one} {bearer_two}",
                    "kind": "diagnostic",
                    "canonical_path": "~/projects/redaction",
                },
                {
                    "id": f'json {{"api_key":"{quoted_json}"}}',
                    "kind": "diagnostic",
                    "canonical_path": "~/projects/redaction",
                },
                {
                    "id": f"yaml 'access_token': '{quoted_yaml}'",
                    "kind": "diagnostic",
                    "canonical_path": "~/projects/redaction",
                },
                {
                    "id": f"provider {provider_value}",
                    "kind": "diagnostic",
                    "canonical_path": "~/projects/redaction",
                },
                {
                    "id": ordinary + " " + " ".join(safe_uris),
                    "kind": "safe-diagnostic",
                    "canonical_path": "~/projects/redaction",
                },
            ],
        )
        before = tree_fingerprint(self.base)

        as_json = self.run_public_cli(fixture_root, home, "doctor", "--json", fake_bin=fake_bin)
        as_human = self.run_public_cli(fixture_root, home, "doctor", fake_bin=fake_bin)

        self.assertEqual(as_json.returncode, 0, as_json.stderr)
        self.assertEqual(as_human.returncode, 0, as_human.stderr)
        self.assertEqual(as_json.stderr, "")
        self.assertEqual(as_human.stderr, "")
        payload = json.loads(as_json.stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(
            [line for line in as_human.stdout.splitlines() if line.startswith("==")],
            ["== instance ==", "== skillpack ==", "== assets =="],
        )
        rendered = as_json.stdout + as_human.stdout
        for forbidden in (
            "fixture-user",
            ftp_secret,
            bearer_one,
            bearer_two,
            quoted_json,
            quoted_yaml,
            provider_value,
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertIn("ftp://safe.example/safe/repo.git?***REDACTED***#***REDACTED***", rendered)
        for safe_uri in safe_uris:
            self.assertIn(safe_uri, rendered)
        self.assertIn(ordinary, rendered)
        self.assertEqual(before, tree_fingerprint(self.base))

    def test_public_cli_human_and_json_share_redaction_for_assignment_shaped_paths(self) -> None:
        fixture_marker = "".join(("fixture", "-path-marker"))
        home_marker = "".join(("home", "-path-marker"))
        fixture_root = self.make_cli_fixture(self.base / f"credential={fixture_marker}")
        home = self.base / f"api_key={home_marker}"
        fake_bin = self.prepare_healthy_home(home)
        before = tree_fingerprint(self.base)

        as_json = self.run_public_cli(fixture_root, home, "doctor", "--json", fake_bin=fake_bin)
        as_human = self.run_public_cli(fixture_root, home, "doctor", fake_bin=fake_bin)

        self.assertEqual(as_json.returncode, 0, as_json.stderr)
        self.assertEqual(as_human.returncode, 0, as_human.stderr)
        self.assertEqual(as_json.stderr, "")
        self.assertEqual(as_human.stderr, "")
        payload = json.loads(as_json.stdout)
        self.assertEqual([check["id"] for check in payload["checks"]], ["instance", "skillpack", "assets"])
        self.assertTrue(all(check["ok"] for check in payload["checks"]))
        self.assertEqual(
            [line for line in as_human.stdout.splitlines() if line.startswith("==")],
            ["== instance ==", "== skillpack ==", "== assets =="],
        )
        for rendered in (as_json.stdout, as_human.stdout):
            self.assertNotIn(fixture_marker, rendered)
            self.assertNotIn(home_marker, rendered)
            self.assertIn(str(self.base), rendered)
        self.assertEqual(before, tree_fingerprint(self.base))

    def test_public_cli_git_probes_ignore_ambient_config_fsmonitor_hooks_and_index_writes(self) -> None:
        fixture_root = self.make_cli_fixture(self.base / "git-isolation-cli")
        home = self.base / "explicit-home"
        fake_bin = self.prepare_healthy_home(home)
        ambient = self.base / "ambient"
        ambient.mkdir()
        xdg = self.base / "ambient-xdg"
        (xdg / "git").mkdir(parents=True)
        system_config = self.base / "ambient-system.gitconfig"
        ambient_fsmonitor_marker = self.base / "ambient-fsmonitor-ran"
        local_fsmonitor_marker = self.base / "local-fsmonitor-ran"
        ambient_hook_marker = self.base / "ambient-hook-ran"
        local_hook_marker = self.base / "local-hook-ran"
        ambient_fsmonitor = ambient / "fsmonitor.sh"
        local_fsmonitor = ambient / "local-fsmonitor.sh"
        self.write_executable(ambient_fsmonitor, f"#!/bin/sh\n: > {ambient_fsmonitor_marker}\nexit 0\n")
        self.write_executable(local_fsmonitor, f"#!/bin/sh\n: > {local_fsmonitor_marker}\nexit 0\n")
        ambient_hooks = ambient / "hooks"
        local_hooks = ambient / "local-hooks"
        self.write_executable(ambient_hooks / "post-index-change", f"#!/bin/sh\n: > {ambient_hook_marker}\nexit 0\n")
        self.write_executable(local_hooks / "post-index-change", f"#!/bin/sh\n: > {local_hook_marker}\nexit 0\n")
        (ambient / ".gitconfig").write_text(
            "[core]\n"
            f"\tfsmonitor = {ambient_fsmonitor}\n"
            f"\thooksPath = {ambient_hooks}\n"
            '[url "https://ambient-home.invalid/"]\n'
            "\tinsteadOf = https://raw-home.invalid/\n",
            encoding="utf-8",
        )
        (xdg / "git" / "config").write_text(
            '[url "https://ambient-xdg.invalid/"]\n'
            "\tinsteadOf = https://raw-xdg.invalid/\n",
            encoding="utf-8",
        )
        system_config.write_text(
            '[url "https://ambient-system.invalid/"]\n'
            "\tinsteadOf = https://raw-system.invalid/\n",
            encoding="utf-8",
        )

        remote_cases = {
            "home": "https://raw-home.invalid/repo.git",
            "xdg": "https://raw-xdg.invalid/repo.git",
            "system": "https://raw-system.invalid/repo.git",
            "env": "https://raw-env.invalid/repo.git",
            "local": "https://raw-local.invalid/repo.git",
            "index": "https://raw-index.invalid/repo.git",
        }
        assets: list[dict[str, str]] = []
        repos: dict[str, Path] = {}
        for name, remote in remote_cases.items():
            repo = home / "projects" / name
            tracked = self.init_repo(repo, remote)
            repos[name] = repo
            link = home / "discovery" / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(repo, target_is_directory=True)
            assets.append(
                {
                    "id": name,
                    "kind": "repository",
                    "canonical_path": f"~/projects/{name}",
                    "remote": remote,
                    "discovery_link": f"~/discovery/{name}",
                }
            )
            if name == "local":
                self.git(repo, "config", "--local", "core.fsmonitor", str(local_fsmonitor))
                self.git(repo, "config", "--local", "core.hooksPath", str(local_hooks))
            if name == "index":
                self.git(repo, "config", "--local", "core.fsmonitor", "false")
                os.utime(tracked, (1, 1))
        self.write_assets(fixture_root, assets)
        before = tree_fingerprint(self.base)
        index_hashes = {
            name: hashlib.sha256((repo / ".git" / "index").read_bytes()).hexdigest()
            for name, repo in repos.items()
        }

        cp = self.run_public_cli(
            fixture_root,
            home,
            "doctor",
            "--json",
            fake_bin=fake_bin,
            extra_env={
                "HOME": str(ambient),
                "XDG_CONFIG_HOME": str(xdg),
                "GIT_CONFIG_SYSTEM": str(system_config),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "url.https://ambient-env.invalid/.insteadOf",
                "GIT_CONFIG_VALUE_0": "https://raw-env.invalid/",
            },
        )

        payload = json.loads(cp.stdout)
        assets_check = next(check for check in payload["checks"] if check["id"] == "assets")
        rendered = "\n".join(assets_check["messages"])
        violations: list[str] = []
        if cp.returncode != 0 or not payload["ok"] or not assets_check["ok"]:
            violations.append(f"unexpected health: exit={cp.returncode} payload={payload['ok']} assets={assets_check['ok']}")
        for remote in remote_cases.values():
            if f"origin: {remote}" not in rendered:
                violations.append(f"raw origin missing: {remote}")
        for rewritten_host in (
            "ambient-home.invalid",
            "ambient-xdg.invalid",
            "ambient-system.invalid",
            "ambient-env.invalid",
        ):
            if rewritten_host in rendered:
                violations.append(f"ambient rewrite observed: {rewritten_host}")
        for marker in (
            ambient_fsmonitor_marker,
            local_fsmonitor_marker,
            ambient_hook_marker,
            local_hook_marker,
        ):
            if marker.exists():
                violations.append(f"ambient/repo executable ran: {marker.name}")
        for name, repo in repos.items():
            after_hash = hashlib.sha256((repo / ".git" / "index").read_bytes()).hexdigest()
            if after_hash != index_hashes[name]:
                violations.append(f"index mutated: {name}")
        if before != tree_fingerprint(self.base):
            violations.append("fixture tree mutated")
        self.assertEqual(violations, [], "\n".join(violations) + "\n" + rendered)

    def test_public_cli_remote_mismatch_fails_assets_and_aggregate(self) -> None:
        fixture_root = self.make_cli_fixture(self.base / "remote-mismatch-cli")
        home = self.base / "remote-mismatch-home"
        fake_bin = self.prepare_healthy_home(home)
        repo = home / "projects" / "mismatch"
        observed = "https://observed.safe.invalid/repo.git"
        expected = "https://expected.safe.invalid/repo.git"
        self.init_repo(repo, observed)
        self.write_assets(
            fixture_root,
            [
                {
                    "id": "mismatch",
                    "kind": "repository",
                    "canonical_path": "~/projects/mismatch",
                    "remote": expected,
                }
            ],
        )
        before = tree_fingerprint(self.base)

        as_json = self.run_public_cli(fixture_root, home, "doctor", "--json", fake_bin=fake_bin)
        as_human = self.run_public_cli(fixture_root, home, "doctor", fake_bin=fake_bin)

        payload = json.loads(as_json.stdout)
        assets_check = next(check for check in payload["checks"] if check["id"] == "assets")
        self.assertEqual(as_json.returncode, 1)
        self.assertEqual(as_human.returncode, 1)
        self.assertIs(payload["ok"], False)
        self.assertIs(assets_check["ok"], False)
        self.assertEqual([problem["check"] for problem in payload["problems"]], ["assets"])
        self.assertIn(f"origin: {observed}", as_json.stdout)
        self.assertIn(f"expected: {expected}", as_json.stdout)
        self.assertEqual(
            [line for line in as_human.stdout.splitlines() if line.startswith("==")],
            ["== instance ==", "== skillpack ==", "== assets =="],
        )
        self.assertEqual(before, tree_fingerprint(self.base))

    def test_public_cli_redacts_exception_text_in_json_and_human_modes(self) -> None:
        fixture_root = self.make_cli_fixture(self.base / "exception-cli")
        home = self.base / "exception-home"
        fake_bin = self.prepare_healthy_home(home)
        exception_marker = "".join(("exception", "-marker"))
        overlong = str(home / (f"api_key={exception_marker}-" + "x" * 300))
        self.write_assets(
            fixture_root,
            [
                {
                    "id": "exception",
                    "kind": "repository",
                    "canonical_path": overlong,
                }
            ],
        )
        before = tree_fingerprint(self.base)

        as_json = self.run_public_cli(fixture_root, home, "doctor", "--json", fake_bin=fake_bin)
        as_human = self.run_public_cli(fixture_root, home, "doctor", fake_bin=fake_bin)

        payload = json.loads(as_json.stdout)
        assets_check = next(check for check in payload["checks"] if check["id"] == "assets")
        self.assertEqual(as_json.returncode, 1)
        self.assertEqual(as_human.returncode, 1)
        self.assertIs(assets_check["ok"], False)
        self.assertNotIn(exception_marker, as_json.stdout + as_json.stderr)
        self.assertNotIn(exception_marker, as_human.stdout + as_human.stderr)
        self.assertEqual(as_human.stderr, "")
        self.assertIn("OSError:", as_json.stdout)
        self.assertIn("OSError:", as_human.stdout)
        self.assertEqual(
            [line for line in as_human.stdout.splitlines() if line.startswith("==")],
            ["== instance ==", "== skillpack ==", "== assets =="],
        )
        self.assertEqual(before, tree_fingerprint(self.base))


if __name__ == "__main__":
    unittest.main()

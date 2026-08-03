#!/usr/bin/env python3
"""Offline integration tests for the GitHub source acquisition cache helper."""
from __future__ import annotations

import contextlib
import fcntl
import http.server
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

from scripts import github_source_cache as source_cache

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "github_source_cache.py"
SEARCH_CLI = ROOT / "skills" / "github-repo-search" / "scripts" / "github_repo_search.py"


class GithubSourceCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-github-cache-test-", dir="/tmp")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.cache_root = self.root / "cache"
        self.remotes = self.root / "remotes"
        self.workspaces = self.root / "workspaces"
        self.remotes.mkdir()
        self.workspaces.mkdir()
        self.gitconfig = self.home / ".gitconfig"
        real_git = shutil.which("git")
        if real_git is None:
            self.fail("system Git is required for source-cache fixtures")
        self.real_git = real_git
        self.git_map = self.root / "git-map.json"
        self.git_map.write_text("{}\n", encoding="utf-8")
        self.git_wrapper_dir = self.root / "git-wrapper"
        self.git_wrapper_dir.mkdir()
        wrapper = self.git_wrapper_dir / "git"
        wrapper.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import json
                import os
                import sys
                import time

                real_git = {self.real_git!r}
                map_path = os.environ.get("AIOS_TEST_GIT_MAP", "")
                mapping = json.loads(open(map_path, encoding="utf-8").read()) if map_path else {{}}
                args = sys.argv[1:]
                log_path = os.environ.get("AIOS_TEST_GIT_CALL_LOG")
                if log_path:
                    record = json.dumps({{"args": args}}, sort_keys=True) + "\\n"
                    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    try:
                        os.write(fd, record.encode("utf-8"))
                    finally:
                        os.close(fd)
                if "clone" in args:
                    delay = float(os.environ.get("AIOS_TEST_GIT_CLONE_DELAY", "0"))
                    if delay > 0:
                        time.sleep(delay)
                injected = ["-c", "protocol.file.allow=always"]
                for canonical, replacement in sorted(mapping.items()):
                    injected.extend(["-c", f"url.{{replacement}}.insteadOf={{canonical}}"])
                os.execv(real_git, [real_git, *injected, *args])
                """
            ),
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "AIOS_TEST_GIT_MAP": str(self.git_map),
            "PATH": str(self.git_wrapper_dir) + os.pathsep + os.environ.get("PATH", ""),
            "LC_ALL": "C",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(
        self,
        *args: str,
        cwd: Path | None = None,
        ok: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [self.real_git, *args],
            cwd=cwd or self.root,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if ok and result.returncode != 0:
            self.fail(
                f"git command failed: {args}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        if not ok and result.returncode == 0:
            self.fail(f"git command unexpectedly passed: {args}")
        return result

    def cache_has_local_object(self, cache: Path, object_id: str) -> bool:
        result = subprocess.run(
            [self.real_git, "--git-dir", str(cache), "cat-file", "-e", object_id],
            cwd=ROOT,
            env={**self.env, "GIT_NO_LAZY_FETCH": "1"},
            text=True,
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0

    def run_cli(
        self,
        *args: str,
        ok: bool = True,
        timeout: float = 30,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env={**self.env, **(env_extra or {})},
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if ok and result.returncode != 0:
            self.fail(
                f"source-cache command failed: {args}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        if not ok and result.returncode == 0:
            self.fail(
                f"source-cache command unexpectedly passed: {args}\n"
                f"stdout={result.stdout}"
            )
        return result

    def json_cli(
        self,
        *args: str,
        ok: bool = True,
        env_extra: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        result = self.run_cli(*args, ok=ok, env_extra=env_extra)
        raw = result.stdout or result.stderr
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            self.fail(
                f"command did not return JSON: {args}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
            raise exc

    @contextlib.contextmanager
    def helper_environment(self):
        """Run direct helper API calls through the test-only Git executable."""
        with mock.patch.dict(os.environ, self.env, clear=True):
            yield

    def map_remote(self, repository: str, remote: Path) -> None:
        canonical = f"https://github.com/{repository}.git"
        mapping = json.loads(self.git_map.read_text(encoding="utf-8"))
        mapping[canonical] = remote.resolve().as_uri()
        self.git_map.write_text(json.dumps(mapping, sort_keys=True) + "\n", encoding="utf-8")

    def make_remote(self, repository: str, text: str = "version one\n") -> tuple[Path, Path, str]:
        slug = repository.replace("/", "__")
        remote = self.remotes / f"{slug}.git"
        work = self.workspaces / slug
        self.git("init", "--bare", "--initial-branch=main", str(remote))
        self.git("--git-dir", str(remote), "config", "uploadpack.allowFilter", "true")
        self.git("--git-dir", str(remote), "config", "uploadpack.allowAnySHA1InWant", "true")
        self.git("init", "--initial-branch=main", str(work))
        self.git("config", "user.name", "AIOS Fixture", cwd=work)
        self.git("config", "user.email", "fixture@example.invalid", cwd=work)
        (work / "README.md").write_text(text, encoding="utf-8")
        self.git("add", "README.md", cwd=work)
        self.git("commit", "-m", "initial fixture", cwd=work)
        self.git("remote", "add", "origin", remote.resolve().as_uri(), cwd=work)
        self.git("push", "-u", "origin", "main", cwd=work)
        self.map_remote(repository, remote)
        sha = self.git("rev-parse", "HEAD", cwd=work).stdout.strip()
        return remote, work, sha

    def add_commit(self, work: Path, text: str) -> str:
        (work / "README.md").write_text(text, encoding="utf-8")
        self.git("add", "README.md", cwd=work)
        self.git("commit", "-m", f"fixture update {text.strip()}", cwd=work)
        self.git("push", "origin", "main", cwd=work)
        return self.git("rev-parse", "HEAD", cwd=work).stdout.strip()

    def cache_path(self, repository: str) -> Path:
        owner, name = repository.split("/", 1)
        return self.cache_root / "repos" / owner / f"{name}.git"

    def ensure_args(self, repository: str, commit: str | None = None) -> list[str]:
        args = ["ensure", repository, "--cache-root", str(self.cache_root), "--json"]
        if commit:
            args.extend(["--commit", commit])
        return args

    def test_canonical_url_variants_share_identity_and_cache_path(self) -> None:
        variants = [
            "Example-Owner/Repo.Name",
            "https://github.com/Example-Owner/Repo.Name",
            "https://github.com/Example-Owner/Repo.Name.git",
            "https://github.com/Example-Owner/Repo.Name/",
            "git@github.com:Example-Owner/Repo.Name.git",
        ]
        payloads = [
            self.json_cli(
                "canonicalize",
                value,
                "--cache-root",
                str(self.cache_root),
                "--json",
            )
            for value in variants
        ]
        self.assertEqual({item["repository"] for item in payloads}, {"example-owner/repo.name"})
        self.assertEqual({item["cache_path"] for item in payloads}, {str(self.cache_path("example-owner/repo.name"))})
        self.assertTrue(all(item["schema"] == "aios.github-source-cache-canonical.v1" for item in payloads))
        self.assertFalse(self.cache_root.exists(), "canonicalize must not create the cache root")

    def test_default_root_uses_home_and_missing_status_is_read_only(self) -> None:
        expected_root = self.home / "aios" / "cache" / "github"
        canonical = self.json_cli("canonicalize", "fixture/default-root", "--json")
        self.assertEqual(canonical["cache_root"], str(expected_root))
        self.assertFalse(expected_root.exists())

        status = self.json_cli("status", "fixture/default-root", "--json")
        self.assertFalse(status["exists"])
        self.assertFalse(status["network_performed"])
        self.assertFalse(expected_root.exists(), "status must not create a missing default cache root")

    def test_canonicalization_rejects_unsafe_or_secret_inputs_without_echo(self) -> None:
        cases = [
            ("https://github.example/owner/repo", []),
            ("https://github.com/owner/repo/issues", []),
            ("https://github.com/owner//repo.git", []),
            ("owner/../repo", []),
            (" owner/repo", []),
            ("owner/repo\n", []),
            ("https://github.com/owner/repo?token=query-secret", ["query-secret"]),
            ("https://oauth2:credential-secret@github.com/owner/repo.git", ["credential-secret", "oauth2"]),
        ]
        for value, forbidden in cases:
            with self.subTest(value=value.split("?", 1)[0]):
                result = self.run_cli(
                    "canonicalize",
                    value,
                    "--cache-root",
                    str(self.cache_root),
                    "--json",
                    ok=False,
                )
                output = result.stdout + result.stderr
                payload = json.loads(result.stdout or result.stderr)
                self.assertFalse(payload["ok"])
                for secret in forbidden:
                    self.assertNotIn(secret, output)

    def test_first_ensure_then_fixed_commit_reuse_without_remote(self) -> None:
        repository = "fixture/reuse"
        remote, work, commit = self.make_remote(repository)
        first = self.json_cli(
            *self.ensure_args(repository, commit),
            "--cited-path",
            "README.md",
        )
        self.assertEqual(first["mode"], "cloned")
        self.assertTrue(first["network_performed"])
        self.assertEqual(first["commit"], commit)
        self.assertEqual(first["cited_paths"], ["README.md"])
        cache = self.cache_path(repository)
        self.assertEqual(
            self.git("--git-dir", str(cache), "rev-parse", "--is-bare-repository").stdout.strip(),
            "true",
        )
        self.assertEqual(
            self.git("--git-dir", str(cache), "config", "--get", "remote.origin.promisor").stdout.strip(),
            "true",
        )
        self.assertEqual(
            self.git("--git-dir", str(cache), "config", "--get", "remote.origin.partialclonefilter").stdout.strip(),
            "blob:none",
        )
        readme_blob = self.git("rev-parse", f"{commit}:README.md", cwd=work).stdout.strip()
        self.assertFalse(self.cache_has_local_object(cache, readme_blob))

        offline = remote.with_name(remote.name + ".offline")
        remote.rename(offline)
        second = self.json_cli(*self.ensure_args(repository, commit))
        self.assertEqual(second["mode"], "reused_commit")
        self.assertFalse(second["network_performed"])
        self.assertEqual(second["commit"], commit)

    def test_missing_commit_requires_explicit_fetch(self) -> None:
        repository = "fixture/fetch"
        _remote, work, first_commit = self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository, first_commit))
        new_commit = self.add_commit(work, "version two\n")

        trace_path = self.root / "missing-commit-trace.jsonl"
        call_log = self.root / "missing-commit-git-calls.jsonl"
        missing = self.json_cli(
            *self.ensure_args(repository, new_commit),
            ok=False,
            env_extra={
                "GIT_TRACE2_EVENT": str(trace_path),
                "AIOS_TEST_GIT_CALL_LOG": str(call_log),
            },
        )
        self.assertEqual(missing["error"]["code"], "missing_commit")
        self.assertFalse(trace_path.exists(), "ambient Git trace destinations must be stripped")
        git_calls = [json.loads(line)["args"] for line in call_log.read_text(encoding="utf-8").splitlines()]
        self.assertFalse(
            any("fetch" in args for args in git_calls),
            "local commit checks must not invoke an explicit Git fetch",
        )

        fetched = self.json_cli(
            *self.ensure_args(repository, new_commit),
            "--fetch-missing",
        )
        self.assertEqual(fetched["mode"], "fetched_commit")
        self.assertTrue(fetched["network_performed"])
        self.assertEqual(fetched["commit"], new_commit)

    def test_cache_published_while_waiting_still_requires_explicit_fetch(self) -> None:
        repository = "fixture/waiting-fetch-authorization"
        _remote, work, first_commit = self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository, first_commit))
        cache = self.cache_path(repository)
        parked_cache = cache.with_name(cache.name + ".waiting-publisher")
        cache.rename(parked_cache)
        new_commit = self.add_commit(work, "published while caller waits\n")

        @contextlib.contextmanager
        def publish_before_lock_yields(
            _identity: source_cache.RepoIdentity,
            _timeout: float,
        ) -> Iterator[None]:
            parked_cache.rename(cache)
            yield

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_repo_lock",
            side_effect=publish_before_lock_yields,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.ensure_cache(
                    repository,
                    commit=new_commit,
                    cache_root=self.cache_root,
                    fetch_missing=False,
                )
        self.assertEqual(raised.exception.code, "missing_commit")
        self.assertFalse(self.cache_has_local_object(cache, new_commit))

    def test_exact_commit_sha_rejects_annotated_tag_object(self) -> None:
        repository = "fixture/tag-object"
        _remote, work, commit = self.make_remote(repository)
        self.git("tag", "-a", "v1", "-m", "annotated fixture tag", cwd=work)
        self.git("push", "origin", "refs/tags/v1", cwd=work)
        tag_object = self.git("rev-parse", "refs/tags/v1", cwd=work).stdout.strip()

        rejected = self.json_cli(*self.ensure_args(repository, tag_object), ok=False)
        self.assertEqual(rejected["error"]["code"], "commit_type_mismatch")
        self.assertFalse(self.cache_path(repository).exists(), "failed first pinned ensure must not publish a cache")

        self.json_cli(*self.ensure_args(repository, commit))
        self.assertEqual(
            self.git("--git-dir", str(self.cache_path(repository)), "cat-file", "-t", tag_object).stdout.strip(),
            "tag",
        )

    def test_external_object_alternate_cannot_satisfy_local_commit_check(self) -> None:
        repository = "fixture/external-alternate"
        remote, work, first_commit = self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository, first_commit))
        new_commit = self.add_commit(work, "alternate-only commit\n")

        missing = self.json_cli(
            *self.ensure_args(repository, new_commit),
            ok=False,
            env_extra={"GIT_ALTERNATE_OBJECT_DIRECTORIES": str(remote / "objects")},
        )
        self.assertEqual(missing["error"]["code"], "missing_commit")

    def test_global_git_url_rewrite_is_ignored_without_leaking_it(self) -> None:
        repository = "fixture/rewrite-policy"
        _remote, _work, commit = self.make_remote(repository)
        canonical = f"https://github.com/{repository}.git"
        forbidden_value = "rewrite-" + "credential-" + "sentinel"
        self.git(
            "config",
            "--file",
            str(self.gitconfig),
            "--add",
            f"url.https://user:{forbidden_value}@example.invalid/.insteadOf",
            canonical,
        )

        result = self.run_cli(*self.ensure_args(repository, commit))
        payload = json.loads(result.stdout)
        self.assertEqual(payload["repository"], repository)
        self.assertEqual(payload["source_url"], f"https://github.com/{repository}")
        self.assertEqual(payload["commit"], commit)
        self.assertNotIn(forbidden_value, result.stdout + result.stderr)

    def test_commit_and_refresh_are_mutually_exclusive_without_side_effects(self) -> None:
        rejected = self.json_cli(
            *self.ensure_args("fixture/ambiguous-options", "0" * 40),
            "--refresh",
            ok=False,
        )
        self.assertEqual(rejected["error"]["code"], "invalid_options")
        self.assertFalse(self.cache_root.exists())

    def test_explicit_refresh_updates_known_head(self) -> None:
        repository = "fixture/refresh"
        _remote, work, first_commit = self.make_remote(repository)
        initial = self.json_cli(*self.ensure_args(repository))
        self.assertEqual(initial["commit"], first_commit)
        new_commit = self.add_commit(work, "version refreshed\n")

        before = self.json_cli(
            "status",
            repository,
            "--cache-root",
            str(self.cache_root),
            "--json",
        )
        self.assertEqual(before["commit"], first_commit)
        self.assertFalse(before["latest_verified"])

        refreshed = self.json_cli(
            *self.ensure_args(repository),
            "--refresh",
        )
        self.assertEqual(refreshed["mode"], "refreshed")
        self.assertEqual(refreshed["commit"], new_commit)
        self.assertTrue(refreshed["network_performed"])
        self.assertEqual(
            self.git("--git-dir", str(self.cache_path(repository)), "cat-file", "-t", first_commit).stdout.strip(),
            "commit",
        )

    def test_refresh_failure_preserves_existing_cache_and_releases_lock(self) -> None:
        repository = "fixture/refresh-failure"
        remote, _work, commit = self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository, commit))
        cache = self.cache_path(repository)
        offline = remote.with_name(remote.name + ".offline")
        remote.rename(offline)

        failed = self.json_cli(*self.ensure_args(repository), "--refresh", ok=False)
        self.assertEqual(failed["error"]["code"], "git_fetch_failed")
        self.assertTrue(cache.is_dir())
        self.assertEqual(self.git("--git-dir", str(cache), "cat-file", "-t", commit).stdout.strip(), "commit")
        self.assertEqual(
            self.git("--git-dir", str(cache), "rev-parse", "--is-bare-repository").stdout.strip(),
            "true",
        )
        self.assertTrue((self.cache_root / "locks" / "fixture" / "refresh-failure.lock").is_file())

    def test_clone_failure_cleans_partial_and_never_publishes_cache(self) -> None:
        repository = "fixture/missing-remote"
        nonexistent = self.remotes / "does-not-exist.git"
        self.map_remote(repository, nonexistent)

        failed = self.json_cli(*self.ensure_args(repository), ok=False)
        self.assertEqual(failed["error"]["code"], "git_clone_failed")
        cache = self.cache_path(repository)
        self.assertFalse(cache.exists())
        owner_dir = cache.parent
        partials = list(owner_dir.glob(".missing-remote.git.partial-*")) if owner_dir.exists() else []
        self.assertEqual(partials, [])

    def test_failed_first_pinned_ensure_never_publishes_formal_cache(self) -> None:
        repository = "fixture/first-pinned-failure"
        self.make_remote(repository)
        missing_commit = "f" * 40

        missing = self.json_cli(*self.ensure_args(repository, missing_commit), ok=False)
        self.assertEqual(missing["error"]["code"], "missing_commit")
        self.assertFalse(self.cache_path(repository).exists())

        fetch_failed = self.json_cli(
            *self.ensure_args(repository, missing_commit),
            "--fetch-missing",
            ok=False,
        )
        self.assertEqual(fetch_failed["error"]["code"], "git_fetch_failed")
        self.assertFalse(self.cache_path(repository).exists())

    def test_clone_failure_preserves_foreign_partial_replacement(self) -> None:
        repository = "fixture/foreign-partial"
        self.make_remote(repository)
        original_run_git = source_cache._run_git
        foreign_marker: Path | None = None

        def replace_partial(args: list[str] | tuple[str, ...], **kwargs: Any):
            nonlocal foreign_marker
            if "clone" in args:
                partial = Path(args[-1])
                shutil.rmtree(partial)
                partial.mkdir()
                foreign_marker = partial / "foreign-marker"
                foreign_marker.write_text("preserve\n", encoding="utf-8")
                raise source_cache.SourceCacheError("git_clone_failed", "forced fixture failure")
            return original_run_git(args, **kwargs)

        with self.helper_environment(), mock.patch.object(source_cache, "_run_git", side_effect=replace_partial):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.ensure_cache(repository, cache_root=self.cache_root)
        self.assertEqual(raised.exception.code, "git_clone_failed")
        self.assertIsNotNone(foreign_marker)
        self.assertTrue(foreign_marker.is_file() if foreign_marker else False)
        self.assertFalse(self.cache_path(repository).exists())

    def test_partial_cleanup_preserves_replacement_inserted_after_ownership_check(self) -> None:
        repository = "fixture/partial-check-use-race"
        original_run_git = source_cache._run_git
        original_matches = source_cache._owned_directory_matches
        state: dict[str, Any] = {"swapped": False, "marker": None}

        def fail_clone(args: list[str] | tuple[str, ...], **kwargs: Any):
            if "clone" in args:
                raise source_cache.SourceCacheError("git_clone_failed", "forced fixture failure")
            return original_run_git(args, **kwargs)

        def swap_after_positive_check(owned: source_cache.OwnedDirectory) -> bool:
            matched = original_matches(owned)
            if matched and not state["swapped"] and ".partial-" in owned.path.name:
                shutil.rmtree(owned.path)
                owned.path.mkdir(mode=0o700)
                marker = owned.path / "foreign-marker"
                marker.write_text("preserve\n", encoding="utf-8")
                state.update({"swapped": True, "marker": marker})
            return matched

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_run_git",
            side_effect=fail_clone,
        ), mock.patch.object(
            source_cache,
            "_owned_directory_matches",
            side_effect=swap_after_positive_check,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.ensure_cache(repository, cache_root=self.cache_root)
        self.assertEqual(raised.exception.code, "git_clone_failed")
        self.assertTrue(state["swapped"])
        marker = state["marker"]
        self.assertTrue(marker.is_file() if isinstance(marker, Path) else False)
        self.assertFalse(self.cache_path(repository).exists())

    def test_publish_source_replacement_is_restored_and_never_becomes_formal_cache(self) -> None:
        repository = "fixture/publish-source-replacement"
        self.make_remote(repository)
        original_rename = source_cache._rename_noreplace
        state: dict[str, Any] = {"partial": None, "marker": None}

        def replace_source_then_publish(source: Path, destination: Path) -> None:
            shutil.rmtree(source)
            source.mkdir(mode=0o700)
            marker = source / "foreign-marker"
            marker.write_text("preserve\n", encoding="utf-8")
            state.update({"partial": source, "marker": marker})
            original_rename(source, destination)

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_rename_noreplace",
            side_effect=replace_source_then_publish,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.ensure_cache(repository, cache_root=self.cache_root)
        self.assertEqual(raised.exception.code, "path_ownership_lost")
        self.assertFalse(self.cache_path(repository).exists())
        marker = state["marker"]
        self.assertTrue(marker.is_file() if isinstance(marker, Path) else False)

    def test_publish_recovery_clears_formal_path_when_partial_name_is_reoccupied(self) -> None:
        repository = "fixture/publish-recovery-conflict"
        self.make_remote(repository)
        original_rename = source_cache._rename_noreplace
        state: dict[str, Any] = {"partial": None}

        def replace_publish_source_and_reoccupy(source: Path, destination: Path) -> None:
            shutil.rmtree(source)
            source.mkdir(mode=0o700)
            (source / "foreign-one").write_text("preserve one\n", encoding="utf-8")
            original_rename(source, destination)
            source.mkdir(mode=0o700)
            (source / "foreign-two").write_text("preserve two\n", encoding="utf-8")
            state["partial"] = source

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_rename_noreplace",
            side_effect=replace_publish_source_and_reoccupy,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.ensure_cache(repository, cache_root=self.cache_root)
        self.assertEqual(raised.exception.code, "path_ownership_lost")
        final = self.cache_path(repository)
        self.assertFalse(final.exists())
        partial = state["partial"]
        self.assertTrue((partial / "foreign-two").is_file() if isinstance(partial, Path) else False)
        preserved_first = [path for path in final.parent.rglob("foreign-one") if not path.is_relative_to(final)]
        self.assertEqual(len(preserved_first), 1)

    def test_atomic_publish_never_replaces_unexpected_final_path(self) -> None:
        repository = "fixture/publish-conflict"
        self.make_remote(repository)
        final = self.cache_path(repository)
        original_rename = source_cache._rename_noreplace

        def inject_conflict(source: Path, destination: Path) -> None:
            destination.mkdir()
            (destination / "foreign-marker").write_text("preserve\n", encoding="utf-8")
            original_rename(source, destination)

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_rename_noreplace",
            side_effect=inject_conflict,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.ensure_cache(repository, cache_root=self.cache_root)
        self.assertEqual(raised.exception.code, "cache_conflict")
        self.assertEqual((final / "foreign-marker").read_text(encoding="utf-8"), "preserve\n")
        self.assertEqual(list(final.parent.glob(".publish-conflict.git.partial-*")), [])

    def test_two_concurrent_first_ensures_publish_one_cache(self) -> None:
        repository = "fixture/concurrent"
        _remote, _work, commit = self.make_remote(repository)
        command = [sys.executable, str(CLI), *self.ensure_args(repository, commit)]
        call_log = self.root / "git-calls.jsonl"
        overlap_env = {
            **self.env,
            "AIOS_TEST_GIT_CALL_LOG": str(call_log),
            "AIOS_TEST_GIT_CLONE_DELAY": "0.5",
        }
        first = subprocess.Popen(
            command,
            cwd=ROOT,
            env=overlap_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if call_log.exists() and any(
                "clone" in json.loads(line)["args"]
                for line in call_log.read_text(encoding="utf-8").splitlines()
            ):
                break
            time.sleep(0.02)
        else:
            first.kill()
            self.fail("first ensure never reached the forced clone overlap point")
        second = subprocess.Popen(
            command,
            cwd=ROOT,
            env=overlap_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes = [first, second]
        results: list[dict[str, Any]] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, f"stdout={stdout}\nstderr={stderr}")
            results.append(json.loads(stdout))

        self.assertEqual(sum(item["mode"] == "cloned" for item in results), 1)
        self.assertEqual({item["commit"] for item in results}, {commit})
        calls = [json.loads(line)["args"] for line in call_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum("clone" in args for args in calls), 1)
        cache = self.cache_path(repository)
        self.assertTrue(cache.is_dir())
        self.assertEqual(list(cache.parent.glob(".concurrent.git.partial-*")), [])

    def test_active_file_lock_times_out_without_deleting_unknown_lock(self) -> None:
        repository = "fixture/locked"
        self.make_remote(repository)
        lock = self.cache_root / "locks" / "fixture" / "locked.lock"
        lock.parent.mkdir(parents=True)
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = self.json_cli(
                *self.ensure_args(repository),
                "--lock-timeout",
                "0.1",
                ok=False,
            )
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.assertEqual(result["error"]["code"], "cache_locked")
        self.assertTrue(lock.is_file(), "helper must not delete the persistent lock file")
        self.assertFalse(self.cache_path(repository).exists())

    def test_non_finite_lock_timeout_is_rejected_without_creating_cache(self) -> None:
        result = self.json_cli(
            "ensure",
            "fixture/non-finite-lock",
            "--cache-root",
            str(self.cache_root),
            "--lock-timeout",
            "nan",
            "--json",
            ok=False,
        )
        self.assertEqual(result["error"]["code"], "invalid_lock_timeout")
        self.assertFalse(self.cache_root.exists())

        git_timeout = self.json_cli(
            "ensure",
            "fixture/non-finite-git-timeout",
            "--cache-root",
            str(self.cache_root),
            "--git-timeout",
            "inf",
            "--json",
            ok=False,
        )
        self.assertEqual(git_timeout["error"]["code"], "invalid_git_timeout")
        self.assertFalse(self.cache_root.exists())

    def test_lock_owner_does_not_remove_same_content_replacement_inode(self) -> None:
        identity = source_cache.canonicalize("fixture/replaced-lock", self.cache_root)
        with self.helper_environment(), self.assertRaises(source_cache.SourceCacheError) as raised:
            with source_cache._repo_lock(identity, 1):
                identity.lock_path.unlink()
                identity.lock_path.write_text("", encoding="utf-8")
        self.assertEqual(raised.exception.code, "lock_ownership_lost")
        self.assertTrue(identity.lock_path.is_file())
        self.assertEqual(identity.lock_path.read_text(encoding="utf-8"), "")

    def test_worktree_is_detached_pinned_and_outside_bare_cache(self) -> None:
        repository = "fixture/worktree"
        _remote, work, commit = self.make_remote(repository, "pinned content\n")
        self.json_cli(*self.ensure_args(repository, commit))
        cache = self.cache_path(repository)
        readme_blob = self.git("rev-parse", f"{commit}:README.md", cwd=work).stdout.strip()
        self.assertFalse(self.cache_has_local_object(cache, readme_blob))
        target = self.root / "task-local" / "repo"

        receipt = self.json_cli(
            "worktree",
            repository,
            "--commit",
            commit,
            "--path",
            str(target),
            "--cache-root",
            str(self.cache_root),
            "--json",
        )
        self.assertEqual(receipt["mode"], "worktree_created")
        self.assertEqual(receipt["commit"], commit)
        self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "pinned content\n")
        self.assertTrue(self.cache_has_local_object(cache, readme_blob))
        self.assertEqual(self.git("-C", str(target), "rev-parse", "HEAD").stdout.strip(), commit)
        self.assertNotEqual(
            self.git("-C", str(target), "symbolic-ref", "-q", "HEAD", ok=False).returncode,
            0,
        )
        self.assertEqual(
            self.git(
                "--git-dir",
                str(self.cache_path(repository)),
                "rev-parse",
                "--is-bare-repository",
            ).stdout.strip(),
            "true",
        )

    def test_worktree_does_not_run_global_post_checkout_hook(self) -> None:
        repository = "fixture/no-global-hook"
        _remote, _work, commit = self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository, commit))

        marker = self.root / "unexpected-hook-marker"
        hooks = self.root / "global-hooks"
        hooks.mkdir()
        hook = hooks / "post-checkout"
        hook.write_text(f"#!/bin/sh\nprintf touched > {marker}\n", encoding="utf-8")
        hook.chmod(0o755)
        self.git("config", "--file", str(self.gitconfig), "core.hooksPath", str(hooks))

        target = self.root / "task-local" / "hook-safe"
        self.json_cli(
            "worktree",
            repository,
            "--commit",
            commit,
            "--path",
            str(target),
            "--cache-root",
            str(self.cache_root),
            "--json",
        )
        self.assertFalse(marker.exists())

    def test_worktree_does_not_run_global_smudge_filter(self) -> None:
        repository = "fixture/no-global-filter"
        _remote, work, _first_commit = self.make_remote(repository)
        (work / ".gitattributes").write_text("README.md filter=fixture-command\n", encoding="utf-8")
        self.git("add", ".gitattributes", cwd=work)
        self.git("commit", "-m", "add fixture filter attribute", cwd=work)
        self.git("push", "origin", "main", cwd=work)
        commit = self.git("rev-parse", "HEAD", cwd=work).stdout.strip()

        marker = self.root / "unexpected-filter-marker"
        filter_script = self.root / "fixture-smudge-filter"
        filter_script.write_text(
            f"#!/bin/sh\nprintf touched > {marker}\ncat\n",
            encoding="utf-8",
        )
        filter_script.chmod(0o755)
        self.git(
            "config",
            "--file",
            str(self.gitconfig),
            "filter.fixture-command.smudge",
            str(filter_script),
        )
        self.git(
            "config",
            "--file",
            str(self.gitconfig),
            "filter.fixture-command.required",
            "true",
        )

        self.json_cli(*self.ensure_args(repository, commit))
        target = self.root / "task-local" / "filter-safe"
        self.json_cli(
            "worktree",
            repository,
            "--commit",
            commit,
            "--path",
            str(target),
            "--cache-root",
            str(self.cache_root),
            "--json",
        )
        self.assertFalse(marker.exists())
        self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "version one\n")

    def test_worktree_rejects_cache_local_smudge_and_process_filters(self) -> None:
        repository = "fixture/no-cache-local-filter"
        _remote, work, _first_commit = self.make_remote(repository)
        (work / ".gitattributes").write_text("README.md filter=fixture-command\n", encoding="utf-8")
        self.git("add", ".gitattributes", cwd=work)
        self.git("commit", "-m", "add fixture filter attribute", cwd=work)
        self.git("push", "origin", "main", cwd=work)
        commit = self.git("rev-parse", "HEAD", cwd=work).stdout.strip()
        self.json_cli(*self.ensure_args(repository, commit))
        cache = self.cache_path(repository)

        for filter_kind in ("smudge", "process"):
            with self.subTest(filter_kind=filter_kind):
                marker = self.root / f"unexpected-cache-{filter_kind}-marker"
                filter_script = self.root / f"cache-{filter_kind}-filter"
                filter_script.write_text(
                    f"#!/bin/sh\nprintf touched > {marker}\ncat\n",
                    encoding="utf-8",
                )
                filter_script.chmod(0o700)
                key = f"filter.fixture-command.{filter_kind}"
                self.git("--git-dir", str(cache), "config", key, str(filter_script))
                target = self.root / "task-local" / f"cache-{filter_kind}-safe"
                result = self.json_cli(
                    "worktree",
                    repository,
                    "--commit",
                    commit,
                    "--path",
                    str(target),
                    "--cache-root",
                    str(self.cache_root),
                    "--json",
                    ok=False,
                )
                self.assertEqual(result["error"]["code"], "unsafe_git_configuration")
                self.assertFalse(marker.exists())
                self.assertFalse(target.exists())
                self.git("--git-dir", str(cache), "config", "--unset-all", key)

    def test_cache_local_transport_or_credential_config_is_rejected_and_redacted(self) -> None:
        repository = "fixture/no-cache-local-credentials"
        self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository))
        cache = self.cache_path(repository)
        forbidden_value = "authorization-" + "sentinel"

        unsafe_entries = (
            ("http.https://github.com/.extraHeader", f"Authorization: Basic {forbidden_value}"),
            ("http.proxy", f"https://user:{forbidden_value}@example.invalid"),
            ("credential.helper", f"!printf {forbidden_value}"),
            ("include.path", str(self.root / forbidden_value)),
            ("core.fsmonitor", f"printf {forbidden_value}"),
        )
        for key, value in unsafe_entries:
            with self.subTest(key=key):
                self.git("--git-dir", str(cache), "config", key, value)
                result = self.run_cli(
                    "status",
                    repository,
                    "--cache-root",
                    str(self.cache_root),
                    "--json",
                    ok=False,
                )
                payload = json.loads(result.stdout or result.stderr)
                self.assertEqual(payload["error"]["code"], "unsafe_git_configuration")
                self.assertNotIn(forbidden_value, result.stdout + result.stderr)
                self.git("--git-dir", str(cache), "config", "--unset-all", key)

    def test_persistent_alternates_and_external_common_dir_are_rejected(self) -> None:
        repository = "fixture/persistent-alternates"
        remote, _work, commit = self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository, commit))
        cache = self.cache_path(repository)
        alternates = cache / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(str(remote / "objects") + "\n", encoding="utf-8")

        result = self.run_cli(
            "status",
            repository,
            "--cache-root",
            str(self.cache_root),
            "--json",
            ok=False,
        )
        payload = json.loads(result.stdout or result.stderr)
        self.assertEqual(payload["error"]["code"], "cache_invalid")
        self.assertNotIn(str(remote), result.stdout + result.stderr)

        alternates.unlink()
        external_common = self.root / "external-common.git"
        self.git("init", "--bare", str(external_common))
        (cache / "commondir").write_text(str(external_common) + "\n", encoding="utf-8")
        common_result = self.run_cli(
            "status",
            repository,
            "--cache-root",
            str(self.cache_root),
            "--json",
            ok=False,
        )
        common_payload = json.loads(common_result.stdout or common_result.stderr)
        self.assertEqual(common_payload["error"]["code"], "cache_invalid")
        self.assertNotIn(str(external_common), common_result.stdout + common_result.stderr)

    def test_cache_rejects_external_objects_and_worktree_metadata_directories(self) -> None:
        repository = "fixture/metadata-boundary"
        self.make_remote(repository)
        receipt = self.json_cli(*self.ensure_args(repository))
        commit = receipt["commit"]
        cache = self.cache_path(repository)

        external_objects = self.root / "external-objects"
        (cache / "objects").rename(external_objects)
        (cache / "objects").symlink_to(external_objects, target_is_directory=True)
        objects_result = self.run_cli(
            "status",
            repository,
            "--cache-root",
            str(self.cache_root),
            "--json",
            ok=False,
        )
        objects_payload = json.loads(objects_result.stdout or objects_result.stderr)
        self.assertEqual(objects_payload["error"]["code"], "cache_invalid")
        self.assertNotIn(str(external_objects), objects_result.stdout + objects_result.stderr)

        (cache / "objects").unlink()
        external_objects.rename(cache / "objects")
        external_worktrees = self.root / "external-worktrees"
        external_worktrees.mkdir()
        (cache / "worktrees").symlink_to(external_worktrees, target_is_directory=True)
        target = self.root / "task-local" / "metadata-boundary"
        worktree_result = self.run_cli(
            "worktree",
            repository,
            "--commit",
            commit,
            "--path",
            str(target),
            "--cache-root",
            str(self.cache_root),
            "--json",
            ok=False,
        )
        worktree_payload = json.loads(worktree_result.stdout or worktree_result.stderr)
        self.assertEqual(worktree_payload["error"]["code"], "cache_invalid")
        self.assertEqual(list(external_worktrees.iterdir()), [])
        self.assertFalse(target.exists())

    def test_worktree_failure_preserves_foreign_target_replacement(self) -> None:
        repository = "fixture/worktree-replacement"
        self.make_remote(repository)
        receipt = self.json_cli(*self.ensure_args(repository))
        commit = receipt["commit"]
        target = self.root / "task-local" / "foreign-replacement"
        original_run_git = source_cache._run_git

        def replace_target(args: list[str] | tuple[str, ...], **kwargs: Any):
            if "worktree" in args and "add" in args:
                if target.exists():
                    shutil.rmtree(target)
                target.mkdir(parents=True)
                (target / "foreign-marker").write_text("preserve\n", encoding="utf-8")
                raise source_cache.SourceCacheError("git_worktree_failed", "forced fixture failure")
            return original_run_git(args, **kwargs)

        with self.helper_environment(), mock.patch.object(source_cache, "_run_git", side_effect=replace_target):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.create_worktree(
                    repository,
                    commit=commit,
                    path=target,
                    cache_root=self.cache_root,
                )
        self.assertEqual(raised.exception.code, "git_worktree_failed")
        self.assertEqual((target / "foreign-marker").read_text(encoding="utf-8"), "preserve\n")

    def test_worktree_cleanup_preserves_replacement_inserted_after_ownership_check(self) -> None:
        repository = "fixture/worktree-check-use-race"
        self.make_remote(repository)
        receipt = self.json_cli(*self.ensure_args(repository))
        commit = receipt["commit"]
        target = self.root / "task-local" / "race-target"
        original_run_git = source_cache._run_git
        original_matches = source_cache._owned_directory_matches
        state: dict[str, Any] = {"checks": 0, "swapped": False, "marker": None}

        def fail_worktree_add(args: list[str] | tuple[str, ...], **kwargs: Any):
            if "worktree" in args and "add" in args:
                raise source_cache.SourceCacheError("git_worktree_failed", "forced fixture failure")
            return original_run_git(args, **kwargs)

        def swap_after_cleanup_check(owned: source_cache.OwnedDirectory) -> bool:
            matched = original_matches(owned)
            if matched and owned.path == target:
                state["checks"] += 1
                if state["checks"] == 2:
                    shutil.rmtree(target)
                    target.mkdir(mode=0o700)
                    marker = target / "foreign-marker"
                    marker.write_text("preserve\n", encoding="utf-8")
                    state.update({"swapped": True, "marker": marker})
            return matched

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_run_git",
            side_effect=fail_worktree_add,
        ), mock.patch.object(
            source_cache,
            "_owned_directory_matches",
            side_effect=swap_after_cleanup_check,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.create_worktree(
                    repository,
                    commit=commit,
                    path=target,
                    cache_root=self.cache_root,
                )
        self.assertEqual(raised.exception.code, "git_worktree_failed")
        self.assertTrue(state["swapped"])
        marker = state["marker"]
        self.assertTrue(marker.is_file() if isinstance(marker, Path) else False)

    def test_marker_present_cleanup_quarantines_target_before_metadata_removal(self) -> None:
        repository = "fixture/worktree-marker-race"
        self.make_remote(repository)
        receipt = self.json_cli(*self.ensure_args(repository))
        commit = receipt["commit"]
        target = self.root / "task-local" / "marker-race-target"
        original_run_git = source_cache._run_git
        original_matches = source_cache._owned_directory_matches
        state: dict[str, Any] = {
            "target_checks": 0,
            "swapped": False,
            "marker": None,
            "gitdir": None,
        }

        def force_post_checkout_verification_failure(
            args: list[str] | tuple[str, ...],
            **kwargs: Any,
        ):
            if "symbolic-ref" in args and str(target) in args:
                return subprocess.CompletedProcess(args, 0, "refs/heads/main\n", "")
            return original_run_git(args, **kwargs)

        def swap_target_at_quarantine_check(owned: source_cache.OwnedDirectory) -> bool:
            matched = original_matches(owned)
            if matched and owned.path == target:
                state["target_checks"] += 1
                if state["target_checks"] == 3:
                    marker_text = (target / ".git").read_text(encoding="utf-8")
                    state["gitdir"] = Path(marker_text.removeprefix("gitdir: ").strip())
                    shutil.rmtree(target)
                    target.mkdir(mode=0o700)
                    marker = target / "foreign-marker"
                    marker.write_text("preserve\n", encoding="utf-8")
                    state.update({"swapped": True, "marker": marker})
            return matched

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_run_git",
            side_effect=force_post_checkout_verification_failure,
        ), mock.patch.object(
            source_cache,
            "_owned_directory_matches",
            side_effect=swap_target_at_quarantine_check,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.create_worktree(
                    repository,
                    commit=commit,
                    path=target,
                    cache_root=self.cache_root,
                )
        self.assertEqual(raised.exception.code, "git_worktree_failed")
        self.assertTrue(state["swapped"])
        marker = state["marker"]
        self.assertTrue(marker.is_file() if isinstance(marker, Path) else False)
        gitdir = state["gitdir"]
        self.assertTrue(gitdir.is_dir() if isinstance(gitdir, Path) else False)

    def test_marker_present_cleanup_removes_only_verified_target_and_metadata(self) -> None:
        repository = "fixture/worktree-marker-owned-cleanup"
        self.make_remote(repository)
        receipt = self.json_cli(*self.ensure_args(repository))
        commit = receipt["commit"]
        target = self.root / "task-local" / "owned-marker-target"
        original_run_git = source_cache._run_git
        original_capture = source_cache._capture_verified_worktree_metadata
        state: dict[str, Path | None] = {"gitdir": None}

        def force_post_checkout_verification_failure(
            args: list[str] | tuple[str, ...],
            **kwargs: Any,
        ):
            if "symbolic-ref" in args and str(target) in args:
                return subprocess.CompletedProcess(args, 0, "refs/heads/main\n", "")
            return original_run_git(args, **kwargs)

        def capture_metadata(
            identity: source_cache.RepoIdentity,
            owned: source_cache.OwnedDirectory,
            gitdir: Path,
        ) -> source_cache.OwnedDirectory:
            state["gitdir"] = gitdir
            return original_capture(identity, owned, gitdir)

        with self.helper_environment(), mock.patch.object(
            source_cache,
            "_run_git",
            side_effect=force_post_checkout_verification_failure,
        ), mock.patch.object(
            source_cache,
            "_capture_verified_worktree_metadata",
            side_effect=capture_metadata,
        ):
            with self.assertRaises(source_cache.SourceCacheError) as raised:
                source_cache.create_worktree(
                    repository,
                    commit=commit,
                    path=target,
                    cache_root=self.cache_root,
                )
        self.assertEqual(raised.exception.code, "git_worktree_failed")
        self.assertFalse(target.exists())
        gitdir = state["gitdir"]
        self.assertFalse(gitdir.exists() if isinstance(gitdir, Path) else True)
        listed = self.git(
            "--git-dir",
            str(self.cache_path(repository)),
            "worktree",
            "list",
            "--porcelain",
        ).stdout
        self.assertNotIn(str(target), listed)

    def test_git_subprocess_does_not_consume_ambient_home_auth_file(self) -> None:
        repository = "fixture/home-auth-boundary"
        observed_authorization: list[bool] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                observed_authorization.append(self.headers.get("Authorization") is not None)
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="fixture"')
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        canonical = f"https://github.com/{repository}.git"
        replacement = f"http://127.0.0.1:{port}/{repository}.git"
        wrapper_dir = self.root / "home-auth-wrapper"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        wrapper.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import os
                import sys
                real_git = {self.real_git!r}
                injected = [
                    "-c", "protocol.http.allow=always",
                    "-c", {f"url.{replacement}.insteadOf={canonical}"!r},
                ]
                os.execv(real_git, [real_git, *injected, *sys.argv[1:]])
                """
            ),
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        (self.home / ".netrc").write_text(
            "machine 127.0.0.1 login fixture-user " + "password fixture-value\n",
            encoding="utf-8",
        )
        (self.home / ".netrc").chmod(0o600)
        try:
            result = self.run_cli(
                *self.ensure_args(repository),
                ok=False,
                env_extra={
                    "PATH": str(wrapper_dir) + os.pathsep + self.env["PATH"],
                    "NO_PROXY": "127.0.0.1,localhost",
                    "no_proxy": "127.0.0.1,localhost",
                    "HTTP_PROXY": "",
                    "http_proxy": "",
                    "HTTPS_PROXY": "",
                    "https_proxy": "",
                    "ALL_PROXY": "",
                    "all_proxy": "",
                },
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        payload = json.loads(result.stdout or result.stderr)
        self.assertEqual(payload["error"]["code"], "git_clone_failed")
        self.assertGreaterEqual(len(observed_authorization), 1)
        self.assertFalse(any(observed_authorization))
        self.assertNotIn("fixture-value", result.stdout + result.stderr)
        self.assertFalse(self.cache_path(repository).exists())

    def test_production_helper_has_no_fixture_transport_escape(self) -> None:
        source = CLI.read_text(encoding="utf-8")
        self.assertNotIn("AIOS_GITHUB_SOURCE_CACHE_TEST_MODE", source)
        self.assertNotIn("_test_file_rewrite_allowed", source)
        self.assertNotIn("_fixture_test_mode", source)

    def test_worktree_rejects_cache_internal_or_existing_target(self) -> None:
        repository = "fixture/worktree-boundary"
        _remote, _work, commit = self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository, commit))

        inside = self.cache_root / "task-worktree"
        unsafe = self.json_cli(
            "worktree",
            repository,
            "--commit",
            commit,
            "--path",
            str(inside),
            "--cache-root",
            str(self.cache_root),
            "--json",
            ok=False,
        )
        self.assertEqual(unsafe["error"]["code"], "unsafe_worktree_path")
        self.assertFalse(inside.exists())

        existing = self.root / "existing-empty"
        existing.mkdir()
        occupied = self.json_cli(
            "worktree",
            repository,
            "--commit",
            commit,
            "--path",
            str(existing),
            "--cache-root",
            str(self.cache_root),
            "--json",
            ok=False,
        )
        self.assertEqual(occupied["error"]["code"], "worktree_path_exists")
        self.assertEqual(list(existing.iterdir()), [])

    def test_cache_identity_error_redacts_existing_remote_credentials(self) -> None:
        repository = "fixture/mismatch"
        self.make_remote(repository)
        self.json_cli(*self.ensure_args(repository))
        cache = self.cache_path(repository)
        self.git(
            "--git-dir",
            str(cache),
            "config",
            "remote.origin.url",
            "https://oauth2:remote-secret@github.com/fixture/other.git",
        )

        result = self.run_cli(
            "status",
            repository,
            "--cache-root",
            str(self.cache_root),
            "--json",
            ok=False,
        )
        output = result.stdout + result.stderr
        payload = json.loads(result.stdout or result.stderr)
        self.assertEqual(payload["error"]["code"], "cache_identity_mismatch")
        self.assertNotIn("remote-secret", output)
        self.assertNotIn("oauth2", output)

    def test_existing_github_search_cli_surface_still_loads(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SEARCH_CLI), "--help"],
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--readme-top-n", result.stdout)
        self.assertIn("--prefer-gh", result.stdout)

        module_name = "aios_test_github_repo_search"
        spec = importlib.util.spec_from_file_location(module_name, SEARCH_CLI)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            args = module.parse_args(["--query", "fixture", "--out", str(self.root / "search-output")])
            output_dir = self.root / "empty-search-output"
            with mock.patch.object(module, "http_search", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                returncode = module.main(
                    [
                        "--query",
                        "fixture",
                        "--out",
                        str(output_dir),
                        "--no-gh",
                        "--no-proxy",
                    ]
                )
        finally:
            sys.modules.pop(module_name, None)

        self.assertEqual(args.limit_per_query, 30)
        self.assertEqual(args.min_stars, 100)
        self.assertEqual(args.top_k, 40)
        self.assertEqual(args.readme_top_n, 40)
        self.assertEqual(args.metadata_top_n, 80)
        self.assertTrue(args.prefer_gh)
        self.assertFalse(args.refresh_readme)
        self.assertEqual(returncode, 0)
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {key: manifest[key] for key in ("raw_count", "deduped_count", "filtered_count", "candidate_count")},
            {"raw_count": 0, "deduped_count": 0, "filtered_count": 0, "candidate_count": 0},
        )
        self.assertTrue(
            {"started_at", "finished_at", "topic", "constraints", "args", "prefer_gh", "rate_limit_summary"}
            <= set(manifest)
        )
        self.assertNotIn("source_acquisition", manifest)
        self.assertFalse(self.cache_root.exists())


if __name__ == "__main__":
    unittest.main()

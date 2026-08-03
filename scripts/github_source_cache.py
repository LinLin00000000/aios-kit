#!/usr/bin/env python3
"""Safe, stdlib-only GitHub source acquisition cache helper.

The helper keeps one rebuildable bare cache per canonical public GitHub
``owner/repo`` and creates detached task-local worktrees at full commit SHAs.
It intentionally does not manage search candidates, conclusions, backups,
private credentials, garbage collection, or legacy clone migration.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import datetime as dt
import errno
import fcntl
import json
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Sequence

ERROR_SCHEMA = "aios.github-source-cache-error.v1"
CANONICAL_SCHEMA = "aios.github-source-cache-canonical.v1"
STATUS_SCHEMA = "aios.github-source-cache-status.v1"
RECEIPT_SCHEMA = "aios.github-source-cache-receipt.v1"
WORKTREE_SCHEMA = "aios.github-source-worktree-receipt.v1"
FULL_SHA_RE = re.compile(r"[0-9a-fA-F]{40}\Z")
OWNER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z")
REPO_RE = re.compile(r"[A-Za-z0-9._-]+\Z")
AT_FDCWD = -100
RENAME_NOREPLACE = 1
SAFE_CACHE_CONFIG_KEYS = {
    "core.repositoryformatversion",
    "core.filemode",
    "core.bare",
    "remote.origin.url",
    "remote.origin.fetch",
    "remote.origin.promisor",
    "remote.origin.partialclonefilter",
}


class SourceCacheError(Exception):
    """Expected fail-closed error with a safe user-facing message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class RepoIdentity:
    owner: str
    name: str
    repository: str
    source_url: str
    clone_url: str
    cache_root: Path
    cache_path: Path
    lock_path: Path


@dataclass(frozen=True)
class OwnedDirectory:
    path: Path
    device: int
    inode: int
    fd: int


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _default_cache_root() -> Path:
    return Path.home() / "aios" / "cache" / "github"


def _resolved_root(cache_root: str | os.PathLike[str] | None) -> Path:
    raw = Path(cache_root).expanduser() if cache_root is not None else _default_cache_root()
    try:
        return raw.resolve(strict=False)
    except OSError as exc:
        raise SourceCacheError("unsafe_cache_root", "cache root cannot be resolved safely") from exc


def _reject_controls(value: str) -> None:
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SourceCacheError("invalid_repository", "repository identity is empty or malformed")


def _split_repository(value: str) -> tuple[str, str]:
    _reject_controls(value)
    if value != value.strip():
        raise SourceCacheError("invalid_repository", "repository identity must not contain surrounding whitespace")
    text = value
    if "?" in text or "#" in text:
        raise SourceCacheError("invalid_repository", "query and fragment components are not supported")

    owner: str
    name: str
    if text.startswith("git@"):
        prefix = "git@github.com:"
        if not text.lower().startswith(prefix):
            raise SourceCacheError("unsupported_host", "only public github.com repository identities are supported")
        path = text[len(prefix) :]
        if "@" in path or ":" in path:
            raise SourceCacheError("invalid_repository", "repository identity is malformed")
        path = path.rstrip("/")
        parts = path.split("/")
        if len(parts) != 2:
            raise SourceCacheError("invalid_repository", "repository identity must contain exactly owner/repo")
        owner, name = parts
    elif "://" in text:
        try:
            parsed = urllib.parse.urlsplit(text)
            port = parsed.port
        except (TypeError, ValueError) as exc:
            raise SourceCacheError("invalid_repository", "repository URL is malformed") from exc
        if parsed.scheme.lower() != "https":
            raise SourceCacheError("unsupported_scheme", "only HTTPS and git@github.com SSH identities are supported")
        if parsed.username is not None or parsed.password is not None:
            raise SourceCacheError("embedded_credential", "embedded URL credentials are not supported")
        if (parsed.hostname or "").lower() != "github.com" or port is not None:
            raise SourceCacheError("unsupported_host", "only public github.com repository identities are supported")
        if parsed.query or parsed.fragment:
            raise SourceCacheError("invalid_repository", "query and fragment components are not supported")
        path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "":
            raise SourceCacheError("invalid_repository", "repository URL must contain exactly owner/repo")
        owner, name = parts[1], parts[2]
    else:
        if any(token in text for token in ("@", ":", "\\")):
            raise SourceCacheError("invalid_repository", "repository identity is malformed")
        parts = text.rstrip("/").split("/")
        if len(parts) != 2:
            raise SourceCacheError("invalid_repository", "repository identity must contain exactly owner/repo")
        owner, name = parts

    if name.lower().endswith(".git"):
        name = name[:-4]
    if not owner or not name or owner in {".", ".."} or name in {".", ".."}:
        raise SourceCacheError("invalid_repository", "repository owner and name must be non-empty")
    if not OWNER_RE.fullmatch(owner) or not REPO_RE.fullmatch(name):
        raise SourceCacheError("invalid_repository", "repository owner or name contains unsupported characters")
    return owner.lower(), name.lower()


def _assert_no_layout_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise SourceCacheError("unsafe_cache_layout", f"{label} must not be a symbolic link")


def canonicalize(
    repository: str,
    cache_root: str | os.PathLike[str] | None = None,
) -> RepoIdentity:
    owner, name = _split_repository(repository)
    root = _resolved_root(cache_root)
    repos_root = root / "repos"
    locks_root = root / "locks"
    owner_cache = repos_root / owner
    owner_locks = locks_root / owner
    for candidate, label in (
        (repos_root, "cache repos directory"),
        (locks_root, "cache locks directory"),
        (owner_cache, "repository owner cache directory"),
        (owner_locks, "repository owner lock directory"),
    ):
        if candidate.exists() or candidate.is_symlink():
            _assert_no_layout_symlink(candidate, label)
    cache_path = owner_cache / f"{name}.git"
    lock_path = owner_locks / f"{name}.lock"
    if cache_path.is_symlink():
        raise SourceCacheError("unsafe_cache_layout", "cache repository must not be a symbolic link")
    canonical = f"{owner}/{name}"
    return RepoIdentity(
        owner=owner,
        name=name,
        repository=canonical,
        source_url=f"https://github.com/{canonical}",
        clone_url=f"https://github.com/{canonical}.git",
        cache_root=root,
        cache_path=cache_path,
        lock_path=lock_path,
    )


def _canonical_payload(identity: RepoIdentity) -> dict[str, Any]:
    return {
        "schema": CANONICAL_SCHEMA,
        "ok": True,
        "repository": identity.repository,
        "owner": identity.owner,
        "name": identity.name,
        "source_url": identity.source_url,
        "cache_root": str(identity.cache_root),
        "cache_path": str(identity.cache_path),
        "lock_path": str(identity.lock_path),
    }


def _prepare_layout(identity: RepoIdentity) -> None:
    for candidate, label in (
        (identity.cache_root, "cache root"),
        (identity.cache_root / "repos", "cache repos directory"),
        (identity.cache_root / "locks", "cache locks directory"),
        (identity.cache_path.parent, "repository owner cache directory"),
        (identity.lock_path.parent, "repository owner lock directory"),
    ):
        if candidate.exists() or candidate.is_symlink():
            _assert_no_layout_symlink(candidate, label)
        candidate.mkdir(parents=True, exist_ok=True)
        _assert_no_layout_symlink(candidate, label)


def _git_env(*, allow_lazy_fetch: bool = False) -> dict[str, str]:
    # Git configuration and GIT_* environment are executable input. Keep
    # ordinary process settings such as PATH, proxy variables, and locale,
    # remove every ambient Git override, and hide user-home credential files.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.pop("SSH_ASKPASS", None)
    env.pop("CURL_HOME", None)
    env.pop("NETRC", None)
    env["HOME"] = os.devnull
    env["XDG_CONFIG_HOME"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = os.devnull
    env["SSH_ASKPASS"] = os.devnull
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    env["GIT_PAGER"] = "cat"
    if not allow_lazy_fetch:
        env["GIT_NO_LAZY_FETCH"] = "1"
    return env


def _git_prefix(cache_path: Path | None = None) -> list[str]:
    prefix = ["--git-dir", str(cache_path)] if cache_path is not None else []
    prefix.extend(
        [
            "-c",
            "credential.helper=",
            "-c",
            "credential.interactive=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
        ]
    )
    return prefix


def _run_git(
    args: Sequence[str],
    *,
    error_code: str,
    timeout: float = 300,
    check: bool = True,
    allow_lazy_fetch: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            env=_git_env(allow_lazy_fetch=allow_lazy_fetch),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourceCacheError(error_code, "Git operation could not be completed") from exc
    if check and result.returncode != 0:
        raise SourceCacheError(error_code, f"Git operation failed with exit code {result.returncode}")
    return result


def _read_cache_config(cache: Path) -> dict[str, list[str]]:
    config_path = cache / "config"
    try:
        config_stat = config_path.lstat()
    except OSError as exc:
        raise SourceCacheError("cache_invalid", "repository cache configuration is missing or unsafe") from exc
    if not stat.S_ISREG(config_stat.st_mode) or config_path.is_symlink():
        raise SourceCacheError("cache_invalid", "repository cache configuration is missing or unsafe")
    result = _run_git(
        [*_git_prefix(), "config", "--file", str(config_path), "--null", "--list", "--no-includes"],
        error_code="unsafe_git_configuration",
    )
    entries: dict[str, list[str]] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        key, separator, value = record.partition("\n")
        if not separator:
            raise SourceCacheError("unsafe_git_configuration", "repository cache configuration is malformed")
        lowered = key.lower()
        if lowered not in SAFE_CACHE_CONFIG_KEYS:
            raise SourceCacheError(
                "unsafe_git_configuration",
                "repository cache contains unsupported executable, credential, or transport configuration",
            )
        entries.setdefault(lowered, []).append(value)
    return entries


def _single_config(entries: dict[str, list[str]], key: str) -> str:
    values = entries.get(key, [])
    if len(values) != 1:
        raise SourceCacheError("cache_invalid", "repository cache configuration is incomplete or ambiguous")
    return values[0]


def _validate_cache_config(identity: RepoIdentity, cache: Path) -> None:
    entries = _read_cache_config(cache)
    if _single_config(entries, "core.repositoryformatversion") != "1":
        raise SourceCacheError("cache_invalid", "repository cache format is not the expected partial-clone format")
    if _single_config(entries, "core.filemode") not in {"true", "false"}:
        raise SourceCacheError("cache_invalid", "repository cache filemode configuration is malformed")
    if _single_config(entries, "core.bare") != "true":
        raise SourceCacheError("cache_invalid", "repository cache is not configured as bare")
    if _single_config(entries, "remote.origin.url") != identity.clone_url:
        raise SourceCacheError(
            "cache_identity_mismatch",
            "repository cache origin does not match the canonical GitHub identity",
        )
    if _single_config(entries, "remote.origin.promisor") != "true":
        raise SourceCacheError("cache_invalid", "repository cache is not configured as a promisor remote")
    if _single_config(entries, "remote.origin.partialclonefilter") != "blob:none":
        raise SourceCacheError("cache_invalid", "repository cache partial-clone filter is not blob:none")
    for refspec in entries.get("remote.origin.fetch", []):
        if refspec not in {
            "+refs/heads/*:refs/remotes/origin/*",
            "+refs/heads/*:refs/heads/*",
        }:
            raise SourceCacheError("unsafe_git_configuration", "repository cache contains an unsupported fetch refspec")


def _validate_cache_tree(cache: Path) -> None:
    """Reject path indirection inside the bare repository control tree."""

    required_directories = (cache / "objects", cache / "refs")
    required_files = (cache / "HEAD", cache / "config")
    try:
        for entry in required_directories:
            entry_stat = entry.lstat()
            if not stat.S_ISDIR(entry_stat.st_mode) or entry.is_symlink():
                raise SourceCacheError("cache_invalid", "repository cache metadata directory is unsafe")
        for entry in required_files:
            entry_stat = entry.lstat()
            if not stat.S_ISREG(entry_stat.st_mode) or entry.is_symlink():
                raise SourceCacheError("cache_invalid", "repository cache metadata file is unsafe")

        for current, directories, files in os.walk(cache, topdown=True, followlinks=False):
            base = Path(current)
            for name in (*directories, *files):
                entry = base / name
                entry_stat = entry.lstat()
                if entry.is_symlink() or not (
                    stat.S_ISDIR(entry_stat.st_mode) or stat.S_ISREG(entry_stat.st_mode)
                ):
                    raise SourceCacheError("cache_invalid", "repository cache contains unsafe path indirection")
    except SourceCacheError:
        raise
    except OSError as exc:
        raise SourceCacheError("cache_invalid", "repository cache metadata cannot be inspected safely") from exc


def _validate_cache(identity: RepoIdentity, path: Path | None = None) -> None:
    cache = path or identity.cache_path
    try:
        cache_stat = cache.lstat()
    except FileNotFoundError as exc:
        raise SourceCacheError("cache_missing", "repository cache does not exist") from exc
    except OSError as exc:
        raise SourceCacheError("cache_invalid", "repository cache cannot be inspected safely") from exc
    if not stat.S_ISDIR(cache_stat.st_mode) or cache.is_symlink():
        raise SourceCacheError("cache_invalid", "repository cache is not a safe directory")
    _validate_cache_tree(cache)
    if (cache / "commondir").exists() or (cache / "commondir").is_symlink():
        raise SourceCacheError("cache_invalid", "repository cache must own its Git common directory")
    alternates = cache / "objects" / "info" / "alternates"
    if alternates.exists() or alternates.is_symlink():
        try:
            alternate_stat = alternates.lstat()
            alternate_data = alternates.read_bytes()
        except OSError as exc:
            raise SourceCacheError("cache_invalid", "repository cache alternates cannot be inspected safely") from exc
        if not stat.S_ISREG(alternate_stat.st_mode) or alternates.is_symlink() or alternate_data.strip():
            raise SourceCacheError("cache_invalid", "repository cache must not use external object alternates")

    _validate_cache_config(identity, cache)
    bare = _run_git(
        [*_git_prefix(cache), "rev-parse", "--is-bare-repository"],
        error_code="cache_invalid",
        check=False,
    )
    if bare.returncode != 0 or bare.stdout.strip() != "true":
        raise SourceCacheError("cache_invalid", "repository cache is not a valid bare Git repository")
    common = _run_git(
        [*_git_prefix(cache), "rev-parse", "--git-common-dir"],
        error_code="cache_invalid",
        check=False,
    )
    if common.returncode != 0:
        raise SourceCacheError("cache_invalid", "repository cache common directory cannot be verified")
    common_path = Path(common.stdout.strip())
    if not common_path.is_absolute():
        common_path = cache / common_path
    try:
        if common_path.resolve(strict=True) != cache.resolve(strict=True):
            raise SourceCacheError("cache_invalid", "repository cache common directory escapes the cache")
    except OSError as exc:
        raise SourceCacheError("cache_invalid", "repository cache common directory cannot be verified") from exc


def _normalize_full_sha(value: str | None) -> str | None:
    if value is None:
        return None
    if not FULL_SHA_RE.fullmatch(value):
        raise SourceCacheError("invalid_commit", "commit must be a full 40-character hexadecimal SHA")
    return value.lower()


def _validate_git_timeout(value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise SourceCacheError("invalid_git_timeout", "Git timeout must be a positive finite number")


def _has_commit(cache_path: Path, commit: str) -> bool:
    result = _run_git(
        [*_git_prefix(cache_path), "cat-file", "-t", commit],
        error_code="cache_invalid",
        check=False,
    )
    if result.returncode != 0:
        return False
    if result.stdout.strip() != "commit":
        raise SourceCacheError("commit_type_mismatch", "requested object is not an exact commit object")
    return True


def _head_commit(cache_path: Path) -> str | None:
    result = _run_git(
        [*_git_prefix(cache_path), "rev-parse", "--verify", "HEAD^{commit}"],
        error_code="cache_invalid",
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip().lower()
    return value if FULL_SHA_RE.fullmatch(value) else None


def _normalize_cited_paths(paths: Sequence[str] | None) -> list[str]:
    output: list[str] = []
    for raw in paths or []:
        if not raw or len(raw) > 4096 or "\\" in raw:
            raise SourceCacheError("invalid_cited_path", "cited paths must be safe repository-relative POSIX paths")
        _reject_controls(raw)
        path = PurePosixPath(raw)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise SourceCacheError("invalid_cited_path", "cited paths must be safe repository-relative POSIX paths")
        normalized = path.as_posix()
        if normalized not in output:
            output.append(normalized)
    return output


@contextlib.contextmanager
def _repo_lock(identity: RepoIdentity, timeout: float) -> Iterator[None]:
    if not math.isfinite(timeout) or timeout < 0:
        raise SourceCacheError("invalid_lock_timeout", "lock timeout must be non-negative")
    _prepare_layout(identity)
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    fd = -1
    try:
        fd = os.open(identity.lock_path, flags, 0o600)
        lock_stat = os.fstat(fd)
        if not stat.S_ISREG(lock_stat.st_mode):
            os.close(fd)
            fd = -1
            raise OSError(errno.EINVAL, "lock path is not a regular file")
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        raise SourceCacheError("cache_locked", "repository cache lock path is unsafe or unavailable") from exc
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise SourceCacheError(
                    "cache_locked",
                    "repository cache is locked by another operation; the lock was not removed",
                )
            time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))
        except OSError as exc:
            os.close(fd)
            raise SourceCacheError("cache_locked", "repository cache lock could not be acquired") from exc
    try:
        yield
    finally:
        try:
            current = identity.lock_path.lstat()
            ownership_lost = (
                not stat.S_ISREG(current.st_mode)
                or current.st_dev != lock_stat.st_dev
                or current.st_ino != lock_stat.st_ino
            )
        except OSError:
            ownership_lost = True
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        if ownership_lost:
            raise SourceCacheError(
                "lock_ownership_lost",
                "repository cache lock changed while the operation was running; replacement lock was preserved",
            )


def _capture_owned_directory(path: Path) -> OwnedDirectory:
    fd = -1
    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        current = os.fstat(fd)
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        raise SourceCacheError("path_ownership_lost", "owned directory cannot be inspected safely") from exc
    if not stat.S_ISDIR(current.st_mode):
        os.close(fd)
        raise SourceCacheError("path_ownership_lost", "owned directory was replaced or changed type")
    return OwnedDirectory(path=path, device=current.st_dev, inode=current.st_ino, fd=fd)


def _close_owned_directory(owned: OwnedDirectory) -> None:
    try:
        os.close(owned.fd)
    except OSError:
        pass


def _owned_directory_matches(owned: OwnedDirectory) -> bool:
    try:
        current = owned.path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(current.st_mode)
        and not owned.path.is_symlink()
        and current.st_dev == owned.device
        and current.st_ino == owned.inode
    )


def _unique_sibling(path: Path, purpose: str) -> Path:
    for _attempt in range(16):
        candidate = path.parent / f".{path.name}.{purpose}-{os.getpid()}-{secrets.token_hex(8)}"
        try:
            candidate.lstat()
        except FileNotFoundError:
            return candidate
        except OSError as exc:
            raise SourceCacheError("path_ownership_lost", "temporary sibling cannot be inspected safely") from exc
    raise SourceCacheError("path_ownership_lost", "unique temporary sibling could not be allocated")


def _clear_directory_fd(fd: int) -> bool:
    """Remove children through an already-open directory, never by a replaced root path."""

    try:
        names = os.listdir(fd)
    except OSError:
        return False
    for name in names:
        child_fd = -1
        try:
            child_stat = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(child_stat.st_mode):
                child_fd = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=fd,
                )
                if not _clear_directory_fd(child_fd):
                    return False
                os.close(child_fd)
                child_fd = -1
                os.rmdir(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)
        except FileNotFoundError:
            continue
        except OSError:
            return False
        finally:
            if child_fd >= 0:
                os.close(child_fd)
    return True


def _rename_noreplace_kernel(source: Path, destination: Path) -> None:
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        raise SourceCacheError("unsupported_platform", "atomic no-replace cache publication requires Linux renameat2")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    ) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise SourceCacheError("cache_conflict", "repository cache appeared during first acquisition")
    raise SourceCacheError("cache_publish_failed", "repository cache could not be moved atomically")


def _quarantine_owned_directory(owned: OwnedDirectory) -> OwnedDirectory | None:
    """Move an owned path aside, restoring any raced replacement instead of deleting it."""

    if not _owned_directory_matches(owned):
        _close_owned_directory(owned)
        return None
    quarantine = _unique_sibling(owned.path, "cleanup")
    try:
        _rename_noreplace_kernel(owned.path, quarantine)
    except SourceCacheError:
        _close_owned_directory(owned)
        return None
    moved = OwnedDirectory(quarantine, owned.device, owned.inode, owned.fd)
    if _owned_directory_matches(moved):
        return moved
    try:
        _rename_noreplace_kernel(quarantine, owned.path)
    except SourceCacheError:
        pass
    _close_owned_directory(moved)
    return None


def _destroy_quarantined_directory(moved: OwnedDirectory) -> bool:
    if not _clear_directory_fd(moved.fd):
        _close_owned_directory(moved)
        return False
    if not _owned_directory_matches(moved):
        _close_owned_directory(moved)
        return False
    try:
        os.rmdir(moved.path)
    except OSError:
        _close_owned_directory(moved)
        return False
    _close_owned_directory(moved)
    return not moved.path.exists() and not moved.path.is_symlink()


def _restore_quarantined_directory(moved: OwnedDirectory, original: Path) -> bool:
    if not _owned_directory_matches(moved):
        _close_owned_directory(moved)
        return False
    try:
        _rename_noreplace_kernel(moved.path, original)
    except SourceCacheError:
        _close_owned_directory(moved)
        return False
    restored = OwnedDirectory(original, moved.device, moved.inode, moved.fd)
    matched = _owned_directory_matches(restored)
    _close_owned_directory(restored)
    return matched


def _cleanup_owned_directory(owned: OwnedDirectory) -> bool:
    moved = _quarantine_owned_directory(owned)
    if moved is None:
        return False
    return _destroy_quarantined_directory(moved)


def _rename_noreplace(source: Path, destination: Path) -> None:
    _rename_noreplace_kernel(source, destination)


def _recover_displaced_publish(destination: Path, original: Path) -> bool:
    """Clear the formal path while preserving raced content at a non-formal sibling."""

    try:
        _rename_noreplace_kernel(destination, original)
        return not destination.exists() and not destination.is_symlink()
    except SourceCacheError:
        pass
    try:
        displaced = _unique_sibling(original, "displaced")
        _rename_noreplace_kernel(destination, displaced)
    except SourceCacheError:
        return False
    return not destination.exists() and not destination.is_symlink()


def _clone_partial(identity: RepoIdentity, *, git_timeout: float) -> OwnedDirectory:
    partial = Path(
        tempfile.mkdtemp(
            prefix=f".{identity.name}.git.partial-",
            dir=str(identity.cache_path.parent),
        )
    )
    owned = _capture_owned_directory(partial)
    try:
        _run_git(
            [
                *_git_prefix(),
                "clone",
                "--bare",
                "--filter=blob:none",
                "--origin",
                "origin",
                identity.clone_url,
                str(partial),
            ],
            error_code="git_clone_failed",
            timeout=git_timeout,
        )
        if not _owned_directory_matches(owned):
            raise SourceCacheError("path_ownership_lost", "partial cache directory was replaced during clone")
        _validate_cache(identity, partial)
        return owned
    except Exception:
        _cleanup_owned_directory(owned)
        raise


def _publish_partial(identity: RepoIdentity, owned: OwnedDirectory) -> None:
    if not _owned_directory_matches(owned):
        raise SourceCacheError("path_ownership_lost", "partial cache directory was replaced before publication")
    _validate_cache(identity, owned.path)
    _rename_noreplace(owned.path, identity.cache_path)
    published = OwnedDirectory(identity.cache_path, owned.device, owned.inode, owned.fd)
    if not _owned_directory_matches(published):
        _recover_displaced_publish(identity.cache_path, owned.path)
        _close_owned_directory(published)
        raise SourceCacheError(
            "path_ownership_lost",
            "partial cache path changed during publication; a replacement path was preserved",
        )
    try:
        _validate_cache(identity)
    except Exception:
        _cleanup_owned_directory(published)
        raise
    _close_owned_directory(published)


def _refresh_cache(identity: RepoIdentity, *, git_timeout: float) -> None:
    _validate_cache(identity)
    _run_git(
        [
            *_git_prefix(identity.cache_path),
            "fetch",
            "--atomic",
            "--force",
            "--no-prune",
            "origin",
            "+refs/heads/*:refs/heads/*",
            "+refs/tags/*:refs/tags/*",
        ],
        error_code="git_fetch_failed",
        timeout=git_timeout,
    )
    _validate_cache(identity)


def _fetch_commit(identity: RepoIdentity, cache: Path, commit: str, *, git_timeout: float) -> None:
    _validate_cache(identity, cache)
    _run_git(
        [
            *_git_prefix(cache),
            "fetch",
            "--atomic",
            "--no-tags",
            "origin",
            commit,
        ],
        error_code="git_fetch_failed",
        timeout=git_timeout,
    )
    _validate_cache(identity, cache)


def _acquire_new_cache(
    identity: RepoIdentity,
    *,
    requested: str | None,
    fetch_missing: bool,
    git_timeout: float,
) -> tuple[str, str | None]:
    owned = _clone_partial(identity, git_timeout=git_timeout)
    mode = "cloned"
    try:
        if requested is not None and not _has_commit(owned.path, requested):
            if not fetch_missing:
                raise SourceCacheError("missing_commit", "requested commit is not available in the repository cache")
            _fetch_commit(identity, owned.path, requested, git_timeout=git_timeout)
            mode = "cloned_and_fetched_commit"
        if requested is not None and not _has_commit(owned.path, requested):
            raise SourceCacheError("missing_commit", "requested commit is not available in the repository cache")
        resolved = requested if requested is not None else _head_commit(owned.path)
        _publish_partial(identity, owned)
        return mode, resolved
    except Exception:
        _cleanup_owned_directory(owned)
        raise


def _receipt(
    identity: RepoIdentity,
    *,
    mode: str,
    commit: str | None,
    requested_commit: str | None,
    network_performed: bool,
    refresh_requested: bool,
    fetch_missing_requested: bool,
    cited_paths: Sequence[str] | None,
) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "ok": True,
        "repository": identity.repository,
        "source_url": identity.source_url,
        "cache_path": str(identity.cache_path),
        "cache_bare": True,
        "mode": mode,
        "commit": commit,
        "requested_commit": requested_commit,
        "retrieved_at": utc_now(),
        "network_performed": network_performed,
        "refresh_requested": refresh_requested,
        "fetch_missing_requested": fetch_missing_requested,
        "latest_verified": False,
        "cited_paths": _normalize_cited_paths(cited_paths),
    }


def cache_status(
    repository: str,
    *,
    cache_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    identity = canonicalize(repository, cache_root)
    if not identity.cache_path.exists():
        return {
            "schema": STATUS_SCHEMA,
            "ok": True,
            "repository": identity.repository,
            "source_url": identity.source_url,
            "cache_path": str(identity.cache_path),
            "exists": False,
            "cache_bare": None,
            "commit": None,
            "checked_at": utc_now(),
            "network_performed": False,
            "latest_verified": False,
        }
    _validate_cache(identity)
    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "repository": identity.repository,
        "source_url": identity.source_url,
        "cache_path": str(identity.cache_path),
        "exists": True,
        "cache_bare": True,
        "commit": _head_commit(identity.cache_path),
        "checked_at": utc_now(),
        "network_performed": False,
        "latest_verified": False,
    }


def ensure_cache(
    repository: str,
    *,
    cache_root: str | os.PathLike[str] | None = None,
    commit: str | None = None,
    refresh: bool = False,
    fetch_missing: bool = False,
    lock_timeout: float = 30,
    git_timeout: float = 300,
    cited_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    _validate_git_timeout(git_timeout)
    identity = canonicalize(repository, cache_root)
    requested = _normalize_full_sha(commit)
    normalized_citations = _normalize_cited_paths(cited_paths)
    if fetch_missing and requested is None:
        raise SourceCacheError("invalid_options", "--fetch-missing requires --commit")
    if refresh and requested is not None:
        raise SourceCacheError(
            "invalid_options",
            "--refresh cannot be combined with --commit; use --fetch-missing for a missing pinned commit",
        )

    if identity.cache_path.exists():
        _validate_cache(identity)
        local_hit = _has_commit(identity.cache_path, requested) if requested is not None else False
        if local_hit:
            return _receipt(
                identity,
                mode="reused_commit",
                commit=requested,
                requested_commit=requested,
                network_performed=False,
                refresh_requested=False,
                fetch_missing_requested=fetch_missing,
                cited_paths=normalized_citations,
            )
        if requested is not None and not fetch_missing:
            raise SourceCacheError(
                "missing_commit",
                "requested commit is not present; use --fetch-missing explicitly",
            )
        if requested is None and not refresh:
            return _receipt(
                identity,
                mode="reused_cache",
                commit=_head_commit(identity.cache_path),
                requested_commit=None,
                network_performed=False,
                refresh_requested=False,
                fetch_missing_requested=False,
                cited_paths=normalized_citations,
            )

    with _repo_lock(identity, lock_timeout):
        if not identity.cache_path.exists():
            mode, resolved_commit = _acquire_new_cache(
                identity,
                requested=requested,
                fetch_missing=fetch_missing,
                git_timeout=git_timeout,
            )
            return _receipt(
                identity,
                mode=mode,
                commit=resolved_commit,
                requested_commit=requested,
                network_performed=True,
                refresh_requested=refresh,
                fetch_missing_requested=fetch_missing,
                cited_paths=normalized_citations,
            )

        _validate_cache(identity)
        if requested is not None:
            if _has_commit(identity.cache_path, requested):
                mode = "reused_commit"
                network_performed = False
            else:
                if not fetch_missing:
                    raise SourceCacheError(
                        "missing_commit",
                        "requested commit is not present; use --fetch-missing explicitly",
                    )
                _fetch_commit(identity, identity.cache_path, requested, git_timeout=git_timeout)
                if not _has_commit(identity.cache_path, requested):
                    raise SourceCacheError("missing_commit", "requested commit is not available in the repository cache")
                mode = "fetched_commit"
                network_performed = True
            resolved_commit = requested
        elif refresh:
            _refresh_cache(identity, git_timeout=git_timeout)
            mode = "refreshed"
            network_performed = True
            resolved_commit = _head_commit(identity.cache_path)
        else:
            mode = "reused_cache"
            network_performed = False
            resolved_commit = _head_commit(identity.cache_path)
        return _receipt(
            identity,
            mode=mode,
            commit=resolved_commit,
            requested_commit=requested,
            network_performed=network_performed,
            refresh_requested=refresh,
            fetch_missing_requested=fetch_missing,
            cited_paths=normalized_citations,
        )


def _safe_worktree_target(target: str | os.PathLike[str], cache_root: Path) -> Path:
    raw = Path(target).expanduser()
    if ".." in raw.parts:
        raise SourceCacheError("unsafe_worktree_path", "worktree target must not contain parent traversal")
    absolute = Path(os.path.abspath(raw))
    if absolute.exists() or absolute.is_symlink():
        raise SourceCacheError(
            "worktree_path_exists",
            "MVP worktree creation requires a target path that does not already exist",
        )
    try:
        resolved = absolute.resolve(strict=False)
    except OSError as exc:
        raise SourceCacheError("unsafe_worktree_path", "worktree target cannot be resolved safely") from exc
    if resolved != absolute:
        raise SourceCacheError("unsafe_worktree_path", "worktree target must not traverse symbolic links")
    if resolved == cache_root or resolved.is_relative_to(cache_root):
        raise SourceCacheError("unsafe_worktree_path", "worktree target must be outside the cache root")
    return resolved


def _reserve_worktree_target(target: Path, cache_root: Path) -> OwnedDirectory:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SourceCacheError("unsafe_worktree_path", "worktree parent could not be created safely") from exc
    rechecked = _safe_worktree_target(target, cache_root)
    if rechecked != target:
        raise SourceCacheError("unsafe_worktree_path", "worktree target changed while being prepared")
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise SourceCacheError("worktree_path_exists", "worktree target appeared during creation") from exc
    except OSError as exc:
        raise SourceCacheError("unsafe_worktree_path", "worktree target could not be reserved safely") from exc
    return _capture_owned_directory(target)


def _owned_worktree_gitdir(identity: RepoIdentity, owned: OwnedDirectory) -> Path | None:
    marker = owned.path / ".git"
    if not marker.exists() and not marker.is_symlink():
        return None
    try:
        marker_stat = marker.lstat()
        text = marker.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SourceCacheError("git_worktree_failed", "worktree metadata cannot be verified safely") from exc
    if not stat.S_ISREG(marker_stat.st_mode) or marker.is_symlink() or not text.startswith("gitdir: "):
        raise SourceCacheError("git_worktree_failed", "worktree metadata is malformed")
    raw_gitdir = Path(text[len("gitdir: ") :].strip())
    if not raw_gitdir.is_absolute():
        raw_gitdir = owned.path / raw_gitdir
    try:
        gitdir = raw_gitdir.resolve(strict=True)
        expected_root = (identity.cache_path / "worktrees").resolve(strict=True)
    except OSError as exc:
        raise SourceCacheError("git_worktree_failed", "worktree metadata escapes the repository cache") from exc
    if gitdir.parent != expected_root:
        raise SourceCacheError("git_worktree_failed", "worktree metadata escapes the repository cache")
    return gitdir


def _read_owned_metadata_text(owned: OwnedDirectory, name: str) -> str:
    file_fd = -1
    try:
        file_fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=owned.fd,
        )
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > 4096:
            raise OSError("metadata entry is not a bounded regular file")
        data = os.read(file_fd, 4097)
        if len(data) > 4096:
            raise OSError("metadata entry is too large")
        return data.decode("utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise SourceCacheError("git_worktree_failed", "worktree metadata cannot be verified safely") from exc
    finally:
        if file_fd >= 0:
            os.close(file_fd)


def _capture_verified_worktree_metadata(
    identity: RepoIdentity,
    owned: OwnedDirectory,
    gitdir: Path,
) -> OwnedDirectory:
    metadata = _capture_owned_directory(gitdir)
    try:
        marker_reference = Path(_read_owned_metadata_text(metadata, "gitdir"))
        if not marker_reference.is_absolute():
            marker_reference = metadata.path / marker_reference
        common_reference = Path(_read_owned_metadata_text(metadata, "commondir"))
        if not common_reference.is_absolute():
            common_reference = metadata.path / common_reference
        expected_marker = (owned.path / ".git").resolve(strict=True)
        expected_common = identity.cache_path.resolve(strict=True)
        if marker_reference.resolve(strict=True) != expected_marker:
            raise SourceCacheError("git_worktree_failed", "worktree metadata does not match the reserved target")
        if common_reference.resolve(strict=True) != expected_common:
            raise SourceCacheError("git_worktree_failed", "worktree metadata does not match the repository cache")
        if not _owned_directory_matches(metadata):
            raise SourceCacheError("path_ownership_lost", "worktree metadata changed during verification")
        return metadata
    except (OSError, SourceCacheError):
        _close_owned_directory(metadata)
        raise


def _cleanup_failed_worktree(identity: RepoIdentity, owned: OwnedDirectory) -> bool:
    if not _owned_directory_matches(owned):
        _close_owned_directory(owned)
        return False
    try:
        gitdir = _owned_worktree_gitdir(identity, owned)
    except SourceCacheError:
        _close_owned_directory(owned)
        return False
    if gitdir is None:
        return _cleanup_owned_directory(owned)
    try:
        _validate_cache(identity)
        metadata = _capture_verified_worktree_metadata(identity, owned, gitdir)
    except SourceCacheError:
        _close_owned_directory(owned)
        return False
    moved_metadata = _quarantine_owned_directory(metadata)
    if moved_metadata is None:
        _close_owned_directory(owned)
        return False
    moved_target = _quarantine_owned_directory(owned)
    if moved_target is None:
        _restore_quarantined_directory(moved_metadata, gitdir)
        return False
    metadata_removed = _destroy_quarantined_directory(moved_metadata)
    target_removed = _destroy_quarantined_directory(moved_target)
    return metadata_removed and target_removed


def create_worktree(
    repository: str,
    *,
    commit: str,
    path: str | os.PathLike[str],
    cache_root: str | os.PathLike[str] | None = None,
    lock_timeout: float = 30,
    git_timeout: float = 300,
    cited_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    _validate_git_timeout(git_timeout)
    identity = canonicalize(repository, cache_root)
    requested = _normalize_full_sha(commit)
    assert requested is not None
    citations = _normalize_cited_paths(cited_paths)
    _validate_cache(identity)
    if not _has_commit(identity.cache_path, requested):
        raise SourceCacheError("missing_commit", "requested commit is not present in the repository cache")
    target = _safe_worktree_target(path, identity.cache_root)

    with _repo_lock(identity, lock_timeout):
        _validate_cache(identity)
        if not _has_commit(identity.cache_path, requested):
            raise SourceCacheError("missing_commit", "requested commit is not present in the repository cache")
        owned = _reserve_worktree_target(target, identity.cache_root)
        try:
            _run_git(
                [
                    *_git_prefix(identity.cache_path),
                    "worktree",
                    "add",
                    "--detach",
                    str(target),
                    requested,
                ],
                error_code="git_worktree_failed",
                timeout=git_timeout,
                allow_lazy_fetch=True,
            )
            if not _owned_directory_matches(owned):
                raise SourceCacheError("path_ownership_lost", "worktree target was replaced during checkout")
            if _owned_worktree_gitdir(identity, owned) is None:
                raise SourceCacheError("git_worktree_failed", "worktree metadata is missing")
            _validate_cache(identity)
            actual = _run_git(
                [*_git_prefix(), "-C", str(target), "rev-parse", "--verify", "HEAD^{commit}"],
                error_code="git_worktree_failed",
            ).stdout.strip().lower()
            attached = _run_git(
                [*_git_prefix(), "-C", str(target), "symbolic-ref", "-q", "HEAD"],
                error_code="git_worktree_failed",
                check=False,
            )
            if actual != requested or attached.returncode == 0:
                raise SourceCacheError("git_worktree_failed", "worktree verification failed")
            _close_owned_directory(owned)
        except Exception:
            _cleanup_failed_worktree(identity, owned)
            raise

    return {
        "schema": WORKTREE_SCHEMA,
        "ok": True,
        "repository": identity.repository,
        "source_url": identity.source_url,
        "cache_path": str(identity.cache_path),
        "worktree_path": str(target),
        "commit": requested,
        "mode": "worktree_created",
        "detached": True,
        "created_at": utc_now(),
        "network_performed": None,
        "network_note": "partial-clone object hydration may contact origin if required blobs are absent",
        "cited_paths": citations,
    }


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cache-root", help="cache root; defaults to ~/aios/cache/github")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    canonical_parser = subparsers.add_parser("canonicalize", help="normalize a public GitHub repository identity")
    canonical_parser.add_argument("repository")
    _add_common_options(canonical_parser)

    ensure_parser = subparsers.add_parser("ensure", help="create or safely reuse a shared bare repository cache")
    ensure_parser.add_argument("repository")
    ensure_parser.add_argument("--commit", help="required full 40-character commit SHA")
    ensure_parser.add_argument("--refresh", action="store_true", help="explicitly refresh upstream branch/tag refs")
    ensure_parser.add_argument("--fetch-missing", action="store_true", help="explicitly fetch a missing full commit")
    ensure_parser.add_argument("--lock-timeout", type=float, default=30.0)
    ensure_parser.add_argument("--git-timeout", type=float, default=300.0)
    ensure_parser.add_argument("--cited-path", action="append", default=[])
    _add_common_options(ensure_parser)

    status_parser = subparsers.add_parser("status", help="inspect local cache state without network access")
    status_parser.add_argument("repository")
    _add_common_options(status_parser)

    worktree_parser = subparsers.add_parser("worktree", help="create a detached task-local worktree at a full commit")
    worktree_parser.add_argument("repository")
    worktree_parser.add_argument("--commit", required=True)
    worktree_parser.add_argument("--path", required=True)
    worktree_parser.add_argument("--lock-timeout", type=float, default=30.0)
    worktree_parser.add_argument("--git-timeout", type=float, default=300.0)
    worktree_parser.add_argument("--cited-path", action="append", default=[])
    _add_common_options(worktree_parser)
    return parser.parse_args(list(argv))


def _print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if payload.get("ok") is False:
        error = payload.get("error") or {}
        print(f"ERROR [{error.get('code', 'error')}]: {error.get('message', 'operation failed')}", file=sys.stderr)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.command == "canonicalize":
            payload = _canonical_payload(canonicalize(args.repository, args.cache_root))
        elif args.command == "status":
            payload = cache_status(args.repository, cache_root=args.cache_root)
        elif args.command == "ensure":
            payload = ensure_cache(
                args.repository,
                cache_root=args.cache_root,
                commit=args.commit,
                refresh=args.refresh,
                fetch_missing=args.fetch_missing,
                lock_timeout=args.lock_timeout,
                git_timeout=args.git_timeout,
                cited_paths=args.cited_path,
            )
        elif args.command == "worktree":
            payload = create_worktree(
                args.repository,
                commit=args.commit,
                path=args.path,
                cache_root=args.cache_root,
                lock_timeout=args.lock_timeout,
                git_timeout=args.git_timeout,
                cited_paths=args.cited_path,
            )
        else:  # pragma: no cover - argparse owns command selection
            raise SourceCacheError("invalid_command", "unsupported command")
        _print_payload(payload, as_json=args.json)
        return 0
    except SourceCacheError as exc:
        payload = {
            "schema": ERROR_SCHEMA,
            "ok": False,
            "error": {"code": exc.code, "message": exc.safe_message},
        }
        _print_payload(payload, as_json=args.json)
        return 2
    except Exception:
        payload = {
            "schema": ERROR_SCHEMA,
            "ok": False,
            "error": {"code": "internal_error", "message": "source cache operation failed safely"},
        }
        _print_payload(payload, as_json=args.json)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

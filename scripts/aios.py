#!/usr/bin/env python3
"""aios-kit thin CLI.

Stdlib-first orchestrator for local AIOS kit structure, skillpack sync, and asset checks.
It intentionally does not replace `npx skills`; it only groups and records operations.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import datetime as _dt
import fcntl
import getpass
import hashlib
import html
import io
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Support both the repository wrapper (`python scripts/aios.py`) and the
# package-style entrypoint (`python -m scripts.aios`).
if __package__:
    from .aios_promotion import apply_promotion as apply_asset_promotion
    from .aios_promotion import validate_promotion as validate_asset_promotion
else:
    # Python safe-path mode can omit the script directory for direct execution.
    _SCRIPT_DIR = Path(__file__).resolve().parent
    if str(_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR))
    from aios_promotion import apply_promotion as apply_asset_promotion
    from aios_promotion import validate_promotion as validate_asset_promotion

ROOT = Path(__file__).resolve().parents[1]
SKILLPACK_FILE = ROOT / "skillpack.yaml"
SKILLPACK_LOCAL_FILE = ROOT / "skillpack.local.yaml"
ASSET_FILES = [
    ROOT / "manifests" / "local-assets.local.json",
    ROOT / "manifests" / "local-assets.json",
    ROOT / "manifests" / "local-assets.example.json",
]
PACK_NAME = "aios-kit"


def expand(p: str | None, *, home: Path | None = None) -> Path | None:
    if p is None:
        return None
    home = home or Path.home()
    if p.startswith("~/"):
        return home / p[2:]
    return Path(os.path.expandvars(p)).expanduser()


def resolve_repo_path(p: str | None, *, home: Path | None = None) -> Path | None:
    path = expand(p, home=home)
    if path is None:
        return None
    if path.is_absolute() or (p or "").startswith("~/"):
        return path
    return ROOT / path


def aios_root(home: Path, raw: str | None = None) -> Path:
    """Return the deployed AIOS instance root.

    Product source lives in git repositories; deployed instance state, skills,
    workdirs, logs, and caches live under this root by default.
    """
    value = raw or os.environ.get("AIOS_ROOT") or os.environ.get("AIOS_HOME") or "~/aios"
    out = expand(value, home=home)
    if out is None:
        raise SystemExit("invalid AIOS root")
    return out


def instance_paths(home: Path, *, root: str | None = None, ops: str | None = None, skills_dir: str | None = None) -> dict[str, Path]:
    root_path = aios_root(home, root)
    ops_path = expand(ops, home=home) if ops else root_path / "vault" / "ops"
    # The AIOS instance has a skills metadata/cache directory, but it must not
    # take over an agent's real skills directory. Universal skills are installed
    # one-by-one into the real agent target, defaulting to ~/.agents/skills.
    agent_skills_path = (
        expand(skills_dir, home=home)
        if skills_dir
        else expand(os.environ.get("AIOS_AGENT_SKILLS_DIR") or os.environ.get("AIOS_SKILLS_DIR"), home=home)
        if (os.environ.get("AIOS_AGENT_SKILLS_DIR") or os.environ.get("AIOS_SKILLS_DIR"))
        else home / ".agents" / "skills"
    )
    if ops_path is None or agent_skills_path is None:
        raise SystemExit("invalid AIOS instance path")
    return {
        "root": root_path,
        "config": root_path / "config",
        "vault": root_path / "vault",
        "ops": ops_path,
        "projects": ops_path / "projects",
        "sources": ops_path / "sources",
        "data": root_path / "data",
        "work": root_path / "work",
        "skills": root_path / "skills",
        "agent_skills": agent_skills_path,
        "modules": root_path / "modules",
        "state": root_path / "state",
        "logs": root_path / "logs",
        "cache": root_path / "cache",
        "view": root_path / "view",
    }


OPS_LOG_REQUIRED_FIELDS = (
    "schema_version",
    "ts",
    "date",
    "actor",
    "type",
    "scope",
    "summary",
    "status",
)
OPS_LOG_MAX_ENTRY_BYTES = 256 * 1024


def _ops_log_fail(message: str) -> None:
    raise SystemExit(f"aios ops log append: {message}")


def _ops_log_timestamp(raw: str | None) -> tuple[str, str]:
    if raw is None:
        value = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    else:
        value = raw.strip()
    try:
        parsed = _dt.datetime.fromisoformat(value)
    except ValueError:
        _ops_log_fail("--ts must be a valid ISO-8601 timestamp with an explicit timezone offset")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _ops_log_fail("--ts must include an explicit timezone offset")
    return value, parsed.date().isoformat()


def _ops_log_scalar(name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        _ops_log_fail(f"--{name} must not be empty")
    if "\x00" in cleaned:
        _ops_log_fail(f"--{name} must not contain NUL bytes")
    return cleaned


def _ops_log_source(values: list[str]) -> dict[str, str]:
    source: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        key = key.strip()
        item = item.strip()
        if not separator or not key or not item:
            _ops_log_fail("--source must use non-empty KEY=VALUE syntax")
        if key in source:
            _ops_log_fail(f"duplicate --source key: {key}")
        source[key] = item
    return source


def _ops_log_read_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while True:
        chunk = os.pread(fd, 1024 * 1024, offset)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        offset += len(chunk)


def _ops_log_validate_existing(payload: bytes) -> int:
    if not payload:
        return 0
    if not payload.endswith(b"\n"):
        _ops_log_fail("existing maintenance log is missing its terminal newline")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        _ops_log_fail(f"invalid existing maintenance log UTF-8: {exc}")
    line_count = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            _ops_log_fail(f"invalid existing maintenance log: blank line {line_number}")
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            _ops_log_fail(f"invalid existing maintenance log JSON at line {line_number}: {exc.msg}")
        if not isinstance(item, dict):
            _ops_log_fail(f"invalid existing maintenance log object at line {line_number}")
        line_count += 1
    return line_count


def ops_log_append(args: argparse.Namespace) -> None:
    """Append one complete, verified JSON event without replacing the log inode."""
    home = Path(args.home).expanduser() if args.home else Path.home()
    ops_root = instance_paths(home)["ops"]
    log_path = ops_root / "maintenance-log.jsonl"
    lock_path = ops_root / ".maintenance-log.lock"
    if not ops_root.is_dir():
        _ops_log_fail(f"OPS vault does not exist: {ops_root}")
    try:
        metadata = log_path.lstat()
    except FileNotFoundError:
        _ops_log_fail(f"maintenance log does not exist: {log_path}")
    if not stat.S_ISREG(metadata.st_mode) or log_path.is_symlink():
        _ops_log_fail("maintenance log must be a regular non-symlink file")
    if metadata.st_nlink != 1:
        _ops_log_fail("maintenance log must have exactly one hard link")

    ts, date = _ops_log_timestamp(args.ts)
    entry: dict[str, Any] = {
        "schema_version": 1,
        "ts": ts,
        "date": date,
        "actor": _ops_log_scalar("actor", args.actor),
        "type": _ops_log_scalar("type", args.event_type),
        "scope": _ops_log_scalar("scope", args.scope),
        "summary": _ops_log_scalar("summary", args.summary),
        "objects": args.object,
        "changes": args.change,
        "verification": args.verification,
        "impact": args.impact,
        "followups": args.followup,
        "artifacts": args.artifact,
        "status": _ops_log_scalar("status", args.status),
        "tags": args.tag,
    }
    source = _ops_log_source(args.source)
    if source:
        entry["source"] = source
    if args.sensitive_handling:
        entry["sensitive_handling"] = _ops_log_scalar("sensitive-handling", args.sensitive_handling)
    missing = [field for field in OPS_LOG_REQUIRED_FIELDS if field not in entry or entry[field] in (None, "")]
    if missing:
        _ops_log_fail(f"entry is missing required fields: {', '.join(missing)}")
    encoded = (json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > OPS_LOG_MAX_ENTRY_BYTES:
        _ops_log_fail(f"entry exceeds {OPS_LOG_MAX_ENTRY_BYTES} bytes")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    try:
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | nofollow | cloexec, 0o600)
    except OSError as exc:
        _ops_log_fail(f"cannot open lock file: {exc}")
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            log_fd = os.open(log_path, os.O_RDWR | os.O_APPEND | nofollow | cloexec)
        except OSError as exc:
            _ops_log_fail(f"cannot open maintenance log with O_APPEND: {exc}")
        try:
            current = os.fstat(log_fd)
            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                _ops_log_fail("maintenance log identity changed or is not a single-link regular file")
            if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                _ops_log_fail("maintenance log identity changed before append")
            mode = stat.S_IMODE(current.st_mode)
            if mode != 0o600:
                _ops_log_fail(f"maintenance log mode must be 0600 before append (current {mode:04o}); configure permissions separately")
            before = _ops_log_read_fd(log_fd)
            previous_lines = _ops_log_validate_existing(before)
            written = os.write(log_fd, encoded)
            if written != len(encoded):
                _ops_log_fail(f"short append write: expected {len(encoded)} bytes, wrote {written}")
            os.fsync(log_fd)
            after = _ops_log_read_fd(log_fd)
            prefix_preserved = after[: len(before)] == before
            readback_verified = prefix_preserved and after[len(before) :] == encoded
            if not readback_verified:
                _ops_log_fail("append readback failed; existing prefix or appended record differs")
        finally:
            os.close(log_fd)
    finally:
        os.close(lock_fd)

    receipt = {
        "schema": "aios.ops-log-append.v1",
        "version": 1,
        "ok": True,
        "path": str(log_path),
        "inode": current.st_ino,
        "previous_lines": previous_lines,
        "line_number": previous_lines + 1,
        "entry_bytes": len(encoded),
        "entry_sha256": hashlib.sha256(encoded).hexdigest(),
        "prefix_bytes": len(before),
        "prefix_sha256": hashlib.sha256(before).hexdigest(),
        "prefix_preserved": prefix_preserved,
        "readback_verified": readback_verified,
    }
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    else:
        print(
            f"appended line {receipt['line_number']} to {display_path(log_path, home)} "
            f"(prefix_preserved=true readback_verified=true entry_sha256={receipt['entry_sha256']})"
        )


def display_path(path: Path, home: Path | None = None) -> str:
    home = home or Path.home()
    try:
        return "~/" + str(path.resolve().relative_to(home.resolve()))
    except Exception:
        return str(path)


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(x.strip()) for x in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def load_yaml_like(path: Path) -> dict[str, Any]:
    """Load the small YAML subset; use PyYAML when available."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    data: dict[str, Any] = {}
    current_section: str | None = None
    current_item: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0:
            current_item = None
            if stripped.endswith(":"):
                key = stripped[:-1]
                current_section = key
                data[key] = [] if key in {"external", "first_party"} else {}
            else:
                key, val = stripped.split(":", 1)
                data[key.strip()] = parse_scalar(val)
                current_section = None
        elif indent == 2 and current_section in {"external", "first_party"} and stripped.startswith("- "):
            current_item = {}
            data[current_section].append(current_item)
            rest = stripped[2:].strip()
            if rest:
                key, val = rest.split(":", 1)
                current_item[key.strip()] = parse_scalar(val)
        elif indent in {2, 4}:
            key, val = stripped.split(":", 1)
            if current_section in {"external", "first_party"} and current_item is not None:
                current_item[key.strip()] = parse_scalar(val)
            elif current_section:
                data.setdefault(current_section, {})[key.strip()] = parse_scalar(val)
    return data


def merge_skillpack(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key in {"external", "first_party"}:
            merged[key] = list(merged.get(key, []) or []) + list(value or [])
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            tmp = dict(merged[key])
            tmp.update(value)
            merged[key] = tmp
        else:
            merged[key] = value
    return merged


def load_skillpack(path: Path = SKILLPACK_FILE) -> dict[str, Any]:
    data = load_yaml_like(path)
    if SKILLPACK_LOCAL_FILE.exists():
        data = merge_skillpack(data, load_yaml_like(SKILLPACK_LOCAL_FILE))
    return data


def load_assets() -> dict[str, Any]:
    for path in ASSET_FILES:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise SystemExit("no local-assets manifest found; expected manifests/local-assets.local.json or manifests/local-assets.example.json")


def enabled_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind in ("external", "first_party"):
        for item in manifest.get(kind, []) or []:
            if item.get("enabled", True):
                item = dict(item)
                item["kind"] = kind
                out.append(item)
    return out


def target_dirs(target: str, home: Path) -> dict[str, Path]:
    hermes_home = Path(os.environ.get("HERMES_HOME", str(home / ".hermes"))).expanduser()
    all_dirs = {
        "universal": instance_paths(home)["agent_skills"],
        # Hermes profile skills remain profile-scoped unless explicitly targeted.
        "hermes": hermes_home / "skills",
    }
    if target == "both":
        return all_dirs
    if target not in all_dirs:
        raise SystemExit(f"unknown target: {target}")
    return {target: all_dirs[target]}


def skills_cli_agent(target: str) -> str:
    """Translate an AIOS runtime target to the external skills CLI agent id."""
    return "hermes-agent" if target == "hermes" else target


def state_path(home: Path, manifest: dict[str, Any], state_dir: str | None = None) -> Path:
    raw = state_dir or (manifest.get("defaults") or {}).get("state_dir")
    base = expand(raw, home=home) if raw else instance_paths(home)["ops"] / "state" / "aios-kit"
    if base is None:
        raise SystemExit("invalid state dir")
    return base / "install-state.json"


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "aios-kit.install-state.v1", "pack": PACK_NAME, "managed": []}
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    """Hash an install-state preimage for selected-entry CAS checks."""
    if not path.exists():
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _dt.datetime.now(_dt.UTC).isoformat()
    payload = json.dumps(state, indent=2, ensure_ascii=False) + "\n"
    target_mode = (path.stat().st_mode & 0o777) if path.exists() else 0o664
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, target_mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def run(cmd: list[str], *, apply: bool, attempts: int = 3) -> int:
    print(("RUN " if apply else "DRY ") + " ".join(cmd))
    if not apply:
        return 0
    rc = 1
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            print(f"RETRY {attempt}/{attempts}: " + " ".join(cmd))
        rc = subprocess.run(cmd, check=False).returncode
        if rc == 0:
            return 0
        if attempt < attempts:
            time.sleep(min(2 * attempt, 5))
    return rc


def copytree(src: Path, dst: Path, *, apply: bool, old_entry: dict[str, Any] | None = None, force: bool = False) -> str | None:
    marker = dst / ".aios-kit-managed"
    print(f"{'COPY' if apply else 'DRY copy'} {src} -> {dst}")
    if not apply:
        return hash_dir(src)
    if dst.exists() or dst.is_symlink():
        if not marker.exists() and os.environ.get("AIOS_KIT_OVERWRITE_UNMANAGED") != "1":
            raise SystemExit(f"refusing to overwrite unmanaged skill target: {dst}; move it aside or set AIOS_KIT_OVERWRITE_UNMANAGED=1")
        changed, reason = local_modified(dst, old_entry)
        if changed and not force:
            raise SystemExit(
                f"refusing to overwrite locally modified managed skill: {dst} ({reason}); "
                "review your edits or rerun with --force"
            )
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            shutil.rmtree(dst)
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")
    shutil.copytree(src, dst, ignore=ignore)
    (dst / ".aios-kit-managed").write_text("managed by aios-kit\n", encoding="utf-8")
    return hash_dir(dst)


def symlink(src: Path, dst: Path, *, apply: bool) -> None:
    print(f"{'LINK' if apply else 'DRY link'} {dst} -> {src}")
    if not apply:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        if dst.resolve() == src.resolve():
            return
        dst.unlink()
    elif dst.exists():
        raise SystemExit(f"refusing to replace non-symlink target: {dst}")
    dst.symlink_to(src, target_is_directory=True)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def skillpack_list(args: argparse.Namespace) -> None:
    manifest = load_skillpack()
    print(f"{manifest.get('name')} {manifest.get('version')}")
    for item in enabled_items(manifest):
        print(f"- {item['kind']}: {item.get('id')} skill={item.get('skill')} source={item.get('source')} path={item.get('path','')}")


def validate_skill_dir(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    if not (path / "SKILL.md").exists():
        return False, "missing SKILL.md"
    return True, "ok"


def hash_dir(path: Path) -> str | None:
    """Stable content hash for local modification detection."""
    if not path.exists() or not path.is_dir():
        return None
    import hashlib

    h = hashlib.sha256()
    for file in sorted(x for x in path.rglob("*") if x.is_file() and ".git" not in x.parts and "__pycache__" not in x.parts):
        if file.name == ".aios-kit-managed":
            continue
        rel = file.relative_to(path).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(file.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def local_modified(dst: Path, old_entry: dict[str, Any] | None) -> tuple[bool, str]:
    """Return whether a previously managed copy differs from the recorded hash."""
    if not old_entry or not old_entry.get("installed_hash"):
        return False, "no previous hash"
    current = hash_dir(dst)
    if not current:
        return False, "missing current hash"
    expected = str(old_entry.get("installed_hash"))
    return current != expected, f"current={current[:12]} expected={expected[:12]}"


def skillpack_doctor(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    manifest = load_skillpack()
    ok = True
    print(f"repo: {ROOT}")
    print(f"home: {home}")
    print(f"skillpack: {SKILLPACK_FILE}" + (f" + {SKILLPACK_LOCAL_FILE}" if SKILLPACK_LOCAL_FILE.exists() else ""))
    for cmd in ["git", "node", "npx", "python3"]:
        exists = command_exists(cmd)
        print(f"{cmd}: {'ok' if exists else 'missing'}")
        ok = ok and exists
    for name, d in target_dirs(args.target, home).items():
        print(f"target {name}: {d} {'exists' if d.exists() else 'missing'}")
    check_dirs = target_dirs(args.target, home)
    for item in enabled_items(manifest):
        if item["kind"] == "first_party":
            p = resolve_repo_path(item.get("path"), home=home)
            valid, msg = validate_skill_dir(p) if p else (False, "no path")
            if valid:
                print(f"first_party {item.get('id')}: {p} -> {msg}")
                continue

            # Friend/new-machine installs often do not have the author's source
            # checkout for an independent first-party repo such as
            # `lins-living-loop`. In that case sync falls back to `npx skills add
            # <source>`, so doctor should validate the installed runtime skill.
            source = item.get("source")
            name = str(item.get("skill") or item.get("id"))
            if source and source not in {"local-only", "local-hermes"}:
                installed = []
                for target_name, dst_root in check_dirs.items():
                    runtime = dst_root / name
                    runtime_ok, runtime_msg = validate_skill_dir(runtime)
                    installed.append(f"{target_name}:{runtime} -> {runtime_msg}")
                    valid = valid or runtime_ok
                print(f"first_party {item.get('id')}: source checkout {p} -> {msg}; runtime fallback: " + "; ".join(installed))
                ok = ok and valid
                continue

            print(f"first_party {item.get('id')}: {p} -> {msg}")
            ok = ok and valid
    sp = state_path(home, manifest, args.state_dir)
    print(f"state: {sp} {'exists' if sp.exists() else 'new'}")
    raise SystemExit(0 if ok else 1)


def read_skill_frontmatter_name(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)", text)
    return match.group(1).strip() if match else None


def find_runtime_skill_candidates(name: str, home: Path) -> list[Path]:
    roots = [home / ".agents" / "skills", home / ".hermes" / "skills"]
    candidates: list[Path] = []
    seen: set[Path] = set()
    skip_dirs = {".git", "node_modules", "__pycache__", ".archive", ".curator_backups", ".aios-backups"}
    for root in roots:
        direct = root / name
        if validate_skill_dir(direct)[0]:
            real = direct.resolve()
            if real not in seen:
                candidates.append(direct)
                seen.add(real)
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            if any(part in skip_dirs for part in skill_md.parts):
                continue
            skill_dir = skill_md.parent
            fm_name = read_skill_frontmatter_name(skill_dir)
            if fm_name == name:
                real = skill_dir.resolve()
                if real not in seen:
                    candidates.append(skill_dir)
                    seen.add(real)
    return candidates


def skillpack_base_entries() -> list[dict[str, Any]]:
    return list((load_yaml_like(SKILLPACK_FILE).get("first_party") or []))


def ensure_not_managed_skill(name: str) -> None:
    for item in skillpack_base_entries():
        if item.get("id") == name or item.get("skill") == name:
            raise SystemExit(f"skill already managed in {SKILLPACK_FILE}: {name}")


def yaml_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./~:@+-]+", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def append_first_party_manifest_entry(entry: dict[str, str], *, apply: bool) -> None:
    block = """
  - id: {id}
    path: {path}
    source: {source}
    skill: {skill}
    enabled: true
    default_mode: copy
    targets: universal
    reason: {reason}
""".format(
        id=yaml_quote(entry["id"]),
        path=yaml_quote(entry["path"]),
        source=yaml_quote(entry["source"]),
        skill=yaml_quote(entry["skill"]),
        reason=yaml_quote(entry["reason"]),
    )
    print(f"{'APPEND' if apply else 'DRY append'} first_party {entry['id']} -> {SKILLPACK_FILE}")
    if not apply:
        print(block.rstrip())
        return
    text = SKILLPACK_FILE.read_text(encoding="utf-8")
    if "\nfirst_party:\n" not in text:
        text = text.rstrip() + "\n\nfirst_party:\n"
    SKILLPACK_FILE.write_text(text.rstrip() + "\n" + block, encoding="utf-8")


def skillpack_adopt(args: argparse.Namespace) -> None:
    """Promote a locally created runtime skill into aios-kit as first-party source."""
    home = Path(args.home).expanduser() if args.home else Path.home()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", args.skill.strip()).strip("-")
    if not name:
        raise SystemExit("invalid skill name")
    ensure_not_managed_skill(name)
    if args.from_path:
        src = Path(args.from_path).expanduser()
    else:
        candidates = find_runtime_skill_candidates(name, home)
        if not candidates:
            raise SystemExit(f"no local runtime skill found for {name}; pass --from PATH")
        if len(candidates) > 1:
            formatted = "\n".join(f"- {p} -> {p.resolve()}" for p in candidates)
            raise SystemExit(f"multiple local skill candidates for {name}; pass --from PATH\n{formatted}")
        src = candidates[0]
    valid, msg = validate_skill_dir(src)
    if not valid:
        raise SystemExit(f"invalid source skill: {src} ({msg})")
    fm_name = read_skill_frontmatter_name(src)
    if fm_name and fm_name != name and not args.allow_name_mismatch:
        raise SystemExit(f"SKILL.md name is {fm_name!r}, expected {name!r}; pass --allow-name-mismatch to adopt anyway")
    dest_rel = args.dest or f"skills/{name}"
    if dest_rel.startswith("/") or ".." in Path(dest_rel).parts:
        raise SystemExit("--dest must be a safe repository-relative path")
    dest = ROOT / dest_rel
    apply = bool(args.apply)
    runtime = expand(args.runtime_path, home=home) if args.runtime_path else home / ".agents" / "skills" / name
    if runtime is None:
        raise SystemExit("invalid runtime path")
    runtime_already = (runtime.exists() or runtime.is_symlink()) and runtime.resolve() == dest.resolve()
    print(f"source: {src} -> {src.resolve()}")
    print(f"dest:   {dest}")
    print(f"runtime:{runtime}")
    if dest.exists() and dest.resolve() != src.resolve() and not args.force:
        raise SystemExit(f"destination exists: {dest}; pass --force after review")
    if apply:
        if not os.access(SKILLPACK_FILE, os.W_OK):
            raise SystemExit(f"skillpack is not writable: {SKILLPACK_FILE}")
        if (runtime.exists() or runtime.is_symlink()) and not runtime_already and not args.replace_runtime:
            raise SystemExit(f"runtime target exists: {runtime}; rerun with --replace-runtime after review")
    if not apply:
        print(f"DRY {'move' if args.move else 'copy'} {src} -> {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            if dest.resolve() != src.resolve() and args.force:
                if dest.is_symlink() or dest.is_file():
                    dest.unlink()
                else:
                    shutil.rmtree(dest)
            elif dest.resolve() != src.resolve():
                raise SystemExit(f"destination exists: {dest}")
        if not (dest.exists() and dest.resolve() == src.resolve()):
            if args.move:
                print(f"MOVE {src} -> {dest}")
                shutil.move(str(src), str(dest))
            else:
                print(f"COPY {src} -> {dest}")
                ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")
                shutil.copytree(src, dest, ignore=ignore)
    entry = {
        "id": name,
        "path": dest_rel,
        "source": args.source,
        "skill": name,
        "reason": args.reason or f"First-party AIOS skill managed from {dest_rel}.",
    }
    append_first_party_manifest_entry(entry, apply=apply)
    if runtime_already:
        print(f"OK runtime already points to source: {runtime} -> {dest}")
    else:
        print(f"{'LINK' if apply else 'DRY link'} {runtime} -> {dest}")
        if apply:
            runtime.parent.mkdir(parents=True, exist_ok=True)
            if runtime.exists() or runtime.is_symlink():
                if not args.replace_runtime:
                    raise SystemExit(f"runtime target exists: {runtime}; rerun with --replace-runtime after review")
                if runtime.is_symlink() or runtime.is_file():
                    runtime.unlink()
                else:
                    shutil.rmtree(runtime)
            runtime.symlink_to(dest, target_is_directory=True)
    print("next: run `./aios skillpack doctor --target universal` and commit the source + skillpack changes")


def github_source_url(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://") or source.startswith("git@"):
        return source
    return f"https://github.com/{source}.git"


def install_first_party_from_remote(source: str, name: str, dst: Path, *, apply: bool, state_entries: list[dict[str, Any]], item: dict[str, Any], target: str, mode: str, old_entry: dict[str, Any] | None = None, force: bool = False) -> None:
    """Fallback installer for independent first-party skill repos.

    `npx skills add` is preferred because it understands skill repositories.
    This fallback keeps friend installs robust when the skills CLI has a transient
    failure after GitHub itself is reachable.
    """
    url = github_source_url(source)
    print(f"FALLBACK git clone {url} for {name}")
    if not apply:
        return
    with tempfile.TemporaryDirectory(prefix="aios-skill-") as tmp:
        clone_dir = Path(tmp) / "repo"
        rc = subprocess.run(["git", "clone", "--depth", "1", url, str(clone_dir)], check=False).returncode
        if rc:
            raise SystemExit(rc)
        candidates = [clone_dir, clone_dir / "skills" / name]
        src = next((p for p in candidates if validate_skill_dir(p)[0]), None)
        if src is None:
            raise SystemExit(f"remote source cloned but no skill found for {name}: {url}")
        installed_hash = copytree(src, dst, apply=True, old_entry=old_entry, force=force)
    state_entries.append({"kind": "first_party", "id": item.get("id"), "skill": name, "target": target, "mode": f"{mode}-remote-copy", "source": source, "installed_path": str(dst), "installed_hash": installed_hash})


def install_first_party(item: dict[str, Any], target: str, dst_root: Path, mode: str, apply: bool, home: Path, state_entries: list[dict[str, Any]], old_entry: dict[str, Any] | None = None, force: bool = False) -> None:
    # `home` is the target HOME (useful for temp-home tests or friend installs).
    # Source paths in this repo's manifest describe this author's local source layout,
    # so resolve `~/...` against the real process HOME, not the simulated target HOME.
    src = resolve_repo_path(item.get("path"), home=Path.home())
    name = str(item.get("skill") or item.get("id"))
    runtime_path = item.get("runtime_path")
    if runtime_path:
        dst_candidate = expand(str(runtime_path), home=home)
        if dst_candidate is None:
            raise SystemExit(f"invalid runtime_path for {name}: {runtime_path}")
        dst = dst_candidate
    else:
        dst = dst_root / name
    installed_hash: str | None = None
    if not src or not src.exists():
        source = item.get("source")
        if source and source not in {"local-only", "local-hermes"}:
            cmd = ["npx", "--yes", "skills@latest", "add", source, "--skill", name, "-g", "-y", "--agent", skills_cli_agent(target)]
            if mode == "copy":
                cmd.append("--copy")
            rc = run(cmd, apply=apply)
            if apply:
                runtime_ok, runtime_msg = validate_skill_dir(dst)
                if rc == 0 and runtime_ok:
                    state_entries.append({"kind": "first_party", "id": item.get("id"), "skill": name, "target": target, "mode": mode, "source": source, "installed_path": str(dst), "installed_hash": hash_dir(dst)})
                    return
                print(f"WARN npx install did not produce valid runtime skill {dst}: rc={rc}, {runtime_msg}")
                install_first_party_from_remote(str(source), name, dst, apply=apply, state_entries=state_entries, item=item, target=target, mode=mode, old_entry=old_entry, force=force)
            return
        raise SystemExit(f"first-party source missing for {name}: {src}")
    valid, msg = validate_skill_dir(src)
    if not valid:
        raise SystemExit(f"invalid first-party skill {name}: {src} ({msg})")
    dst_root.mkdir(parents=True, exist_ok=True) if apply else None
    if dst.exists() or dst.is_symlink():
        if dst.resolve() == src.resolve():
            # Keep an existing dev symlink/worktree even when the public manifest
            # default is copy. Public installs copy; author machines may opt into
            # per-skill symlinks via `aios skillpack dev-link --apply`.
            print(f"OK existing worktree/link {dst} -> {src}")
        elif mode == "copy":
            installed_hash = copytree(src, dst, apply=apply, old_entry=old_entry, force=force)
        else:
            raise SystemExit(f"refusing to replace existing non-matching target {dst}; move it or use copy mode")
    else:
        if mode == "symlink":
            symlink(src, dst, apply=apply)
        else:
            installed_hash = copytree(src, dst, apply=apply, old_entry=old_entry, force=force)
    if mode == "symlink" or (dst.exists() and dst.resolve() == src.resolve()):
        installed_hash = hash_dir(src)
    state_entries.append({"kind": "first_party", "id": item.get("id"), "skill": name, "target": target, "mode": mode, "source_path": str(src), "installed_path": str(dst), "installed_hash": installed_hash})


def skillpack_sync(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    manifest = load_skillpack()
    apply = bool(args.apply)
    mode_default = args.mode or (manifest.get("defaults") or {}).get("mode") or "copy"
    sp = state_path(home, manifest, args.state_dir)
    state = load_state(sp)
    old_entries = state.get("managed", [])
    old_by_key = {(e.get("target"), e.get("skill")): e for e in old_entries}
    only_names = [str(name).strip() for name in (getattr(args, "only", None) or []) if str(name).strip()]
    eligible_items = [
        item for item in enabled_items(manifest)
        if not getattr(args, "first_party_only", False) or item["kind"] == "first_party"
    ]
    eligible_by_name = {
        str(item.get("skill") or item.get("id")): item for item in eligible_items
    }
    state_skill_names = {str(entry.get("skill") or "") for entry in old_entries}
    if only_names:
        unknown = [
            name for name in only_names
            if name not in eligible_by_name and not (args.prune and name in state_skill_names)
        ]
        if unknown:
            raise SystemExit(f"unknown --only skill: {', '.join(unknown)}")
        selected_items = [
            eligible_by_name[name]
            for name in dict.fromkeys(only_names)
            if name in eligible_by_name
        ]
    else:
        selected_items = eligible_items

    # Resolve the selected target keys before any projection write.  This lets
    # --only preserve every unselected install-state row byte-for-byte and
    # gives the actuator a precise write set for its dry-run receipt.
    selected_keys: set[tuple[str, str]] = set()
    selected_targets: dict[int, list[tuple[str, Path]]] = {}
    for index, item in enumerate(selected_items):
        explicit_targets = item.get("targets") or item.get("target")
        item_targets_raw = explicit_targets or (manifest.get("defaults") or {}).get("agent") or args.target
        if args.target != "default" and not explicit_targets:
            item_targets_raw = args.target
        targets = [item_targets_raw] if isinstance(item_targets_raw, str) else list(item_targets_raw)
        expanded: list[tuple[str, Path]] = []
        for target in targets:
            for target_name, dst_root in target_dirs(target, home).items():
                expanded.append((target_name, dst_root))
                selected_keys.add((target_name, str(item.get("skill") or item.get("id"))))
        selected_targets[index] = expanded
    if only_names and args.prune:
        for entry in old_entries:
            name = str(entry.get("skill") or "")
            target = str(entry.get("target") or "")
            if name in only_names and name not in eligible_by_name:
                if args.target == "default" or target == args.target:
                    selected_keys.add((target, name))

    preimage_sha = file_sha256(sp)
    expected_state_sha = getattr(args, "expected_state_sha256", None)
    print(f"STATE PREIMAGE SHA256 {preimage_sha}")
    if expected_state_sha and expected_state_sha != preimage_sha:
        raise SystemExit(
            f"install-state CAS mismatch: current={preimage_sha} expected={expected_state_sha}"
        )
    if apply and only_names and not expected_state_sha:
        raise SystemExit("selected-entry apply requires --expected-state-sha256")

    new_entries: list[dict[str, Any]] = []
    if only_names:
        # Selected-entry mode is deliberately conservative: keep every row
        # outside the exact selected (target, skill) key set, including
        # external rows and first-party rows not named by --only.
        new_entries.extend(e for e in old_entries if (e.get("target"), e.get("skill")) not in selected_keys)
    elif getattr(args, "first_party_only", False):
        # dev-link updates local/first-party entries but preserves external entries
        # installed by a previous full sync. Otherwise dev-link would make the
        # state forget externally managed skills and report them as stale.
        new_entries.extend(e for e in old_entries if e.get("kind") != "first_party")
    current_skills: set[tuple[str, str]] = {
        (e.get("target"), e.get("skill"))
        for e in new_entries
        if e.get("target") and e.get("skill")
    }

    # Recheck immediately before the first live projection write.  Dry-runs
    # never perform this write path, while applies fail closed on a concurrent
    # install-state writer rather than overwriting its receipt.
    if apply and file_sha256(sp) != preimage_sha:
        raise SystemExit("install-state CAS mismatch before projection write")

    for index, item in enumerate(selected_items):
        for target, dst_root in selected_targets[index]:
            skill_name = item.get("skill") or item.get("id")
            current_skills.add((target, skill_name))
            mode = args.mode or item.get("default_mode") or mode_default
            old_entry = old_by_key.get((target, skill_name))
            force = bool(getattr(args, "force", False))
            if item["kind"] == "external":
                dst = dst_root / str(skill_name)
                changed, reason = local_modified(dst, old_entry)
                if changed and not force:
                    print(f"SKIP locally modified external skill {target}:{skill_name} at {dst} ({reason}); rerun with --force to overwrite")
                    new_entries.append(old_entry or {"kind": "external", "id": item.get("id"), "skill": skill_name, "target": target, "mode": mode, "source": item.get("source"), "installed_path": str(dst), "local_modified": True})
                    continue
                cmd = ["npx", "--yes", "skills@latest", "add", item["source"], "--skill", skill_name, "-g", "-y", "--agent", skills_cli_agent(target)]
                if mode == "copy":
                    cmd.append("--copy")
                rc = run(cmd, apply=apply)
                if rc:
                    raise SystemExit(rc)
                new_entries.append({"kind": "external", "id": item.get("id"), "skill": skill_name, "target": target, "mode": mode, "source": item.get("source"), "installed_path": str(dst), "installed_hash": hash_dir(dst)})
            else:
                install_first_party(item, target, dst_root, mode, apply, home, new_entries, old_entry=old_entry, force=force)

    if only_names:
        generated_by_key = {
            (entry.get("target"), entry.get("skill")): entry
            for entry in new_entries
            if (entry.get("target"), entry.get("skill")) in selected_keys
        }
        # Put selected replacements back at their previous positions and append
        # only genuinely new rows.  Unselected rows retain their original value
        # and relative order instead of being regenerated or moved.
        ordered_entries: list[dict[str, Any]] = []
        emitted: set[tuple[str, str]] = set()
        for old_entry in old_entries:
            key = (old_entry.get("target"), old_entry.get("skill"))
            if key in selected_keys:
                replacement = generated_by_key.get(key)
                if replacement is not None:
                    ordered_entries.append(replacement)
                    emitted.add(key)
            else:
                ordered_entries.append(old_entry)
        for key in selected_keys:
            if key not in emitted and key in generated_by_key:
                ordered_entries.append(generated_by_key[key])
        new_entries = ordered_entries
        old_by_key = {(e.get("target"), e.get("skill")): e for e in old_entries}
        new_by_key = {(e.get("target"), e.get("skill")): e for e in new_entries}
        for key in sorted(selected_keys):
            before = old_by_key.get(key)
            after = new_by_key.get(key)
            operation = (
                "create" if before is None else
                "delete" if after is None else
                "noop" if before == after else
                "update"
            )
            print("STATE ROW DELTA " + json.dumps({
                "key": {"target": key[0], "skill": key[1]},
                "operation": operation,
                "before": before,
                "after": after,
            }, ensure_ascii=False, sort_keys=True))

    old_entries = state.get("managed", [])
    stale = [e for e in old_entries if (e.get("target"), e.get("skill")) not in current_skills]
    if stale:
        print("stale managed skills:")
        for e in stale:
            print(f"- {e.get('target')}:{e.get('skill')} {e.get('installed_path')}")
    if stale and args.prune:
        for e in stale:
            p = Path(e.get("installed_path", ""))
            print(f"{'PRUNE' if apply else 'DRY prune'} {p}")
            if apply and (p.exists() or p.is_symlink()):
                if p.is_symlink() or p.is_file():
                    p.unlink()
                else:
                    shutil.rmtree(p)
    elif stale:
        print("Use --prune --apply to remove stale managed skills.")

    if apply:
        if only_names and file_sha256(sp) != preimage_sha:
            raise SystemExit("install-state CAS mismatch before state commit; projection may require rollback")
        state["managed"] = new_entries
        save_state(sp, state)
        print(f"state written: {sp}")
    else:
        print("dry-run only; no state written")


def write_if_missing(path: Path, content: str, *, apply: bool) -> None:
    print(f"{'WRITE' if apply else 'DRY write'} {path}")
    if not apply:
        return
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def mkdir(path: Path, *, apply: bool) -> None:
    print(f"{'MKDIR' if apply else 'DRY mkdir'} {path}")
    if apply:
        path.mkdir(parents=True, exist_ok=True)


def compat_symlink(src: Path, dst: Path, *, apply: bool) -> bool:
    print(f"{'LINK' if apply else 'DRY link'} {dst} -> {src}")
    if not apply:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        if dst.resolve() == src.resolve():
            return True
        print(f"WARN refusing to replace existing symlink {dst} -> {dst.resolve()}")
        return False
    if dst.exists():
        print(f"WARN refusing to replace existing path: {dst}")
        return False
    dst.symlink_to(src, target_is_directory=True)
    return True


def init_instance(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    apply = not bool(getattr(args, "dry_run", False))
    paths = instance_paths(home, root=args.root, ops=args.ops, skills_dir=args.skills_dir)
    for key in ["root", "config", "vault", "ops", "projects", "sources", "data", "work", "skills", "agent_skills", "modules", "state", "logs", "cache", "view"]:
        mkdir(paths[key], apply=apply)
    for data_dir in ["inbox", "managed", "archive", "quarantine"]:
        mkdir(paths["data"] / data_dir, apply=apply)
    write_if_missing(paths["root"] / "README.md", "# AIOS instance\n\nThis directory is the local deployed AIOS instance root. Product source lives in repositories; this instance contains local vaults, workdirs, skills, module checkouts, logs, state, and cache.\n", apply=apply)
    write_if_missing(paths["work"] / "README.md", "# AIOS work\n\nLLL and agent workdirs live here for this AIOS instance. Public installs do not create legacy path symlinks by default.\n", apply=apply)
    write_if_missing(paths["skills"] / "README.md", "# AIOS skills\n\nAIOS skill metadata/cache area. Agent-loadable skills are installed one-by-one into the real agent skills directory, defaulting to `~/.agents/skills`.\n", apply=apply)
    write_if_missing(paths["agent_skills"] / "README.aios-kit.md", "# Agent skills managed by aios-kit\n\nAIOS installs or links only the skills listed in its skillpack. Existing unrelated skills in this directory are left alone.\n", apply=apply)
    write_if_missing(paths["modules"] / "README.md", "# AIOS modules\n\nReusable module checkouts used by this AIOS distribution/instance, such as aios-kit and templates.\n", apply=apply)
    write_if_missing(paths["projects"] / "README.md", "# AIOS project registry\n\nMinimal project registry for the local AIOS instance. Facts here are private/live instance state, not public source.\n\n- `registry.jsonl`: one JSON object per project.\n- `aliases.yaml`: human aliases mapped to canonical project ids.\n", apply=apply)
    instance_yaml = f"""version: 1
instance_id: local-default
root: {display_path(paths['root'], home)}
paths:
  vault: {display_path(paths['vault'], home)}
  ops: {display_path(paths['ops'], home)}
  work: {display_path(paths['work'], home)}
  skills: {display_path(paths['skills'], home)}
  agent_skills: {display_path(paths['agent_skills'], home)}
  modules: {display_path(paths['modules'], home)}
  state: {display_path(paths['state'], home)}
  logs: {display_path(paths['logs'], home)}
  cache: {display_path(paths['cache'], home)}
compat:
  default: none
  note: legacy symlinks are not created by public installs; use canonical AIOS paths directly
"""
    write_if_missing(paths["config"] / "instance.yaml", instance_yaml, apply=apply)
    write_if_missing(paths["projects"] / "registry.jsonl", "", apply=apply)
    write_if_missing(paths["projects"] / "aliases.yaml", "aliases: {}\n", apply=apply)
    if getattr(args, "compat_links", False):
        compat_symlink(paths["work"], home / "lll-work", apply=apply)
        # Compatibility mode only creates the optional workdir convenience link.
        # The OPS vault remains <AIOS_ROOT>/vault/ops, and the agent skills
        # directory is never replaced wholesale. Skills are installed one by one
        # by skillpack sync so existing user skills are preserved.
    print(f"AIOS root: {paths['root']}")



# ---------------------------------------------------------------------------
# Secret Registry + Minimal Secret Runtime MVP
# ---------------------------------------------------------------------------

SECRET_SCHEMA = "aios.secret.v1"
SECRET_VALUE_SCHEMA = "aios.secret.values.v1"


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def safe_secret_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    if not cleaned:
        raise SystemExit("invalid empty secret id")
    return cleaned


def secret_root(home: Path) -> Path:
    return instance_paths(home)["vault"] / "secrets"


def secret_dirs(home: Path) -> dict[str, Path]:
    root = secret_root(home)
    return {
        "root": root,
        "items": root / "items",
        "consumers": root / "consumers",
        "replicas": root / "replicas",
        "requests": root / "requests",
        "pending": root / "requests" / "pending",
        "done": root / "requests" / "done",
        "expired": root / "requests" / "expired",
        "receipts": root / "receipts",
        "values": root / "values",
        "policies": root / "policies",
        "audit": root / "audit.jsonl",
    }


def chmod_private(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except PermissionError:
        print(f"warning: could not chmod {path}", file=sys.stderr)


def ensure_secret_layout(home: Path, *, verbose: bool = False) -> dict[str, Path]:
    dirs = secret_dirs(home)
    for key, path in dirs.items():
        if key == "audit":
            continue
        path.mkdir(parents=True, exist_ok=True)
        chmod_private(path, 0o700)
    if not dirs["audit"].exists():
        fd = os.open(dirs["audit"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    chmod_private(dirs["audit"], 0o600)
    if verbose:
        print(f"secret root: {dirs['root']}")
        for key in ["items", "consumers", "replicas", "pending", "done", "expired", "receipts", "values", "policies", "audit"]:
            print(f"- {key}: {dirs[key]}")
    return dirs


def load_yaml_doc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
    except Exception:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected object")
    return data


def dump_yaml_doc(data: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    except Exception:
        # JSON is valid YAML 1.2 and keeps the CLI stdlib-first when PyYAML is absent.
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def write_private_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    chmod_private(path, mode)


def write_yaml_doc(path: Path, data: dict[str, Any], *, mode: int = 0o600) -> None:
    write_private_text(path, dump_yaml_doc(data), mode=mode)


def secret_item_path(home: Path, secret_id: str) -> Path:
    return secret_dirs(home)["items"] / f"{safe_secret_id(secret_id)}.yaml"


def secret_consumer_path(home: Path, consumer_id: str) -> Path:
    return secret_dirs(home)["consumers"] / f"{safe_secret_id(consumer_id)}.yaml"


def secret_replica_path(home: Path, replica_id: str) -> Path:
    return secret_dirs(home)["replicas"] / f"{safe_secret_id(replica_id)}.yaml"


def secret_value_path(home: Path, secret_id: str) -> Path:
    return secret_dirs(home)["values"] / f"{safe_secret_id(secret_id)}.json"


def find_request_path(home: Path, request_id: str, *, include_done: bool = True) -> Path:
    dirs = secret_dirs(home)
    roots = [dirs["pending"]]
    if include_done:
        roots.extend([dirs["done"], dirs["expired"]])
    for root in roots:
        for suffix in (".yaml", ".yml", ".json"):
            path = root / f"{safe_secret_id(request_id)}{suffix}"
            if path.exists():
                return path
    raise SystemExit(f"request not found: {request_id}")


def append_secret_audit(home: Path, event: dict[str, Any]) -> None:
    dirs = ensure_secret_layout(home)
    event = {"ts": now_iso(), "schema": SECRET_SCHEMA, **event, "secret_values_exposed": False}
    with dirs["audit"].open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    chmod_private(dirs["audit"], 0o600)


def field_is_secret(field: dict[str, Any]) -> bool:
    return bool(field.get("secret")) or str(field.get("type", "")).lower() in {"password", "secret", "token"}


def redacted_item_metadata(item: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(item, ensure_ascii=False))
    fields = out.get("fields")
    if isinstance(fields, dict):
        for meta in fields.values():
            if isinstance(meta, dict) and meta.get("secret"):
                meta.pop("value", None)
                meta["value_status"] = meta.get("value_status") or "stored_redacted"
    out["secret_values_exposed"] = False
    return out


def consumer_env_map(consumer: dict[str, Any]) -> dict[str, str]:
    """Return the environment map for the only supported MVP runtime: env.

    New consumers should declare `runtime: {kind: env, env_map: ...}`. The
    top-level `env_map` remains supported as a compatibility mirror for older
    metadata and scripts.
    """
    runtime = consumer.get("runtime")
    env_map: Any = None
    if isinstance(runtime, dict):
        kind = str(runtime.get("kind") or "env")
        if kind != "env":
            raise SystemExit(f"unsupported consumer runtime kind: {kind}; MVP supports only env")
        env_map = runtime.get("env_map")
    elif runtime not in (None, ""):
        raise SystemExit("consumer runtime must be an object")
    if env_map is None:
        env_map = consumer.get("env_map")
    if not isinstance(env_map, dict) or not env_map:
        raise SystemExit("consumer missing runtime.env_map or legacy env_map")
    return {str(k): str(v) for k, v in env_map.items()}


def normalize_consumer_runtime(consumer: dict[str, Any], secret_id: str) -> dict[str, Any]:
    """Normalize request-time consumer metadata without dropping compatibility."""
    out = json.loads(json.dumps(consumer, ensure_ascii=False))
    out.setdefault("uses_secret", secret_id)
    legacy_env_map = out.get("env_map")
    runtime = out.get("runtime")
    if isinstance(runtime, dict):
        kind = str(runtime.get("kind") or "env")
        if kind == "env" and runtime.get("env_map") is None and isinstance(legacy_env_map, dict):
            runtime["env_map"] = legacy_env_map
        if kind == "env" and out.get("env_map") is None and isinstance(runtime.get("env_map"), dict):
            out["env_map"] = runtime["env_map"]
    elif isinstance(legacy_env_map, dict):
        out["runtime"] = {"kind": "env", "env_map": legacy_env_map}
    return out


def request_manifest_issues(req: dict[str, Any]) -> list[dict[str, str]]:
    """Validate a secret intake request manifest without reading any values."""
    issues: list[dict[str, str]] = []

    def add(path: str, message: str, severity: str = "error") -> None:
        issues.append({"severity": severity, "path": path, "message": message})

    def check_no_values(obj: Any, path: str = "$") -> None:
        forbidden = {"value", "values", "secret_value", "secret_values", "plaintext", "password_value", "api_key_value", "token_value"}
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_s = str(key)
                if key_s.lower() in forbidden:
                    add(f"{path}.{key_s}", "request manifests must not contain secret values")
                check_no_values(value, f"{path}.{key_s}")
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                check_no_values(value, f"{path}[{i}]")

    check_no_values(req)
    if str(req.get("kind") or "") != "secret_intake":
        add("kind", "request kind must be secret_intake")
    if not str(req.get("request_id") or ""):
        add("request_id", "request_id is required")
    secret_id = str(req.get("secret_id") or "")
    if not secret_id:
        add("secret_id", "secret_id is required")
    fields = req.get("fields") or []
    if not isinstance(fields, list) or not fields:
        add("fields", "fields must be a non-empty list")
        fields = []
    field_names: set[str] = set()
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            add(f"fields[{i}]", "field must be an object")
            continue
        name = str(field.get("name") or "")
        if not name:
            add(f"fields[{i}].name", "field name is required")
            continue
        if name in field_names:
            add(f"fields[{i}].name", f"duplicate field name: {name}")
        field_names.add(name)
        if "confirm" in field and not isinstance(field.get("confirm"), bool):
            add(f"fields[{i}].confirm", "confirm must be a boolean; use true to opt in")
        if field_is_secret(field) and "default" in field:
            add(f"fields[{i}].default", "secret fields must not define defaults")

    item = req.get("item")
    if not isinstance(item, dict):
        item = {}
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    if metadata.get("agent_can_read_plaintext") is True:
        add("item.metadata.agent_can_read_plaintext", "agent_can_read_plaintext must not be true")

    for i, consumer in enumerate(req.get("consumers") or []):
        if not isinstance(consumer, dict):
            add(f"consumers[{i}]", "consumer must be an object")
            continue
        if not consumer.get("id"):
            add(f"consumers[{i}].id", "consumer id is required")
        uses_secret = str(consumer.get("uses_secret") or secret_id)
        if secret_id and uses_secret != secret_id:
            add(f"consumers[{i}].uses_secret", "consumer uses_secret must match request secret_id")
        runtime = consumer.get("runtime")
        env_map = consumer.get("env_map")
        if isinstance(runtime, dict):
            kind = str(runtime.get("kind") or "env")
            if kind != "env":
                add(f"consumers[{i}].runtime.kind", "MVP supports only runtime.kind: env")
            if runtime.get("env_map") is not None:
                env_map = runtime.get("env_map")
        elif runtime not in (None, ""):
            add(f"consumers[{i}].runtime", "runtime must be an object")
        if env_map is not None:
            if not isinstance(env_map, dict) or not env_map:
                add(f"consumers[{i}].env_map", "env_map must be a non-empty object")
            else:
                for env_name, field_name in env_map.items():
                    if str(field_name) not in field_names:
                        add(f"consumers[{i}].env_map.{env_name}", f"field not defined in request: {field_name}")

    for i, replica in enumerate(req.get("replicas") or []):
        if not isinstance(replica, dict):
            add(f"replicas[{i}]", "replica must be an object")
            continue
        if not replica.get("id"):
            add(f"replicas[{i}].id", "replica id is required")
        source = str(replica.get("source_secret_ref") or secret_id)
        if secret_id and source != secret_id:
            add(f"replicas[{i}].source_secret_ref", "replica source_secret_ref must match request secret_id")
        keys = replica.get("keys") or {}
        if keys is not None:
            if not isinstance(keys, dict):
                add(f"replicas[{i}].keys", "replica keys must be an object")
            else:
                for key, field_name in keys.items():
                    if str(field_name) not in field_names:
                        add(f"replicas[{i}].keys.{key}", f"field not defined in request: {field_name}")
    return issues


def fail_manifest_issues(issues: list[dict[str, str]]) -> None:
    errors = [i for i in issues if i.get("severity") == "error"]
    if not errors:
        return
    lines = ["invalid secret request manifest:"]
    lines.extend(f"- {i['path']}: {i['message']}" for i in errors)
    raise SystemExit("\n".join(lines))


def load_secret_values(home: Path, secret_id: str) -> dict[str, Any]:
    path = secret_value_path(home, secret_id)
    if not path.exists():
        raise SystemExit(f"secret value backend missing for {secret_id}; run `aios secret intake <request-id>` first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
        raise SystemExit(f"invalid secret value backend: {path}")
    return data


def secret_layout_init(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    ensure_secret_layout(home, verbose=True)


def secret_request_show(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    path = find_request_path(home, args.request_id)
    data = load_yaml_doc(path)
    print(json.dumps({"path": str(path), "request": data, "secret_values_exposed": False}, ensure_ascii=False, indent=2))


def default_translation_request(request_id: str = "req_ai_api_translation_default") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "kind": "secret_intake",
        "secret_id": "ai-api.translation.default",
        "title": "AI API profile for AIOS Kit documentation translation",
        "created_by": "agent",
        "created_at": now_iso(),
        "fields": [
            {"name": "provider", "label": "Provider name", "type": "string", "secret": False, "required": True, "default": "custom"},
            {"name": "base_url", "label": "OpenAI-compatible Base URL", "type": "url", "secret": False, "required": True},
            {"name": "model", "label": "Model name", "type": "string", "secret": False, "required": True},
            {"name": "api_mode", "label": "API mode", "type": "enum", "choices": ["chat_completions", "responses"], "default": "chat_completions", "secret": False, "required": True},
            {"name": "api_key", "label": "API Key", "type": "password", "secret": True, "required": True, "confirm": False},
        ],
        "routes": {"canonical": {"backend": "aios-local", "item_path": "$AIOS_ROOT/vault/secrets/items/ai-api.translation.default.yaml"}},
        "item": {"kind": "ai_api_profile", "intended_use": ["docs-translation", "batch-text-generation"], "metadata": {"agent_can_read_plaintext": False}},
        "consumers": [
            {
                "id": "aios-kit.translation",
                "kind": "consumer",
                "uses_secret": "ai-api.translation.default",
                "env_map": {
                    "TRANSLATE_PROVIDER": "provider",
                    "TRANSLATE_BASE_URL": "base_url",
                    "TRANSLATE_MODEL": "model",
                    "TRANSLATE_API_MODE": "api_mode",
                    "TRANSLATE_API_KEY": "api_key",
                },
                "runtime": {
                    "kind": "env",
                    "env_map": {
                        "TRANSLATE_PROVIDER": "provider",
                        "TRANSLATE_BASE_URL": "base_url",
                        "TRANSLATE_MODEL": "model",
                        "TRANSLATE_API_MODE": "api_mode",
                        "TRANSLATE_API_KEY": "api_key",
                    },
                },
                "local_run": {"preferred": "aios secret run --consumer aios-kit.translation -- python3 scripts/translate_docs.py"},
                "legacy_materialization": {"path": "~/aios/config/secrets/aios-kit-translation.env", "status": "remove-after-secret-module-mvp"},
            }
        ],
        "replicas": [
            {
                "id": "github.aios-kit.translation",
                "kind": "external_replica",
                "backend": "github_actions",
                "repo": "LinLin00000000/aios-kit",
                "source_secret_ref": "ai-api.translation.default",
                "keys": {
                    "TRANSLATE_PROVIDER": "provider",
                    "TRANSLATE_BASE_URL": "base_url",
                    "TRANSLATE_MODEL": "model",
                    "TRANSLATE_API_MODE": "api_mode",
                    "TRANSLATE_API_KEY": "api_key",
                },
                "sync": "manual",
                "status": "pending_sync",
            }
        ],
    }


def secret_request_init_translation(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    dirs = ensure_secret_layout(home)
    request_id = args.request_id or "req_ai_api_translation_default"
    path = dirs["pending"] / f"{safe_secret_id(request_id)}.yaml"
    if path.exists() and not args.force:
        raise SystemExit(f"request already exists: {path}; pass --force to overwrite")
    data = default_translation_request(request_id)
    fail_manifest_issues(request_manifest_issues(data))
    write_yaml_doc(path, data)
    append_secret_audit(home, {"event": "request_created", "request_id": request_id, "secret_id": data["secret_id"], "status": "pending"})
    print("Created secret intake request")
    print(f"- request_id: {request_id}")
    print(f"- path: {path}")
    print("Next: run `aios secret request show {}` then `aios secret intake {}` in a real shell/TTY.".format(request_id, request_id))


def secret_request_create(args: argparse.Namespace) -> None:
    """Create a pending request from a generic manifest without secret values."""
    home = Path(args.home).expanduser() if args.home else Path.home()
    dirs = secret_dirs(home) if args.dry_run else ensure_secret_layout(home)
    src = Path(args.manifest).expanduser()
    if not src.exists():
        raise SystemExit(f"manifest not found: {src}")
    data = load_yaml_doc(src)
    issues = request_manifest_issues(data)
    if args.json:
        payload = {"schema": SECRET_SCHEMA, "ok": not any(i.get("severity") == "error" for i in issues), "manifest": str(src), "issues": issues, "secret_values_exposed": False}
        if args.dry_run or not payload["ok"]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            raise SystemExit(0 if payload["ok"] else 1)
    fail_manifest_issues(issues)
    request_id = str(data.get("request_id") or "")
    path = dirs["pending"] / f"{safe_secret_id(request_id)}.yaml"
    if path.exists() and not args.force:
        raise SystemExit(f"request already exists: {path}; pass --force to overwrite")
    if args.dry_run:
        print("Secret request create dry-run")
        print(f"- manifest: {src}")
        print(f"- request_id: {request_id}")
        print(f"- target: {path}")
        print("- secret_values_exposed: false")
        return
    write_yaml_doc(path, data)
    append_secret_audit(home, {"event": "request_created", "request_id": request_id, "secret_id": data["secret_id"], "status": "pending", "source_manifest": str(src)})
    if args.json:
        print(json.dumps({"schema": SECRET_SCHEMA, "ok": True, "request_id": request_id, "path": str(path), "secret_values_exposed": False}, ensure_ascii=False, indent=2))
        return
    print("Created secret intake request")
    print(f"- request_id: {request_id}")
    print(f"- path: {path}")
    print("- secret_values_exposed: false")


def prompt_field(field: dict[str, Any]) -> str:
    name = str(field.get("name"))
    label = str(field.get("label") or name)
    default = field.get("default")
    choices = field.get("choices") or []
    suffix = f" [{default}]" if default not in (None, "") else ""
    if choices:
        suffix += " choices=" + ",".join(str(x) for x in choices)
    while True:
        if field_is_secret(field):
            value = getpass.getpass(f"{label}: ")
            if field.get("confirm") is True:
                again = getpass.getpass(f"Confirm {label}: ")
                if value != again:
                    print("values did not match; try again", file=sys.stderr)
                    continue
        else:
            value = input(f"{label}{suffix}: ").strip()
            if not value and default not in (None, ""):
                value = str(default)
        if not value and field.get("required"):
            print(f"{name} is required", file=sys.stderr)
            continue
        if choices and value and value not in [str(x) for x in choices]:
            print(f"{name} must be one of: {', '.join(str(x) for x in choices)}", file=sys.stderr)
            continue
        return value


def write_consumer_from_request(home: Path, secret_id: str, consumer: dict[str, Any]) -> str:
    cid = str(consumer.get("id") or "")
    if not cid:
        return ""
    normalized = normalize_consumer_runtime(consumer, secret_id)
    data = {"schema_version": 1, "id": cid, "kind": "consumer", "uses_secret": secret_id, "updated_at": now_iso(), **normalized}
    write_yaml_doc(secret_consumer_path(home, cid), data)
    return cid


def write_replica_from_request(home: Path, secret_id: str, replica: dict[str, Any]) -> str:
    rid = str(replica.get("id") or "")
    if not rid:
        return ""
    data = {"schema_version": 1, "id": rid, "kind": "external_replica", "source_secret_ref": secret_id, "updated_at": now_iso(), **replica}
    write_yaml_doc(secret_replica_path(home, rid), data)
    return rid


def store_secret_request(
    home: Path,
    dirs: dict[str, Path],
    req_path: Path,
    req: dict[str, Any],
    request_id: str,
    values: dict[str, Any],
    field_meta: dict[str, Any],
    *,
    audit_event: str,
) -> dict[str, Any]:
    """Persist one completed request through the shared intake path."""
    secret_id = str(req.get("secret_id") or "")
    consumers = [write_consumer_from_request(home, secret_id, c) for c in (req.get("consumers") or []) if isinstance(c, dict)]
    replicas = [write_replica_from_request(home, secret_id, r) for r in (req.get("replicas") or []) if isinstance(r, dict)]
    consumers = [x for x in consumers if x]
    replicas = [x for x in replicas if x]
    item_info = req.get("item") if isinstance(req.get("item"), dict) else {}
    item = {
        "schema_version": 1,
        "id": secret_id,
        "kind": item_info.get("kind", req.get("secret_kind", "generic_secret")),
        "ownership": "aios_owned",
        "backend": "aios-local-file",
        "status": "configured",
        "fields": field_meta,
        "backend_ref": f"values/{safe_secret_id(secret_id)}.json",
        "intended_use": item_info.get("intended_use", []),
        "consumers": consumers,
        "replicas": replicas,
        "metadata": {"agent_can_read_plaintext": False, **(item_info.get("metadata", {}) if isinstance(item_info.get("metadata"), dict) else {})},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    val_path = secret_value_path(home, secret_id)
    item_path = secret_item_path(home, secret_id)
    value_doc = {"schema_version": 1, "schema": SECRET_VALUE_SCHEMA, "secret_id": secret_id, "stored_at": now_iso(), "values": values}
    write_private_text(val_path, json.dumps(value_doc, ensure_ascii=False, indent=2) + "\n", mode=0o600)
    write_yaml_doc(item_path, item)
    request_id = str(req.get("request_id") or request_id)
    receipt = {
        "schema_version": 1,
        "request_id": request_id,
        "secret_id": secret_id,
        "status": "stored",
        "stored_at": now_iso(),
        "backend": "aios-local-file",
        "fields": list(values.keys()),
        "secret_fields": [k for k, v in field_meta.items() if v.get("secret")],
        "consumer_ids": consumers,
        "replica_ids": replicas,
        "secret_values_exposed": False,
    }
    receipt_path = dirs["receipts"] / f"{safe_secret_id(request_id)}.json"
    receipt["receipt_path"] = str(receipt_path)
    write_private_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    done_path = dirs["done"] / req_path.name
    if done_path.exists():
        done_path.unlink()
    req_path.rename(done_path)
    append_secret_audit(home, {"event": audit_event, "request_id": request_id, "secret_id": secret_id, "fields": list(values.keys()), "consumer_ids": consumers, "replica_ids": replicas, "receipt": str(receipt_path)})
    return {
        "secret_id": secret_id,
        "item_path": item_path,
        "receipt_path": receipt_path,
        "fields": list(values.keys()),
        "secret_fields": [k for k, v in field_meta.items() if v.get("secret")],
        "consumer_ids": consumers,
        "replica_ids": replicas,
    }


_HUMAN_CREDENTIAL_FIELD_RE = re.compile(
    r"(?i)(?:api[\s_-]*key|access[\s_-]*key|refresh[\s_-]*token|"
    r"auth(?:entication)?[\s_-]*token|bearer[\s_-]*token|"
    r"password|passphrase|client[\s_-]*secret|token)"
)
GENERATED_SECRET_MIN_BYTES = 16


def secret_generation_plan(fields: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, Any], list[str], list[str]]:
    """Validate a whole request before generating any secret value."""
    lengths: dict[str, int] = {}
    defaults: dict[str, Any] = {}
    generated_fields: list[str] = []
    default_fields: list[str] = []
    issues: list[str] = []
    for field in fields:
        name = str(field.get("name") or "")
        if field_is_secret(field):
            generate = field.get("generate")
            if "generate" in field and not isinstance(generate, bool):
                issues.append(f"{name}: generate must be a boolean")
            if _HUMAN_CREDENTIAL_FIELD_RE.search(" ".join([name, str(field.get("label") or "")])) and generate is not True:
                issues.append(f"{name}: appears to be a human-provided credential; use intake or set generate: true")
            elif generate is False:
                issues.append(f"{name}: generation is disabled; use intake or set generate: true")
            length = field.get("length", 32)
            if isinstance(length, bool) or not isinstance(length, int):
                issues.append(f"{name}: length must be an integer number of bytes")
            elif length < GENERATED_SECRET_MIN_BYTES:
                issues.append(f"{name}: length must be at least {GENERATED_SECRET_MIN_BYTES} bytes")
            else:
                lengths[name] = length
                generated_fields.append(name)
        else:
            if "default" not in field:
                issues.append(f"{name}: non-secret fields must define a default for generate; use intake or add a default")
                continue
            default = field.get("default")
            if default is None:
                issues.append(f"{name}: default must not be null for generate")
                continue
            if field.get("required") and default == "":
                issues.append(f"{name}: required default must not be empty")
                continue
            choices = field.get("choices") or []
            if choices and str(default) not in [str(choice) for choice in choices]:
                issues.append(f"{name}: default must be one of the declared choices")
                continue
            defaults[name] = default
            default_fields.append(name)
    if issues:
        raise SystemExit("secret generation refused:\n- " + "\n- ".join(issues))
    return lengths, defaults, generated_fields, default_fields


def secret_generate(args: argparse.Namespace) -> None:
    """Generate machine-only secret fields without exposing their values."""
    home = Path(args.home).expanduser() if args.home else Path.home()
    dirs = secret_dirs(home) if args.dry_run else ensure_secret_layout(home)
    req_path = find_request_path(home, args.request_id, include_done=False)
    req = load_yaml_doc(req_path)
    fail_manifest_issues(request_manifest_issues(req))
    fields = req.get("fields") or []
    if not isinstance(fields, list) or not fields:
        raise SystemExit(f"request has no fields: {req_path}")
    secret_id = str(req.get("secret_id") or "")
    if not secret_id:
        raise SystemExit("request missing secret_id")
    val_path = secret_value_path(home, secret_id)
    item_path = secret_item_path(home, secret_id)
    if (val_path.exists() or item_path.exists()) and not args.force:
        raise SystemExit(f"secret already exists for {secret_id}; pass --force to replace")
    lengths, defaults, generated_fields, default_fields = secret_generation_plan([field for field in fields if isinstance(field, dict)])
    if args.dry_run:
        payload = {
            "request": str(req_path),
            "secret_id": secret_id,
            "generated_fields": generated_fields,
            "default_fields": default_fields,
            "secret_values_exposed": False,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Secret generation dry-run")
            print(f"- request: {req_path}")
            print(f"- secret_id: {secret_id}")
            print("- generated_fields: " + ", ".join(generated_fields))
            print("- default_fields: " + ", ".join(default_fields))
            print("- secret_values_exposed: false")
        return
    values: dict[str, Any] = {}
    field_meta: dict[str, Any] = {}
    for field in fields:
        name = str(field["name"])
        secret = field_is_secret(field)
        value = secrets.token_hex(lengths[name]) if secret else defaults[name]
        values[name] = value
        meta = {"type": field.get("type", "string"), "secret": secret, "required": bool(field.get("required")), "value_status": "stored"}
        if not secret:
            meta["value"] = value
        field_meta[name] = meta
    stored = store_secret_request(home, dirs, req_path, req, args.request_id, values, field_meta, audit_event="generate_completed")
    payload = {
        "secret_id": stored["secret_id"],
        "item": str(stored["item_path"]),
        "receipt": str(stored["receipt_path"]),
        "generated_fields": generated_fields,
        "secret_values_exposed": False,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Secret generation completed")
        print(f"- secret_id: {stored['secret_id']}")
        print(f"- item: {stored['item_path']}")
        print(f"- receipt: {stored['receipt_path']}")
        print("- generated_fields: " + ", ".join(generated_fields))
        print("- secret_values_exposed: false")


def secret_intake(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    dirs = ensure_secret_layout(home)
    req_path = find_request_path(home, args.request_id, include_done=False)
    req = load_yaml_doc(req_path)
    fail_manifest_issues(request_manifest_issues(req))
    fields = req.get("fields") or []
    if not isinstance(fields, list) or not fields:
        raise SystemExit(f"request has no fields: {req_path}")
    secret_id = str(req.get("secret_id") or "")
    if not secret_id:
        raise SystemExit("request missing secret_id")
    if args.dry_run:
        print("Secret intake dry-run")
        print(f"- request: {req_path}")
        print(f"- secret_id: {secret_id}")
        print("- fields: " + ", ".join(str(f.get("name")) + ("(secret)" if field_is_secret(f) else "") for f in fields if isinstance(f, dict)))
        print("- secret_values_exposed: false")
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("refusing non-TTY secret intake; run this command in a real local shell/TTY")
    val_path = secret_value_path(home, secret_id)
    item_path = secret_item_path(home, secret_id)
    if (val_path.exists() or item_path.exists()) and not args.force:
        raise SystemExit(f"secret already exists for {secret_id}; pass --force to rotate/update")
    print(f"Secret intake: {req.get('title') or secret_id}")
    print(f"Secret id: {secret_id}")
    print("Values will be stored locally; secret fields are hidden and never printed.")
    values: dict[str, str] = {}
    field_meta: dict[str, Any] = {}
    for field in fields:
        if not isinstance(field, dict):
            raise SystemExit("invalid field entry in request")
        name = str(field.get("name") or "")
        if not name:
            raise SystemExit("field missing name")
        value = prompt_field(field)
        values[name] = value
        meta = {"type": field.get("type", "string"), "secret": field_is_secret(field), "required": bool(field.get("required")), "value_status": "stored"}
        if not meta["secret"]:
            meta["value"] = value
        field_meta[name] = meta
    stored = store_secret_request(home, dirs, req_path, req, args.request_id, values, field_meta, audit_event="intake_completed")
    item_path = stored["item_path"]
    receipt_path = stored["receipt_path"]
    print("Secret intake completed")
    print(f"- secret_id: {secret_id}")
    print(f"- item: {item_path}")
    print(f"- receipt: {receipt_path}")
    print("- secret_values_exposed: false")


def secret_validate_report(home: Path) -> dict[str, Any]:
    """Validate Secret Registry metadata without reading secret values."""
    dirs = ensure_secret_layout(home)
    problems: list[dict[str, str]] = []

    def add(severity: str, path: str, message: str) -> None:
        problems.append({"severity": severity, "path": path, "message": message})

    def metadata_files(kind: str) -> list[Path]:
        root = dirs[kind]
        out: list[Path] = []
        for suffix in ("*.yaml", "*.yml", "*.json"):
            out.extend(root.glob(suffix))
        return sorted(set(out))

    def safe_load(path: Path) -> dict[str, Any] | None:
        try:
            return load_yaml_doc(path)
        except SystemExit as exc:
            add("error", str(path), str(exc))
        except Exception as exc:
            add("error", str(path), f"could not parse metadata: {exc}")
        return None

    def check_metadata_for_values(obj: Any, path: str, *, allow_field_value: bool = False) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_s = str(key)
                child_path = f"{path}.{key_s}"
                if key_s.lower() in {"values", "secret_value", "secret_values", "plaintext", "password_value", "api_key_value", "token_value"}:
                    add("error", child_path, "metadata must not contain secret values")
                if key_s == "value" and not allow_field_value:
                    add("error", child_path, "metadata must not contain secret values")
                check_metadata_for_values(value, child_path, allow_field_value=allow_field_value)
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                check_metadata_for_values(value, f"{path}[{i}]", allow_field_value=allow_field_value)

    def check_private_mode(path: Path, expected_kind: str) -> None:
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            add("error", str(path), f"missing {expected_kind}")
            return
        if mode & 0o077:
            add("warning", str(path), f"{expected_kind} should not be group/world accessible; mode={oct(mode)}")

    check_private_mode(dirs["root"], "secret root")
    for key in ["items", "consumers", "replicas", "requests", "pending", "done", "expired", "receipts", "values", "policies"]:
        check_private_mode(dirs[key], key)
    check_private_mode(dirs["audit"], "audit log")
    for value_file in sorted(dirs["values"].glob("*.json")):
        check_private_mode(value_file, "value backend")

    items: dict[str, dict[str, Any]] = {}
    for path in metadata_files("items"):
        item = safe_load(path)
        if item is None:
            continue
        check_metadata_for_values(item, str(path), allow_field_value=True)
        item_id = str(item.get("id") or "")
        if not item_id:
            add("error", str(path), "secret item missing id")
            item_id = path.stem
        if item_id in items:
            add("error", str(path), f"duplicate secret item id: {item_id}")
        items[item_id] = item
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if isinstance(metadata, dict) and metadata.get("agent_can_read_plaintext") is True:
            add("error", f"{path}.metadata.agent_can_read_plaintext", "agent_can_read_plaintext must not be true")
        fields = item.get("fields")
        if item.get("ownership") != "app_owned" and not isinstance(fields, dict):
            add("error", f"{path}.fields", "AIOS-owned item fields must be an object")
        if isinstance(fields, dict):
            for field_name, meta in fields.items():
                if isinstance(meta, dict) and meta.get("secret") and "value" in meta:
                    add("error", f"{path}.fields.{field_name}.value", "secret field metadata must not store plaintext value")
        if item.get("ownership") == "app_owned":
            if item.get("do_not_move") is not True:
                add("warning", f"{path}.do_not_move", "app/OS-owned secrets should declare do_not_move: true")
            if item.get("do_not_symlink") is not True:
                add("warning", f"{path}.do_not_symlink", "app/OS-owned secrets should declare do_not_symlink: true")
        else:
            value_path = secret_value_path(home, item_id)
            if not value_path.exists():
                add("warning", str(value_path), f"value backend missing for configured item {item_id}")

    for path in metadata_files("consumers"):
        consumer = safe_load(path)
        if consumer is None:
            continue
        check_metadata_for_values(consumer, str(path), allow_field_value=False)
        cid = str(consumer.get("id") or "")
        if not cid:
            add("error", str(path), "consumer missing id")
        secret_id = str(consumer.get("uses_secret") or "")
        if not secret_id:
            add("error", f"{path}.uses_secret", "consumer missing uses_secret")
            continue
        item = items.get(secret_id)
        if item is None:
            add("error", f"{path}.uses_secret", f"consumer references missing secret item: {secret_id}")
            continue
        try:
            env_map = consumer_env_map(consumer)
        except SystemExit as exc:
            add("error", str(path), str(exc))
            continue
        raw_item_fields = item.get("fields")
        item_fields = raw_item_fields if isinstance(raw_item_fields, dict) else {}
        for env_name, field_name in env_map.items():
            if field_name not in item_fields:
                add("error", f"{path}.runtime.env_map.{env_name}", f"field not defined on item {secret_id}: {field_name}")
        rotation = consumer.get("rotation")
        if rotation is not None:
            if not isinstance(rotation, dict) or not isinstance(rotation.get("fields"), list) or not rotation.get("fields"):
                add("error", f"{path}.rotation.fields", "rotation fields must be a non-empty list")
            else:
                for field_name in rotation.get("fields", []):
                    field_name = str(field_name)
                    meta = item_fields.get(field_name)
                    if not isinstance(meta, dict):
                        add("error", f"{path}.rotation.fields", f"rotation field not defined on item {secret_id}: {field_name}")
                    elif not meta.get("secret"):
                        add("error", f"{path}.rotation.fields", f"rotation field must be secret on item {secret_id}: {field_name}")

    for path in metadata_files("replicas"):
        replica = safe_load(path)
        if replica is None:
            continue
        check_metadata_for_values(replica, str(path), allow_field_value=False)
        if not replica.get("id"):
            add("error", str(path), "replica missing id")
        secret_id = str(replica.get("source_secret_ref") or "")
        if not secret_id:
            add("error", f"{path}.source_secret_ref", "replica missing source_secret_ref")
            continue
        item = items.get(secret_id)
        if item is None:
            add("error", f"{path}.source_secret_ref", f"replica references missing secret item: {secret_id}")
            continue
        keys = replica.get("keys") or {}
        if isinstance(keys, dict):
            raw_item_fields = item.get("fields")
            item_fields = raw_item_fields if isinstance(raw_item_fields, dict) else {}
            for key, field_name in keys.items():
                if str(field_name) not in item_fields:
                    add("error", f"{path}.keys.{key}", f"field not defined on item {secret_id}: {field_name}")
        else:
            add("error", f"{path}.keys", "replica keys must be an object")

    request_counts: dict[str, int] = {}
    for bucket in ["pending", "done", "expired"]:
        request_counts[bucket] = 0
        for path in metadata_files(bucket):
            request_counts[bucket] += 1
            req = safe_load(path)
            if req is None:
                continue
            for issue in request_manifest_issues(req):
                add(issue.get("severity", "error"), f"{path}:{issue.get('path')}", issue.get("message", "invalid request"))

    for receipt_path in sorted(dirs["receipts"].glob("*.json")):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            add("error", str(receipt_path), f"invalid JSON receipt: {exc}")
            continue
        if isinstance(receipt, dict) and receipt.get("secret_values_exposed") is True:
            add("error", f"{receipt_path}.secret_values_exposed", "receipt must not expose secret values")
        check_metadata_for_values(receipt, str(receipt_path), allow_field_value=False)

    audit_events = 0
    if dirs["audit"].exists():
        for lineno, raw in enumerate(dirs["audit"].read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            audit_events += 1
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                add("error", f"{dirs['audit']}:{lineno}", f"invalid JSONL audit event: {exc}")
                continue
            if isinstance(event, dict) and event.get("secret_values_exposed") is True:
                add("error", f"{dirs['audit']}:{lineno}.secret_values_exposed", "audit must not expose secret values")

    counts = {
        "items": len(metadata_files("items")),
        "consumers": len(metadata_files("consumers")),
        "replicas": len(metadata_files("replicas")),
        "pending_requests": request_counts.get("pending", 0),
        "done_requests": request_counts.get("done", 0),
        "expired_requests": request_counts.get("expired", 0),
        "receipts": len(sorted(dirs["receipts"].glob("*.json"))),
        "value_backends": len(sorted(dirs["values"].glob("*.json"))),
        "audit_events": audit_events,
    }
    return {"schema": SECRET_SCHEMA, "ok": not any(p["severity"] == "error" for p in problems), "root": str(dirs["root"]), "counts": counts, "problems": problems, "secret_values_exposed": False}


def secret_validate(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    report = secret_validate_report(home)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Secret registry validation: {'ok' if report['ok'] else 'problems'}")
        for key, value in report["counts"].items():
            print(f"- {key}: {value}")
        for problem in report["problems"]:
            print(f"- {problem['severity']}: {problem['path']}: {problem['message']}")
        print("- secret_values_exposed: false")
    raise SystemExit(0 if report["ok"] else 1)


def secret_doctor(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    report = secret_validate_report(home)
    report = {**report, "doctor": "Secret Registry + Minimal Secret Runtime", "runtime_modes_supported": ["env"], "advanced_runtime_deferred": ["always-on broker", "proxy", "MCP secret tools", "provider plugins", "session leases"]}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Secret doctor: {'ok' if report['ok'] else 'problems'}")
        print(f"- root: {report['root']}")
        print("- runtime_modes_supported: env")
        for key, value in report["counts"].items():
            print(f"- {key}: {value}")
        for problem in report["problems"]:
            print(f"- {problem['severity']}: {problem['path']}: {problem['message']}")
        print("- secret_values_exposed: false")
    raise SystemExit(0 if report["ok"] else 1)


def secret_list(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    ensure_secret_layout(home)
    rows = []
    for path in sorted(secret_dirs(home)["items"].glob("*.yaml")):
        item = load_yaml_doc(path)
        rows.append({"id": item.get("id"), "kind": item.get("kind"), "status": item.get("status"), "consumers": item.get("consumers", []), "replicas": item.get("replicas", []), "path": str(path)})
    if args.json:
        print(json.dumps({"schema": SECRET_SCHEMA, "items": rows, "secret_values_exposed": False}, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("no secret items")
        return
    for row in rows:
        print(f"- {row['id']} [{row.get('status')}] {row.get('kind')} consumers={len(row.get('consumers') or [])} replicas={len(row.get('replicas') or [])}")


def secret_show(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    path = secret_item_path(home, args.secret_id)
    if not path.exists():
        raise SystemExit(f"secret metadata not found: {args.secret_id}")
    if not args.metadata:
        raise SystemExit("refusing to show secret values; pass --metadata to show redacted metadata")
    item = load_yaml_doc(path)
    print(json.dumps(redacted_item_metadata(item), ensure_ascii=False, indent=2))


def api_health_request(values: dict[str, Any], timeout: int) -> dict[str, str]:
    base_url = str(values.get("base_url") or "").rstrip("/")
    credential = str(values.get("api_key") or "")
    model = str(values.get("model") or "")
    mode = str(values.get("api_mode") or "chat_completions").strip().lower() or "chat_completions"
    if not base_url or not credential or not model:
        raise RuntimeError("missing base_url/api_key/model")
    if mode in {"responses", "codex_responses", "openai_responses"}:
        url = base_url + "/responses"
        payload = {"model": model, "input": [{"role": "user", "content": "Reply with exactly: ok"}]}
    else:
        url = base_url + "/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly: ok"}], "temperature": 0}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = str(resp.status)
            resp.read(2048)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"API HTTP {exc.code}") from exc
    parsed = urllib.parse.urlparse(base_url)
    return {"status": status, "base_url_host": parsed.netloc or "<unknown>", "model": model, "api_mode": mode}


def secret_verify(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    path = secret_item_path(home, args.secret_id)
    if not path.exists():
        raise SystemExit(f"secret metadata not found: {args.secret_id}")
    item = load_yaml_doc(path)
    kind = str(item.get("kind") or "")
    if kind == "ai_api_profile":
        fields = item.get("fields") or {}
        required = ["base_url", "api_key", "model"]
        missing_meta = [x for x in required if x not in fields]
        if missing_meta:
            raise SystemExit("missing metadata fields: " + ", ".join(missing_meta))
        if args.offline:
            val_path = secret_value_path(home, args.secret_id)
            print("AI API metadata check passed")
            print(f"- secret_id: {args.secret_id}")
            print(f"- value_backend: {'present' if val_path.exists() else 'missing'}")
            print("- secret_values_exposed: false")
            raise SystemExit(0 if val_path.exists() else 1)
        values = load_secret_values(home, args.secret_id).get("values", {})
        try:
            result = api_health_request(values, args.timeout)
        except Exception as exc:
            print("AI API verify failed")
            print(f"- secret_id: {args.secret_id}")
            print(f"- error: {exc}")
            print("- secret_values_exposed: false")
            raise SystemExit(1)
        print("AI API verify passed")
        for key in ["base_url_host", "model", "api_mode", "status"]:
            print(f"- {key}: {result[key]}")
        print("- secret_values_exposed: false")
        return
    if item.get("ownership") == "app_owned":
        loc = expand(str(item.get("canonical_location") or ""), home=home)
        ok = bool(loc and path_exists_no_secret_read(loc))
        print("App-owned secret metadata check")
        print(f"- secret_id: {args.secret_id}")
        print(f"- canonical_location: {loc}")
        print(f"- exists: {ok}")
        print(f"- do_not_move: {item.get('do_not_move', True)}")
        print(f"- do_not_symlink: {item.get('do_not_symlink', True)}")
        print("- secret_values_exposed: false")
        raise SystemExit(0 if ok or args.allow_missing_app_owned else 1)
    print("Generic metadata check passed")
    print(f"- secret_id: {args.secret_id}")
    print("- secret_values_exposed: false")


def secret_sync_github(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    item = load_yaml_doc(secret_item_path(home, args.secret_id))
    replica_path = secret_replica_path(home, args.replica)
    if not replica_path.exists():
        raise SystemExit(f"replica metadata not found: {args.replica}")
    replica = load_yaml_doc(replica_path)
    if replica.get("backend") != "github_actions":
        raise SystemExit(f"replica backend is not github_actions: {replica.get('backend')}")
    repo = str(replica.get("repo") or "")
    keys = replica.get("keys") or {}
    if not repo or not isinstance(keys, dict) or not keys:
        raise SystemExit("replica missing repo or keys")
    print(f"GitHub secret sync {'dry-run' if args.dry_run else 'apply'}")
    print(f"- repo: {repo}")
    print(f"- replica: {args.replica}")
    if args.dry_run:
        for env_name, field in keys.items():
            print(f"- would_set: {env_name} <- {field}")
        print("- source_values_read: false")
        print("- secret_values_exposed: false")
        return
    if not args.yes:
        raise SystemExit("refusing external GitHub write without --yes; run again from a trusted shell after reviewing `--dry-run`")
    values = load_secret_values(home, args.secret_id).get("values", {})
    missing = [field for field in keys.values() if str(field) not in values]
    if missing:
        raise SystemExit("missing source fields: " + ", ".join(str(x) for x in missing))
    if shutil.which("gh") is None:
        raise SystemExit("gh CLI not found")
    for env_name, field in keys.items():
        cp = subprocess.run(["gh", "secret", "set", str(env_name), "--repo", repo], input=str(values[str(field)]), text=True, capture_output=True)
        if cp.returncode != 0:
            print(cp.stdout, end="")
            print(cp.stderr, end="", file=sys.stderr)
            raise SystemExit(cp.returncode)
        print(f"- set: {env_name}")
    replica["status"] = "synced"
    replica["last_synced_at"] = now_iso()
    write_yaml_doc(replica_path, replica)
    append_secret_audit(home, {"event": "github_sync", "secret_id": args.secret_id, "replica_id": args.replica, "repo": repo, "keys": list(keys.keys()), "status": "synced"})
    print("- secret_values_exposed: false")


@contextlib.contextmanager
def secret_rotation_lock(home: Path, secret_id: str) -> Any:
    """Serialize value-backend updates for one secret item."""
    value_path = secret_value_path(home, secret_id)
    lock_path = value_path.with_suffix(value_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(f"secret rotation lock is busy: {secret_id}") from exc
        yield lock_path
    finally:
        os.close(fd)


def secret_rotate(args: argparse.Namespace) -> None:
    """Atomically update fields explicitly allow-listed by one consumer.

    Values are accepted only through stdin and are never included in output,
    audit records, command arguments, or metadata.  This is intentionally
    narrower than generic secret editing so an OAuth refresh worker cannot
    rewrite unrelated fields.
    """
    home = Path(args.home).expanduser() if args.home else Path.home()
    if args.field and args.json_stdin:
        raise SystemExit("choose either --field or --json-stdin")
    if not args.field and not args.json_stdin:
        raise SystemExit("one of --field or --json-stdin is required")
    if sys.stdin.isatty():
        raise SystemExit("secret rotation requires values from a pipe, never interactive terminal input")

    consumer_path = secret_consumer_path(home, args.consumer)
    if not consumer_path.exists():
        raise SystemExit(f"consumer metadata not found: {args.consumer}")
    consumer = load_yaml_doc(consumer_path)
    secret_id = str(consumer.get("uses_secret") or "")
    if secret_id != args.secret_id:
        raise SystemExit(f"consumer does not use secret: {args.consumer} -> {secret_id}")
    rotation = consumer.get("rotation")
    allowed = rotation.get("fields") if isinstance(rotation, dict) else None
    if not isinstance(allowed, list) or not allowed:
        raise SystemExit(f"consumer has no rotation allowlist: {args.consumer}")
    allowed_fields = {str(field) for field in allowed}

    item_path = secret_item_path(home, args.secret_id)
    if not item_path.exists():
        raise SystemExit(f"secret metadata not found: {args.secret_id}")
    item = load_yaml_doc(item_path)
    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}

    if args.json_stdin:
        raw = sys.stdin.read()
        try:
            updates = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"rotation JSON is invalid: {exc}") from exc
        if not isinstance(updates, dict) or not updates:
            raise SystemExit("rotation JSON must be a non-empty object")
    else:
        value = sys.stdin.read().rstrip("\r\n")
        if not value:
            raise SystemExit("rotation value must not be empty")
        updates = {str(args.field): value}

    if len(json.dumps(updates, ensure_ascii=False)) > 128 * 1024:
        raise SystemExit("rotation input exceeds 128 KiB")
    for field_name, value in updates.items():
        field_name = str(field_name)
        if field_name not in allowed_fields:
            raise SystemExit(f"field is not allow-listed for consumer: {field_name}")
        meta = fields.get(field_name)
        if not isinstance(meta, dict) or not meta.get("secret"):
            raise SystemExit(f"rotation field must be a secret field: {field_name}")
        if not isinstance(value, str) or not value:
            raise SystemExit(f"rotation value must be a non-empty string: {field_name}")

    value_path = secret_value_path(home, args.secret_id)
    with secret_rotation_lock(home, args.secret_id):
        value_doc = load_secret_values(home, args.secret_id)
        current = value_doc.get("values")
        if not isinstance(current, dict):
            raise SystemExit(f"invalid secret value backend: {value_path}")
        current = dict(current)
        current.update({str(key): value for key, value in updates.items()})
        value_doc["values"] = current
        value_doc["stored_at"] = now_iso()
        atomic_bytes(value_path, json_bytes(value_doc), mode=0o600)

    append_secret_audit(home, {"event": "secret_rotated", "secret_id": args.secret_id, "consumer_id": args.consumer, "fields": sorted(str(key) for key in updates), "status": "stored"})
    print("Secret rotation completed")
    print(f"- secret_id: {args.secret_id}")
    print(f"- consumer: {args.consumer}")
    print("- fields: " + ", ".join(sorted(str(key) for key in updates)))
    print("- secret_values_exposed: false")


_DOCTOR_URL_RE = re.compile(
    r"(?i)(?<![A-Z0-9+.-])(?P<prefix>[0-9+.-]*)(?P<url>[A-Z][A-Z0-9+.-]*://[^\s<>\"']+)"
)
_AUTHORIZATION_BEARER_RE = re.compile(
    r"(?ix)(?<![A-Za-z0-9_])"
    r"(?P<key_quote>[\"']?)(?P<key>authorization)(?P=key_quote)"
    r"(?P<spacing>\s*)(?P<operator>[:=])(?P<value_spacing>\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|Bearer(?:[ \t]+[^\s,;}\]]+)+)"
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])"
    r"(?P<key_quote>[\"']?)"
    r"(?P<key>"
    r"(?=[A-Za-z0-9_-]*(?:"
    r"api[_-]?key|access[_-]?key|private[_-]?key|"
    r"secret[_-]?(?:access[_-]?key|key|value|material)|"
    r"(?:access|refresh|auth|bearer)[_-]?token|token|"
    r"password|passwd|passphrase|client[_-]?secret|secret|credentials?|authorization"
    r")(?P=key_quote)\s*[:=])"
    r"[A-Za-z][A-Za-z0-9_-]*"
    r")"
    r"(?P=key_quote)"
    r"(?P<spacing>\s*)(?P<operator>[:=])(?P<value_spacing>\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;}\]]+)"
)
_PROVIDER_SECRET_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
)


def _redact_credential_url(match: re.Match[str]) -> str:
    prefix = match.group("prefix")
    raw = match.group("url")
    try:
        parsed = urllib.parse.urlsplit(raw)
        if not parsed.hostname:
            return prefix + "***REDACTED-URL***"
        if not (parsed.username or parsed.password or parsed.query or parsed.fragment):
            return prefix + raw
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        try:
            port = parsed.port
        except ValueError:
            return prefix + "***REDACTED-URL***"
        netloc = hostname + (f":{port}" if port is not None else "")
        query = "***REDACTED***" if parsed.query else ""
        fragment = "***REDACTED***" if parsed.fragment else ""
        return prefix + urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, query, fragment))
    except ValueError:
        return prefix + "***REDACTED-URL***"


def redact_output(text: str, secret_values: list[str]) -> str:
    """Redact known values plus credential-shaped data from diagnostic output."""
    out = text
    for value in sorted((v for v in secret_values if v and len(v) >= 4), key=len, reverse=True):
        out = out.replace(value, "***REDACTED***")
    out = _DOCTOR_URL_RE.sub(_redact_credential_url, out)
    out = _AUTHORIZATION_BEARER_RE.sub(
        lambda match: (
            f"{match.group('key_quote')}{match.group('key')}{match.group('key_quote')}"
            f"{match.group('spacing')}{match.group('operator')}"
            f"{match.group('value_spacing')}***REDACTED***"
        ),
        out,
    )
    out = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group('key_quote')}{match.group('key')}{match.group('key_quote')}"
            f"{match.group('spacing')}{match.group('operator')}"
            f"{match.group('value_spacing')}***REDACTED***"
        ),
        out,
    )
    for pattern in _PROVIDER_SECRET_RES:
        out = pattern.sub("***REDACTED***", out)
    return out


def secret_run(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    consumer_path = secret_consumer_path(home, args.consumer)
    if not consumer_path.exists():
        raise SystemExit(f"consumer metadata not found: {args.consumer}")
    consumer = load_yaml_doc(consumer_path)
    secret_id = str(consumer.get("uses_secret") or "")
    if not secret_id:
        raise SystemExit("consumer missing uses_secret")
    item = load_yaml_doc(secret_item_path(home, secret_id))
    value_doc = load_secret_values(home, secret_id)
    values = value_doc.get("values", {})
    env_map = consumer_env_map(consumer)
    cmd = list(args.command or [])
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise SystemExit("command required after --")
    env = os.environ.copy()
    for env_name, field_name in env_map.items():
        field_name = str(field_name)
        if field_name not in values:
            raise SystemExit(f"source field missing for consumer env {env_name}: {field_name}")
        env[str(env_name)] = str(values[field_name])
    secret_fields = []
    fields_meta = item.get("fields") or {}
    if isinstance(fields_meta, dict):
        for field_name, meta in fields_meta.items():
            if isinstance(meta, dict) and meta.get("secret") and field_name in values:
                secret_fields.append(str(values[field_name]))
    cp = subprocess.run(cmd, env=env, text=True, capture_output=True)
    stdout = redact_output(cp.stdout, secret_fields)
    stderr = redact_output(cp.stderr, secret_fields)
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    append_secret_audit(home, {"event": "consumer_run", "secret_id": secret_id, "consumer_id": args.consumer, "command": cmd[:1], "exit_code": cp.returncode})
    raise SystemExit(cp.returncode)


def path_exists_no_secret_read(path: Path) -> bool:
    try:
        return path.exists()
    except PermissionError:
        return True


def secret_index_native(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    ensure_secret_layout(home)
    written: list[str] = []
    if args.ssh:
        ssh_dir = home / ".ssh"
        item = {
            "schema_version": 1,
            "id": "ssh.local-directory",
            "kind": "ssh_secret_directory",
            "ownership": "app_owned",
            "owner": "openssh",
            "canonical_location": str(ssh_dir),
            "aios_role": "indexed_only",
            "expected_mode": "0700",
            "do_not_move": True,
            "do_not_symlink": True,
            "verification": ["directory_exists", "stat_mode", "native_ssh_checks_when_needed"],
            "status": "indexed" if path_exists_no_secret_read(ssh_dir) else "missing",
            "updated_at": now_iso(),
            "metadata": {"agent_can_read_plaintext": False, "note": "AIOS indexes the native SSH directory without enumerating or reading private key values."},
        }
        write_yaml_doc(secret_item_path(home, item["id"]), item)
        append_secret_audit(home, {"event": "app_owned_indexed", "secret_id": item["id"], "kind": item["kind"], "status": item["status"]})
        written.append(item["id"])
    if args.caddy:
        candidates = [Path("/var/lib/caddy/.local/share/caddy"), home / ".local" / "share" / "caddy"]
        found = next((p for p in candidates if path_exists_no_secret_read(p)), candidates[0])
        item = {
            "schema_version": 1,
            "id": "tls.caddy.auto-managed",
            "kind": "tls_certificate_private_key",
            "ownership": "app_owned",
            "owner": "caddy",
            "canonical_location": str(found),
            "aios_role": "indexed_only",
            "managed_by": "caddy",
            "do_not_move": True,
            "do_not_symlink": True,
            "verification": ["caddy_storage_path_exists", "certificate_expiry_check_when_needed"],
            "status": "indexed" if path_exists_no_secret_read(found) else "missing",
            "updated_at": now_iso(),
            "metadata": {"agent_can_read_plaintext": False, "note": "AIOS records Caddy-managed storage location only; Caddy remains the canonical owner."},
        }
        write_yaml_doc(secret_item_path(home, item["id"]), item)
        append_secret_audit(home, {"event": "app_owned_indexed", "secret_id": item["id"], "kind": item["kind"], "status": item["status"]})
        written.append(item["id"])
    if not written:
        raise SystemExit("choose at least one native secret class: --ssh and/or --caddy")
    print("Indexed app/OS-owned secret locations")
    for item_id in written:
        print(f"- {item_id}")
    print("- secret_values_exposed: false")

def project_paths(home: Path) -> tuple[Path, Path]:
    projects = instance_paths(home)["projects"]
    return projects / "registry.jsonl", projects / "aliases.yaml"


def read_projects(home: Path) -> list[dict[str, Any]]:
    registry, _ = project_paths(home)
    if not registry.exists():
        return []
    out: list[dict[str, Any]] = []
    for lineno, raw in enumerate(registry.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{registry}:{lineno}: invalid JSON: {e}")
        if not isinstance(item, dict):
            raise SystemExit(f"{registry}:{lineno}: expected JSON object")
        item["_lineno"] = lineno
        out.append(item)
    return out


def read_aliases(home: Path) -> dict[str, str]:
    _, aliases_path = project_paths(home)
    if not aliases_path.exists():
        return {}
    data = load_yaml_like(aliases_path)
    aliases = data.get("aliases", {}) if isinstance(data, dict) else {}
    if not isinstance(aliases, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in aliases.items()}


def write_aliases(home: Path, aliases: dict[str, str]) -> None:
    _, aliases_path = project_paths(home)
    aliases_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["aliases:"]
    for key in sorted(aliases):
        lines.append(f"  {key}: {aliases[key]}")
    aliases_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_projects(home: Path, *, verbose: bool = True) -> bool:
    ok = True
    projects = read_projects(home)
    ids: set[str] = set()
    valid_status = {"idea", "active", "paused", "archived"}
    for item in projects:
        pid = item.get("id")
        if not isinstance(pid, str) or not pid:
            print(f"project line {item.get('_lineno')}: missing id")
            ok = False
            continue
        if pid in ids:
            print(f"project {pid}: duplicate id")
            ok = False
        ids.add(pid)
        if item.get("kind", "project") != "project":
            print(f"project {pid}: kind must be project")
            ok = False
        if item.get("status", "active") not in valid_status:
            print(f"project {pid}: invalid status {item.get('status')}")
            ok = False
    registry_aliases: dict[str, str] = {}
    for item in projects:
        pid = str(item.get("id", ""))
        for alias in item.get("aliases", []) or []:
            key = str(alias).lower()
            if key in registry_aliases and registry_aliases[key] != pid:
                print(f"registry alias {key}: used by both {registry_aliases[key]} and {pid}")
                ok = False
            registry_aliases[key] = pid
    aliases = read_aliases(home)
    for alias, pid in aliases.items():
        if pid not in ids:
            print(f"alias {alias}: points to missing project {pid}")
            ok = False
    if verbose:
        print(f"projects: {len(projects)} entries, {len(aliases)} aliases, {'ok' if ok else 'problems'}")
    return ok


def resolve_project(home: Path, query: str) -> dict[str, Any] | None:
    q = query.lower()
    projects = read_projects(home)
    by_id = {str(p.get("id")): p for p in projects if p.get("id")}
    if query in by_id:
        return by_id[query]
    aliases = read_aliases(home)
    if q in aliases and aliases[q] in by_id:
        return by_id[aliases[q]]
    matches = []
    for p in projects:
        vals = [str(p.get("name", "")).lower(), str(p.get("id", "")).lower()]
        vals.extend(str(a).lower() for a in p.get("aliases", []) or [])
        if q in vals:
            matches.append(p)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit("ambiguous project query: " + ", ".join(str(m.get("id")) for m in matches))
    return None


def project_list(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    projects = read_projects(home)
    if args.status:
        projects = [p for p in projects if p.get("status", "active") == args.status]
    if args.json:
        print(json.dumps([{k: v for k, v in p.items() if k != "_lineno"} for p in projects], ensure_ascii=False, indent=2))
        return
    if not projects:
        print("no projects")
        return
    for p in projects:
        print(f"- {p.get('id')} [{p.get('status','active')}] {p.get('name','')} {p.get('role_in_aios','')}")


def project_get(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    p = resolve_project(home, args.query)
    if not p:
        raise SystemExit(f"project not found: {args.query}")
    p = {k: v for k, v in p.items() if k != "_lineno"}
    print(json.dumps(p, ensure_ascii=False, indent=2))


def project_add(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    registry, _ = project_paths(home)
    registry.parent.mkdir(parents=True, exist_ok=True)
    projects = read_projects(home)
    if any(p.get("id") == args.id for p in projects):
        raise SystemExit(f"project id already exists: {args.id}")
    locations = []
    if args.path:
        locations.append({"kind": "local", "path": args.path})
    if args.github:
        locations.append({"kind": "github", "url": args.github})
    item: dict[str, Any] = {
        "id": args.id,
        "kind": "project",
        "name": args.name,
        "aliases": args.alias or [],
        "status": args.status,
        "locations": locations,
        "role_in_aios": args.role or "",
        "notes": args.notes or "",
        "updated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    aliases = read_aliases(home)
    for alias in args.alias or []:
        key = alias.lower()
        if key in aliases and aliases[key] != args.id:
            raise SystemExit(f"alias already points elsewhere: {alias} -> {aliases[key]}")
    with registry.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    for alias in args.alias or []:
        aliases[alias.lower()] = args.id
    write_aliases(home, aliases)
    print(f"added project: {args.id}")


def project_alias(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    if not resolve_project(home, args.id):
        raise SystemExit(f"project not found: {args.id}")
    aliases = read_aliases(home)
    key = args.alias.lower()
    if key in aliases and aliases[key] != args.id and not args.force:
        raise SystemExit(f"alias already exists: {args.alias} -> {aliases[key]}")
    aliases[key] = args.id
    write_aliases(home, aliases)
    print(f"alias added: {args.alias} -> {args.id}")


def project_validate(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    raise SystemExit(0 if validate_projects(home) else 1)


SOURCE_KINDS = {"data_root", "worksite_root", "vault", "managed_zone", "project_connector", "service_view"}
SOURCE_ACCESS_MODES = {"read_only_reference", "maintain_in_place", "curate_reversible", "source_specific"}
SOURCE_SYNC_MODES = {"none", "device_authoritative_mirror", "managed_bidirectional", "server_canonical_replica", "metadata_only_remote"}
SOURCE_BACKUP_STATES = {"unknown", "not_required", "planned", "verified"}
SOURCE_SENSITIVITY = {"public", "internal", "private", "sensitive", "mixed"}
SOURCE_STATUSES = {"active", "paused", "archived"}
SOURCE_VIEW_STATUSES = SOURCE_STATUSES | {"idea"}


def source_paths(home: Path) -> tuple[Path, Path]:
    sources = instance_paths(home)["sources"]
    return sources / "registry.jsonl", sources / "aliases.yaml"


def read_sources(home: Path) -> list[dict[str, Any]]:
    registry, _ = source_paths(home)
    if not registry.exists():
        return []
    out: list[dict[str, Any]] = []
    for lineno, raw in enumerate(registry.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{registry}:{lineno}: invalid JSON: {e}")
        if not isinstance(item, dict):
            raise SystemExit(f"{registry}:{lineno}: expected JSON object")
        item["_lineno"] = lineno
        out.append(item)
    return out


def read_source_aliases(home: Path) -> dict[str, str]:
    _, aliases_path = source_paths(home)
    if not aliases_path.exists():
        return {}
    data = load_yaml_like(aliases_path)
    aliases = data.get("aliases", {}) if isinstance(data, dict) else {}
    if not isinstance(aliases, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in aliases.items()}


def write_source_aliases(home: Path, aliases: dict[str, str]) -> None:
    _, aliases_path = source_paths(home)
    aliases_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["aliases:"]
    for key in sorted(aliases):
        lines.append(f"  {key}: {aliases[key]}")
    payload = "\n".join(lines) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=aliases_path.parent, delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(aliases_path)


def project_source_projection(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(project.get("id", "")),
        "kind": "project",
        "name": project.get("name", ""),
        "aliases": project.get("aliases", []) or [],
        "status": project.get("status", "active"),
        "locations": project.get("locations", []) or [],
        "authority": "project_registry",
        "owner_ref": f"project:{project.get('id', '')}",
        "access_mode": "source_specific",
        "sync_mode": "none",
        "backup_status": "unknown",
        "sensitivity": "mixed",
        "record_type": "project_projection",
        "notes": project.get("notes", ""),
    }


def compiled_sources(home: Path, *, explicit_only: bool = False) -> list[dict[str, Any]]:
    explicit = [{k: v for k, v in item.items() if k != "_lineno"} for item in read_sources(home)]
    if explicit_only:
        return explicit
    explicit_ids = {str(item.get("id", "")) for item in explicit}
    projected = [project_source_projection(project) for project in read_projects(home) if str(project.get("id", "")) not in explicit_ids]
    return explicit + projected


def source_identity_claims(home: Path) -> dict[str, set[str]]:
    """Compile every Source/Project id and alias into one case-insensitive namespace."""
    claims: dict[str, set[str]] = {}

    def claim(name: Any, owner: Any) -> None:
        key = str(name or "").strip().lower()
        target = str(owner or "").strip().lower()
        if key and target:
            claims.setdefault(key, set()).add(target)

    for item in compiled_sources(home):
        sid = item.get("id")
        claim(sid, sid)
        aliases = item.get("aliases", []) or []
        if isinstance(aliases, list):
            for alias in aliases:
                claim(alias, sid)
    for alias, sid in read_source_aliases(home).items():
        claim(alias, sid)
    for alias, sid in read_aliases(home).items():
        claim(alias, sid)
    return claims


def resolve_source(home: Path, query: str) -> dict[str, Any] | None:
    q = query.lower()
    sources = compiled_sources(home)
    by_id = {str(item.get("id")): item for item in sources if item.get("id")}
    if query in by_id:
        return by_id[query]
    aliases = read_source_aliases(home)
    aliases.update(read_aliases(home))
    if q in aliases and aliases[q] in by_id:
        return by_id[aliases[q]]
    matches = []
    for item in sources:
        values = [str(item.get("id", "")).lower(), str(item.get("name", "")).lower()]
        values.extend(str(alias).lower() for alias in item.get("aliases", []) or [])
        if q in values:
            matches.append(item)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit("ambiguous source query: " + ", ".join(str(item.get("id")) for item in matches))
    return None


def validate_sources(home: Path, *, verbose: bool = True) -> bool:
    ok = True
    sources = read_sources(home)
    ids: set[str] = set()
    project_ids = {str(project.get("id", "")) for project in read_projects(home)}
    for item in sources:
        sid = item.get("id")
        if not isinstance(sid, str) or not sid:
            print(f"source line {item.get('_lineno')}: missing id")
            ok = False
            continue
        if sid in ids:
            print(f"source {sid}: duplicate id")
            ok = False
        if sid in project_ids:
            print(f"source {sid}: conflicts with project projection id")
            ok = False
        ids.add(sid)
        checks = [
            ("kind", SOURCE_KINDS),
            ("access_mode", SOURCE_ACCESS_MODES),
            ("sync_mode", SOURCE_SYNC_MODES),
            ("backup_status", SOURCE_BACKUP_STATES),
            ("sensitivity", SOURCE_SENSITIVITY),
            ("status", SOURCE_STATUSES),
        ]
        for field, allowed in checks:
            if item.get(field) not in allowed:
                print(f"source {sid}: invalid {field} {item.get(field)!r}")
                ok = False
        locations = item.get("locations")
        if not isinstance(locations, list) or not locations:
            print(f"source {sid}: locations must be a non-empty list")
            ok = False
        else:
            for location in locations:
                if not isinstance(location, dict):
                    print(f"source {sid}: invalid location")
                    ok = False
                    continue
                kind = location.get("kind")
                valid = (
                    (kind in {"local", "view"} and bool(location.get("path")) and not location.get("url"))
                    or (kind in {"github", "remote"} and bool(location.get("url")) and not location.get("path"))
                )
                if not valid:
                    print(f"source {sid}: invalid location for kind {kind!r}")
                    ok = False
        inline_aliases = item.get("aliases", []) or []
        if not isinstance(inline_aliases, list) or not all(isinstance(alias, str) and alias.strip() for alias in inline_aliases):
            print(f"source {sid}: aliases must be a list of non-empty strings")
            ok = False
    aliases = read_source_aliases(home)
    project_aliases = read_aliases(home)
    for alias, sid in aliases.items():
        if sid not in ids:
            print(f"source alias {alias}: points to missing explicit source {sid}")
            ok = False
        if alias in ids and alias != sid:
            print(f"source alias {alias}: conflicts with explicit source id {alias}")
            ok = False
        if alias in project_ids and alias != sid:
            print(f"source alias {alias}: conflicts with project projection id {alias}")
            ok = False
        if alias in project_aliases and project_aliases[alias] != sid:
            print(f"source alias {alias}: conflicts with project alias -> {project_aliases[alias]}")
            ok = False
    for name, owners in sorted(source_identity_claims(home).items()):
        if len(owners) > 1:
            print(f"source identity {name}: claimed by {', '.join(sorted(owners))}")
            ok = False
    if verbose:
        print(f"sources: {len(sources)} explicit, {len(project_ids)} project projections, {len(aliases)} aliases, {'ok' if ok else 'problems'}")
    return ok


def source_list(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    sources = compiled_sources(home, explicit_only=args.explicit_only)
    if args.kind:
        sources = [item for item in sources if item.get("kind") == args.kind]
    if args.status:
        sources = [item for item in sources if item.get("status", "active") == args.status]
    if args.json:
        print(json.dumps(sources, ensure_ascii=False, indent=2))
        return
    if not sources:
        print("no sources")
        return
    for item in sources:
        owner = item.get("authority", "source_registry")
        print(f"- {item.get('id')} [{item.get('status','active')}] {item.get('kind')} {item.get('name','')} ({owner})")


def source_get(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    item = resolve_source(home, args.query)
    if not item:
        raise SystemExit(f"source not found: {args.query}")
    print(json.dumps(item, ensure_ascii=False, indent=2))


def source_add(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    registry, _ = source_paths(home)
    registry.parent.mkdir(parents=True, exist_ok=True)
    if resolve_source(home, args.id):
        raise SystemExit(f"source id already exists or conflicts with project: {args.id}")
    if args.path and args.location_kind not in {None, "local", "view"}:
        raise SystemExit(f"location kind {args.location_kind!r} is invalid for --path; use local or view")
    if args.url and args.location_kind not in {None, "github", "remote"}:
        raise SystemExit(f"location kind {args.location_kind!r} is invalid for --url; use github or remote")
    locations = []
    if args.path:
        locations.append({"kind": args.location_kind or "local", "path": args.path})
    if args.url:
        locations.append({"kind": args.location_kind or "remote", "url": args.url})
    if not locations:
        raise SystemExit("source add requires --path or --url")
    aliases = read_source_aliases(home)
    project_aliases = read_aliases(home)
    claims = source_identity_claims(home)
    new_id = args.id.lower()
    if new_id in claims:
        raise SystemExit(f"source id conflicts with existing identity: {args.id}")
    for alias in args.alias or []:
        key = alias.lower()
        if key in claims:
            owners = ", ".join(sorted(claims[key]))
            raise SystemExit(f"source alias conflicts with existing identity: {alias} -> {owners}")
        if key == new_id:
            raise SystemExit(f"source alias duplicates its source id: {alias}")
        if key in aliases and aliases[key] != args.id:
            raise SystemExit(f"source alias already points elsewhere: {alias} -> {aliases[key]}")
        if key in project_aliases and project_aliases[key] != args.id:
            raise SystemExit(f"source alias conflicts with project alias: {alias} -> {project_aliases[key]}")
    item: dict[str, Any] = {
        "id": args.id,
        "kind": args.kind,
        "name": args.name,
        "aliases": args.alias or [],
        "status": args.status,
        "locations": locations,
        "authority": args.authority,
        "owner_ref": args.owner_ref or "",
        "access_mode": args.access_mode,
        "sync_mode": args.sync_mode,
        "backup_status": args.backup_status,
        "sensitivity": args.sensitivity,
        "include": args.include or [],
        "exclude": args.exclude or [],
        "notes": args.notes or "",
        "updated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with registry.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    for alias in args.alias or []:
        aliases[alias.lower()] = args.id
    write_source_aliases(home, aliases)
    print(f"added source: {args.id}")


def source_alias(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    if not any(item.get("id") == args.id for item in read_sources(home)):
        raise SystemExit(f"explicit source not found: {args.id}")
    aliases = read_source_aliases(home)
    project_aliases = read_aliases(home)
    key = args.alias.lower()
    claims = source_identity_claims(home)
    owners = claims.get(key, set())
    if owners and owners != {args.id.lower()}:
        raise SystemExit(f"source alias conflicts with existing identity: {args.alias} -> {', '.join(sorted(owners))}")
    if key in aliases and aliases[key] != args.id and not args.force:
        raise SystemExit(f"source alias already exists: {args.alias} -> {aliases[key]}")
    if key in project_aliases and project_aliases[key] != args.id:
        raise SystemExit(f"source alias conflicts with project alias: {args.alias} -> {project_aliases[key]}")
    aliases[key] = args.id
    write_source_aliases(home, aliases)
    print(f"source alias added: {args.alias} -> {args.id}")


def source_validate(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    raise SystemExit(0 if validate_sources(home) else 1)


RESOURCE_REF_SCHEMA = "aios.resource-ref.v1"
RESOURCE_RESOLUTION_SCHEMA = "aios.resource-resolution.v1"
DECISION_PACKET_SCHEMA = "aios.decision-packet.v1"
DECISION_ROUTE_ID = "aios.decision-surface.route.v1"
DECISION_POLICY_ID = "decision-surface"
DECISION_CHECK_SCHEMA = "aios.decision-shape-check.v1"
DECISION_MAX_ROUTE_DEPTH = 2
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_without_internal_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def _resource_candidates(home: Path) -> list[dict[str, Any]]:
    """Read existing Project and Source records without creating another registry."""
    project_registry, _ = project_paths(home)
    source_registry, _ = source_paths(home)
    project_aliases = read_aliases(home)
    source_aliases = read_source_aliases(home)
    out: list[dict[str, Any]] = []

    def append(
        record: dict[str, Any],
        *,
        resource_kind: str,
        registry_path: Path,
        registry_owner: str,
        file_aliases: dict[str, str],
    ) -> None:
        resource_id = str(record.get("id") or "")
        aliases_for_record = [
            alias
            for alias, target in file_aliases.items()
            if resource_id and str(target).casefold() == resource_id.casefold()
        ]
        out.append(
            {
                "record": record,
                "resource_kind": resource_kind,
                "registry_path": registry_path,
                "registry_owner": registry_owner,
                "file_aliases": aliases_for_record,
            }
        )

    for project in read_projects(home):
        append(
            project,
            resource_kind="project",
            registry_path=project_registry,
            registry_owner="project_registry",
            file_aliases=project_aliases,
        )
    for source in read_sources(home):
        append(
            source,
            resource_kind="source",
            registry_path=source_registry,
            registry_owner="source_registry",
            file_aliases=source_aliases,
        )
    return out


def _resource_match(candidate: dict[str, Any], query: str) -> str | None:
    record = candidate["record"]
    expected = query.strip().casefold()
    if not expected:
        return None
    if str(record.get("id") or "").casefold() == expected:
        return "id"
    inline_aliases = record.get("aliases", []) or []
    if not isinstance(inline_aliases, list):
        inline_aliases = []
    aliases = [str(alias).casefold() for alias in inline_aliases]
    aliases.extend(str(alias).casefold() for alias in candidate["file_aliases"])
    if expected in aliases:
        return "alias"
    if str(record.get("name") or "").casefold() == expected:
        return "name"
    return None


def _resource_canonical_id(candidate: dict[str, Any]) -> str:
    record = candidate["record"]
    profile = str(record.get("profile") or "default")
    return f"{candidate['resource_kind']}:{profile}:{record.get('id', '')}"


def _resource_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    record = candidate["record"]
    return {
        "canonical_id": _resource_canonical_id(candidate),
        "id": str(record.get("id") or ""),
        "profile": str(record.get("profile") or "default"),
        "resource_kind": candidate["resource_kind"],
        "status": str(record.get("status") or "active"),
    }


def _resource_failure(
    query: str,
    failure_class: str,
    *,
    resource_kind: str | None = None,
    profile: str | None = None,
    candidates: list[dict[str, Any]] | None = None,
    details: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RESOURCE_RESOLUTION_SCHEMA,
        "verdict": "BLOCKED",
        "failure_class": failure_class,
        "query": {"value": query, "kind": resource_kind, "profile": profile},
        "candidates": [_resource_summary(candidate) for candidate in (candidates or [])],
        "details": details or [],
    }


def _resolved_path(home: Path, location: dict[str, Any] | None) -> str | None:
    if not location or not location.get("path"):
        return None
    path = expand(str(location["path"]), home=home)
    return str(path) if path is not None else None


def _resource_ref_from_candidate(home: Path, candidate: dict[str, Any], matched_by: str) -> dict[str, Any]:
    record = candidate["record"]
    clean_record = _record_without_internal_fields(record)
    locations = record.get("locations", []) or []
    if not isinstance(locations, list):
        locations = []
    valid_locations = [location for location in locations if isinstance(location, dict)]
    primary = next(
        (location for location in valid_locations if location.get("kind") in {"local", "view"} and location.get("path")),
        valid_locations[0] if valid_locations else None,
    )
    resource_id = str(record.get("id") or "")
    owner_ref = str(record.get("owner_ref") or "")
    if not owner_ref:
        owner_ref = f"project:{resource_id}" if candidate["resource_kind"] == "project" else str(record.get("authority") or "source_registry")
    registry_path: Path = candidate["registry_path"]
    return {
        "schema": RESOURCE_REF_SCHEMA,
        "canonical_id": _resource_canonical_id(candidate),
        "id": resource_id,
        "name": str(record.get("name") or ""),
        "resource_kind": candidate["resource_kind"],
        "kind": str(record.get("kind") or candidate["resource_kind"]),
        "profile": str(record.get("profile") or "default"),
        "matched_by": matched_by,
        "status": str(record.get("status") or "active"),
        "owner_ref": owner_ref,
        "version": str(record.get("version") or record.get("updated_at") or "unversioned"),
        "record_sha256": _stable_json_sha256(clean_record),
        "path": _resolved_path(home, primary),
        "primary_location": primary,
        "locations": valid_locations,
        "source_ref": {
            "owner": candidate["registry_owner"],
            "path": str(registry_path),
            "schema_version": f"aios.{candidate['resource_kind']}-registry.v1",
            "sha256": _file_sha256(registry_path),
            "line": record.get("_lineno"),
        },
    }


def resolve_resource_ref(
    home: Path,
    query: str,
    *,
    resource_kind: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    try:
        candidates = [
            candidate
            for candidate in _resource_candidates(home)
            if resource_kind is None or candidate["resource_kind"] == resource_kind
        ]
    except SystemExit as error:
        return _resource_failure(
            query,
            "INVALID_RESOURCE_SOURCE",
            resource_kind=resource_kind,
            profile=profile,
            details=[str(error)],
        )
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        matched_by = _resource_match(candidate, query)
        if matched_by:
            candidate = dict(candidate)
            candidate["matched_by"] = matched_by
            matches.append(candidate)

    if profile is not None:
        selected = [
            candidate
            for candidate in matches
            if str(candidate["record"].get("profile") or "default").casefold() == profile.casefold()
        ]
        if not selected and matches:
            return _resource_failure(
                query,
                "CROSS_PROFILE_MISMATCH",
                resource_kind=resource_kind,
                profile=profile,
                candidates=matches,
                details=["exact matches exist only in another profile"],
            )
        matches = selected
    elif len({str(candidate["record"].get("profile") or "default").casefold() for candidate in matches}) > 1:
        return _resource_failure(
            query,
            "CROSS_PROFILE_AMBIGUOUS",
            resource_kind=resource_kind,
            candidates=matches,
            details=["specify --profile; no default profile is selected silently"],
        )

    if not matches:
        alias_maps: list[dict[str, str]] = []
        if resource_kind in {None, "project"}:
            alias_maps.append(read_aliases(home))
        if resource_kind in {None, "source"}:
            alias_maps.append(read_source_aliases(home))
        if any(query.strip().casefold() in aliases for aliases in alias_maps):
            return _resource_failure(
                query,
                "STALE_ALIAS",
                resource_kind=resource_kind,
                profile=profile,
                details=["alias points to a missing resource record"],
            )
        return _resource_failure(query, "MISSING_RESOURCE", resource_kind=resource_kind, profile=profile)

    canonical_ids = [_resource_canonical_id(candidate).casefold() for candidate in matches]
    if len(canonical_ids) != len(set(canonical_ids)):
        return _resource_failure(
            query,
            "DUPLICATE_RESOURCE_ID",
            resource_kind=resource_kind,
            profile=profile,
            candidates=matches,
        )
    if len(matches) > 1:
        return _resource_failure(
            query,
            "AMBIGUOUS_RESOURCE",
            resource_kind=resource_kind,
            profile=profile,
            candidates=matches,
        )

    candidate = matches[0]
    record = candidate["record"]
    status = str(record.get("status") or "active").casefold()
    if bool(record.get("stale")) or status == "archived":
        return _resource_failure(
            query,
            "STALE_RESOURCE",
            resource_kind=resource_kind,
            profile=profile,
            candidates=matches,
        )
    if status != "active":
        return _resource_failure(
            query,
            "UNAVAILABLE_RESOURCE",
            resource_kind=resource_kind,
            profile=profile,
            candidates=matches,
        )
    return {
        "schema": RESOURCE_RESOLUTION_SCHEMA,
        "verdict": "RESOLVED",
        "failure_class": None,
        "query": {"value": query, "kind": resource_kind, "profile": profile},
        "resource_ref": _resource_ref_from_candidate(home, candidate, candidate["matched_by"]),
    }


def resource_resolve(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    receipt = resolve_resource_ref(home, args.query, resource_kind=args.kind, profile=args.profile)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    if receipt["verdict"] != "RESOLVED":
        raise SystemExit(2)



def _decision_failure(
    args: argparse.Namespace,
    failure_class: str,
    *,
    verdict: str = "FAIL_SHAPE",
    details: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": DECISION_CHECK_SCHEMA,
        "verdict": verdict,
        "failure_class": failure_class,
        "route": {
            "route_id": args.route_id,
            "policy_id": args.policy_id,
            "depth": args.route_depth,
            "max_depth": DECISION_MAX_ROUTE_DEPTH,
            "visited_ids": list(args.visited or []),
        },
        "details": details or [],
    }


def _decision_stop(
    args: argparse.Namespace,
    failure_class: str,
    *,
    verdict: str = "FAIL_SHAPE",
    details: list[str] | None = None,
) -> None:
    print(json.dumps(_decision_failure(args, failure_class, verdict=verdict, details=details), ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(2)


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def _decision_source_path(home: Path, raw: str | None) -> Path:
    """Resolve the one direct Local Policy source; never consult an index."""
    if not raw:
        return aios_root(home) / "workflow" / "local-policy.md"
    if raw.startswith("~/"):
        return home / raw[2:]
    path = Path(raw).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _decision_policy_schema(source_text: str) -> str | None:
    match = re.search(r"(?m)^schema:\s*([^\s]+)\s*$", source_text)
    return match.group(1) if match else None


def _decision_packet_shape(
    packet: dict[str, Any],
    policy_entry: dict[str, Any],
    route_id: str,
) -> tuple[str | None, list[str], dict[str, Any]]:
    required_packet = {
        "schema",
        "packet_id",
        "matter_ref",
        "mission_sha256",
        "policy_refs",
        "questions",
        "dependency_batches",
        "created_by",
    }
    missing_packet = sorted(required_packet - set(packet))
    if missing_packet:
        return "MALFORMED_PACKET", ["missing packet fields: " + ", ".join(missing_packet)], {}
    if packet.get("schema") != DECISION_PACKET_SCHEMA:
        return "MALFORMED_PACKET", ["unsupported packet schema"], {}
    for field in ("packet_id", "matter_ref", "created_by"):
        if not isinstance(packet.get(field), str) or not packet.get(field):
            return "MALFORMED_PACKET", [f"{field} must be a non-empty string"], {}
    if not isinstance(packet.get("mission_sha256"), str) or not _SHA256_PATTERN.fullmatch(packet["mission_sha256"]):
        return "MALFORMED_PACKET", ["mission_sha256 must be a lowercase SHA-256"], {}

    policy_refs = packet.get("policy_refs")
    if not isinstance(policy_refs, list) or not all(isinstance(ref, dict) for ref in policy_refs):
        return "MALFORMED_PACKET", ["policy_refs must be an object list"], {}
    exact_refs = [ref for ref in policy_refs if ref.get("id") == policy_entry.get("id")]
    if len(exact_refs) != 1:
        return "MALFORMED_PACKET", ["packet must contain exactly one exact policy ref"], {}
    packet_ref = exact_refs[0]
    if packet_ref.get("route_id") != route_id or packet_ref.get("source_sha256") != policy_entry.get("source_sha256"):
        return "MALFORMED_PACKET", ["packet policy ref does not match the exact route/source hash"], {}

    questions = packet.get("questions")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 5:
        return "MALFORMED_PACKET", ["questions must contain 1 to 5 entries"], {}
    required_question = {
        "id",
        "axis",
        "plain_language_question",
        "why_human_owned",
        "depends_on",
        "batch_id",
        "options",
        "recommendation",
        "authorization_effect",
    }
    required_option = {
        "id",
        "label",
        "description",
        "advantages",
        "costs",
        "risks",
        "reversibility",
        "future_bias",
        "viable",
    }
    question_by_id: dict[str, dict[str, Any]] = {}
    option_ids: set[str] = set()
    option_counts: dict[str, int] = {}
    dependencies: dict[str, list[str]] = {}
    for question in questions:
        if not isinstance(question, dict):
            return "MALFORMED_PACKET", ["every question must be an object"], {}
        missing = sorted(required_question - set(question))
        if missing:
            return "MALFORMED_PACKET", ["question missing fields: " + ", ".join(missing)], {}
        question_id = question.get("id")
        if not isinstance(question_id, str) or not question_id or question_id in question_by_id:
            return "MALFORMED_PACKET", ["question IDs must be non-empty and unique"], {}
        for field in ("axis", "plain_language_question", "why_human_owned", "batch_id"):
            if not isinstance(question.get(field), str) or not question.get(field):
                return "MALFORMED_PACKET", [f"question {question_id}: {field} must be non-empty"], {}
        depends_on = question.get("depends_on")
        if not isinstance(depends_on, list) or not all(isinstance(item, str) and item for item in depends_on):
            return "MALFORMED_PACKET", [f"question {question_id}: depends_on must be a string list"], {}
        if len(depends_on) != len(set(depends_on)):
            return "MALFORMED_PACKET", [f"question {question_id}: duplicate dependencies"], {}
        options = question.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 4:
            return "MALFORMED_PACKET", [f"question {question_id}: options must contain 2 to 4 entries"], {}
        local_option_ids: set[str] = set()
        for option in options:
            if not isinstance(option, dict):
                return "MALFORMED_PACKET", [f"question {question_id}: every option must be an object"], {}
            missing = sorted(required_option - set(option))
            if missing:
                return "MALFORMED_PACKET", [f"question {question_id}: option missing fields: " + ", ".join(missing)], {}
            option_id = option.get("id")
            if not isinstance(option_id, str) or not option_id or option_id in option_ids:
                return "MALFORMED_PACKET", ["option IDs must be non-empty and globally unique"], {}
            for field in ("label", "description", "reversibility", "future_bias"):
                if not isinstance(option.get(field), str) or not option.get(field):
                    return "MALFORMED_PACKET", [f"option {option_id}: {field} must be non-empty"], {}
            for field in ("advantages", "costs", "risks"):
                if not isinstance(option.get(field), list):
                    return "MALFORMED_PACKET", [f"option {option_id}: {field} must be a list"], {}
            if not isinstance(option.get("viable"), bool):
                return "MALFORMED_PACKET", [f"option {option_id}: viable must be boolean"], {}
            if option.get("kind", "option") not in {"option", "hybrid"}:
                return "MALFORMED_PACKET", [f"option {option_id}: kind must be option or hybrid"], {}
            option_ids.add(option_id)
            local_option_ids.add(option_id)
        for option in options:
            if option.get("kind", "option") == "hybrid":
                combines = option.get("combines")
                if not isinstance(combines, list) or not 2 <= len(combines) <= 3 or len(combines) != len(set(combines)):
                    return "MALFORMED_PACKET", [f"hybrid {option.get('id')}: combines must contain 2 to 3 unique option IDs"], {}
                if option.get("id") in combines or not set(combines).issubset(local_option_ids):
                    return "MALFORMED_PACKET", [f"hybrid {option.get('id')}: combines must reference sibling options"], {}
        recommendation = question.get("recommendation")
        if not isinstance(recommendation, dict) or recommendation.get("option_id") not in local_option_ids or not isinstance(recommendation.get("assumptions"), list):
            return "MALFORMED_PACKET", [f"question {question_id}: recommendation must reference one option and list assumptions"], {}
        authorization_effect = question.get("authorization_effect")
        if not isinstance(authorization_effect, (str, dict)) or not authorization_effect:
            return "MALFORMED_PACKET", [f"question {question_id}: authorization_effect must be a non-empty string or object"], {}
        question_by_id[question_id] = question
        dependencies[question_id] = depends_on
        option_counts[question_id] = len(options)

    question_ids = set(question_by_id)
    for question_id, refs in dependencies.items():
        missing = sorted(set(refs) - question_ids)
        if missing:
            return "MISSING_DEPENDENCY", [f"question {question_id}: missing dependencies {', '.join(missing)}"], {}
        if question_id in refs:
            return "DEPENDENCY_CYCLE", [f"question {question_id}: self dependency"], {}

    visiting: set[str] = set()
    visited: set[str] = set()

    def has_cycle(question_id: str) -> bool:
        if question_id in visiting:
            return True
        if question_id in visited:
            return False
        visiting.add(question_id)
        if any(has_cycle(dependency) for dependency in dependencies[question_id]):
            return True
        visiting.remove(question_id)
        visited.add(question_id)
        return False

    if any(has_cycle(question_id) for question_id in question_by_id):
        return "DEPENDENCY_CYCLE", ["question dependency graph contains a cycle"], {}

    batches = packet.get("dependency_batches")
    if not isinstance(batches, list) or not batches:
        return "MALFORMED_PACKET", ["dependency_batches must be a non-empty list"], {}
    batch_index: dict[str, int] = {}
    question_batch_index: dict[str, int] = {}
    listed_questions: list[str] = []
    for index, batch in enumerate(batches):
        if not isinstance(batch, dict) or not isinstance(batch.get("id"), str) or not batch.get("id"):
            return "MALFORMED_PACKET", ["every dependency batch needs a non-empty id"], {}
        batch_id = batch["id"]
        if batch_id in batch_index:
            return "MALFORMED_PACKET", ["dependency batch IDs must be unique"], {}
        question_list = batch.get("question_ids")
        if not isinstance(question_list, list) or not all(isinstance(item, str) for item in question_list):
            return "MALFORMED_PACKET", [f"batch {batch_id}: question_ids must be a string list"], {}
        if len(question_list) != len(set(question_list)):
            return "MALFORMED_PACKET", [f"batch {batch_id}: duplicate question IDs"], {}
        batch_index[batch_id] = index
        for question_id in question_list:
            if question_id in question_batch_index:
                return "MALFORMED_PACKET", [f"question {question_id}: listed in multiple batches"], {}
            question_batch_index[question_id] = index
            listed_questions.append(question_id)
    if set(listed_questions) != question_ids:
        return "MALFORMED_PACKET", ["dependency batches must list every question exactly once"], {}
    for question_id, question in question_by_id.items():
        batch_id = question["batch_id"]
        if batch_id not in batch_index or question_batch_index.get(question_id) != batch_index[batch_id]:
            return "MALFORMED_PACKET", [f"question {question_id}: batch_id does not match dependency_batches"], {}
        if any(question_batch_index[dependency] >= question_batch_index[question_id] for dependency in dependencies[question_id]):
            return "MALFORMED_PACKET", [f"question {question_id}: dependency must be in an earlier batch"], {}

    return None, [], {
        "packet_id": packet["packet_id"],
        "question_count": len(questions),
        "option_counts": option_counts,
        "dependency_batch_count": len(batches),
    }


def decision_check(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    if args.route_id != DECISION_ROUTE_ID:
        _decision_stop(args, "MISSING_ROUTE_ID", verdict="BLOCKED_MISSING_REF", details=["route ID must be exact"])
    if args.route_depth < 0 or args.route_depth > DECISION_MAX_ROUTE_DEPTH:
        _decision_stop(args, "DEPTH_EXCEEDED")
    visited_ids = list(args.visited or [])
    if len(visited_ids) != len(set(visited_ids)) or args.policy_id in visited_ids:
        _decision_stop(args, "CYCLE_DETECTED")
    if args.policy_id != DECISION_POLICY_ID:
        _decision_stop(args, "MISSING_POLICY_REF", verdict="BLOCKED_MISSING_REF")

    packet_path = Path(args.packet).expanduser()
    if not packet_path.exists():
        _decision_stop(args, "MISSING_PACKET", verdict="BLOCKED_MISSING_REF")
    try:
        packet = _read_json_object(packet_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        _decision_stop(args, "MALFORMED_PACKET", details=[str(error)])
    policy_refs = packet.get("policy_refs")
    if not isinstance(policy_refs, list) or not all(isinstance(ref, dict) for ref in policy_refs):
        _decision_stop(args, "MALFORMED_PACKET", details=["policy_refs must be an object list"])
    exact_refs = [ref for ref in policy_refs if ref.get("id") == args.policy_id]
    if not exact_refs:
        _decision_stop(args, "MISSING_POLICY_REF", verdict="BLOCKED_MISSING_REF")
    if len(exact_refs) > 1:
        _decision_stop(args, "AMBIGUOUS_POLICY_REF")
    packet_ref = exact_refs[0]
    if packet_ref.get("route_id") != args.route_id:
        _decision_stop(args, "MISSING_ROUTE_ID", verdict="BLOCKED_MISSING_REF")
    expected_sha = packet_ref.get("source_sha256")
    if not isinstance(expected_sha, str) or not _SHA256_PATTERN.fullmatch(expected_sha):
        _decision_stop(args, "MALFORMED_PACKET", details=["policy source hash must be a lowercase SHA-256"])

    source_path = _decision_source_path(home, args.policy_source)
    if not source_path.exists() or not source_path.is_file():
        _decision_stop(args, "MISSING_POLICY_SOURCE", verdict="BLOCKED_MISSING_REF")
    try:
        source_bytes = source_path.read_bytes()
        source_text = source_bytes.decode("utf-8")
    except (OSError, UnicodeError) as error:
        _decision_stop(args, "MALFORMED_POLICY_SOURCE", details=[str(error)])
    actual_sha = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha != expected_sha:
        _decision_stop(args, "SOURCE_HASH_MISMATCH", verdict="STALE_REF")
    source_schema_version = _decision_policy_schema(source_text)
    if source_schema_version != "workflow.local-policy.v1":
        _decision_stop(args, "MALFORMED_POLICY_SOURCE", details=["unsupported or missing Local Policy schema"])
    fragment = args.policy_fragment
    if not isinstance(fragment, str) or not re.fullmatch(r"#[a-z0-9][a-z0-9._-]*", fragment):
        _decision_stop(args, "MALFORMED_POLICY_REF")
    anchor = re.escape(fragment[1:])
    if not re.search(rf"<a\s+id=[\"']{anchor}[\"']\s*>\s*</a>", source_text):
        _decision_stop(args, "MISSING_POLICY_FRAGMENT", verdict="BLOCKED_MISSING_REF")

    entry = {
        "id": args.policy_id,
        "source_path": str(source_path),
        "fragment": fragment,
        "source_schema_version": source_schema_version,
        "source_sha256": actual_sha,
    }
    failure_class, details, summary = _decision_packet_shape(packet, entry, args.route_id)
    if failure_class:
        verdict = "BLOCKED_MISSING_REF" if failure_class == "MISSING_DEPENDENCY" else "FAIL_SHAPE"
        _decision_stop(args, failure_class, verdict=verdict, details=details)

    receipt = {
        "schema": DECISION_CHECK_SCHEMA,
        "verdict": "PASS_SHAPE",
        "failure_class": None,
        "route": {
            "route_id": args.route_id,
            "policy_id": args.policy_id,
            "depth": args.route_depth,
            "max_depth": DECISION_MAX_ROUTE_DEPTH,
            "visited_ids": visited_ids + [args.policy_id],
        },
        "policy_ref": entry,
        "packet": summary,
        "semantic_decision_performed": False,
        "authorization_evaluated": False,
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))

def instance_doctor(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    ok = True
    print("== instance ==")
    for key in ["root", "config", "ops", "projects", "work", "skills", "agent_skills", "modules", "state", "logs", "cache"]:
        exists = paths[key].exists()
        print(f"{key}: {paths[key]} {'exists' if exists else 'missing'}")
        ok = ok and exists
    for key in ["sources", "data"]:
        exists = paths[key].exists()
        print(f"{key}: {paths[key]} {'exists' if exists else 'optional/not-initialized'}")
    legacy_ops = home / "ai-ops"
    if legacy_ops.exists() or legacy_ops.is_symlink():
        print(f"legacy path warning: {legacy_ops} exists; canonical OPS vault is {paths['ops']}")
    legacy_work = home / "lll-work"
    if legacy_work.exists() or legacy_work.is_symlink():
        good = legacy_work.is_symlink() and legacy_work.resolve() == paths["work"].resolve()
        print(f"local compat lll-work: {legacy_work} -> {legacy_work.resolve() if legacy_work.is_symlink() else 'not-symlink'} {'ok' if good else 'local-only/check'}")
    else:
        print("local compat lll-work: not configured")
    ok = validate_projects(home) and ok
    ok = validate_sources(home) and ok
    raise SystemExit(0 if ok else 1)


def status(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    projects = read_projects(home)
    explicit_sources = read_sources(home)
    sources = compiled_sources(home)
    counts: dict[str, int] = {}
    for p in projects:
        counts[str(p.get("status", "active"))] = counts.get(str(p.get("status", "active")), 0) + 1
    if args.json:
        payload = {
            "schema": "aios.status.v1",
            "ok": True,
            "paths": {
                key: str(paths[key])
                for key in ("root", "ops", "work", "skills", "agent_skills", "modules")
            },
            "projects": {
                "total": len(projects),
                "by_status": dict(sorted(counts.items())),
            },
            "sources": {
                "total": len(sources),
                "explicit": len(explicit_sources),
                "project_projections": len(sources) - len(explicit_sources),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return
    print(f"AIOS root: {paths['root']}")
    print(f"OPS vault: {paths['ops']}")
    print(f"Work root: {paths['work']}")
    print(f"AIOS skills metadata/cache: {paths['skills']}")
    print(f"Agent runtime skills: {paths['agent_skills']}")
    print(f"Modules: {paths['modules']}")
    print(f"Projects: {len(projects)} {counts}")
    explicit_source_count = len(explicit_sources)
    print(f"Sources: {len(sources)} ({explicit_source_count} explicit + {len(sources) - explicit_source_count} project projections)")




def update_modules(args: argparse.Namespace, *, paths: dict[str, Path] | None = None, apply: bool | None = None) -> int:
    """Update one or more Git module checkouts under ~/aios/modules."""
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = paths or instance_paths(home)
    apply = (not bool(args.dry_run)) if apply is None else apply
    modules = paths["modules"]
    selected = getattr(args, "modules", None) or getattr(args, "module", None) or []
    if isinstance(selected, str):
        selected = [selected]
    code = 0

    print("== modules ==")
    if not modules.exists():
        print(f"modules dir missing: {modules}")
        return 1

    children = [modules / name for name in selected] if selected else sorted(modules.iterdir(), key=lambda x: x.name)
    for child in children:
        real = child.resolve() if child.exists() or child.is_symlink() else child
        if not child.exists() and not child.is_symlink():
            print(f"missing module: {child}")
            code = max(code, 1)
            continue
        if (real / ".git").exists():
            rc = run(["git", "-C", str(real), "pull", "--ff-only"], apply=apply)
            code = max(code, rc)
        else:
            print(f"skip non-git module: {child}")
    return code


def update_ops(args: argparse.Namespace, *, paths: dict[str, Path] | None = None, apply: bool | None = None) -> int:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = paths or instance_paths(home)
    apply = (not bool(args.dry_run)) if apply is None else apply
    print("== ops vault template ==")
    tpl = ROOT / "modules" / "aiops-vault-template"
    script = tpl / "scripts" / "install.py"
    if script.exists():
        # Runtime skills are owned by skillpack sync. Keep update_ops focused on
        # refreshing the vault template so `aios update all` does not create
        # unmanaged skill directories before the skillpack phase runs.
        return run(["python3", str(script), "--vault", str(paths["ops"]), "--agent", "none"], apply=apply)
    print(f"missing bundled ops template installer: {script}")
    return 1


def update_skills(args: argparse.Namespace, *, apply: bool | None = None) -> int:
    apply = (not bool(args.dry_run)) if apply is None else apply
    print("== skills ==")
    skill_args = argparse.Namespace(
        home=args.home,
        apply=apply,
        dry_run=not apply,
        prune=getattr(args, "prune", False),
        force=getattr(args, "force", False),
        mode=getattr(args, "mode", None),
        target=getattr(args, "target", "universal"),
        state_dir=None,
        first_party_only=False,
    )
    try:
        skillpack_sync(skill_args)
        return 0
    except SystemExit as e:
        if isinstance(e.code, int):
            return int(e.code or 0)
        if e.code:
            print(e.code)
        return 1


def update(args: argparse.Namespace) -> None:
    """Product-level update entrypoint. Defaults to all update phases."""
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    apply = not bool(args.dry_run)
    subject = getattr(args, "subject", None) or "all"
    code = 0

    if subject != "all" and (getattr(args, "no_skills", False) or getattr(args, "no_ops", False)):
        print("error: --no-skills and --no-ops only apply to `aios update all`", file=sys.stderr)
        raise SystemExit(2)

    if subject in {"all", "modules"}:
        code = max(code, update_modules(args, paths=paths, apply=apply))
    if subject in {"all", "ops"} and not getattr(args, "no_ops", False):
        code = max(code, update_ops(args, paths=paths, apply=apply))
    if subject in {"all", "skills"} and not getattr(args, "no_skills", False):
        code = max(code, update_skills(args, apply=apply))

    raise SystemExit(code)


def assets_manifest_path() -> Path | None:
    for path in ASSET_FILES:
        if path.exists():
            return path
    return None


def _doctor_git_env(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return env


def _run_doctor_git(home: Path, path: Path, *git_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-C",
            str(path),
            *git_args,
        ],
        text=True,
        capture_output=True,
        env=_doctor_git_env(home),
    )


def assets_doctor(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if getattr(args, "home", None) else Path.home()
    manifest_path = assets_manifest_path()
    safe = lambda value: redact_output(str(value), [])
    print(f"assets manifest: {safe(manifest_path)}")
    example_only = bool(manifest_path and manifest_path.name == "local-assets.example.json")
    assets = load_assets().get("assets", [])
    ok = True
    for a in assets:
        path = expand(a.get("canonical_path"), home=home)
        print(f"\n[{safe(a.get('id'))}] {safe(a.get('kind'))}\n  path: {safe(path)}")
        if not path or not path.exists():
            print("  status: missing" + (" (example only)" if example_only else ""))
            ok = ok and example_only
            continue
        if path.is_symlink():
            print(f"  symlink -> {safe(path.resolve())}")
        remote = a.get("remote")
        if remote:
            result = _run_doctor_git(home, path, "config", "--local", "--no-includes", "--get-all", "remote.origin.url")
            if result.returncode == 0:
                got = result.stdout.splitlines()[0].strip()
                print(f"  origin: {safe(got)}")
                if got != str(remote):
                    print(f"  expected: {safe(remote)}")
                    ok = False
            else:
                print("  git: not a repo or no origin")
                ok = False
            st = _run_doctor_git(home, path, "status", "--short", "--branch")
            if st.returncode == 0:
                print("  git status:")
                for line in st.stdout.rstrip().splitlines()[:20]:
                    print(f"    {safe(line)}")
        link = a.get("discovery_link")
        if link:
            lp = expand(link, home=home)
            print(f"  discovery_link: {safe(lp)} {'exists' if lp and lp.exists() else 'missing'}")
    raise SystemExit(0 if ok else 1)


def assets_link(args: argparse.Namespace) -> None:
    apply = bool(args.apply)
    for a in load_assets().get("assets", []):
        link = a.get("discovery_link")
        if not link:
            continue
        src = expand(a.get("canonical_path"))
        dst = expand(link)
        if not src or not dst:
            continue
        symlink(src, dst, apply=apply)


MATTER_OPEN_STATES = {"active", "paused"}
MATTER_CLOSED_STATES = {"closed", "archived"}
DELIVERY_EXTENSIONS = {".md", ".html", ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".zip"}
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
MATTER_ROLLOVER_AUTHORIZED_OPERATION = (
    "B6 one exact Matter current Worksite rollover through a CAS/idempotent/receipt-backed actuator"
)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, json_bytes(value))


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(
    path: Path,
    data: bytes,
    *,
    mode: int | None = None,
    expected_current_sha256: str | None = None,
) -> None:
    """Publish one file durably without exposing a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    inherited_mode = (path.stat().st_mode & 0o777) if path.exists() else None
    fd, raw = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=str(path.parent))
    tmp = Path(raw)
    try:
        os.fchmod(fd, mode if mode is not None else inherited_mode if inherited_mode is not None else 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if expected_current_sha256 is not None:
            try:
                observed = sha256_file(path)
            except OSError as exc:
                matter_rollover_failure(
                    "CANONICAL_CAS_MISMATCH",
                    "canonical file became unreadable immediately before atomic replace",
                    path=str(path),
                    expected_sha256=expected_current_sha256,
                    error=str(exc),
                )
            if observed != expected_current_sha256:
                matter_rollover_failure(
                    "CANONICAL_CAS_MISMATCH",
                    "canonical file changed immediately before atomic replace",
                    path=str(path),
                    expected_sha256=expected_current_sha256,
                    observed_sha256=observed,
                )
        os.replace(tmp, path)
        fsync_directory(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def mission_fields(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:40000]
    except OSError:
        return {}
    out: dict[str, str] = {}
    heading = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    if heading:
        out["title"] = heading.group(1).strip()
    for key in ["mission_id", "parent_matter_id", "parent_worksite", "status", "phase", "kind", "project_id", "asset_policy", "retention", "updated_at", "created_at"]:
        match = re.search(rf"^{re.escape(key)}:\s*([^\n#]+)", text, re.M)
        if match:
            out[key] = match.group(1).strip()
    return out


def normalize_matter_lifecycle(raw_status: str, lifecycle: dict[str, Any], location_kind: str) -> tuple[str, bool, str]:
    explicit = str(lifecycle.get("state") or "").strip().lower()
    attention = str(lifecycle.get("attention") or "").strip().lower() or "current"
    status = (raw_status or "").strip().lower()
    if location_kind in {"archive", "quarantine"}:
        state = "archived" if location_kind == "archive" else "closed"
    elif explicit in {"active", "paused", "closed", "archived"}:
        state = explicit
    elif any(token in status for token in ["archive", "closed", "cancel", "abandon"]):
        state = "archived" if "archive" in status else "closed"
    elif any(token in status for token in ["complete", "done", "succeeded"]):
        state = "closed"
    elif any(token in status for token in ["pause", "waiting", "defer", "backlog"]):
        state = "paused"
    else:
        state = "active"
    reopenable = bool(lifecycle.get("reopenable", state in {"active", "paused"}))
    return state, reopenable, attention


def matter_roots(home: Path) -> list[tuple[str, Path]]:
    paths = instance_paths(home)
    candidates = [
        ("work", paths["work"]),
        ("quarantine", paths["data"] / "quarantine" / "worksites"),
        ("archive", paths["data"] / "archive" / "worksites"),
        ("archive", home / "lll-archive"),
    ]
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for kind, root in candidates:
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key not in seen:
            seen.add(key)
            out.append((kind, root))
    return out


def infer_delivery_paths(workdir: Path, matter: dict[str, Any]) -> list[str]:
    configured_raw = matter.get("delivery")
    configured: dict[str, Any] = configured_raw if isinstance(configured_raw, dict) else {}
    featured_raw = configured.get("featured")
    featured: list[Any] = featured_raw if isinstance(featured_raw, list) else []
    candidates: list[str] = ["mission.md"]
    candidates.extend(str(x) for x in featured)
    if not featured:
        human_views_raw = matter.get("human_views")
        human_views: list[Any] = human_views_raw if isinstance(human_views_raw, list) else []
        for view in human_views:
            if not isinstance(view, dict) or view.get("status") not in {"current", "accepted", "final", "final_validated_pass_with_notes"}:
                continue
            rel = str(view.get("path") or "")
            if rel and "/" not in rel:
                candidates.append(rel)
        if len(candidates) == 1:
            root_files = []
            for child in workdir.iterdir():
                if child.is_file() and child.name != "mission.md" and child.suffix.lower() in DELIVERY_EXTENSIONS:
                    score = 0
                    lowered = child.name.lower()
                    for token, weight in [("final", 8), ("report", 7), ("summary", 6), ("delivery", 6), ("readme", 5), ("plan", 3), ("notes", 1)]:
                        if token in lowered:
                            score += weight
                    root_files.append((-score, -child.stat().st_mtime, child.name))
            candidates.extend(x[2] for x in sorted(root_files)[:8])
    limit = int(configured.get("limit") or 12)
    selected: list[str] = []
    for rel in candidates:
        if not rel or rel in selected:
            continue
        path = (workdir / rel).resolve()
        try:
            path.relative_to(workdir.resolve())
        except ValueError:
            continue
        if path.is_file() and (rel == "mission.md" or path.suffix.lower() in DELIVERY_EXTENSIONS):
            selected.append(rel)
        if len(selected) >= limit:
            break
    return selected


def compile_matter_record(workdir: Path, *, location_kind: str, home: Path) -> dict[str, Any]:
    matter_path = workdir / "internal" / "matter.json"
    matter = read_json_dict(matter_path)
    owner_workdir = workdir.resolve()
    formal_worksite = matter.get("worksite") if isinstance(matter.get("worksite"), dict) else {}
    current_raw = formal_worksite.get("path") if formal_worksite else None
    current_workdir = Path(str(current_raw)).expanduser().resolve() if current_raw else owner_workdir
    mission = mission_fields(current_workdir / "mission.md")
    lifecycle_raw = matter.get("lifecycle")
    lifecycle: dict[str, Any] = lifecycle_raw if isinstance(lifecycle_raw, dict) else {}
    raw_status = str(matter.get("status") or mission.get("status") or "unknown")
    state, reopenable, attention = normalize_matter_lifecycle(raw_status, lifecycle, location_kind)
    matter_id = str(matter.get("id") or f"worksite:{workdir.name}")
    title = str(matter.get("title") or mission.get("title") or workdir.name)
    updated = str(matter.get("updated_at") or mission.get("updated_at") or _dt.datetime.fromtimestamp(owner_workdir.stat().st_mtime).astimezone().isoformat(timespec="seconds"))
    aliases_raw = matter.get("aliases")
    aliases: list[Any] = aliases_raw if isinstance(aliases_raw, list) else []
    return {
        "id": matter_id,
        "record_type": "matter" if matter else "inferred_worksite",
        "title": title,
        "aliases": [str(x) for x in aliases],
        "status": raw_status,
        "lifecycle_state": state,
        "attention": attention,
        "reopenable": reopenable,
        "priority": matter.get("priority"),
        "current_focus": matter.get("current_focus"),
        "worksite_name": current_workdir.name,
        "worksite_path": str(current_workdir),
        "owner_worksite_path": str(owner_workdir) if matter else None,
        "display_path": display_path(current_workdir, home),
        "location_kind": location_kind,
        "mission_path": str(matter.get("mission_path") or "mission.md"),
        "delivery_paths": infer_delivery_paths(current_workdir, matter),
        "matter_path": str(matter_path.resolve()) if matter_path.exists() else None,
        "updated_at": updated,
    }


def compile_matter_index(home: Path) -> dict[str, Any]:
    candidates: list[tuple[str, Path]] = []
    seen_owner_paths: set[str] = set()
    for location_kind, root in matter_roots(home):
        if not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            probable, _ = is_probable_lll_workdir(child)
            if not probable and not (child / "internal" / "matter.json").exists():
                continue
            resolved = str(child.resolve())
            if resolved in seen_owner_paths:
                continue
            seen_owner_paths.add(resolved)
            candidates.append((location_kind, child))

    # Pass 1: formal Matter capsules own their current Worksite claim even when
    # the physical owner capsule remains in an older Worksite.
    records: list[dict[str, Any]] = []
    formal_claims: dict[str, str] = {}
    formal_owners: set[str] = set()
    for location_kind, child in candidates:
        if not (child / "internal" / "matter.json").is_file():
            continue
        record = compile_matter_record(child, location_kind=location_kind, home=home)
        owner_path = str(child.resolve())
        claim = str(Path(record["worksite_path"]).resolve())
        prior = formal_claims.get(claim)
        if prior is not None and prior != record["id"]:
            raise SystemExit(f"duplicate formal Matter Worksite claim: {claim} ({prior}, {record['id']})")
        formal_claims[claim] = str(record["id"])
        formal_owners.add(owner_path)
        records.append(record)

    # Pass 2: infer only unowned Worksites. A formal current pointer suppresses
    # the otherwise duplicated inferred target record.
    for location_kind, child in candidates:
        resolved = str(child.resolve())
        if resolved in formal_owners or resolved in formal_claims:
            continue
        records.append(compile_matter_record(child, location_kind=location_kind, home=home))
    records.sort(key=lambda x: (x.get("updated_at") or "", x["id"]), reverse=True)
    return {
        "schema": "aios.matter.index.v1",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "authority": "derived_from_worksite_files",
        "records": records,
        "counts": {
            "total": len(records),
            **{state: sum(1 for r in records if r["lifecycle_state"] == state) for state in ["active", "paused", "closed", "archived"]},
            "reopenable": sum(1 for r in records if r["reopenable"]),
        },
    }


def matter_index_path(home: Path) -> Path:
    return instance_paths(home)["state"] / "matters" / "index.json"


def refresh_matter_index(home: Path, *, write: bool = True) -> dict[str, Any]:
    index = compile_matter_index(home)
    if write:
        atomic_json(matter_index_path(home), index)
    return index


def resolve_matter_record(index: dict[str, Any], query: str) -> dict[str, Any] | None:
    needle = query.strip().lower()
    records = index.get("records", [])
    exact = [r for r in records if needle in {str(r.get("id", "")).lower(), str(r.get("worksite_name", "")).lower(), *(str(x).lower() for x in r.get("aliases", []))}]
    if len(exact) == 1:
        return exact[0]
    matches = [r for r in records if needle in " ".join([str(r.get("id", "")), str(r.get("title", "")), str(r.get("worksite_name", "")), " ".join(r.get("aliases", []))]).lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit("ambiguous Matter query: " + ", ".join(str(r["id"]) for r in matches[:10]))
    return None


def matter_index(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    index = refresh_matter_index(home, write=not args.dry_run)
    if args.json:
        print(json.dumps(index, ensure_ascii=False, indent=2))
    else:
        target = "dry-run" if args.dry_run else str(matter_index_path(home))
        print(f"Matter index: {target}")
        print(" ".join(f"{k}={v}" for k, v in index["counts"].items()))


def matter_list(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    index = refresh_matter_index(home, write=False)
    rows = index["records"]
    if args.state:
        rows = [r for r in rows if r["lifecycle_state"] == args.state]
    if args.reopenable:
        rows = [r for r in rows if r["reopenable"]]
    if args.query:
        needle = args.query.lower()
        exact = [r for r in rows if needle in {r["id"].lower(), r["worksite_name"].lower(), *(str(x).lower() for x in r.get("aliases", []))}]
        rows = exact or [r for r in rows if needle in " ".join([r["id"], r["title"], r["worksite_name"], " ".join(r.get("aliases", []))]).lower()]
    if args.limit:
        rows = rows[:args.limit]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    for row in rows:
        reopen = " reopenable" if row["reopenable"] else ""
        print(f"- {row['id']} [{row['lifecycle_state']}/{row['attention']}{reopen}] {row['title']} -> {row['display_path']}")


def matter_get(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    index = refresh_matter_index(home, write=False)
    record = resolve_matter_record(index, args.query)
    if not record:
        raise SystemExit(f"Matter not found: {args.query}")
    print(json.dumps(record, ensure_ascii=False, indent=2))


class MatterRolloverFailure(Exception):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def matter_rollover_failure(code: str, message: str, **details: Any) -> None:
    raise MatterRolloverFailure(code, message, **details)


def matter_rollover_state_root(home: Path) -> Path:
    return instance_paths(home)["state"] / "matters"


def matter_rollover_lock_path(home: Path, matter_id: str) -> Path:
    return matter_rollover_state_root(home) / "locks" / f"{safe_view_component(matter_id)}.lock"


def safe_view_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "item"


def matter_rollover_receipt_path(home: Path, matter_id: str, target_id: str) -> Path:
    name = f"matter-rollover__{safe_view_component(matter_id)}__{safe_view_component(target_id)}.json"
    return matter_rollover_state_root(home) / "change-sets" / name


@contextlib.contextmanager
def matter_rollover_lock(home: Path, matter_id: str) -> Any:
    path = matter_rollover_lock_path(home, matter_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            matter_rollover_failure("LOCK_BUSY", "Matter rollover lock is busy", lock_path=str(path))
        yield path
    finally:
        os.close(fd)


def formal_matter_sources(home: Path) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for _kind, root in matter_roots(home):
        if not root.exists():
            continue
        try:
            resolved_root = root.resolve(strict=True)
        except OSError:
            continue
        for child in root.iterdir():
            if child.is_symlink() or not child.is_dir():
                continue
            try:
                resolved_child = child.resolve(strict=True)
                resolved_child.relative_to(resolved_root)
            except (OSError, ValueError):
                continue
            path = resolved_child / "internal" / "matter.json"
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            value = read_json_dict(path)
            if value:
                found.append((path.resolve(), value))
    return found


def exact_formal_matter(home: Path, matter_id: str) -> tuple[Path, dict[str, Any]]:
    matches = [(path, value) for path, value in formal_matter_sources(home) if value.get("id") == matter_id]
    if not matches:
        matter_rollover_failure("MATTER_NOT_FOUND", "exact formal Matter ID was not found", matter_id=matter_id)
    if len(matches) != 1:
        matter_rollover_failure(
            "MATTER_AMBIGUOUS",
            "exact formal Matter ID has multiple owner records",
            matter_id=matter_id,
            paths=[str(path) for path, _value in matches],
        )
    return matches[0]


def read_event_stream(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        matter_rollover_failure("EXPECTED_CURRENT_MISMATCH", "Matter event stream is missing or unreadable", path=str(path), error=str(exc))
    events: list[dict[str, Any]] = []
    try:
        for line in data.splitlines():
            if line.strip():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("event row is not an object")
                events.append(event)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        matter_rollover_failure("EXPECTED_CURRENT_MISMATCH", "Matter event stream is invalid JSONL", path=str(path), error=str(exc))
    return data, events


def required_rollover_args(args: argparse.Namespace) -> None:
    required = [
        "expected_current_id",
        "expected_current_path",
        "expected_current_role",
        "expected_matter_sha256",
        "expected_events_sha256",
        "expected_event_line_count",
        "to_worksite",
        "to_worksite_id",
        "to_role",
        "idempotency_key",
        "fence_token",
    ]
    missing = ["--" + name.replace("_", "-") for name in required if getattr(args, name, None) in {None, ""}]
    if missing:
        matter_rollover_failure("INVALID_PLAN", "rollover plan is missing required arguments", missing=missing)


def expected_worksite_object(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": args.expected_current_id,
        "path": str(Path(args.expected_current_path).expanduser().resolve()),
        "role": args.expected_current_role,
        "recovery_path": "internal/recovery.json",
        "binding": "owned",
        "owner_matter_id": args.matter_id,
    }


def target_worksite_object(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": args.to_worksite_id,
        "path": str(Path(args.to_worksite).expanduser().resolve()),
        "role": args.to_role,
        "recovery_path": "internal/recovery.json",
        "binding": "owned",
        "owner_matter_id": args.matter_id,
    }


def _authorization_scope_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        return None
    try:
        return str(path.resolve(strict=True))
    except OSError:
        return None


def validate_rollover_authorization(
    args: argparse.Namespace,
    *,
    target: Path,
    target_mission: dict[str, str],
) -> dict[str, Any]:
    """Validate the durable exact-operation grant before creating the lock or a receipt."""
    if not args.authorization_ref:
        matter_rollover_failure("OWNER_AUTHORIZATION_MISSING", "--apply requires --authorization-ref")
    reference = Path(args.authorization_ref).expanduser()
    if not reference.exists():
        matter_rollover_failure(
            "AUTHORIZATION_REF_NOT_FOUND",
            "durable authorization JSON does not exist",
            authorization_ref=str(reference),
        )
    if not reference.is_file():
        matter_rollover_failure(
            "AUTHORIZATION_REF_UNREADABLE",
            "durable authorization reference is not a readable regular file",
            authorization_ref=str(reference),
        )
    try:
        raw = reference.read_bytes()
    except OSError as exc:
        matter_rollover_failure(
            "AUTHORIZATION_REF_UNREADABLE",
            "durable authorization JSON is unreadable",
            authorization_ref=str(reference),
            error=str(exc),
        )
    try:
        authorization = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        matter_rollover_failure(
            "AUTHORIZATION_INVALID",
            "durable authorization is not valid JSON",
            authorization_ref=str(reference),
            error=str(exc),
        )
    if not isinstance(authorization, dict) or authorization.get("schema") != "aios.phase_b.authorization.v1":
        matter_rollover_failure(
            "AUTHORIZATION_INVALID",
            "durable authorization schema must be aios.phase_b.authorization.v1",
            authorization_ref=str(reference),
        )
    scope = authorization.get("scope") if isinstance(authorization.get("scope"), dict) else {}
    authorized = authorization.get("authorized") if isinstance(authorization.get("authorized"), list) else []
    parent_worksite = _authorization_scope_path(target_mission.get("parent_worksite"))
    expected = {
        "worksite": str(target.resolve()),
        "parent_worksite": parent_worksite,
        "parent_matter": target_mission.get("parent_matter_id"),
    }
    observed = {
        "worksite": _authorization_scope_path(scope.get("worksite")),
        "parent_worksite": _authorization_scope_path(scope.get("parent_worksite")),
        "parent_matter": scope.get("parent_matter"),
    }
    if (
        parent_worksite is None
        or target_mission.get("parent_matter_id") != args.matter_id
        or observed != expected
        or MATTER_ROLLOVER_AUTHORIZED_OPERATION not in authorized
    ):
        matter_rollover_failure(
            "AUTHORIZATION_SCOPE_MISMATCH",
            "durable authorization does not grant this exact B6 Matter rollover scope",
            authorization_ref=str(reference.resolve()),
        )
    return {
        "path": str(reference.resolve()),
        "sha256": sha256_bytes(raw),
        "authorization_id": authorization.get("authorization_id"),
    }


def validate_sha256_arg(value: str, option: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        matter_rollover_failure("INVALID_PLAN", f"{option} must be a lowercase SHA-256 digest")


def build_rollover_candidate(args: argparse.Namespace, home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    required_rollover_args(args)
    validate_sha256_arg(args.expected_matter_sha256, "--expected-matter-sha256")
    validate_sha256_arg(args.expected_events_sha256, "--expected-events-sha256")
    if not Path(args.expected_current_path).expanduser().is_absolute() or not Path(args.to_worksite).expanduser().is_absolute():
        matter_rollover_failure("INVALID_PLAN", "current and target Worksite paths must be absolute")

    matter_path, matter = exact_formal_matter(home, args.matter_id)
    events_path = matter_path.with_name("matter.events.jsonl")
    matter_data = matter_path.read_bytes()
    events_data, events = read_event_stream(events_path)
    target = Path(args.to_worksite).expanduser().resolve()
    if not target.is_dir():
        matter_rollover_failure("TARGET_NOT_FOUND", "target Worksite directory was not found", target=str(target))
    mission_path = target / "mission.md"
    recovery_path = target / "internal" / "recovery.json"
    if not mission_path.is_file():
        matter_rollover_failure("TARGET_NOT_FOUND", "target mission.md was not found", target=str(target))
    mission = mission_fields(mission_path)
    recovery = read_json_dict(recovery_path)
    if mission.get("mission_id") != args.to_worksite_id or mission.get("parent_matter_id") != args.matter_id:
        matter_rollover_failure(
            "TARGET_IDENTITY_MISMATCH",
            "target mission identity does not match the exact rollover plan",
            observed_mission_id=mission.get("mission_id"),
            observed_parent_matter_id=mission.get("parent_matter_id"),
        )
    if not recovery or not str(recovery.get("schema") or "").startswith("lll.recovery.") or not recovery.get("status"):
        matter_rollover_failure("TARGET_RECOVERY_INVALID", "target recovery is missing or invalid", recovery_path=str(recovery_path))
    mission_status = str(mission.get("status") or "").lower()
    target_status = str(recovery.get("status") or mission.get("status") or "").lower()
    if mission_status and mission_status != target_status:
        matter_rollover_failure(
            "TARGET_RECOVERY_INVALID",
            "target mission and recovery lifecycle statuses disagree",
            mission_status=mission_status,
            recovery_status=target_status,
        )
    if target_status not in {"active", "completed"}:
        matter_rollover_failure(
            "TARGET_RECOVERY_INVALID",
            "target Worksite lifecycle status must be active or completed",
            target_status=target_status,
        )
    if args.to_role != "current_canonical":
        matter_rollover_failure(
            "TARGET_IDENTITY_MISMATCH",
            "the formal current Worksite binding requires lifecycle-neutral role current_canonical",
        )
    if (target / "internal" / "matter.json").exists():
        matter_rollover_failure("TARGET_ALREADY_CLAIMED", "target Worksite contains a formal Matter owner", target=str(target))
    for other_path, other in formal_matter_sources(home):
        other_worksite = other.get("worksite") if isinstance(other.get("worksite"), dict) else {}
        claimed = other_worksite.get("path")
        if claimed and Path(str(claimed)).expanduser().resolve() == target and other.get("id") != args.matter_id:
            matter_rollover_failure(
                "TARGET_ALREADY_CLAIMED",
                "another formal Matter claims the target Worksite",
                claiming_matter_id=other.get("id"),
                matter_path=str(other_path),
            )

    before = expected_worksite_object(args)
    after = target_worksite_object(args)
    candidate = {
        "schema": "aios.matter.rollover.candidate.v1",
        "matter_id": args.matter_id,
        "matter_path": str(matter_path),
        "expected_matter_sha256": args.expected_matter_sha256,
        "expected_event_sha256": args.expected_events_sha256,
        "expected_event_sequence": args.expected_event_line_count,
        "from_worksite": before,
        "to_worksite": after,
        "target_mission_sha256": sha256_file(mission_path),
        "target_recovery_sha256": sha256_file(recovery_path),
        "target_mission_status": str(mission.get("status") or ""),
        "target_recovery_status": str(recovery.get("status") or ""),
        "target_parent_matter_id": args.matter_id,
        "idempotency_key": args.idempotency_key,
    }
    plan_digest = sha256_bytes(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    supplied_fence = args.fence_token.removeprefix("sha256:")
    if supplied_fence != plan_digest:
        matter_rollover_failure("FENCE_TOKEN_MISMATCH", "fence token does not bind the exact rollover candidate", expected=f"sha256:{plan_digest}")
    context = {
        "matter_path": matter_path,
        "events_path": events_path,
        "matter": matter,
        "matter_data": matter_data,
        "events": events,
        "events_data": events_data,
        "target": target,
        "mission": mission,
        "recovery": recovery,
        "plan_digest": plan_digest,
    }
    return candidate, context


def assert_expected_rollover_preimage(args: argparse.Namespace, context: dict[str, Any]) -> None:
    observed = {
        "matter_sha256": sha256_bytes(context["matter_data"]),
        "worksite": context["matter"].get("worksite"),
        "events_sha256": sha256_bytes(context["events_data"]),
        "event_line_count": len(context["events"]),
    }
    expected = {
        "matter_sha256": args.expected_matter_sha256,
        "worksite": expected_worksite_object(args),
        "events_sha256": args.expected_events_sha256,
        "event_line_count": args.expected_event_line_count,
    }
    if observed != expected:
        matter_rollover_failure("EXPECTED_CURRENT_MISMATCH", "Matter snapshot or event CAS did not match", expected=expected, observed=observed)


def find_rollover_receipt(home: Path, candidate: dict[str, Any], plan_digest: str) -> tuple[Path, dict[str, Any]] | None:
    root = matter_rollover_state_root(home) / "change-sets"
    expected_path = matter_rollover_receipt_path(home, candidate["matter_id"], candidate["to_worksite"]["id"])
    if not root.exists():
        return None
    for path in root.glob(f"matter-rollover__{safe_view_component(candidate['matter_id'])}__*.json"):
        value = read_json_dict(path)
        same_slot = path.resolve() == expected_path.resolve()
        same_key = value.get("idempotency_key") == candidate["idempotency_key"]
        if not same_slot and not same_key:
            continue
        assert_rollover_receipt_integrity(value)
        if value.get("plan_digest") != plan_digest:
            matter_rollover_failure(
                "IDEMPOTENCY_CONFLICT",
                "receipt slot or idempotency key is already bound to a different plan",
                receipt_path=str(path),
            )
        return path, value
    return None


def find_rollover_receipt_for_request(home: Path, args: argparse.Namespace) -> tuple[Path, dict[str, Any]] | None:
    """Resolve an existing exact slot/key without rebuilding a post-commit candidate."""
    root = matter_rollover_state_root(home) / "change-sets"
    expected_path = matter_rollover_receipt_path(home, args.matter_id, args.to_worksite_id)
    if not root.exists():
        return None
    requested_candidate = {
        "matter_id": args.matter_id,
        "expected_matter_sha256": args.expected_matter_sha256,
        "expected_event_sha256": args.expected_events_sha256,
        "expected_event_sequence": args.expected_event_line_count,
        "from_worksite": expected_worksite_object(args),
        "to_worksite": target_worksite_object(args),
        "idempotency_key": args.idempotency_key,
    }
    for path in root.glob(f"matter-rollover__{safe_view_component(args.matter_id)}__*.json"):
        receipt = read_json_dict(path)
        same_slot = path.resolve() == expected_path.resolve()
        same_key = receipt.get("idempotency_key") == args.idempotency_key
        if not same_slot and not same_key:
            continue
        assert_rollover_receipt_integrity(receipt)
        frozen = receipt.get("candidate") if isinstance(receipt.get("candidate"), dict) else {}
        frozen_subset = {key: frozen.get(key) for key in requested_candidate}
        if (
            frozen_subset != requested_candidate
            or receipt.get("plan_digest") != args.fence_token.removeprefix("sha256:")
            or receipt.get("fence_token") != args.fence_token
        ):
            matter_rollover_failure(
                "IDEMPOTENCY_CONFLICT",
                "receipt slot or idempotency key is already bound to a different plan",
                receipt_path=str(path),
            )
        return path, receipt
    return None


def assert_rollover_receipt_target_current(receipt: dict[str, Any]) -> None:
    target = Path(str(receipt.get("target", {}).get("path") or "")).expanduser().resolve()
    mission = mission_fields(target / "mission.md")
    recovery = read_json_dict(target / "internal" / "recovery.json")
    mission_status = str(mission.get("status") or "").lower()
    recovery_status = str(recovery.get("status") or "").lower()
    if (
        not target.is_dir()
        or mission.get("mission_id") != receipt.get("target", {}).get("mission_id")
        or mission.get("parent_matter_id") != receipt.get("matter_id")
        or not str(recovery.get("schema") or "").startswith("lll.recovery.")
        or mission_status != recovery_status
        or recovery_status not in {"active", "completed"}
    ):
        matter_rollover_failure(
            "TARGET_IDENTITY_MISMATCH",
            "receipt target identity or lifecycle is no longer valid",
            target=str(target),
        )


def assert_rollover_receipt_canonical_guards(receipt: dict[str, Any]) -> None:
    matter_path = Path(receipt["matter"]["path"])
    events_path = Path(receipt["events"]["path"])
    events_data, events = read_event_stream(events_path)
    observed = {
        "matter_sha256": sha256_file(matter_path),
        "events_sha256": sha256_bytes(events_data),
        "event_line_count": len(events),
        "event_id": events[-1].get("event_id") if events else None,
    }
    expected = receipt["rollback_guards"]
    if observed != expected:
        matter_rollover_failure(
            "CANONICAL_GUARD_MISMATCH",
            "canonical Matter/event facts no longer match the receipt postimage",
            expected=expected,
            observed=observed,
        )


def write_rollover_receipt(path: Path, receipt: dict[str, Any], *, state: str | None = None) -> None:
    if state is not None:
        receipt["state"] = state
    receipt["updated_at"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    receipt["receipt_digest"] = rollover_receipt_immutable_digest(receipt)
    atomic_json(path, receipt)


def rollover_receipt_immutable_digest(receipt: dict[str, Any]) -> str:
    keys = [
        "schema",
        "receipt_id",
        "transaction_id",
        "event_id",
        "idempotency_key",
        "authorization_ref",
        "authorization",
        "owner_ref",
        "matter_id",
        "plan_digest",
        "fence_token",
        "candidate",
        "matter",
        "events",
        "target",
        "rollback_guards",
        "state",
        "rollback_digest",
    ]
    payload = {key: receipt.get(key) for key in keys}
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def assert_rollover_receipt_integrity(receipt: dict[str, Any]) -> None:
    if receipt.get("receipt_digest") != rollover_receipt_immutable_digest(receipt):
        matter_rollover_failure("RECEIPT_INTEGRITY_MISMATCH", "durable rollover receipt immutable fields changed")
    rollback = receipt.get("rollback")
    rollback_digest = receipt.get("rollback_digest")
    if isinstance(rollback, dict) != isinstance(rollback_digest, str):
        matter_rollover_failure("RECEIPT_INTEGRITY_MISMATCH", "durable rollback receipt binding is incomplete")
    if isinstance(rollback, dict):
        digest = sha256_bytes(json.dumps(rollback, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if rollback_digest != digest:
            matter_rollover_failure("RECEIPT_INTEGRITY_MISMATCH", "durable rollback receipt fields changed")


def maybe_rollover_test_fault(point: str) -> None:
    if os.environ.get("AIOS_TEST_MATTER_ROLLOVER_CRASH_AFTER") == point:
        raise RuntimeError(f"injected Matter rollover crash after {point}")


def maybe_rollover_concurrent_update(point: str, path: Path) -> None:
    if os.environ.get("AIOS_TEST_MATTER_ROLLOVER_CONCURRENT_UPDATE_BEFORE") != point:
        return
    if point == "matter":
        current = read_json_dict(path)
        current["test_concurrent_update"] = True
        atomic_json(path, current)
        return
    line = json.dumps(
        {
            "schema": "aios.workflow.event.v0",
            "event_id": "evt_test_concurrent_update",
            "type": "test.concurrent_update",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    old = path.read_bytes()
    atomic_bytes(path, old + (b"" if not old or old.endswith(b"\n") else b"\n") + line)


def new_rollover_receipt(args: argparse.Namespace, candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    key_digest = sha256_bytes(args.idempotency_key.encode("utf-8"))
    suffix = key_digest[:24]
    post_matter = dict(context["matter"])
    post_matter["worksite"] = candidate["to_worksite"]
    post_matter["updated_at"] = now
    post_matter_data = json_bytes(post_matter)
    event_id = f"evt_matter_rollover_{suffix}"
    event = {
        "schema": "aios.workflow.event.v0",
        "event_id": event_id,
        "ts": now,
        "type": "worksite.migrated",
        "actor": {"kind": "cli", "id": "aios matter rollover"},
        "subject": {"kind": "matter", "id": args.matter_id},
        "summary": "Atomically changed the formal Matter current Worksite pointer.",
        "payload": {
            "from_worksite": candidate["from_worksite"],
            "to_worksite": candidate["to_worksite"],
            "continues_in": candidate["to_worksite"]["path"],
            "receipt_id": f"rcpt_matter_rollover_{suffix}",
            "matter_pre_sha256": args.expected_matter_sha256,
            "matter_post_sha256": sha256_bytes(post_matter_data),
            "recovery_path": candidate["to_worksite"]["recovery_path"],
        },
        "evidence": [{"kind": "file", "path": str(context["matter_path"])}],
        "supersedes": [],
        "idempotency_key": args.idempotency_key,
        "extensions": {},
    }
    event_line = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    events_post_data = context["events_data"] + (b"" if not context["events_data"] or context["events_data"].endswith(b"\n") else b"\n") + event_line
    owner = context["matter"].get("owner") if isinstance(context["matter"].get("owner"), dict) else {}
    receipt = {
        "schema": "aios.matter.rollover.receipt.v1",
        "receipt_id": f"rcpt_matter_rollover_{suffix}",
        "transaction_id": f"tx_matter_rollover_{suffix}",
        "event_id": event_id,
        "idempotency_key": args.idempotency_key,
        "authorization_ref": context["authorization"]["path"],
        "authorization": context["authorization"],
        "owner_ref": owner,
        "matter_id": args.matter_id,
        "plan_digest": context["plan_digest"],
        "fence_token": f"sha256:{context['plan_digest']}",
        "state": "prepared",
        "replayed": False,
        "created_at": now,
        "updated_at": now,
        "completed_steps": ["receipt_prepared"],
        "failure": None,
        "candidate": candidate,
        "matter": {
            "path": str(context["matter_path"]),
            "pre_sha256": args.expected_matter_sha256,
            "post_sha256": sha256_bytes(post_matter_data),
            "before": context["matter"],
            "after": post_matter,
        },
        "events": {
            "path": str(context["events_path"]),
            "pre_sha256": args.expected_events_sha256,
            "pre_line_count": args.expected_event_line_count,
            "post_sha256": sha256_bytes(events_post_data),
            "post_line_count": args.expected_event_line_count + 1,
            "event": event,
        },
        "target": {
            "path": candidate["to_worksite"]["path"],
            "mission_id": candidate["to_worksite"]["id"],
            "parent_matter_id": args.matter_id,
            "mission_sha256": candidate["target_mission_sha256"],
            "recovery_sha256": candidate["target_recovery_sha256"],
            "mission_status": candidate["target_mission_status"],
            "recovery_status": candidate["target_recovery_status"],
        },
        "rollback_guards": {
            "matter_sha256": sha256_bytes(post_matter_data),
            "events_sha256": sha256_bytes(events_post_data),
            "event_line_count": args.expected_event_line_count + 1,
            "event_id": event_id,
        },
        "projection": {},
    }
    receipt["receipt_digest"] = rollover_receipt_immutable_digest(receipt)
    return receipt


def commit_rollover_canonical(receipt_path: Path, receipt: dict[str, Any]) -> None:
    matter_path = Path(receipt["matter"]["path"])
    events_path = Path(receipt["events"]["path"])
    matter_hash = sha256_file(matter_path)
    events_hash = sha256_file(events_path)
    allowed_matter = {receipt["matter"]["pre_sha256"], receipt["matter"]["post_sha256"]}
    allowed_events = {receipt["events"]["pre_sha256"], receipt["events"]["post_sha256"]}
    if matter_hash not in allowed_matter or events_hash not in allowed_events:
        receipt["failure"] = {"code": "CANONICAL_COMMIT_INCOMPLETE", "matter_sha256": matter_hash, "events_sha256": events_hash}
        write_rollover_receipt(receipt_path, receipt)
        matter_rollover_failure("CANONICAL_COMMIT_INCOMPLETE", "canonical files do not match recoverable pre/post images")
    if matter_hash == receipt["matter"]["pre_sha256"]:
        maybe_rollover_concurrent_update("matter", matter_path)
        atomic_bytes(
            matter_path,
            json_bytes(receipt["matter"]["after"]),
            expected_current_sha256=receipt["matter"]["pre_sha256"],
        )
        maybe_rollover_test_fault("matter_committed")
    if events_hash == receipt["events"]["pre_sha256"]:
        maybe_rollover_concurrent_update("events", events_path)
        event_line = json.dumps(receipt["events"]["event"], ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        old = events_path.read_bytes()
        new = old + (b"" if not old or old.endswith(b"\n") else b"\n") + event_line
        atomic_bytes(
            events_path,
            new,
            expected_current_sha256=receipt["events"]["pre_sha256"],
        )
        maybe_rollover_test_fault("event_committed")
    if sha256_file(matter_path) != receipt["matter"]["post_sha256"] or sha256_file(events_path) != receipt["events"]["post_sha256"]:
        matter_rollover_failure("CANONICAL_COMMIT_INCOMPLETE", "canonical postimage readback failed")
    receipt["failure"] = None
    if "canonical_committed" not in receipt["completed_steps"]:
        receipt["completed_steps"].append("canonical_committed")
    write_rollover_receipt(receipt_path, receipt, state="canonical_committed")


def publish_rollover_projections(home: Path, receipt_path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    index_path = matter_index_path(home)
    view_root = instance_paths(home)["view"] / "matters"
    index_pre = sha256_file(index_path) if index_path.is_file() else None
    view_pre = sha256_file(view_root / "index.html") if (view_root / "index.html").is_file() else None
    try:
        index = compile_matter_index(home)
        rollback_mode = isinstance(receipt.get("rollback"), dict)
        target_path = str(Path(receipt["target"]["path"]).resolve())
        expected_formal_path = (
            str(Path(receipt["candidate"]["from_worksite"]["path"]).resolve()) if rollback_mode else target_path
        )
        formal = [row for row in index["records"] if row.get("id") == receipt["matter_id"] and row.get("record_type") == "matter"]
        inferred = [row for row in index["records"] if row.get("record_type") == "inferred_worksite" and row.get("worksite_path") == target_path]
        if len(formal) != 1 or formal[0].get("worksite_path") != expected_formal_path or (inferred and not rollback_mode):
            raise RuntimeError("two-pass compiler did not produce one formal claim and zero inferred duplicates")
        atomic_json(index_path, index)
        maybe_rollover_test_fault("index_committed")
        if os.environ.get("AIOS_TEST_MATTER_ROLLOVER_FAIL_PROJECTION"):
            raise RuntimeError("injected projection failure")
        view = render_matter_view(home, index)
        page = view_root / safe_view_component(receipt["matter_id"]) / "index.html"
        duplicate_page = view_root / safe_view_component("worksite:" + receipt["target"]["mission_id"]) / "index.html"
        if (
            sha256_file(index_path) != sha256_bytes(json_bytes(index))
            or not page.is_file()
            or (duplicate_page.exists() and not rollback_mode)
        ):
            raise RuntimeError("stored index or Matter View readback failed")
        receipt["projection"] = {
            "index_path": str(index_path),
            "index_pre_sha256": index_pre,
            "index_post_sha256": sha256_file(index_path),
            "view_path": str(view_root),
            "view_pre_index_sha256": view_pre,
            "view_post_index_sha256": sha256_file(view_root / "index.html"),
            "formal_page": str(page),
            "inferred_duplicate_count": len(inferred),
            "rendered": view["rendered"],
        }
        receipt["failure"] = None
        if "projections_committed" not in receipt["completed_steps"]:
            receipt["completed_steps"].append("projections_committed")
        write_rollover_receipt(receipt_path, receipt, state="projections_committed")
        return view
    except (Exception, SystemExit) as exc:
        receipt["failure"] = {"code": "PROJECTION_REBUILD_PENDING", "message": str(exc)}
        write_rollover_receipt(receipt_path, receipt, state="projection_pending")
        matter_rollover_failure(
            "PROJECTION_REBUILD_PENDING",
            "canonical Matter is committed but derived projections require same-key retry",
            receipt_path=str(receipt_path),
            error=str(exc),
        )


def apply_rollover(args: argparse.Namespace, home: Path, candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    context["authorization"] = validate_rollover_authorization(
        args,
        target=context["target"],
        target_mission=context["mission"],
    )
    with matter_rollover_lock(home, args.matter_id) as lock_path:
        locked_candidate, locked_context = build_rollover_candidate(args, home)
        if locked_context["plan_digest"] != context["plan_digest"]:
            matter_rollover_failure("EXPECTED_CURRENT_MISMATCH", "rollover candidate changed before lock acquisition")
        locked_context["authorization"] = context["authorization"]
        existing = find_rollover_receipt(home, locked_candidate, locked_context["plan_digest"])
        if existing is None:
            assert_expected_rollover_preimage(args, locked_context)
            receipt_path = matter_rollover_receipt_path(home, args.matter_id, args.to_worksite_id)
            receipt = new_rollover_receipt(args, locked_candidate, locked_context)
            write_rollover_receipt(receipt_path, receipt)
            maybe_rollover_test_fault("receipt_prepared")
        else:
            receipt_path, receipt = existing
            receipt["replayed"] = True
            if receipt.get("state") == "rolled_back":
                write_rollover_receipt(receipt_path, receipt)
                return {"ok": True, "state": "rolled_back", "replayed": True, "receipt_path": str(receipt_path)}
            if receipt.get("state") == "projections_committed":
                write_rollover_receipt(receipt_path, receipt)
                return {
                    "schema": "aios.matter.rollover.result.v1",
                    "ok": True,
                    "mode": "apply",
                    "state": "projections_committed",
                    "replayed": True,
                    "matter_id": args.matter_id,
                    "receipt_id": receipt["receipt_id"],
                    "receipt_path": str(receipt_path),
                    "lock_path": str(lock_path),
                    "plan_digest": context["plan_digest"],
                }
        commit_rollover_canonical(receipt_path, receipt)
        publish_rollover_projections(home, receipt_path, receipt)
        return {
            "schema": "aios.matter.rollover.result.v1",
            "ok": True,
            "mode": "apply",
            "state": receipt["state"],
            "replayed": bool(receipt.get("replayed")),
            "matter_id": args.matter_id,
            "receipt_id": receipt["receipt_id"],
            "receipt_path": str(receipt_path),
            "lock_path": str(lock_path),
            "plan_digest": context["plan_digest"],
        }


def resume_rollover_after_canonical(
    args: argparse.Namespace,
    home: Path,
    initial: tuple[Path, dict[str, Any]],
) -> dict[str, Any]:
    initial_path, initial_receipt = initial
    target = Path(initial_receipt["target"]["path"]).expanduser().resolve()
    validate_rollover_authorization(
        args,
        target=target,
        target_mission=mission_fields(target / "mission.md"),
    )
    with matter_rollover_lock(home, args.matter_id) as lock_path:
        existing = find_rollover_receipt_for_request(home, args)
        if existing is None or existing[0].resolve() != initial_path.resolve():
            matter_rollover_failure("IDEMPOTENCY_CONFLICT", "rollover receipt disappeared or changed before lock acquisition")
        receipt_path, receipt = existing
        assert_rollover_receipt_integrity(receipt)
        assert_rollover_receipt_target_current(receipt)
        assert_rollover_receipt_canonical_guards(receipt)
        receipt["replayed"] = True
        if receipt.get("state") == "projections_committed":
            write_rollover_receipt(receipt_path, receipt)
        elif receipt.get("state") in {"canonical_committed", "projection_pending"}:
            publish_rollover_projections(home, receipt_path, receipt)
        else:
            matter_rollover_failure(
                "CANONICAL_GUARD_MISMATCH",
                "receipt is not in a post-canonical projection-retry state",
                state=receipt.get("state"),
            )
        return {
            "schema": "aios.matter.rollover.result.v1",
            "ok": True,
            "mode": "apply",
            "state": receipt["state"],
            "replayed": True,
            "matter_id": args.matter_id,
            "receipt_id": receipt["receipt_id"],
            "receipt_path": str(receipt_path),
            "lock_path": str(lock_path),
            "plan_digest": receipt["plan_digest"],
        }


def prepare_rollback_receipt(receipt: dict[str, Any]) -> None:
    now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    current_matter = read_json_dict(Path(receipt["matter"]["path"]))
    rollback_matter = dict(current_matter)
    rollback_matter["worksite"] = receipt["candidate"]["from_worksite"]
    rollback_matter["updated_at"] = now
    suffix = receipt["receipt_id"].removeprefix("rcpt_matter_rollover_")
    event_id = f"evt_matter_rollover_compensated_{suffix}"
    event = {
        "schema": "aios.workflow.event.v0",
        "event_id": event_id,
        "ts": now,
        "type": "worksite.migration_compensated",
        "actor": {"kind": "cli", "id": "aios matter rollover"},
        "subject": {"kind": "matter", "id": receipt["matter_id"]},
        "summary": "Compensated a Matter Worksite rollover after guarded postimage verification.",
        "payload": {
            "compensates_event_id": receipt["event_id"],
            "from_worksite": receipt["candidate"]["to_worksite"],
            "to_worksite": receipt["candidate"]["from_worksite"],
            "receipt_id": receipt["receipt_id"],
        },
        "evidence": [{"kind": "file", "path": receipt["matter"]["path"]}],
        "supersedes": [],
        "idempotency_key": "rollback:" + receipt["idempotency_key"],
        "extensions": {},
    }
    event_line = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    current_events = Path(receipt["events"]["path"]).read_bytes()
    post_events = current_events + (b"" if not current_events or current_events.endswith(b"\n") else b"\n") + event_line
    receipt["rollback"] = {
        "prepared_at": now,
        "matter_before_sha256": receipt["matter"]["post_sha256"],
        "matter_after": rollback_matter,
        "matter_after_sha256": sha256_bytes(json_bytes(rollback_matter)),
        "events_before_sha256": receipt["events"]["post_sha256"],
        "events_before_line_count": receipt["events"]["post_line_count"],
        "events_after_sha256": sha256_bytes(post_events),
        "events_after_line_count": receipt["events"]["post_line_count"] + 1,
        "event": event,
        "event_id": event_id,
        "previous_state": receipt.get("state"),
    }
    receipt["rollback_digest"] = sha256_bytes(
        json.dumps(receipt["rollback"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def assert_rollback_guards(receipt: dict[str, Any]) -> None:
    matter_path = Path(receipt["matter"]["path"])
    events_path = Path(receipt["events"]["path"])
    events_data, events = read_event_stream(events_path)
    observed = {
        "matter_sha256": sha256_file(matter_path),
        "events_sha256": sha256_bytes(events_data),
        "event_line_count": len(events),
        "event_id": events[-1].get("event_id") if events else None,
    }
    if observed != receipt["rollback_guards"]:
        matter_rollover_failure("ROLLBACK_GUARD_MISMATCH", "Matter postimage or event tail changed after rollover", expected=receipt["rollback_guards"], observed=observed)


def commit_rollback_canonical(receipt_path: Path, receipt: dict[str, Any]) -> None:
    rollback = receipt["rollback"]
    matter_path = Path(receipt["matter"]["path"])
    events_path = Path(receipt["events"]["path"])
    matter_hash = sha256_file(matter_path)
    events_hash = sha256_file(events_path)
    if matter_hash not in {rollback["matter_before_sha256"], rollback["matter_after_sha256"]} or events_hash not in {rollback["events_before_sha256"], rollback["events_after_sha256"]}:
        matter_rollover_failure("ROLLBACK_GUARD_MISMATCH", "rollback recovery images no longer match")
    if matter_hash == rollback["matter_before_sha256"]:
        atomic_bytes(
            matter_path,
            json_bytes(rollback["matter_after"]),
            expected_current_sha256=rollback["matter_before_sha256"],
        )
    if events_hash == rollback["events_before_sha256"]:
        old = events_path.read_bytes()
        line = json.dumps(rollback["event"], ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        atomic_bytes(
            events_path,
            old + (b"" if not old or old.endswith(b"\n") else b"\n") + line,
            expected_current_sha256=rollback["events_before_sha256"],
        )
    if sha256_file(matter_path) != rollback["matter_after_sha256"] or sha256_file(events_path) != rollback["events_after_sha256"]:
        matter_rollover_failure("CANONICAL_COMMIT_INCOMPLETE", "rollback canonical readback failed")
    write_rollover_receipt(receipt_path, receipt, state="rollback_canonical_committed")


def assert_rollback_receipt_binding(home: Path, matter_id: str, receipt: dict[str, Any]) -> None:
    assert_rollover_receipt_integrity(receipt)
    matter_path, _matter = exact_formal_matter(home, matter_id)
    receipt_matter_path = Path(str(receipt.get("matter", {}).get("path") or "")).expanduser().resolve()
    receipt_events_path = Path(str(receipt.get("events", {}).get("path") or "")).expanduser().resolve()
    candidate = receipt.get("candidate") if isinstance(receipt.get("candidate"), dict) else {}
    candidate_digest = sha256_bytes(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if (
        receipt_matter_path != matter_path
        or receipt_events_path != matter_path.with_name("matter.events.jsonl")
        or candidate.get("matter_path") != str(matter_path)
        or candidate_digest != receipt.get("plan_digest")
        or receipt.get("fence_token") != f"sha256:{candidate_digest}"
    ):
        matter_rollover_failure("INVALID_PLAN", "rollback receipt paths or frozen candidate binding are invalid")


def matter_rollover_rollback(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    if not args.expected_receipt_id:
        matter_rollover_failure("INVALID_PLAN", "rollback requires --expected-receipt-id")
    root = (matter_rollover_state_root(home) / "change-sets").resolve()
    receipt_path = Path(args.rollback).expanduser().resolve()
    if receipt_path.parent != root:
        matter_rollover_failure("INVALID_PLAN", "rollback receipt must be an exact default Matter change-set path")
    receipt = read_json_dict(receipt_path)
    if receipt.get("schema") != "aios.matter.rollover.receipt.v1" or receipt.get("matter_id") != args.matter_id or receipt.get("receipt_id") != args.expected_receipt_id:
        matter_rollover_failure("INVALID_PLAN", "rollback receipt identity does not match")
    assert_rollover_receipt_integrity(receipt)
    if args.apply:
        if not args.authorization_ref:
            matter_rollover_failure("OWNER_AUTHORIZATION_MISSING", "rollback --apply requires --authorization-ref")
        target = Path(str(receipt.get("target", {}).get("path") or "")).expanduser().resolve()
        validate_rollover_authorization(
            args,
            target=target,
            target_mission=mission_fields(target / "mission.md"),
        )
    if receipt.get("state") == "rolled_back":
        assert_rollback_receipt_binding(home, args.matter_id, receipt)
        return {"schema": "aios.matter.rollover.result.v1", "ok": True, "mode": "rollback", "state": "rolled_back", "replayed": True, "receipt_path": str(receipt_path)}
    if not args.apply:
        assert_rollback_receipt_binding(home, args.matter_id, receipt)
        if not isinstance(receipt.get("rollback"), dict):
            assert_rollback_guards(receipt)
        return {
            "schema": "aios.matter.rollover.result.v1",
            "ok": True,
            "mode": "rollback-dry-run",
            "would_write": False,
            "safe_to_apply": True,
            "receipt_path": str(receipt_path),
        }
    with matter_rollover_lock(home, args.matter_id):
        receipt = read_json_dict(receipt_path)
        assert_rollback_receipt_binding(home, args.matter_id, receipt)
        if receipt.get("state") == "rolled_back":
            return {"schema": "aios.matter.rollover.result.v1", "ok": True, "mode": "rollback", "state": "rolled_back", "replayed": True, "receipt_path": str(receipt_path)}
        if not isinstance(receipt.get("rollback"), dict):
            assert_rollback_guards(receipt)
            prepare_rollback_receipt(receipt)
            receipt["rollback_authorization_ref"] = args.authorization_ref
            write_rollover_receipt(receipt_path, receipt, state="rollback_prepared")
        commit_rollback_canonical(receipt_path, receipt)
        try:
            publish_rollover_projections(home, receipt_path, receipt)
        except MatterRolloverFailure as exc:
            if exc.code == "PROJECTION_REBUILD_PENDING":
                receipt = read_json_dict(receipt_path)
                write_rollover_receipt(receipt_path, receipt, state="rollback_projection_pending")
            raise
        maybe_rollover_test_fault("rollback_projections_committed")
        receipt = read_json_dict(receipt_path)
        write_rollover_receipt(receipt_path, receipt, state="rolled_back")
        return {"schema": "aios.matter.rollover.result.v1", "ok": True, "mode": "rollback", "state": "rolled_back", "replayed": False, "receipt_path": str(receipt_path)}


def matter_rollover(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    try:
        if args.rollback:
            report = matter_rollover_rollback(args, home)
        else:
            required_rollover_args(args)
            request_receipt = find_rollover_receipt_for_request(home, args)
            if (
                args.apply
                and request_receipt is not None
                and request_receipt[1].get("state") in {"canonical_committed", "projection_pending", "projections_committed"}
            ):
                report = resume_rollover_after_canonical(args, home, request_receipt)
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return
            candidate, context = build_rollover_candidate(args, home)
            existing = find_rollover_receipt(home, candidate, context["plan_digest"])
            if args.apply:
                report = apply_rollover(args, home, candidate, context)
            else:
                if existing is None:
                    assert_expected_rollover_preimage(args, context)
                report = {
                    "schema": "aios.matter.rollover.result.v1",
                    "ok": True,
                    "mode": "dry-run",
                    "would_write": False,
                    "replayed": existing is not None,
                    "matter_id": args.matter_id,
                    "candidate": candidate,
                    "plan_digest": context["plan_digest"],
                    "receipt_path": str(matter_rollover_receipt_path(home, args.matter_id, args.to_worksite_id)),
                    "lock_path": str(matter_rollover_lock_path(home, args.matter_id)),
                }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except MatterRolloverFailure as exc:
        report = {"schema": "aios.matter.rollover.result.v1", "ok": False, "code": exc.code, "error": exc.message, **exc.details}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)


def _load_matter_material_functions() -> tuple[Any, Any, Any]:
    """Load the optional Matter materials sibling only for its CLI commands."""
    if __package__:
        from .aios_matter_materials import attach_material, list_materials, verify_materials
    else:
        from aios_matter_materials import attach_material, list_materials, verify_materials
    return attach_material, list_materials, verify_materials


def strict_material_matter_resolver(home: Path, query: str) -> dict[str, Any] | None:
    """Resolve current Worksite files without writing the derived Matter index."""
    try:
        record = resolve_matter_record(refresh_matter_index(home, write=False), query)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if not record or record.get("record_type") != "matter":
        return record
    raw = read_json_dict(Path(str(record.get("matter_path") or "")))
    lifecycle = raw.get("lifecycle")
    resolved = dict(record)
    resolved["_material_raw_lifecycle_state"] = lifecycle.get("state") if isinstance(lifecycle, dict) else None
    return resolved


def strict_material_source_resolver(home: Path, query: str) -> dict[str, Any] | None:
    """Resolve exactly one explicit Source Registry record, never a projection."""
    try:
        claims = source_identity_claims(home).get(query.strip().lower(), set())
        records = read_sources(home)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if not claims:
        return None
    if len(claims) != 1:
        raise ValueError("identity is claimed by: " + ", ".join(sorted(claims)))
    canonical = next(iter(claims))
    matches = [record for record in records if str(record.get("id", "")).lower() == canonical]
    if len(matches) != 1:
        raise ValueError(f"canonical Source id has {len(matches)} explicit records: {canonical}")
    return {key: value for key, value in matches[0].items() if key != "_lineno"}


def emit_matter_material_report(report: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    elif report.get("schema") == "aios.matter.material-list.v0" and report.get("ok"):
        rows = report.get("materials", [])
        if not rows:
            print("no Matter materials")
        for row in rows:
            print(
                f"- {row['material_id']} [{row['role']}/{row['custody']}/{row['sensitivity']}] "
                f"source={row['source_state']} snapshot={row['snapshot_state']} "
                f"{row['source']['source_id']}:{row['source']['relative_path']}"
            )
    elif report.get("schema") == "aios.matter.material-verify.v0" and report.get("results"):
        for row in report["results"]:
            print(
                f"- {row['material_id']} [{row['verdict']}] "
                f"source={row['source_state']} snapshot={row['snapshot_state']}"
            )
            print(row["message"])
    elif report.get("ok"):
        print(f"Matter material {report.get('status')}: {report.get('material_id', '')}".rstrip())
    else:
        print(f"Matter material {report.get('status', 'failed')}: {report.get('error', 'verification failed')}", file=sys.stderr)
    if not report.get("ok"):
        raise SystemExit(1)


def matter_material_attach(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    attach_material, _, _ = _load_matter_material_functions()
    report = attach_material(
        home,
        args.matter_id,
        source_query=args.source,
        owner_ref=args.owner_ref,
        locator=args.locator,
        role=args.role,
        custody=args.custody,
        sensitivity=args.sensitivity,
        dry_run=args.dry_run,
        resolve_matter=lambda query: strict_material_matter_resolver(home, query),
        resolve_source=lambda query: strict_material_source_resolver(home, query),
    )
    emit_matter_material_report(report, json_output=args.json)


def matter_material_list(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    _, list_materials, _ = _load_matter_material_functions()
    report = list_materials(
        home,
        args.matter_id,
        resolve_matter=lambda query: strict_material_matter_resolver(home, query),
        resolve_source=lambda query: strict_material_source_resolver(home, query),
    )
    emit_matter_material_report(report, json_output=args.json)


def matter_material_verify(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    _, _, verify_materials = _load_matter_material_functions()
    report = verify_materials(
        home,
        args.matter_id,
        material_id=args.material_id,
        verify_all=args.verify_all,
        resolve_matter=lambda query: strict_material_matter_resolver(home, query),
        resolve_source=lambda query: strict_material_source_resolver(home, query),
    )
    emit_matter_material_report(report, json_output=args.json)


def safe_view_id(record: dict[str, Any]) -> str:
    raw = str(record.get("id") or record.get("worksite_name") or "matter")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-") or "matter"


def exchange_directories(left: Path, right: Path) -> None:
    """Atomically exchange two directories through Linux renameat2."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError("atomic Matter View exchange is unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(left), -100, os.fsencode(right), 2) != 0:  # AT_FDCWD, RENAME_EXCHANGE
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(left), str(right))


def render_matter_view(home: Path, index: dict[str, Any]) -> dict[str, Any]:
    root = instance_paths(home)["view"] / "matters"
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.tmp-", dir=root.parent))
    open_cards: list[str] = []
    closed_cards: list[str] = []
    rendered = 0
    for record in index["records"]:
        workdir = Path(record["worksite_path"])
        if not workdir.exists():
            continue
        view_id = safe_view_id(record)
        item = staging / view_id
        files = item / "files"
        files.mkdir(parents=True)
        links = []
        for rel in record.get("delivery_paths", []):
            src = (workdir / rel).resolve()
            if not src.is_file():
                continue
            name = Path(rel).name
            dst = files / name
            if dst.exists() or dst.is_symlink():
                stem, suffix = dst.stem, dst.suffix
                dst = files / f"{stem}-{hashlib.sha256(rel.encode()).hexdigest()[:6]}{suffix}"
            dst.symlink_to(src)
            links.append(f'<li><a href="files/{urllib.parse.quote(dst.name)}">{html.escape(name)}</a></li>')
        title = html.escape(str(record["title"]))
        state = html.escape(str(record["lifecycle_state"]))
        focus = html.escape(str(record.get("current_focus") or ""))
        item_html = f"""<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{title}</title><style>body{{font:16px/1.6 system-ui;max-width:900px;margin:40px auto;padding:0 20px;color:#202124}}a{{color:#175cd3}}.meta{{color:#667085}}li{{margin:.45rem 0}}</style><h1>{title}</h1><p class=\"meta\">{state} · {html.escape(str(record['attention']))} · {html.escape(record['display_path'])}</p><p>{focus}</p><h2>交付物</h2><ul>{''.join(links)}</ul><p><a href=\"../\">返回事务列表</a></p></html>"""
        (item / "index.html").write_text(item_html, encoding="utf-8")
        card = f'<li><a href="{urllib.parse.quote(view_id)}/">{title}</a> <span>{state} · {len(links)} files</span></li>'
        if record.get("reopenable") or record.get("lifecycle_state") in MATTER_OPEN_STATES:
            open_cards.append(card)
        else:
            closed_cards.append(card)
        rendered += 1
    top = f"""<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>AIOS Matters</title><style>body{{font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:0 20px;color:#202124}}a{{color:#175cd3}}span{{color:#667085}}li{{margin:.6rem 0}}details{{margin-top:2rem}}</style><h1>AIOS 事务与交付物</h1><p>这是从 Worksite 真源生成的只读视图，不包含 internal 过程目录。</p><h2>打开或可继续</h2><ul>{''.join(open_cards)}</ul><details><summary>已关闭或已归档（{len(closed_cards)}）</summary><ul>{''.join(closed_cards)}</ul></details></html>"""
    (staging / "index.html").write_text(top, encoding="utf-8")
    if root.exists() or root.is_symlink():
        if not root.is_dir() or root.is_symlink():
            shutil.rmtree(staging)
            raise SystemExit(f"refusing non-directory Matter View root: {root}")
        try:
            exchange_directories(staging, root)
            fsync_directory(root.parent)
        except Exception:
            shutil.rmtree(staging)
            raise
        # `staging` is now the old complete View. Removal happens only after
        # the new complete tree became visible in one atomic exchange.
        shutil.rmtree(staging)
    else:
        os.replace(staging, root)
        fsync_directory(root.parent)
    return {"schema": "aios.matter.view.v1", "ok": True, "path": str(root), "rendered": rendered}


def matter_view_build(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    index = refresh_matter_index(home, write=True)
    report = render_matter_view(home, index)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"rendered {report['rendered']} Matter views at {report['path']}")


def classify_worksite_closeout(workdir: Path, record: dict[str, Any]) -> dict[str, Any]:
    cache_candidates: list[dict[str, Any]] = []
    archive_candidates: list[dict[str, Any]] = []
    for base, dirs, _files in os.walk(workdir):
        base_path = Path(base)
        for name in list(dirs):
            path = base_path / name
            rel = path.relative_to(workdir).as_posix()
            if name in CACHE_DIR_NAMES:
                size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
                cache_candidates.append({"path": rel, "bytes": size, "action": "quarantine_candidate"})
                dirs.remove(name)
            elif rel in {"internal/agents", "internal/github-search"}:
                size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
                archive_candidates.append({"path": rel, "bytes": size, "action": "review_then_archive"})
    promote_candidates = [path for path in record.get("delivery_paths", []) if path != "mission.md"]
    return {
        "schema": "aios.lll.closeout-plan.v1",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "worksite": record,
        "promote_candidates": promote_candidates,
        "archive_candidates": archive_candidates,
        "quarantine_candidates": cache_candidates,
        "safe_automatic_actions": [],
        "requires_approval": promote_candidates + [x["path"] for x in archive_candidates + cache_candidates],
        "asset_retention_gate": {
            "status": "awaiting_agent_assessment",
            "semantic_score": None,
            "automatic_promotion": False,
            "requires_explicit_user_trigger": True,
        },
        "note": "No file is moved, deleted, or promoted by this plan. Promotion candidates still require Agent value assessment and an explicit user-triggered change set.",
    }


def lll_closeout_plan(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    index = refresh_matter_index(home, write=False)
    record = resolve_matter_record(index, args.workdir)
    if record is None:
        wd = resolve_lll_workdir(home, args.workdir)
        if wd is None or not wd.exists():
            raise SystemExit(f"worksite not found: {args.workdir}")
        record = compile_matter_record(wd, location_kind="work", home=home)
    plan = classify_worksite_closeout(Path(record["worksite_path"]), record)
    if args.write:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = instance_paths(home)["state"] / "matters" / "closeout-plans" / f"{stamp}_{safe_view_id(record)}.json"
        atomic_json(path, plan)
        plan["plan_path"] = str(path)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def promotion_apply(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    report = apply_asset_promotion(
        home,
        Path(args.path),
        apply=args.apply,
        resolve_owner=lambda owner_id: resolve_source(home, owner_id),
        work_root=instance_paths(home)["work"],
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


def promotion_validate(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    report = validate_asset_promotion(
        home,
        Path(args.path),
        resolve_owner=lambda owner_id: resolve_source(home, owner_id),
        work_root=instance_paths(home)["work"],
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


def promotion_undo_check(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    report = validate_asset_promotion(
        home,
        Path(args.path),
        resolve_owner=lambda owner_id: resolve_source(home, owner_id),
        work_root=instance_paths(home)["work"],
    )
    report["schema"] = "aios.asset-promotion-undo-check.v1"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["safe_to_remove_target_directory"] else 1)


def worksite_quarantine_manifest_path(home: Path, token: str) -> Path:
    return instance_paths(home)["state"] / "matters" / "quarantine" / f"{token}.json"


def lll_quarantine(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    index = refresh_matter_index(home, write=True)
    record = resolve_matter_record(index, args.workdir)
    if not record:
        raise SystemExit(f"Matter/worksite not found: {args.workdir}")
    if record["location_kind"] != "work":
        raise SystemExit("only a live worksite can be quarantined")
    if record["lifecycle_state"] in MATTER_OPEN_STATES or record["reopenable"]:
        raise SystemExit("refusing to quarantine an open/reopenable Matter; close it explicitly first")
    src = Path(record["worksite_path"])
    dest_root = instance_paths(home)["data"] / "quarantine" / "worksites"
    dest = dest_root / src.name
    token = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "_" + hashlib.sha256(str(src).encode()).hexdigest()[:10]
    manifest = {"schema": "aios.worksite.quarantine.v1", "token": token, "created_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"), "source": str(src), "destination": str(dest), "matter_id": record["id"], "status": "planned" if not args.apply else "applied"}
    if args.apply:
        if dest.exists():
            raise SystemExit(f"quarantine destination exists: {dest}")
        dest_root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        atomic_json(worksite_quarantine_manifest_path(home, token), manifest)
        refresh_matter_index(home, write=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def lll_restore(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    manifest_path = worksite_quarantine_manifest_path(home, args.token)
    manifest = read_json_dict(manifest_path)
    if not manifest:
        raise SystemExit(f"quarantine token not found: {args.token}")
    src = Path(str(manifest["destination"]))
    dest = Path(str(manifest["source"]))
    report = {**manifest, "restore_status": "planned" if not args.apply else "restored"}
    if args.apply:
        if not src.exists():
            raise SystemExit(f"quarantined worksite missing: {src}")
        if dest.exists():
            raise SystemExit(f"restore destination exists: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        manifest["status"] = "restored"
        manifest["restored_at"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
        atomic_json(manifest_path, manifest)
        refresh_matter_index(home, write=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def discover_lll(home: Path, paths: dict[str, Path] | None = None) -> dict[str, Any]:
    """Find the LLL CLI/helper without making AIOS own LLL state."""
    paths = paths or instance_paths(home)
    env_bin = os.environ.get("AIOS_LLL_BIN")
    if env_bin:
        env_script = Path(env_bin)
        command = [sys.executable, str(env_script)] if env_script.suffix == ".py" else [env_bin]
        return {"kind": "env-bin", "cmd": command, "source_dir": None, "script": env_script, "external_to_aios_root": True}
    env_dir = expand(os.environ.get("AIOS_LLL_DIR"), home=home) if os.environ.get("AIOS_LLL_DIR") else None
    candidates: list[tuple[str, Path]] = []
    if env_dir:
        candidates.extend([("env-dir-bin", env_dir / "lll"), ("env-dir-script", env_dir / "scripts" / "lll.py")])
    module_dir = paths["modules"] / "lins-living-loop"
    candidates.extend([("module-bin", module_dir / "lll"), ("module-script", module_dir / "scripts" / "lll.py")])
    path_bin = shutil.which("lll")
    if path_bin:
        candidates.append(("path", Path(path_bin)))
    tried: list[str] = []
    for kind, c in candidates:
        tried.append(str(c))
        if c.exists():
            if c.suffix == ".py":
                return {"kind": kind, "cmd": [sys.executable, str(c)], "source_dir": c.parents[1], "script": c, "external_to_aios_root": not str(c).startswith(str(paths["root"]))}
            return {"kind": kind, "cmd": [str(c)], "source_dir": c.parent, "script": c, "external_to_aios_root": not str(c).startswith(str(paths["root"]))}
    return {"kind": "missing", "cmd": None, "source_dir": module_dir, "script": None, "external_to_aios_root": False, "tried": tried}


def is_probable_lll_workdir(path: Path) -> tuple[bool, list[str]]:
    markers = [m for m in ["mission.md", "internal/tasks.jsonl", "internal/recovery-state.md", "tasks.jsonl"] if (path / m).exists()]
    return bool(markers), markers


def list_lll_workdirs(home: Path, *, limit: int = 20, include_all: bool = False) -> list[dict[str, Any]]:
    work_root = instance_paths(home)["work"]
    rows: list[dict[str, Any]] = []
    if not work_root.exists():
        return rows
    for child in sorted((x for x in work_root.iterdir() if x.is_dir()), key=lambda x: x.stat().st_mtime, reverse=True):
        is_lll, markers = is_probable_lll_workdir(child)
        if not is_lll and not include_all:
            continue
        rows.append({
            "name": child.name,
            "path": str(child),
            "is_lll": is_lll,
            "markers": markers,
            "mtime": _dt.datetime.fromtimestamp(child.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        })
        if limit and len(rows) >= limit:
            break
    return rows


def resolve_lll_workdir(home: Path, query: str | None) -> Path | None:
    paths = instance_paths(home)
    if not query:
        return None
    raw = expand(query, home=home)
    if raw and (raw.is_absolute() or query.startswith("~/") or "/" in query or "\\" in query):
        return raw.resolve()
    candidate = paths["work"] / query
    if candidate.exists():
        return candidate.resolve()
    matches = [Path(r["path"]) for r in list_lll_workdirs(home, limit=0) if r["name"].startswith(query)]
    if len(matches) == 1:
        return matches[0].resolve()
    if len(matches) > 1:
        raise SystemExit("ambiguous LLL workdir: " + ", ".join(m.name for m in matches[:10]))
    return candidate.resolve()


def lll_helper_report(helper: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": helper.get("kind"),
        "cmd": helper.get("cmd"),
        "source_dir": str(helper.get("source_dir")) if helper.get("source_dir") else None,
        "external_to_aios_root": bool(helper.get("external_to_aios_root")),
        "tried": helper.get("tried"),
    }


def run_lll_capture(home: Path, lll_args: list[str], *, want_json: bool = False) -> dict[str, Any]:
    info = discover_lll(home)
    if not info.get("cmd"):
        return {"ok": False, "exit_code": 127, "command": None, "stdout_text": "", "stderr_text": "LLL CLI/helper not found", "json": None}
    cmd = list(info["cmd"]) + lll_args
    if want_json:
        cmd = cmd + ["--json"]
    cp = subprocess.run(cmd, text=True, capture_output=True)
    parsed = None
    if want_json and cp.stdout.strip():
        try:
            parsed = json.loads(cp.stdout)
        except json.JSONDecodeError:
            parsed = None
    return {"ok": cp.returncode == 0, "exit_code": cp.returncode, "command": cmd, "stdout_text": cp.stdout, "stderr_text": cp.stderr, "json": parsed}


def run_lll_proxy(home: Path, lll_args: list[str], *, json_mode: bool = False) -> int:
    info = discover_lll(home)
    if not info.get("cmd"):
        raise SystemExit("LLL CLI/helper not found; run `aios update modules lins-living-loop` or set AIOS_LLL_BIN")
    cmd = list(info["cmd"]) + lll_args
    if json_mode:
        cp = subprocess.run(cmd + ["--json"], text=True, capture_output=True)
        if cp.returncode == 0:
            print(cp.stdout, end="")
            return 0
        if "unrecognized arguments: --json" not in cp.stderr:
            print(cp.stdout, end="")
            print(cp.stderr, end="", file=sys.stderr)
            return cp.returncode
        cp = subprocess.run(cmd, text=True, capture_output=True)
        print(json.dumps({"schema": "aios.lll.proxy.v1", "json_supported": False, "command": cmd, "exit_code": cp.returncode, "stdout_text": cp.stdout, "stderr_text": cp.stderr}, ensure_ascii=False, indent=2))
        return cp.returncode
    return subprocess.run(cmd).returncode


def lll_list(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    helper = discover_lll(home, paths)
    rows = list_lll_workdirs(home, limit=args.limit, include_all=args.all)
    if args.json:
        print(json.dumps({"schema": "aios.lll.workdirs.v1", "work_root": str(paths["work"]), "helper": lll_helper_report(helper), "workdirs": rows}, ensure_ascii=False, indent=2))
        return
    print(f"LLL helper: {helper.get('cmd') or 'missing'}")
    print(f"Work root: {paths['work']}")
    if not rows:
        print("no LLL workdirs found")
    for r in rows:
        print(f"- {r['name']} [{'lll' if r['is_lll'] else 'dir'}] {r['path']}")


def lll_status(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    if not args.workdir:
        if args.compact:
            raise SystemExit("--compact requires one workdir")
        args.limit = getattr(args, "limit", 10)
        args.json = getattr(args, "json", False)
        args.all = False
        lll_list(args)
        return
    wd = resolve_lll_workdir(home, args.workdir)
    if wd is None:
        raise SystemExit("workdir required")
    cmd = ["status", str(wd)]
    if args.all:
        cmd.append("--all")
    if args.compact:
        cmd.append("--compact")
    raise SystemExit(run_lll_proxy(home, cmd, json_mode=args.json))


def lll_doctor(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    helper = discover_lll(home, paths)
    ok = True
    report: dict[str, Any] = {
        "schema": "aios.lll.doctor.v1",
        "aios_root": str(paths["root"]),
        "work_root": str(paths["work"]),
        "helper": lll_helper_report(helper),
        "checks": [],
    }
    def check(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok = ok and passed
        report["checks"].append({"name": name, "ok": passed, "detail": detail})
        if not args.json:
            print(f"{name}: {'ok' if passed else 'missing'} - {detail}")
    check("aios_root", paths["root"].exists(), str(paths["root"]))
    check("work_root", paths["work"].exists(), str(paths["work"]))
    check("lll_helper", bool(helper.get("cmd")), " ".join(helper.get("cmd") or []))
    if helper.get("cmd"):
        version = run_lll_capture(home, ["--version"], want_json=False)
        report["lll_version"] = (version["stdout_text"] or version["stderr_text"]).strip()
        check("lll_version", version["exit_code"] == 0, report["lll_version"][:160])
        doctor = run_lll_capture(home, ["doctor"], want_json=True)
        report["lll_doctor"] = doctor["json"] if doctor["json"] is not None else {"exit_code": doctor["exit_code"], "stdout_text": doctor["stdout_text"], "stderr_text": doctor["stderr_text"]}
        check("lll_doctor_json", doctor["exit_code"] == 0 and doctor["json"] is not None, "lll doctor --json")
    if args.workdir:
        wd = resolve_lll_workdir(home, args.workdir)
        validation = run_lll_capture(home, ["validate", str(wd), "--mode", "auto"], want_json=True)
        ok = ok and validation["exit_code"] == 0
        report["workdir_validation"] = {"path": str(wd), "exit_code": validation["exit_code"], "validation": validation["json"], "stderr_text": validation["stderr_text"]}
    elif args.all:
        results = []
        for row in list_lll_workdirs(home, limit=0):
            validation = run_lll_capture(home, ["validate", row["path"], "--mode", "auto"], want_json=True)
            results.append({"path": row["path"], "exit_code": validation["exit_code"], "validation": validation["json"], "stderr_text": validation["stderr_text"]})
            ok = ok and validation["exit_code"] == 0
        report["workdir_validations"] = results
    if args.json:
        report["ok"] = ok
        print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


def lll_new(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", args.slug.strip()).strip("-") or "work"
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    wd = paths["work"] / f"{stamp}_{slug}"
    if args.dry_run:
        payload = {"schema": "aios.lll.new.v1", "ok": True, "dry_run": True, "workdir": str(wd), "helper": lll_helper_report(discover_lll(home, paths))}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(wd)
        return
    cmd = ["init", str(wd), "--objective", args.objective]
    if args.force:
        cmd.append("--force")
    if args.json:
        result = run_lll_capture(home, cmd, want_json=True)
        payload = {"schema": "aios.lll.new.v1", "ok": result["exit_code"] == 0, "workdir": str(wd), "helper": lll_helper_report(discover_lll(home, paths)), "lll_init": result["json"], "exit_code": result["exit_code"], "stderr_text": result["stderr_text"]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(result["exit_code"])
    raise SystemExit(run_lll_proxy(home, cmd, json_mode=False))


def lll_open(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    wd = resolve_lll_workdir(home, args.workdir) if args.workdir else None
    if wd is None:
        rows = list_lll_workdirs(home, limit=1)
        if not rows:
            raise SystemExit("no LLL workdir found")
        wd = Path(rows[0]["path"])
    if args.json:
        print(json.dumps({"schema": "aios.lll.open.v1", "ok": True, "workdir": str(wd)}, ensure_ascii=False, indent=2))
    else:
        print(wd)
    if args.editor:
        editor = os.environ.get("EDITOR") or "vi"
        raise SystemExit(subprocess.run([editor, str(wd)]).returncode)
    if args.xdg_open:
        raise SystemExit(subprocess.run(["xdg-open", str(wd)]).returncode)


def _capture_doctor_check(check_id: str, func: Any, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            func(args)
        except SystemExit as exc:
            if exc.code is None:
                code = 0
            elif isinstance(exc.code, int):
                code = int(exc.code)
            else:
                code = 1
                print(str(exc.code), file=sys.stderr)
        except Exception as exc:
            code = 1
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    messages = [
        redact_output(line, [])
        for line in (stdout.getvalue().splitlines() + stderr.getvalue().splitlines())
    ]
    return {"id": check_id, "messages": messages, "ok": code == 0}, code


def _doctor_check_specs(args: argparse.Namespace) -> tuple[tuple[str, Any, argparse.Namespace], ...]:
    return (
        ("instance", instance_doctor, args),
        (
            "skillpack",
            skillpack_doctor,
            argparse.Namespace(home=args.home, target=args.target, state_dir=None),
        ),
        ("assets", assets_doctor, args),
    )


def doctor(args: argparse.Namespace) -> None:
    captured = [
        _capture_doctor_check(check_id, func, check_args)
        for check_id, func, check_args in _doctor_check_specs(args)
    ]
    if getattr(args, "json", False):
        checks = [check for check, _ in captured]
        problems = [
            {
                "check": check["id"],
                "code": "doctor_failed",
                "message": f"{check['id']} doctor reported problems",
            }
            for check in checks
            if not check["ok"]
        ]
        payload = {
            "checks": checks,
            "ok": not problems,
            "problems": problems,
            "schema": "aios.doctor.v1",
            "version": 1,
        }
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        raise SystemExit(max((code for _, code in captured), default=0))
    for index, (check, _) in enumerate(captured):
        if index:
            print(f"== {check['id']} ==")
        for message in check["messages"]:
            print(message)
    raise SystemExit(max((code for _, code in captured), default=0))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aios", description="aios-kit control CLI")
    p.add_argument("--home", help="override HOME for tests")
    sub = p.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="initialize a unified ~/aios instance root")
    init.add_argument("--root", help="AIOS instance root (default: ~/aios or $AIOS_ROOT)")
    init.add_argument("--ops", help="OPS vault path (default: <root>/vault/ops)")
    init.add_argument("--skills-dir", help="agent runtime skills dir (default: ~/.agents/skills; installs skills one-by-one)")
    init.add_argument("--compat-links", action="store_true", help="local migration only: create the optional ~/lll-work symlink when safe; never links the whole skills dir")
    init.add_argument("--dry-run", action="store_true")
    init.set_defaults(func=init_instance)

    st = sub.add_parser("status", help="show AIOS instance summary")
    st.add_argument("--json", action="store_true", help="emit compact aios.status.v1 JSON")
    st.set_defaults(func=status)

    upd = sub.add_parser("update", help="update AIOS modules, skills, and OPS template")
    upd.add_argument("subject", nargs="?", default="all", choices=["all", "modules", "skills", "ops"], help="what to update (default: all)")
    upd.add_argument("modules", nargs="*", help="optional module names for `aios update modules <name>`")
    upd.add_argument("--dry-run", action="store_true")
    upd.add_argument("--target", default="universal", choices=["universal", "hermes", "both"])
    upd.add_argument("--mode", choices=["copy", "symlink"], help="override skill install mode for this update")
    upd.add_argument("--prune", action="store_true", help="prune stale skills managed by this pack")
    upd.add_argument("--force", action="store_true", help="overwrite locally modified managed skill copies")
    upd.add_argument("--no-skills", action="store_true", help="with `update all`, skip managed skills")
    upd.add_argument("--no-ops", action="store_true", help="with `update all`, skip re-running the OPS vault template installer")
    upd.set_defaults(func=update)

    ops = sub.add_parser("ops", help="operate the local OPS vault through guarded native commands")
    ops_sub = ops.add_subparsers(dest="ops_cmd", required=True)
    ops_log = ops_sub.add_parser("log", help="operate the append-only OPS maintenance log")
    ops_log_sub = ops_log.add_subparsers(dest="ops_log_cmd", required=True)
    ops_log_append_parser = ops_log_sub.add_parser(
        "append",
        help="append one validated event with locking, O_APPEND, fsync, and readback",
    )
    ops_log_append_parser.add_argument("--actor", required=True)
    ops_log_append_parser.add_argument("--type", dest="event_type", required=True)
    ops_log_append_parser.add_argument("--scope", required=True)
    ops_log_append_parser.add_argument("--summary", required=True)
    ops_log_append_parser.add_argument("--status", required=True, help="non-empty status value; common values are done/pending/failed/superseded")
    ops_log_append_parser.add_argument("--ts", help="ISO-8601 timestamp with explicit offset; defaults to now")
    ops_log_append_parser.add_argument("--object", action="append", default=[])
    ops_log_append_parser.add_argument("--change", action="append", default=[])
    ops_log_append_parser.add_argument("--verification", action="append", default=[])
    ops_log_append_parser.add_argument("--impact", action="append", default=[])
    ops_log_append_parser.add_argument("--followup", action="append", default=[])
    ops_log_append_parser.add_argument("--artifact", action="append", default=[])
    ops_log_append_parser.add_argument("--tag", action="append", default=[])
    ops_log_append_parser.add_argument("--source", action="append", default=[], metavar="KEY=VALUE")
    ops_log_append_parser.add_argument("--sensitive-handling")
    ops_log_append_parser.add_argument("--json", action="store_true", help="emit a machine-readable append receipt")
    ops_log_append_parser.set_defaults(func=ops_log_append)


    sec = sub.add_parser("secret", help="manage AIOS secret metadata, requests, receipts, replicas, and safe runtime injection")
    sec_sub = sec.add_subparsers(dest="secret_cmd", required=True)
    sec_layout = sec_sub.add_parser("layout", help="initialize/check the AIOS secret vault layout")
    sec_layout_sub = sec_layout.add_subparsers(dest="layout_cmd", required=True)
    sec_layout_init = sec_layout_sub.add_parser("init")
    sec_layout_init.set_defaults(func=secret_layout_init)

    sec_req = sec_sub.add_parser("request", help="manage short-lived secret intake request manifests")
    sec_req_sub = sec_req.add_subparsers(dest="request_cmd", required=True)
    sec_req_show = sec_req_sub.add_parser("show")
    sec_req_show.add_argument("request_id")
    sec_req_show.set_defaults(func=secret_request_show)
    sec_req_init = sec_req_sub.add_parser("init-translation", help="create the default AI API translation profile intake request")
    sec_req_init.add_argument("--request-id")
    sec_req_init.add_argument("--force", action="store_true")
    sec_req_init.set_defaults(func=secret_request_init_translation)
    sec_req_create = sec_req_sub.add_parser("create", help="create a pending intake request from a manifest with no secret values")
    sec_req_create.add_argument("--manifest", required=True, help="YAML/JSON secret_intake manifest")
    sec_req_create.add_argument("--dry-run", action="store_true", help="validate and show target without writing")
    sec_req_create.add_argument("--force", action="store_true")
    sec_req_create.add_argument("--json", action="store_true")
    sec_req_create.set_defaults(func=secret_request_create)

    sec_intake = sec_sub.add_parser("intake", help="complete a request manifest through a real TTY without printing secret values")
    sec_intake.add_argument("request_id")
    sec_intake.add_argument("--dry-run", action="store_true", help="validate request shape without prompting for values")
    sec_intake.add_argument("--force", action="store_true", help="rotate/update an existing local secret item")
    sec_intake.set_defaults(func=secret_intake)

    sec_generate = sec_sub.add_parser("generate", help="generate machine-only secret fields without printing their values")
    sec_generate.add_argument("request_id")
    sec_generate.add_argument("--dry-run", action="store_true", help="validate and list fields without writing")
    sec_generate.add_argument("--force", action="store_true", help="replace an existing local secret item")
    sec_generate.add_argument("--json", action="store_true", help="emit a redacted JSON result")
    sec_generate.set_defaults(func=secret_generate)

    sec_list = sec_sub.add_parser("list", help="list secret item metadata")
    sec_list.add_argument("--json", action="store_true")
    sec_list.set_defaults(func=secret_list)

    sec_validate = sec_sub.add_parser("validate", help="validate Secret Registry metadata without reading values")
    sec_validate.add_argument("--json", action="store_true")
    sec_validate.set_defaults(func=secret_validate)

    sec_doctor = sec_sub.add_parser("doctor", help="diagnose Secret Registry + Minimal Secret Runtime health")
    sec_doctor.add_argument("--json", action="store_true")
    sec_doctor.set_defaults(func=secret_doctor)

    sec_show = sec_sub.add_parser("show", help="show redacted secret metadata only")
    sec_show.add_argument("secret_id")
    sec_show.add_argument("--metadata", action="store_true", help="required: show metadata and never secret values")
    sec_show.set_defaults(func=secret_show)

    sec_verify = sec_sub.add_parser("verify", help="verify secret metadata or backend without exposing values")
    sec_verify.add_argument("secret_id")
    sec_verify.add_argument("--offline", action="store_true", help="metadata/backend presence check only; do not call external APIs")
    sec_verify.add_argument("--timeout", type=int, default=60)
    sec_verify.add_argument("--allow-missing-app-owned", action="store_true", help="for indexed native secrets, treat missing paths as non-fatal")
    sec_verify.set_defaults(func=secret_verify)

    sec_sync = sec_sub.add_parser("sync", help="sync local canonical secret values to external replicas")
    sec_sync_sub = sec_sync.add_subparsers(dest="sync_cmd", required=True)
    sec_sync_gh = sec_sync_sub.add_parser("github", help="sync to GitHub Actions secrets through gh CLI")
    sec_sync_gh.add_argument("secret_id")
    sec_sync_gh.add_argument("--replica", required=True)
    sec_sync_gh.add_argument("--dry-run", action="store_true")
    sec_sync_gh.add_argument("--yes", action="store_true", help="required for external write after reviewing --dry-run")
    sec_sync_gh.set_defaults(func=secret_sync_github)

    sec_run = sec_sub.add_parser("run", help="inject a consumer's secret fields into a child process environment")
    sec_run.add_argument("--consumer", required=True)
    sec_run.add_argument("command", nargs=argparse.REMAINDER)
    sec_run.set_defaults(func=secret_run)

    sec_rotate = sec_sub.add_parser("rotate", help="atomically update consumer-allow-listed secret fields from stdin")
    sec_rotate.add_argument("secret_id")
    sec_rotate.add_argument("--consumer", required=True)
    sec_rotate_input = sec_rotate.add_mutually_exclusive_group(required=True)
    sec_rotate_input.add_argument("--field", help="update one allow-listed secret field from stdin")
    sec_rotate_input.add_argument("--json-stdin", action="store_true", help="update several allow-listed fields from a JSON object on stdin")
    sec_rotate.set_defaults(func=secret_rotate)

    sec_index = sec_sub.add_parser("index", help="index app/OS-owned secret locations without reading secret values")
    sec_index_sub = sec_index.add_subparsers(dest="index_cmd", required=True)
    sec_native = sec_index_sub.add_parser("native", help="index native SSH/Caddy secret locations")
    sec_native.add_argument("--ssh", action="store_true")
    sec_native.add_argument("--caddy", action="store_true")
    sec_native.set_defaults(func=secret_index_native)

    resource = sub.add_parser("resource", help="resolve existing Project/Source records into provider-neutral ResourceRefs")
    resource_sub = resource.add_subparsers(dest="resource_cmd", required=True)
    resource_resolve_parser = resource_sub.add_parser("resolve", help="resolve one exact project/source ID, alias, or name")
    resource_resolve_parser.add_argument("query")
    resource_resolve_parser.add_argument("--kind", choices=["project", "source"])
    resource_resolve_parser.add_argument("--profile")
    resource_resolve_parser.add_argument("--json", action="store_true", help="accepted for consistency; output is always JSON")
    resource_resolve_parser.set_defaults(func=resource_resolve)

    decision = sub.add_parser("decision", help="route and shape-check a provider-neutral Decision packet")
    decision_sub = decision.add_subparsers(dest="decision_cmd", required=True)
    decision_check_parser = decision_sub.add_parser("check", help="check exact policy ref, route guards, and packet shape only")
    decision_check_parser.add_argument("--packet", required=True, help="local Decision packet JSON")
    decision_check_parser.add_argument("--policy-source", help="direct Local Policy Markdown; defaults to $AIOS_ROOT/workflow/local-policy.md")
    decision_check_parser.add_argument("--policy-fragment", default="#policy-decision-surface", help="exact Local Policy fragment anchor")
    decision_check_parser.add_argument("--policy-id", default=DECISION_POLICY_ID)
    decision_check_parser.add_argument("--route-id", default=DECISION_ROUTE_ID)
    decision_check_parser.add_argument("--route-depth", type=int, default=1)
    decision_check_parser.add_argument("--visited", action="append", default=[])
    decision_check_parser.add_argument("--json", action="store_true", help="accepted for consistency; output is always JSON")
    decision_check_parser.set_defaults(func=decision_check)

    proj = sub.add_parser("project", help="manage the minimal AIOS project registry")
    psub = proj.add_subparsers(dest="project_cmd", required=True)
    pl = psub.add_parser("list")
    pl.add_argument("--status", choices=["idea", "active", "paused", "archived"])
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=project_list)
    pg = psub.add_parser("get")
    pg.add_argument("query")
    pg.add_argument("--json", action="store_true", help="accepted for namespace consistency; output is JSON by default")
    pg.set_defaults(func=project_get)
    pa = psub.add_parser("add")
    pa.add_argument("--id", required=True)
    pa.add_argument("--name", required=True)
    pa.add_argument("--path")
    pa.add_argument("--github")
    pa.add_argument("--status", default="active", choices=["idea", "active", "paused", "archived"])
    pa.add_argument("--alias", action="append")
    pa.add_argument("--role")
    pa.add_argument("--notes")
    pa.set_defaults(func=project_add)
    pal = psub.add_parser("alias")
    pal.add_argument("alias")
    pal.add_argument("id")
    pal.add_argument("--force", action="store_true")
    pal.set_defaults(func=project_alias)
    pv = psub.add_parser("validate")
    pv.set_defaults(func=project_validate)

    src = sub.add_parser("source", help="manage and query the federated AIOS Source view")
    ssub = src.add_subparsers(dest="source_cmd", required=True)
    sl = ssub.add_parser("list")
    sl.add_argument("--kind", choices=sorted(SOURCE_KINDS | {"project"}))
    sl.add_argument("--status", choices=sorted(SOURCE_VIEW_STATUSES))
    sl.add_argument("--explicit-only", action="store_true", help="exclude project-registry projections")
    sl.add_argument("--json", action="store_true")
    sl.set_defaults(func=source_list)
    sg = ssub.add_parser("get")
    sg.add_argument("query")
    sg.add_argument("--json", action="store_true", help="accepted for namespace consistency; output is JSON by default")
    sg.set_defaults(func=source_get)
    sa = ssub.add_parser("add")
    sa.add_argument("--id", required=True)
    sa.add_argument("--name", required=True)
    sa.add_argument("--kind", required=True, choices=sorted(SOURCE_KINDS))
    sa.add_argument("--path")
    sa.add_argument("--url")
    sa.add_argument("--location-kind", choices=["local", "github", "remote", "view"], help="defaults to local for --path and remote for --url")
    sa.add_argument("--status", default="active", choices=sorted(SOURCE_STATUSES))
    sa.add_argument("--alias", action="append")
    sa.add_argument("--authority", default="source_registry")
    sa.add_argument("--owner-ref")
    sa.add_argument("--access-mode", default="read_only_reference", choices=sorted(SOURCE_ACCESS_MODES))
    sa.add_argument("--sync-mode", default="none", choices=sorted(SOURCE_SYNC_MODES))
    sa.add_argument("--backup-status", default="unknown", choices=sorted(SOURCE_BACKUP_STATES))
    sa.add_argument("--sensitivity", default="private", choices=sorted(SOURCE_SENSITIVITY))
    sa.add_argument("--include", action="append")
    sa.add_argument("--exclude", action="append")
    sa.add_argument("--notes")
    sa.set_defaults(func=source_add)
    sal = ssub.add_parser("alias")
    sal.add_argument("alias")
    sal.add_argument("id")
    sal.add_argument("--force", action="store_true")
    sal.set_defaults(func=source_alias)
    sv = ssub.add_parser("validate")
    sv.set_defaults(func=source_validate)

    matter = sub.add_parser("matter", help="build/query the derived Matter index and delivery view")
    matter_sub = matter.add_subparsers(dest="matter_cmd", required=True)
    mi = matter_sub.add_parser("index", help="rebuild the derived Matter index from Worksite files")
    mi.add_argument("--dry-run", action="store_true", help="compile without writing ~/aios/state/matters/index.json")
    mi.add_argument("--json", action="store_true")
    mi.set_defaults(func=matter_index)
    ml = matter_sub.add_parser("list", help="list/search Matters and inferred Worksites")
    ml.add_argument("--state", choices=["active", "paused", "closed", "archived"])
    ml.add_argument("--reopenable", action="store_true")
    ml.add_argument("--query")
    ml.add_argument("--limit", type=int, default=20)
    ml.add_argument("--json", action="store_true")
    ml.set_defaults(func=matter_list)
    mg = matter_sub.add_parser("get", help="resolve one Matter by id, alias, title, or Worksite name")
    mg.add_argument("query")
    mg.add_argument("--json", action="store_true", help="accepted for namespace consistency; output is JSON by default")
    mg.set_defaults(func=matter_get)
    mr = matter_sub.add_parser("rollover", help="CAS-protected exact Matter current-Worksite transaction")
    mr.add_argument("matter_id", help="exact formal Matter ID; aliases, titles, and fuzzy matches are rejected")
    mr.add_argument("--expected-current-id")
    mr.add_argument("--expected-current-path")
    mr.add_argument("--expected-current-role")
    mr.add_argument("--expected-matter-sha256")
    mr.add_argument("--expected-events-sha256")
    mr.add_argument("--expected-event-line-count", type=int)
    mr.add_argument("--to-worksite")
    mr.add_argument("--to-worksite-id")
    mr.add_argument("--to-role", choices=["current_canonical"])
    mr.add_argument("--idempotency-key")
    mr.add_argument("--fence-token", help="sha256:<digest> emitted by the frozen pass-1 candidate")
    mr.add_argument("--rollback", help="exact default change-set receipt path for guarded rollback")
    mr.add_argument("--expected-receipt-id")
    mr_mode = mr.add_mutually_exclusive_group()
    mr_mode.add_argument("--apply", action="store_true", help="write canonical files and projections; requires authorization")
    mr_mode.add_argument("--dry-run", action="store_true", help="explicit zero-write mode; also the default")
    mr.add_argument("--authorization-ref", help="durable owner authorization reference required with --apply")
    mr.add_argument("--json", action="store_true", help="accepted for consistency; output is always JSON")
    mr.set_defaults(func=matter_rollover)
    mm = matter_sub.add_parser("material", help="attach, list, or verify bounded source-owned Matter materials")
    mm_sub = mm.add_subparsers(dest="matter_material_cmd", required=True)
    mma = mm_sub.add_parser("attach", help="attach one registered local UTF-8 text file without lifecycle side effects")
    mma.add_argument("matter_id", help="formal active or paused Matter id/query")
    mma.add_argument("--source", required=True, help="explicit registered Source id or unambiguous alias")
    mma.add_argument("--owner-ref", required=True, help="stable owner identity within the Source")
    mma.add_argument("--locator", required=True, help="Source-root-relative POSIX path")
    mma.add_argument("--role", required=True, choices=["reference", "evidence", "decision_input", "deliverable"])
    mma.add_argument("--custody", required=True, choices=["reference_only", "immutable_snapshot"])
    mma.add_argument("--sensitivity", required=True, choices=["internal", "internal_restricted"])
    mma.add_argument("--dry-run", action="store_true", help="perform all resolution, safety, and hash preflight without writing")
    mma.add_argument("--json", action="store_true")
    mma.set_defaults(func=matter_material_attach)
    mml = mm_sub.add_parser("list", help="read only the per-Matter materials manifest")
    mml.add_argument("matter_id", help="formal Matter id/query")
    mml.add_argument("--json", action="store_true")
    mml.set_defaults(func=matter_material_list)
    mmv = mm_sub.add_parser("verify", help="fresh-read source/snapshot bytes without updating state")
    mmv.add_argument("matter_id", help="formal Matter id/query")
    mmv.add_argument("material_id", nargs="?", help="one material id; omit to verify every record")
    mmv.add_argument("--all", action="store_true", dest="verify_all", help="explicitly verify every record")
    mmv.add_argument("--json", action="store_true")
    mmv.set_defaults(func=matter_material_verify)
    mv = matter_sub.add_parser("view", help="build the curated static Matter/deliverable view")
    mv_sub = mv.add_subparsers(dest="matter_view_cmd", required=True)
    mvb = mv_sub.add_parser("build")
    mvb.add_argument("--json", action="store_true")
    mvb.set_defaults(func=matter_view_build)

    promotion = sub.add_parser("promotion", help="apply or validate explicitly authorized asset promotions")
    promotion_sub = promotion.add_subparsers(dest="promotion_cmd", required=True)
    promotion_apply_parser = promotion_sub.add_parser("apply", help="plan or apply a copy-if-absent promotion change set")
    promotion_apply_parser.add_argument("path", help="explicitly authorized pending promotion change set")
    promotion_apply_parser.add_argument("--apply", action="store_true", help="perform the copy; default is a read-only plan")
    promotion_apply_parser.add_argument("--json", action="store_true", help="accepted for consistency; output is always JSON")
    promotion_apply_parser.set_defaults(func=promotion_apply)
    promotion_validate_parser = promotion_sub.add_parser("validate", help="read-only hash, exact-set, owner, and provenance validation")
    promotion_validate_parser.add_argument("path", help="applied promotion change set or target-local receipt JSON")
    promotion_validate_parser.add_argument("--json", action="store_true", help="accepted for consistency; output is always JSON")
    promotion_validate_parser.set_defaults(func=promotion_validate)
    promotion_undo_parser = promotion_sub.add_parser("undo-check", help="read-only precondition check; never deletes the target")
    promotion_undo_parser.add_argument("path", help="applied promotion change set or target-local receipt JSON")
    promotion_undo_parser.add_argument("--json", action="store_true", help="accepted for consistency; output is always JSON")
    promotion_undo_parser.set_defaults(func=promotion_undo_check)


    lll = sub.add_parser("lll", help="discover/proxy Lin's Living Loop workdirs")
    lll_sub = lll.add_subparsers(dest="lll_cmd", required=True)
    ll = lll_sub.add_parser("list", help="list LLL workdirs under the AIOS work root")
    ll.add_argument("--json", action="store_true")
    ll.add_argument("--limit", type=int, default=20)
    ll.add_argument("--all", action="store_true", help="include non-LLL directories under the work root")
    ll.set_defaults(func=lll_list)
    ls = lll_sub.add_parser("status", help="proxy to `lll status` for one workdir, or show summary")
    ls.add_argument("workdir", nargs="?")
    ls.add_argument("--all", action="store_true")
    ls.add_argument("--compact", action="store_true", help="proxy LLL compact status for one workdir")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--limit", type=int, default=10)
    ls.set_defaults(func=lll_status)
    ld = lll_sub.add_parser("doctor", help="check LLL helper/work root or validate workdirs")
    ld.add_argument("workdir", nargs="?")
    ld.add_argument("--json", action="store_true")
    ld.add_argument("--all", action="store_true", help="validate every detected LLL workdir")
    ld.set_defaults(func=lll_doctor)
    ln = lll_sub.add_parser("new", help="create a new LLL workdir under the AIOS work root")
    ln.add_argument("slug")
    ln.add_argument("--objective", default="")
    ln.add_argument("--force", action="store_true")
    ln.add_argument("--dry-run", action="store_true")
    ln.add_argument("--json", action="store_true")
    ln.set_defaults(func=lll_new)
    lo = lll_sub.add_parser("open", help="resolve/print a LLL workdir path")
    lo.add_argument("workdir", nargs="?")
    lo.add_argument("--editor", action="store_true")
    lo.add_argument("--xdg-open", action="store_true")
    lo.add_argument("--json", action="store_true")
    lo.set_defaults(func=lll_open)
    lcp = lll_sub.add_parser("closeout-plan", help="classify promotion/archive/quarantine candidates without changing files")
    lcp.add_argument("workdir", help="Matter query or Worksite name/path")
    lcp.add_argument("--write", action="store_true", help="persist the generated closeout plan under AIOS state; this is not an authorized change set")
    lcp.set_defaults(func=lll_closeout_plan)
    lq = lll_sub.add_parser("quarantine", help="move a closed, non-reopenable Worksite into reversible quarantine")
    lq.add_argument("workdir")
    lq.add_argument("--apply", action="store_true", help="apply; default only prints the manifest")
    lq.set_defaults(func=lll_quarantine)
    lr = lll_sub.add_parser("restore", help="restore one Worksite from a quarantine manifest token")
    lr.add_argument("token")
    lr.add_argument("--apply", action="store_true", help="apply; default only prints the restore plan")
    lr.set_defaults(func=lll_restore)

    d = sub.add_parser("doctor", help="validate instance, skillpack, and assets")
    d.add_argument("--target", default="universal", choices=["universal", "hermes", "both"])
    d.add_argument("--json", action="store_true", help="emit compact aios.doctor.v1 JSON")
    d.set_defaults(func=doctor)

    sp = sub.add_parser("skillpack", help="inspect/sync managed runtime skills")
    sps = sp.add_subparsers(dest="skillpack_cmd", required=True)
    ls = sps.add_parser("list")
    ls.set_defaults(func=skillpack_list)
    doc = sps.add_parser("doctor")
    doc.add_argument("--target", default="both", choices=["universal", "hermes", "both"])
    doc.add_argument("--state-dir")
    doc.set_defaults(func=skillpack_doctor)
    sync = sps.add_parser("sync")
    sync_apply = sync.add_mutually_exclusive_group()
    sync_apply.add_argument("--apply", action="store_true")
    sync_apply.add_argument("--dry-run", action="store_true", help="explicit no-op; default")
    sync.add_argument("--prune", action="store_true")
    sync.add_argument("--mode", choices=["copy", "symlink"])
    sync.add_argument("--force", action="store_true", help="overwrite locally modified managed skill copies")
    sync.add_argument("--only", action="append", default=[], metavar="SKILL", help="select exact skill entries; repeatable and CAS-preserving")
    sync.add_argument("--expected-state-sha256", metavar="SHA256", help="expected install-state SHA-256; fail closed on drift")
    sync.add_argument("--target", default="default", choices=["default", "universal", "hermes", "both"])
    sync.add_argument("--state-dir")
    sync.set_defaults(func=skillpack_sync)
    dev = sps.add_parser("dev-link")
    dev_apply = dev.add_mutually_exclusive_group()
    dev_apply.add_argument("--apply", action="store_true")
    dev_apply.add_argument("--dry-run", action="store_true")
    dev.add_argument("--target", default="default", choices=["default", "universal", "hermes", "both"])
    dev.add_argument("--force", action="store_true", help="overwrite locally modified managed skill copies")
    dev.add_argument("--only", action="append", default=[], metavar="SKILL", help="select exact skill entries; repeatable and CAS-preserving")
    dev.add_argument("--expected-state-sha256", metavar="SHA256", help="expected install-state SHA-256; fail closed on drift")
    dev.add_argument("--state-dir")
    dev.set_defaults(func=lambda a: skillpack_sync(argparse.Namespace(**{**vars(a), "mode": "symlink", "prune": False, "first_party_only": True})))
    adopt = sps.add_parser("adopt", help="promote a local runtime skill into aios-kit first-party source and link runtime to it")
    adopt_apply = adopt.add_mutually_exclusive_group()
    adopt_apply.add_argument("--apply", action="store_true")
    adopt_apply.add_argument("--dry-run", action="store_true", help="explicit no-op; default")
    adopt.add_argument("skill", help="skill/frontmatter name to adopt")
    adopt.add_argument("--from", dest="from_path", help="local runtime skill directory; auto-detects ~/.agents/skills and ~/.hermes/skills when omitted")
    adopt.add_argument("--dest", help="repo-relative destination, default: skills/<skill>")
    adopt.add_argument("--runtime-path", help="runtime symlink path, default: ~/.agents/skills/<skill>")
    adopt.add_argument("--source", default="LinLin00000000/aios-kit")
    adopt.add_argument("--reason")
    adopt.add_argument("--move", action="store_true", default=True, help="move source into repo when applying (default)")
    adopt.add_argument("--copy", action="store_false", dest="move", help="copy source into repo instead of moving")
    adopt.add_argument("--replace-runtime", action="store_true", help="replace existing runtime directory/symlink with a symlink to the repo source")
    adopt.add_argument("--force", action="store_true", help="allow replacing an existing repo destination after review")
    adopt.add_argument("--allow-name-mismatch", action="store_true")
    adopt.set_defaults(func=skillpack_adopt)

    ap = sub.add_parser("assets", help="validate/link local asset discovery manifest")
    aps = ap.add_subparsers(dest="assets_cmd", required=True)
    ad = aps.add_parser("doctor")
    ad.set_defaults(func=assets_doctor)
    al = aps.add_parser("link")
    al_apply = al.add_mutually_exclusive_group()
    al_apply.add_argument("--apply", action="store_true")
    al_apply.add_argument("--dry-run", action="store_true")
    al.set_defaults(func=assets_link)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""aios-kit thin CLI.

Stdlib-first orchestrator for local AIOS kit structure, skillpack sync, and asset checks.
It intentionally does not replace `npx skills`; it only groups and records operations.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import getpass
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

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


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _dt.datetime.now(_dt.UTC).isoformat()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
            cmd = ["npx", "--yes", "skills@latest", "add", source, "--skill", name, "-g", "-y", "--agent", target]
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
    new_entries: list[dict[str, Any]] = []
    if getattr(args, "first_party_only", False):
        # dev-link updates local/first-party entries but preserves external entries
        # installed by a previous full sync. Otherwise dev-link would make the
        # state forget externally managed skills and report them as stale.
        new_entries.extend(e for e in old_entries if e.get("kind") != "first_party")
    current_skills: set[tuple[str, str]] = {
        (e.get("target"), e.get("skill"))
        for e in new_entries
        if e.get("target") and e.get("skill")
    }

    for item in enabled_items(manifest):
        if getattr(args, "first_party_only", False) and item["kind"] != "first_party":
            continue
        explicit_targets = item.get("targets") or item.get("target")
        item_targets_raw = explicit_targets or (manifest.get("defaults") or {}).get("agent") or args.target
        # A CLI target override is for generic/default entries. Explicit per-item targets
        # (for example Hermes-local skills under a categorized Hermes skill path) are kept.
        if args.target != "default" and not explicit_targets:
            item_targets_raw = args.target
        targets = [item_targets_raw] if isinstance(item_targets_raw, str) else list(item_targets_raw)
        expanded_targets: dict[str, Path] = {}
        for t in targets:
            expanded_targets.update(target_dirs(t, home) if t == "both" else target_dirs(t, home))
        for target, dst_root in expanded_targets.items():
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
                cmd = ["npx", "--yes", "skills@latest", "add", item["source"], "--skill", skill_name, "-g", "-y", "--agent", target]
                if mode == "copy":
                    cmd.append("--copy")
                rc = run(cmd, apply=apply)
                if rc:
                    raise SystemExit(rc)
                new_entries.append({"kind": "external", "id": item.get("id"), "skill": skill_name, "target": target, "mode": mode, "source": item.get("source"), "installed_path": str(dst), "installed_hash": hash_dir(dst)})
            else:
                install_first_party(item, target, dst_root, mode, apply, home, new_entries, old_entry=old_entry, force=force)

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
            if apply and p.exists():
                if p.is_symlink() or p.is_file():
                    p.unlink()
                else:
                    shutil.rmtree(p)
    elif stale:
        print("Use --prune --apply to remove stale managed skills.")

    if apply:
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
        if field_is_secret(field) and field.get("default") not in (None, ""):
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
            {"name": "api_key", "label": "API Key", "type": "password", "secret": True, "required": True, "confirm": True},
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
            if field.get("confirm"):
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
    value_doc = {"schema_version": 1, "schema": SECRET_VALUE_SCHEMA, "secret_id": secret_id, "stored_at": now_iso(), "values": values}
    write_private_text(val_path, json.dumps(value_doc, ensure_ascii=False, indent=2) + "\n", mode=0o600)
    write_yaml_doc(item_path, item)
    receipt = {
        "schema_version": 1,
        "request_id": req.get("request_id", args.request_id),
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
    receipt_path = dirs["receipts"] / f"{safe_secret_id(str(req.get('request_id', args.request_id)))}.json"
    receipt["receipt_path"] = str(receipt_path)
    write_private_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    done_path = dirs["done"] / req_path.name
    if done_path.exists():
        done_path.unlink()
    req_path.rename(done_path)
    append_secret_audit(home, {"event": "intake_completed", "request_id": req.get("request_id", args.request_id), "secret_id": secret_id, "fields": list(values.keys()), "consumer_ids": consumers, "replica_ids": replicas, "receipt": str(receipt_path)})
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


def redact_output(text: str, secret_values: list[str]) -> str:
    out = text
    for value in sorted((v for v in secret_values if v and len(v) >= 4), key=len, reverse=True):
        out = out.replace(value, "***REDACTED***")
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
    sources = compiled_sources(home)
    counts: dict[str, int] = {}
    for p in projects:
        counts[str(p.get("status", "active"))] = counts.get(str(p.get("status", "active")), 0) + 1
    print(f"AIOS root: {paths['root']}")
    print(f"OPS vault: {paths['ops']}")
    print(f"Work root: {paths['work']}")
    print(f"AIOS skills metadata/cache: {paths['skills']}")
    print(f"Agent runtime skills: {paths['agent_skills']}")
    print(f"Modules: {paths['modules']}")
    print(f"Projects: {len(projects)} {counts}")
    explicit_source_count = len(read_sources(home))
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


def assets_doctor(args: argparse.Namespace) -> None:
    manifest_path = assets_manifest_path()
    print(f"assets manifest: {manifest_path}")
    example_only = bool(manifest_path and manifest_path.name == "local-assets.example.json")
    assets = load_assets().get("assets", [])
    ok = True
    for a in assets:
        path = expand(a.get("canonical_path"))
        print(f"\n[{a.get('id')}] {a.get('kind')}\n  path: {path}")
        if not path or not path.exists():
            print("  status: missing" + (" (example only)" if example_only else ""))
            ok = ok and example_only
            continue
        if path.is_symlink():
            print(f"  symlink -> {path.resolve()}")
        remote = a.get("remote")
        if remote:
            result = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"], text=True, capture_output=True)
            if result.returncode == 0:
                got = result.stdout.strip()
                print(f"  origin: {got}")
                if got != remote:
                    print(f"  expected: {remote}")
            else:
                print("  git: not a repo or no origin")
                ok = False
            st = subprocess.run(["git", "-C", str(path), "status", "--short", "--branch"], text=True, capture_output=True)
            if st.returncode == 0:
                print("  git status:")
                for line in st.stdout.rstrip().splitlines()[:20]:
                    print(f"    {line}")
        link = a.get("discovery_link")
        if link:
            lp = expand(link)
            print(f"  discovery_link: {lp} {'exists' if lp and lp.exists() else 'missing'}")
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


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=str(path.parent))
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


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
    for key in ["status", "kind", "project_id", "asset_policy", "retention", "updated_at", "created_at"]:
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
    mission = mission_fields(workdir / "mission.md")
    lifecycle_raw = matter.get("lifecycle")
    lifecycle: dict[str, Any] = lifecycle_raw if isinstance(lifecycle_raw, dict) else {}
    raw_status = str(matter.get("status") or mission.get("status") or "unknown")
    state, reopenable, attention = normalize_matter_lifecycle(raw_status, lifecycle, location_kind)
    matter_id = str(matter.get("id") or f"worksite:{workdir.name}")
    title = str(matter.get("title") or mission.get("title") or workdir.name)
    updated = str(matter.get("updated_at") or mission.get("updated_at") or _dt.datetime.fromtimestamp(workdir.stat().st_mtime).astimezone().isoformat(timespec="seconds"))
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
        "worksite_name": workdir.name,
        "worksite_path": str(workdir.resolve()),
        "display_path": display_path(workdir, home),
        "location_kind": location_kind,
        "mission_path": str(matter.get("mission_path") or "mission.md"),
        "delivery_paths": infer_delivery_paths(workdir, matter),
        "matter_path": str(matter_path.resolve()) if matter_path.exists() else None,
        "updated_at": updated,
    }


def compile_matter_index(home: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
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
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
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


def safe_view_id(record: dict[str, Any]) -> str:
    raw = str(record.get("id") or record.get("worksite_name") or "matter")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-") or "matter"


def render_matter_view(home: Path, index: dict[str, Any]) -> dict[str, Any]:
    root = instance_paths(home)["view"] / "matters"
    staging = root.with_name(root.name + ".tmp-" + hashlib.sha256(index["generated_at"].encode()).hexdigest()[:8])
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
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
        if root.is_symlink() or root.is_file():
            root.unlink()
        else:
            shutil.rmtree(root)
    os.replace(staging, root)
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
        return {"kind": "env-bin", "cmd": [env_bin], "source_dir": None, "script": Path(env_bin), "external_to_aios_root": True}
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
            if c.name == "lll.py":
                return {"kind": kind, "cmd": ["python3", str(c)], "source_dir": c.parents[1], "script": c, "external_to_aios_root": not str(c).startswith(str(paths["root"]))}
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


def doctor(args: argparse.Namespace) -> None:
    try:
        instance_doctor(args)
    except SystemExit as e:
        code = int(e.code or 0)
    print("== skillpack ==")
    try:
        skillpack_doctor(argparse.Namespace(home=args.home, target=args.target, state_dir=None))
    except SystemExit as e:
        code = max(code, int(e.code or 0))
    print("== assets ==")
    try:
        assets_doctor(args)
    except SystemExit as e:
        code = max(code, int(e.code or 0))
    raise SystemExit(code)


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

    sec_index = sec_sub.add_parser("index", help="index app/OS-owned secret locations without reading secret values")
    sec_index_sub = sec_index.add_subparsers(dest="index_cmd", required=True)
    sec_native = sec_index_sub.add_parser("native", help="index native SSH/Caddy secret locations")
    sec_native.add_argument("--ssh", action="store_true")
    sec_native.add_argument("--caddy", action="store_true")
    sec_native.set_defaults(func=secret_index_native)

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
    mv = matter_sub.add_parser("view", help="build the curated static Matter/deliverable view")
    mv_sub = mv.add_subparsers(dest="matter_view_cmd", required=True)
    mvb = mv_sub.add_parser("build")
    mvb.add_argument("--json", action="store_true")
    mvb.set_defaults(func=matter_view_build)

    promotion = sub.add_parser("promotion", help="validate applied, explicitly authorized asset promotions")
    promotion_sub = promotion.add_subparsers(dest="promotion_cmd", required=True)
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
    sync.add_argument("--target", default="default", choices=["default", "universal", "hermes", "both"])
    sync.add_argument("--state-dir")
    sync.set_defaults(func=skillpack_sync)
    dev = sps.add_parser("dev-link")
    dev_apply = dev.add_mutually_exclusive_group()
    dev_apply.add_argument("--apply", action="store_true")
    dev_apply.add_argument("--dry-run", action="store_true")
    dev.add_argument("--target", default="default", choices=["default", "universal", "hermes", "both"])
    dev.add_argument("--force", action="store_true", help="overwrite locally modified managed skill copies")
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


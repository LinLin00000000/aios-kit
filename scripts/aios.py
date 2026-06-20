#!/usr/bin/env python3
"""aios-kit thin CLI.

Stdlib-first orchestrator for local AIOS kit structure, skillpack sync, and asset checks.
It intentionally does not replace `npx skills`; it only groups and records operations.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

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
        "work": root_path / "work",
        "skills": root_path / "skills",
        "agent_skills": agent_skills_path,
        "modules": root_path / "modules",
        "state": root_path / "state",
        "logs": root_path / "logs",
        "cache": root_path / "cache",
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
    for key in ["root", "config", "vault", "ops", "projects", "work", "skills", "agent_skills", "modules", "state", "logs", "cache"]:
        mkdir(paths[key], apply=apply)
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
  note: legacy symlinks are local migration choices, not public install defaults
"""
    write_if_missing(paths["config"] / "instance.yaml", instance_yaml, apply=apply)
    write_if_missing(paths["projects"] / "registry.jsonl", "", apply=apply)
    write_if_missing(paths["projects"] / "aliases.yaml", "aliases: {}\n", apply=apply)
    if getattr(args, "compat_links", False):
        compat_symlink(paths["ops"], home / "ai-ops", apply=apply)
        compat_symlink(paths["work"], home / "lll-work", apply=apply)
        # Never symlink the whole agent skills directory. Skills are installed
        # one-by-one by skillpack sync so existing user skills are preserved.
    print(f"AIOS root: {paths['root']}")


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


def instance_doctor(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    ok = True
    print("== instance ==")
    for key in ["root", "config", "ops", "projects", "work", "skills", "agent_skills", "modules", "state", "logs", "cache"]:
        exists = paths[key].exists()
        print(f"{key}: {paths[key]} {'exists' if exists else 'missing'}")
        ok = ok and exists
    for label, link, target in [("ai-ops", home / "ai-ops", paths["ops"]), ("lll-work", home / "lll-work", paths["work"] )]:
        good = link.is_symlink() and link.resolve() == target.resolve()
        if link.exists() or link.is_symlink():
            print(f"local compat {label}: {link} -> {link.resolve() if link.is_symlink() else 'not-symlink'} {'ok' if good else 'local-only/check'}")
        else:
            print(f"local compat {label}: not configured")
    ok = validate_projects(home) and ok
    raise SystemExit(0 if ok else 1)


def status(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    paths = instance_paths(home)
    projects = read_projects(home)
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
    tpl = paths["modules"] / "aiops-vault-template"
    script = tpl / "scripts" / "install.py"
    if script.exists():
        return run(["python3", str(script), "--vault", str(paths["ops"]), "--agent", "auto", "--skills-dir", str(paths["agent_skills"])], apply=apply)
    print(f"skip ops template install; missing {script}")
    return 0


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


def discover_lll(home: Path, paths: dict[str, Path] | None = None) -> dict[str, Any]:
    """Find the LLL CLI/helper without making AIOS own LLL state."""
    paths = paths or instance_paths(home)
    env_bin = os.environ.get("AIOS_LLL_BIN")
    if env_bin:
        return {"kind": "env-bin", "cmd": [env_bin], "source_dir": None, "script": None}
    env_dir = expand(os.environ.get("AIOS_LLL_DIR"), home=home) if os.environ.get("AIOS_LLL_DIR") else None
    candidates: list[Path] = []
    if env_dir:
        candidates.extend([env_dir / "lll", env_dir / "scripts" / "lll.py"])
    path_bin = shutil.which("lll")
    if path_bin:
        return {"kind": "path", "cmd": [path_bin], "source_dir": None, "script": Path(path_bin)}
    module_dir = paths["modules"] / "lins-living-loop"
    candidates.extend([module_dir / "lll", module_dir / "scripts" / "lll.py"])
    for c in candidates:
        if c.exists():
            if c.name == "lll.py":
                return {"kind": "module-script", "cmd": ["python3", str(c)], "source_dir": c.parents[1], "script": c}
            return {"kind": "module-bin", "cmd": [str(c)], "source_dir": c.parent, "script": c}
    return {"kind": "missing", "cmd": None, "source_dir": module_dir, "script": None}


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
        print(json.dumps({"schema": "aios.lll.workdirs.v1", "work_root": str(paths["work"]), "helper": {"kind": helper.get("kind"), "cmd": helper.get("cmd"), "source_dir": str(helper.get("source_dir")) if helper.get("source_dir") else None}, "workdirs": rows}, ensure_ascii=False, indent=2))
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
        "helper": {"kind": helper.get("kind"), "cmd": helper.get("cmd"), "source_dir": str(helper.get("source_dir")) if helper.get("source_dir") else None},
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
        cp = subprocess.run(list(helper["cmd"]) + ["--help"], text=True, capture_output=True)
        check("lll_help", cp.returncode == 0, cp.stdout.splitlines()[0] if cp.stdout else cp.stderr[:120])
    if args.workdir:
        wd = resolve_lll_workdir(home, args.workdir)
        rc = run_lll_proxy(home, ["validate", str(wd), "--mode", "auto"], json_mode=args.json)
        ok = ok and rc == 0
        report["workdir_validate_exit_code"] = rc
    elif args.all:
        results = []
        for row in list_lll_workdirs(home, limit=0):
            rc = run_lll_proxy(home, ["validate", row["path"], "--mode", "auto"], json_mode=False)
            results.append({"path": row["path"], "exit_code": rc})
            ok = ok and rc == 0
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
        print(wd)
        return
    cmd = ["init", str(wd), "--objective", args.objective]
    if args.force:
        cmd.append("--force")
    raise SystemExit(run_lll_proxy(home, cmd, json_mode=False))


def lll_open(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    wd = resolve_lll_workdir(home, args.workdir) if args.workdir else None
    if wd is None:
        rows = list_lll_workdirs(home, limit=1)
        if not rows:
            raise SystemExit("no LLL workdir found")
        wd = Path(rows[0]["path"])
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
    init.add_argument("--compat-links", action="store_true", help="local migration only: create ~/ai-ops and ~/lll-work symlinks when safe; never links the whole skills dir")
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

    proj = sub.add_parser("project", help="manage the minimal AIOS project registry")
    psub = proj.add_subparsers(dest="project_cmd", required=True)
    pl = psub.add_parser("list")
    pl.add_argument("--status", choices=["idea", "active", "paused", "archived"])
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=project_list)
    pg = psub.add_parser("get")
    pg.add_argument("query")
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
    ln.set_defaults(func=lll_new)
    lo = lll_sub.add_parser("open", help="resolve/print a LLL workdir path")
    lo.add_argument("workdir", nargs="?")
    lo.add_argument("--editor", action="store_true")
    lo.add_argument("--xdg-open", action="store_true")
    lo.set_defaults(func=lll_open)

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


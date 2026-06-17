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
import shutil
import subprocess
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
        "universal": home / ".agents" / "skills",
        "hermes": hermes_home / "skills",
    }
    if target == "both":
        return all_dirs
    if target not in all_dirs:
        raise SystemExit(f"unknown target: {target}")
    return {target: all_dirs[target]}


def state_path(home: Path, manifest: dict[str, Any], state_dir: str | None = None) -> Path:
    raw = state_dir or (manifest.get("defaults") or {}).get("state_dir") or "~/.agents/skillpacks/state/aios-kit"
    return expand(raw, home=home) / "install-state.json"  # type: ignore[operator]


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


def copytree(src: Path, dst: Path, *, apply: bool) -> None:
    print(f"{'COPY' if apply else 'DRY copy'} {src} -> {dst}")
    if not apply:
        return
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            shutil.rmtree(dst)
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")
    shutil.copytree(src, dst, ignore=ignore)


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


def install_first_party_from_remote(source: str, name: str, dst: Path, *, apply: bool, state_entries: list[dict[str, Any]], item: dict[str, Any], target: str, mode: str) -> None:
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
        copytree(src, dst, apply=True)
    state_entries.append({"kind": "first_party", "id": item.get("id"), "skill": name, "target": target, "mode": f"{mode}-remote-copy", "source": source, "installed_path": str(dst)})


def install_first_party(item: dict[str, Any], target: str, dst_root: Path, mode: str, apply: bool, home: Path, state_entries: list[dict[str, Any]]) -> None:
    # `home` is the target HOME (useful for temp-home tests or friend installs).
    # Source paths in this repo's manifest describe this author's local source layout,
    # so resolve `~/...` against the real process HOME, not the simulated target HOME.
    src = resolve_repo_path(item.get("path"), home=Path.home())
    name = str(item.get("skill") or item.get("id"))
    runtime_path = item.get("runtime_path")
    if runtime_path:
        dst_candidate = expand(str(runtime_path), home=Path.home())
        if dst_candidate is None:
            raise SystemExit(f"invalid runtime_path for {name}: {runtime_path}")
        dst = dst_candidate
    else:
        dst = dst_root / name
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
                    state_entries.append({"kind": "first_party", "id": item.get("id"), "skill": name, "target": target, "mode": mode, "source": source, "installed_path": str(dst)})
                    return
                print(f"WARN npx install did not produce valid runtime skill {dst}: rc={rc}, {runtime_msg}")
                install_first_party_from_remote(str(source), name, dst, apply=apply, state_entries=state_entries, item=item, target=target, mode=mode)
            return
        raise SystemExit(f"first-party source missing for {name}: {src}")
    valid, msg = validate_skill_dir(src)
    if not valid:
        raise SystemExit(f"invalid first-party skill {name}: {src} ({msg})")
    dst_root.mkdir(parents=True, exist_ok=True) if apply else None
    if dst.exists() or dst.is_symlink():
        if dst.resolve() == src.resolve() and mode == "symlink":
            print(f"OK existing worktree/link {dst} -> {src}")
        elif mode == "copy":
            copytree(src, dst, apply=apply)
        else:
            raise SystemExit(f"refusing to replace existing non-matching target {dst}; move it or use copy mode")
    else:
        if mode == "symlink":
            symlink(src, dst, apply=apply)
        else:
            copytree(src, dst, apply=apply)
    state_entries.append({"kind": "first_party", "id": item.get("id"), "skill": name, "target": target, "mode": mode, "source_path": str(src), "installed_path": str(dst)})


def skillpack_sync(args: argparse.Namespace) -> None:
    home = Path(args.home).expanduser() if args.home else Path.home()
    manifest = load_skillpack()
    apply = bool(args.apply)
    mode_default = args.mode or (manifest.get("defaults") or {}).get("mode") or "copy"
    sp = state_path(home, manifest, args.state_dir)
    state = load_state(sp)
    old_entries = state.get("managed", [])
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
            if item["kind"] == "external":
                cmd = ["npx", "--yes", "skills@latest", "add", item["source"], "--skill", skill_name, "-g", "-y", "--agent", target]
                if mode == "copy":
                    cmd.append("--copy")
                rc = run(cmd, apply=apply)
                if rc:
                    raise SystemExit(rc)
                new_entries.append({"kind": "external", "id": item.get("id"), "skill": skill_name, "target": target, "mode": mode, "source": item.get("source"), "installed_path": str(dst_root / skill_name)})
            else:
                install_first_party(item, target, dst_root, mode, apply, home, new_entries)

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


def assets_manifest_path() -> Path | None:
    for path in ASSET_FILES:
        if path.exists():
            return path
    return None


def assets_doctor(args: argparse.Namespace) -> None:
    manifest_path = assets_manifest_path()
    print(f"assets manifest: {manifest_path}")
    assets = load_assets().get("assets", [])
    ok = True
    for a in assets:
        path = expand(a.get("canonical_path"))
        print(f"\n[{a.get('id')}] {a.get('kind')}\n  path: {path}")
        if not path or not path.exists():
            print("  status: missing")
            ok = False
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


def doctor(args: argparse.Namespace) -> None:
    print("== skillpack ==")
    try:
        skillpack_doctor(argparse.Namespace(home=args.home, target="both", state_dir=None))
    except SystemExit as e:
        code = int(e.code or 0)
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

    d = sub.add_parser("doctor")
    d.set_defaults(func=doctor)

    sp = sub.add_parser("skillpack")
    sps = sp.add_subparsers(dest="skillpack_cmd", required=True)
    ls = sps.add_parser("list")
    ls.set_defaults(func=skillpack_list)
    doc = sps.add_parser("doctor")
    doc.add_argument("--target", default="both", choices=["universal", "hermes", "both"])
    doc.add_argument("--state-dir")
    doc.set_defaults(func=skillpack_doctor)
    sync = sps.add_parser("sync")
    sync.add_argument("--apply", action="store_true")
    sync.add_argument("--dry-run", action="store_true", help="explicit no-op; default")
    sync.add_argument("--prune", action="store_true")
    sync.add_argument("--mode", choices=["copy", "symlink"])
    sync.add_argument("--target", default="default", choices=["default", "universal", "hermes", "both"])
    sync.add_argument("--state-dir")
    sync.set_defaults(func=skillpack_sync)
    dev = sps.add_parser("dev-link")
    dev.add_argument("--apply", action="store_true")
    dev.add_argument("--dry-run", action="store_true")
    dev.add_argument("--target", default="default", choices=["default", "universal", "hermes", "both"])
    dev.add_argument("--state-dir")
    dev.set_defaults(func=lambda a: skillpack_sync(argparse.Namespace(**{**vars(a), "mode": "symlink", "prune": False, "first_party_only": True})))

    ap = sub.add_parser("assets")
    aps = ap.add_subparsers(dest="assets_cmd", required=True)
    ad = aps.add_parser("doctor")
    ad.set_defaults(func=assets_doctor)
    al = aps.add_parser("link")
    al.add_argument("--apply", action="store_true")
    al.add_argument("--dry-run", action="store_true")
    al.set_defaults(func=assets_link)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

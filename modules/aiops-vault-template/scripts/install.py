#!/usr/bin/env python3
"""Install the AIOps vault template into a local vault path.

Safe default: create missing files, skip existing files.
"""
from __future__ import annotations
import argparse, os, shutil
from pathlib import Path

def copy_file(src: Path, dst: Path, overwrite: bool, installed: list[str], skipped: list[str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not overwrite:
        skipped.append(str(dst)); return
    shutil.copy2(src, dst); installed.append(str(dst))

def default_skills_dir(agent: str) -> Path | None:
    home = Path.home()
    if agent in {"hermes", "auto"}:
        hermes = home / ".hermes" / "skills"
        if agent == "hermes" or hermes.parent.exists(): return hermes
    if agent in {"claude-code", "claude"}:
        return home / ".claude" / "skills"
    return None

def main() -> int:
    ap = argparse.ArgumentParser(description="Install AIOps vault template")
    ap.add_argument("--vault", default=os.environ.get("AIOPS_ROOT", str(Path.home() / "aios" / "vault" / "ops")))
    ap.add_argument("--agent", default="auto", choices=["auto", "hermes", "claude-code", "none"])
    ap.add_argument("--skills-dir", help="Explicit skills directory. If omitted, installer guesses for known agents.")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing files. Default is skip.")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    vault = Path(args.vault).expanduser().resolve()
    installed, skipped = [], []
    mapping = {"README.md":"README.md","resources.example.md":"resources.md","maintenance-log.schema.md":"maintenance-log.schema.md","maintenance-log.example.jsonl":"maintenance-log.jsonl","secrets-location.example.md":"secrets-location.example.md",".gitignore":".gitignore","scripts/aiops.py":"scripts/aiops.py","templates/service-card.md":"templates/service-card.md","templates/log-entry.json":"templates/log-entry.json","templates/resources-section.md":"templates/resources-section.md","docs/security-boundaries.md":"docs/security-boundaries.md"}
    for src_rel, dst_rel in mapping.items():
        copy_file(repo/src_rel, vault/dst_rel, args.overwrite, installed, skipped)
    private_secret = vault / "secrets-location.md"
    if not private_secret.exists(): copy_file(repo/"secrets-location.example.md", private_secret, False, installed, skipped)
    else: skipped.append(str(private_secret))
    skills_dir = Path(args.skills_dir).expanduser().resolve() if args.skills_dir else default_skills_dir(args.agent)
    if args.agent != "none" and skills_dir:
        copy_file(repo/"SKILL.md", skills_dir/"aiops-vault"/"SKILL.md", args.overwrite, installed, skipped)
        copy_file(repo/"skills"/"aiops-service-operations"/"SKILL.md", skills_dir/"aiops-service-operations"/"SKILL.md", args.overwrite, installed, skipped)
    elif args.agent != "none":
        skipped.append("skills: no known skills directory; pass --skills-dir")
    print(f"vault: {vault}")
    print("installed:")
    for item in installed: print(f"  + {item}")
    print("skipped:")
    for item in skipped: print(f"  - {item}")
    print(f"next: run python3 {vault}/scripts/aiops.py check")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())

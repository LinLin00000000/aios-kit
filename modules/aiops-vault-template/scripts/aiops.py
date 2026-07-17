#!/usr/bin/env python3
"""Low-token CLI for an AIOps vault."""
from __future__ import annotations
import argparse, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|private[_-]?key|authorization|cookie)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{12,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
]
DEFAULT_EXCLUDES = {".git", "__pycache__", ".pytest_cache", "archive", "evidence/private"}

def looks_like_vault(path: Path) -> bool:
    return any((path / name).exists() for name in ["resources.md", "resources.example.md", "maintenance-log.jsonl", "maintenance-log.example.jsonl"])

def vault_root() -> Path:
    env = os.environ.get("AIOPS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    script_root = Path(__file__).resolve().parents[1]
    if looks_like_vault(script_root):
        return script_root
    here = Path.cwd().resolve()
    if looks_like_vault(here):
        return here
    return (Path.home() / "aios" / "vault" / "ops").resolve()

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def section(text: str, heading: str) -> str | None:
    pattern = re.compile(rf"^(?P<h>#+)\s+{re.escape(heading)}\s*$", re.I | re.M)
    m = pattern.search(text)
    if not m:
        return None
    level = len(m.group("h"))
    start = m.start()
    next_pat = re.compile(rf"^#{{1,{level}}}\s+", re.M)
    n = next_pat.search(text, m.end())
    end = n.start() if n else len(text)
    return text[start:end].strip() + "\n"

def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        parts = set(rel.split("/"))
        if parts & DEFAULT_EXCLUDES:
            continue
        if path.is_file():
            yield path

def cmd_index(args: argparse.Namespace) -> int:
    root = vault_root()
    print(f"AIOPS_ROOT={root}")
    for name in ["README.md", "resources.md", "maintenance-log.jsonl", "maintenance-log.schema.md", "secrets-location.md", "secrets-location.example.md"]:
        p = root / name
        status = "present" if p.exists() else "missing"
        print(f"{status:8} {name}")
    service_dir = root / "services"
    if service_dir.exists():
        cards = sorted(service_dir.glob("*/service-card.md"))
        print(f"services {len(cards)} service-card(s)")
        for card in cards[:20]:
            print(f"  - {card.relative_to(root)}")
    return 0

def resources_path(root: Path) -> Path:
    primary = root / "resources.md"
    if primary.exists():
        return primary
    example = root / "resources.example.md"
    return example if example.exists() else primary

def log_path(root: Path) -> Path:
    primary = root / "maintenance-log.jsonl"
    if primary.exists():
        return primary
    example = root / "maintenance-log.example.jsonl"
    return example if example.exists() else primary

def cmd_resources(args: argparse.Namespace) -> int:
    root = vault_root()
    p = resources_path(root)
    if not p.exists():
        print(f"missing: {p}", file=sys.stderr)
        return 2
    text = read_text(p)
    if args.section:
        out = section(text, args.section)
        if out is None:
            print(f"section not found: {args.section}", file=sys.stderr)
            return 1
        print(out)
    else:
        print(text if args.full else "\n".join(text.splitlines()[:120]))
    return 0

def tokenize_query(query: str) -> list[str]:
    """Split human search text into stable lookup terms."""
    return [t.lower() for t in re.split(r"[^\w\u4e00-\u9fff]+", query) if t.strip()]


def compact_lookup_text(text: str) -> str:
    """Normalize text across spaces, hyphens, underscores, punctuation, and case."""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text).lower()


def query_score(query: str, text: str) -> tuple[int, int, int]:
    """Return a sortable relevance score for a human query against text.

    Score shape: (quality, matched_terms, compact_matches)
    - quality 3: exact substring in the original lowercased text
    - quality 2: all query terms match, allowing compact matching
    - quality 1: partial multi-term match, useful for exploratory lookups
    - quality 0: no meaningful match
    """
    q = query.strip().lower()
    hay = text.lower()
    if not q:
        return (0, 0, 0)
    if q in hay:
        return (3, len(tokenize_query(query)) or 1, 0)
    terms = tokenize_query(query)
    if not terms:
        return (0, 0, 0)
    compact_hay = compact_lookup_text(text)
    matched = 0
    compact_matches = 0
    for term in terms:
        if term in hay:
            matched += 1
        elif compact_lookup_text(term) in compact_hay:
            matched += 1
            compact_matches += 1
    if matched == len(terms):
        return (2, matched, compact_matches)
    # Two strong terms are sufficient for exploratory recall. Conversational
    # CJK wrappers often remain whole tokens, while object/name ranking keeps
    # these partial matches below exact hits.
    if len(terms) >= 3 and matched >= 2:
        return (1, matched, compact_matches)
    return (0, matched, compact_matches)


def query_matches_text(query: str, text: str) -> bool:
    return query_score(query, text)[0] > 0


def markdown_row_cells(line: str) -> list[str]:
    if not line.startswith("|"):
        return []
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def ranked_resource_hits(text: str, query: str) -> list[str]:
    scored: list[tuple[tuple[int, int, int], tuple[int, int, int], int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        score = query_score(query, line)
        if score[0] <= 0:
            continue
        cells = markdown_row_cells(line)
        primary_text = " | ".join(cells[:2]) if cells else line
        primary_score = query_score(query, primary_text)
        scored.append((primary_score, score, -i, line))
    scored.sort(reverse=True)
    return [line for _, _, _, line in scored]


def search_resources(query: str, mode: str) -> int:
    root = vault_root()
    p = resources_path(root)
    if not p.exists():
        print(f"missing: {p}", file=sys.stderr)
        return 2
    resource_text = read_text(p)
    hits = ranked_resource_hits(resource_text, query)
    print(f"# {mode}: {query}")
    if hits:
        for line in hits[:40]:
            print(line)
    else:
        print("no direct resource row match")
    if mode == "service":
        service_dir = root / "services"
        for card in service_dir.glob("*/service-card.md") if service_dir.exists() else []:
            card_text = read_text(card)
            if query_matches_text(query, card.as_posix()) or query_matches_text(query, card_text):
                print(f"\n# service card: {card.relative_to(root)}")
                print("\n".join(card_text.splitlines()[:120]))
                break
    return 0 if hits else 1

def cmd_log(args: argparse.Namespace) -> int:
    root = vault_root()
    p = log_path(root)
    if not p.exists():
        print(f"missing: {p}", file=sys.stderr)
        return 2
    lines = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = lines[-args.tail:] if args.tail else lines
    for line in selected:
        obj = json.loads(line)
        if args.query and not query_matches_text(args.query, json.dumps(obj, ensure_ascii=False)):
            continue
        if args.summary:
            print(f"{obj.get('ts','?')} [{obj.get('type','?')}/{obj.get('status','?')}] {obj.get('scope','?')}: {obj.get('summary','')}")
        else:
            print(json.dumps(obj, ensure_ascii=False))
    return 0

def cmd_append_log(args: argparse.Namespace) -> int:
    root = vault_root()
    p = root / "maintenance-log.jsonl"
    now = datetime.now(timezone.utc).astimezone()
    obj = {"schema_version": 1, "ts": now.isoformat(timespec="seconds"), "date": now.date().isoformat(), "actor": args.actor, "type": args.type, "scope": args.scope, "summary": args.summary, "objects": args.object or [], "changes": args.change or [], "verification": args.verification or [], "impact": args.impact or [], "followups": args.followup or [], "artifacts": args.artifact or [], "status": args.status, "tags": args.tag or []}
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"appended: {p}")
    return 0

def cmd_check(args: argparse.Namespace) -> int:
    root = vault_root()
    errors, warnings = [], []
    required = ["README.md", "maintenance-log.schema.md", "scripts/aiops.py"]
    for name in required:
        if not (root / name).exists():
            errors.append(f"missing required file: {name}")
    if not ((root / "resources.md").exists() or (root / "resources.example.md").exists()):
        errors.append("missing required file: resources.md or resources.example.md")
    if not ((root / "maintenance-log.jsonl").exists() or (root / "maintenance-log.example.jsonl").exists()):
        errors.append("missing required file: maintenance-log.jsonl or maintenance-log.example.jsonl")
    log = log_path(root)
    if log.exists():
        for i, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"maintenance-log.jsonl:{i}: invalid JSON: {e}")
                continue
            for key in ["schema_version", "ts", "type", "scope", "summary", "status"]:
                if key not in obj:
                    warnings.append(f"maintenance-log.jsonl:{i}: missing recommended key {key}")
    gitignore = root / ".gitignore"
    if (root / "secrets-location.md").exists() and (not gitignore.exists() or "secrets-location.md" not in gitignore.read_text(encoding="utf-8", errors="ignore")):
        warnings.append("secrets-location.md exists but .gitignore does not mention it")
    for path in iter_files(root):
        if path.suffix.lower() not in {".md", ".json", ".jsonl", ".py", ".txt", ""}:
            continue
        try:
            txt = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(txt):
                warnings.append(f"possible secret-like pattern in {path.relative_to(root)}")
                break
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    if errors:
        return 1
    print("check passed" if not warnings else "check passed with warnings")
    return 0

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query and validate an AIOps vault")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index").set_defaults(func=cmd_index)
    p = sub.add_parser("resources"); p.add_argument("--section"); p.add_argument("--full", action="store_true"); p.set_defaults(func=cmd_resources)
    p = sub.add_parser("service"); p.add_argument("query"); p.set_defaults(func=lambda a: search_resources(a.query, "service"))
    p = sub.add_parser("host"); p.add_argument("query"); p.set_defaults(func=lambda a: search_resources(a.query, "host"))
    p = sub.add_parser("log"); p.add_argument("--tail", type=int, default=20); p.add_argument("--summary", action="store_true"); p.add_argument("--query"); p.set_defaults(func=cmd_log)
    p = sub.add_parser("append-log")
    p.add_argument("--actor", default="agent"); p.add_argument("--type", default="maintenance"); p.add_argument("--scope", required=True); p.add_argument("--summary", required=True); p.add_argument("--status", default="done")
    for flag in ["object", "change", "verification", "impact", "followup", "artifact", "tag"]:
        p.add_argument(f"--{flag}", action="append")
    p.set_defaults(func=cmd_append_log)
    sub.add_parser("check").set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())

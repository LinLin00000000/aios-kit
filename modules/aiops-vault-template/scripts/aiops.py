#!/usr/bin/env python3
"""Low-token CLI for an AIOps vault."""
from __future__ import annotations
import argparse, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|private[_-]?key|authorization|cookie)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{12,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
]
DEFAULT_EXCLUDES = {".git", "__pycache__", ".pytest_cache", "archive", "evidence/private"}
SERVICE_SCHEMA = "aios.ops.service.v1"

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
    records, errors = load_service_records(root)
    print(f"services {len(records)} metadata record(s)")
    for record in records[:20]:
        print(f"  - {record['id']}: {record['name']} — {record['summary']}")
    for error in errors:
        print(f"WARN {error}")
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

def normalize_identifier(value: str) -> str:
    """Normalize only for exact id/name/alias resolution, not semantic matching."""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value).casefold()


def load_service_records(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records, errors = [], []
    service_dir = root / "services"
    paths = sorted(service_dir.glob("*/service.json")) if service_dir.exists() else []
    for metadata_path in paths:
        rel = metadata_path.relative_to(root)
        try:
            record = json.loads(read_text(metadata_path))
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        if not isinstance(record, dict) or record.get("schema") != SERVICE_SCHEMA:
            errors.append(f"{rel}: expected {SERVICE_SCHEMA} object")
            continue
        missing = [key for key in ["id", "name", "summary", "references"] if key not in record]
        if missing:
            errors.append(f"{rel}: missing {', '.join(missing)}")
            continue
        if not all(isinstance(record[key], str) and record[key].strip() for key in ["id", "name", "summary"]):
            errors.append(f"{rel}: id/name/summary must be non-empty strings")
            continue
        if not isinstance(record["references"], list) or not all(isinstance(ref, dict) for ref in record["references"]):
            errors.append(f"{rel}: references must be an array of objects")
            continue
        aliases = record.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(alias, str) and alias.strip() for alias in aliases):
            errors.append(f"{rel}: aliases must be an array of non-empty strings")
            continue
        details = record.get("details")
        if details is not None:
            details_path = Path(details) if isinstance(details, str) else Path()
            if not isinstance(details, str) or not details.strip() or details_path.is_absolute() or ".." in details_path.parts:
                errors.append(f"{rel}: details must be a safe relative path")
                continue
            if not (metadata_path.parent / details_path).is_file():
                errors.append(f"{rel}: missing details file {details}")
                continue
        item = dict(record)
        item["_metadata_path"] = rel.as_posix()
        item["_details_path"] = (rel.parent / details).as_posix() if details else None
        records.append(item)
    seen: dict[str, str] = {}
    for record in records:
        key = normalize_identifier(record["id"])
        if key in seen:
            errors.append(f"duplicate service id after normalization: {record['id']} / {seen[key]}")
        seen[key] = record["id"]
    return records, errors


def cmd_services(args: argparse.Namespace) -> int:
    records, errors = load_service_records(vault_root())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    catalog = [{"id": r["id"], "name": r["name"], "summary": r["summary"]} for r in records]
    if args.json:
        print(json.dumps({"schema": "aios.ops.service-catalog.v1", "services": catalog}, ensure_ascii=False, indent=2))
    elif catalog:
        for item in catalog:
            print(f"{item['id']}\t{item['name']}\t{item['summary']}")
    else:
        print("No service metadata records. Add services/<id>/service.json.")
    return 0


def cmd_service(args: argparse.Namespace) -> int:
    root = vault_root()
    records, errors = load_service_records(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    wanted = normalize_identifier(args.selector)
    matches = [r for r in records if any(normalize_identifier(v) == wanted for v in [r["id"], r["name"], *r.get("aliases", [])])]
    if len(matches) != 1:
        print("service not found by exact id/name/alias; inspect `aiops.py services --json`, choose semantically, then retry with the selected id", file=sys.stderr)
        return 1
    record = matches[0]
    details = read_text(root / record["_details_path"]) if record["_details_path"] else None
    service = {key: value for key, value in record.items() if not key.startswith("_")}
    context = {"schema": "aios.ops.service-context.v1", "metadata_path": record["_metadata_path"], "details_path": record["_details_path"], "service": service, "details": details}
    if args.json:
        print(json.dumps(context, ensure_ascii=False, indent=2))
    else:
        print(f"# {record['name']} ({record['id']})\nSummary: {record['summary']}\nMetadata: {record['_metadata_path']}")
        if details:
            print(f"Details: {record['_details_path']}\n\n{details}", end="" if details.endswith("\n") else "\n")
        else:
            print("Details: follow metadata references (no dedicated service card)")
    return 0


def text_filter_matches(query: str, text: str) -> bool:
    """Deterministic all-term filter for host rows/logs; not semantic routing."""
    q, hay = query.strip().casefold(), text.casefold()
    if not q:
        return False
    if q in hay:
        return True
    compact = normalize_identifier(text)
    terms = [term.casefold() for term in re.split(r"[^\w\u4e00-\u9fff]+", query) if term.strip()]
    return bool(terms) and all(term in hay or normalize_identifier(term) in compact for term in terms)


def search_resources(query: str, mode: str) -> int:
    root = vault_root()
    p = resources_path(root)
    if not p.exists():
        print(f"missing: {p}", file=sys.stderr)
        return 2
    hits = [line for line in read_text(p).splitlines() if text_filter_matches(query, line)]
    print(f"# {mode}: {query}")
    if hits:
        for line in hits[:40]:
            print(line)
    else:
        print("no direct resource row match")
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
        if args.query and not text_filter_matches(args.query, json.dumps(obj, ensure_ascii=False)):
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
    _, service_errors = load_service_records(root)
    errors.extend(service_errors)
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
    p = sub.add_parser("services", help="emit compact id/name/summary catalog for Agent/LLM selection"); p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_services)
    p = sub.add_parser("service", help="load one service by exact id, name, or alias"); p.add_argument("selector"); p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_service)
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

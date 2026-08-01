#!/usr/bin/env python3
from __future__ import annotations
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    ("absolute-home", re.compile(r"/home/[A-Za-z0-9._-]+")),
    ("windows-drive", re.compile(r"(?<![A-Za-z])[A-Za-z]:[/\\][^\s`'\"]+")),
    ("private-key", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("tailscale-ip", re.compile(r"\b100\.(?!64\.0\.0/10)\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
]
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?P<quote>['\"]?)(?P<key>[A-Za-z0-9_-]*(?:api[_-]?key|token|password|secret))(?P=quote)\s*(?P<operator>[:=])\s*(?P<value>.+?)\s*$"
)
SECRET_METADATA_KEYS = {"uses_secret", "source_secret_ref"}
ALLOW = [
    ("relative-doc", re.compile(r"~/")),
]

def candidate_files():
    # Include tracked plus untracked non-ignored files so new files are audited before commit.
    out = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True)
    ignored_exact = {"go.sum"}
    return [ROOT / line for line in out.splitlines() if line and line not in ignored_exact]

def entropy(s: str) -> float:
    if not s:
        return 0.0
    return -sum((s.count(c)/len(s)) * math.log2(s.count(c)/len(s)) for c in set(s))


def token_assignment_value(line: str) -> str | None:
    """Return a literal secret-like assignment, not a variable/reference expression."""
    match = SECRET_ASSIGNMENT.search(line)
    if not match:
        return None
    key = match.group("key").lower().replace("-", "_")
    key_quoted = bool(match.group("quote"))
    if key in SECRET_METADATA_KEYS:
        return None
    operator = match.group("operator")
    raw_value = match.group("value").strip()
    quoted_match = re.fullmatch(r"(?s)(['\"])(.*)\1\s*,?\s*(?:#.*)?", raw_value)
    quoted = quoted_match is not None
    if quoted_match:
        value = quoted_match.group(2).strip()
    else:
        value = raw_value.split("#", 1)[0].strip().rstrip(",")
    if not quoted and not re.fullmatch(r"[A-Za-z0-9_./+=-]+", value):
        return None
    if len(value) < 8:
        return None
    if value.startswith(("$", "${", "{{")):
        return None
    if value.lower() in {"required", "optional", "placeholder", "redacted"}:
        return None
    if (
        not quoted
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
        and key_quoted
    ):
        return None
    return value

def main() -> int:
    findings = []
    for path in candidate_files():
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT)
        for i, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS:
                if rx.search(line):
                    findings.append((str(rel), i, name, line.strip()[:220]))
            if token_assignment_value(line) is not None:
                findings.append((str(rel), i, "token-assignment", line.strip()[:220]))
            for m in re.finditer(r"[A-Za-z0-9_./+=-]{32,}", line):
                candidate = m.group(0)
                if candidate.startswith("CAP_") or candidate.startswith("AmbientCapabilities=CAP_") or candidate.startswith("CapabilityBoundingSet=CAP_"):
                    continue
                if entropy(candidate) >= 4.2 and not candidate.startswith("https://"):
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", candidate):
                        continue
                    # Avoid path false positives without exempting token-like
                    # strings that merely contain '/'. A candidate with slashes is
                    # path-like only when it also has obvious path syntax.
                    if "/" in candidate and (
                        candidate.startswith(('./', '../', '~/'))
                        or re.search(r"(^|/)[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+($|/)", candidate)
                        or re.search(r"(^|/)(home|tmp|projects|modules|templates|vault|skills|scripts|docs|registries|aios|ai-ops|releases|download|latest)(/|$)", candidate)
                    ):
                        continue
                    findings.append((str(rel), i, "high-entropy-string", candidate[:120]))
    if findings:
        print("Potential public-audit findings:")
        for f in findings:
            print(f"{f[0]}:{f[1]} [{f[2]}] {f[3]}")
        return 1
    print("PASS: no obvious secrets or machine-specific absolute paths in tracked or untracked non-ignored files")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

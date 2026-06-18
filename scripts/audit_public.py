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
    ("token-assignment", re.compile(r"(?i)(token|password|secret|api[_-]?key)\s*[:=]\s*['\"]?[^\s,'\"]{8,}")),
    ("tailscale-ip", re.compile(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
]
ALLOW = [
    ("relative-doc", re.compile(r"~/")),
]

def candidate_files():
    # Include tracked plus untracked non-ignored files so new files are audited before commit.
    out = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True)
    return [ROOT / line for line in out.splitlines() if line]

def entropy(s: str) -> float:
    if not s:
        return 0.0
    return -sum((s.count(c)/len(s)) * math.log2(s.count(c)/len(s)) for c in set(s))

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
            for m in re.finditer(r"[A-Za-z0-9_./+=-]{32,}", line):
                candidate = m.group(0)
                if candidate.startswith("CAP_") or candidate.startswith("AmbientCapabilities=CAP_") or candidate.startswith("CapabilityBoundingSet=CAP_"):
                    continue
                if entropy(candidate) >= 4.2 and not candidate.startswith("https://"):
                    # Avoid path false positives without exempting token-like
                    # strings that merely contain '/'. A candidate with slashes is
                    # path-like only when it also has obvious path syntax.
                    if "/" in candidate and (
                        candidate.startswith(('./', '../', '~/'))
                        or re.search(r"(^|/)[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+($|/)", candidate)
                        or re.search(r"(^|/)(home|tmp|projects|modules|templates|vault|skills|scripts|docs|registries|aios|ai-ops)(/|$)", candidate)
                    ):
                        continue
                    findings.append((str(rel), i, "high-entropy-string", candidate[:120]))
    if findings:
        print("Potential public-audit findings:")
        for f in findings:
            print(f"{f[0]}:{f[1]} [{f[2]}] {f[3]}")
        return 1
    print("PASS: no obvious secrets or machine-specific absolute paths in tracked files")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

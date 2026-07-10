#!/usr/bin/env python3
"""Audit a public HTML report, exported PNG cards, manifest, and optional ZIP.

Stdlib-only. This checks deterministic structure and packaging; it does not replace
human visual review of representative cards.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

DEFAULT_FORBIDDEN = (
    "工作区",
    "标题备选",
    "制作备注",
    "mission.md",
    "internal/",
    "/home/",
    "/Users/",
    "C:" + "/Users/",
    "localhost",
    "screenshot-friendly",
)
REMOTE_ASSET_PATTERNS = (r'src=["\']https?://', r'url\(\s*https?://', r'@import\s+url')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--cards", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--zip", dest="zip_path", type=Path)
    parser.add_argument("--marker", default="data-card-name")
    parser.add_argument("--forbid", action="append", default=[], help="Additional literal forbidden text")
    parser.add_argument("--allow-remote-assets", action="store_true")
    parser.add_argument("--expected-count", type=int)
    return parser.parse_args()


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG signature: {path}")
    return struct.unpack(">II", header[16:24])


def main() -> int:
    args = parse_args()
    checks: list[dict[str, object]] = []
    errors: list[str] = []

    for path, kind in ((args.html, "HTML"), (args.cards, "cards directory"), (args.manifest, "manifest")):
        if not path.exists():
            errors.append(f"Missing {kind}: {path}")
    if errors:
        print(json.dumps({"verdict": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    html = args.html.read_text(encoding="utf-8")
    marker_pattern = rf'{re.escape(args.marker)}=["\']([^"\']+)["\']'
    marker_names = re.findall(marker_pattern, html)
    expected_count = args.expected_count if args.expected_count is not None else len(marker_names)
    if len(marker_names) != len(set(marker_names)):
        errors.append("Card marker names are not unique")
    if len(marker_names) != expected_count:
        errors.append(f"HTML card count {len(marker_names)} != expected {expected_count}")
    checks.append({"name": "html_card_markers", "count": len(marker_names), "unique": len(set(marker_names))})

    forbidden = tuple(dict.fromkeys((*DEFAULT_FORBIDDEN, *args.forbid)))
    forbidden_hits = {term: html.count(term) for term in forbidden if term and term in html}
    if forbidden_hits:
        errors.append(f"Forbidden public text found: {forbidden_hits}")
    checks.append({"name": "public_hygiene", "forbidden_hits": forbidden_hits})

    remote_hits = {
        pattern: len(re.findall(pattern, html, flags=re.IGNORECASE))
        for pattern in REMOTE_ASSET_PATTERNS
        if re.search(pattern, html, flags=re.IGNORECASE)
    }
    if remote_hits and not args.allow_remote_assets:
        errors.append(f"Unexpected remote assets: {remote_hits}")
    checks.append({"name": "remote_assets", "hits": remote_hits, "allowed": args.allow_remote_assets})

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_cards = manifest.get("cards", [])
    if len(manifest_cards) != expected_count:
        errors.append(f"Manifest card count {len(manifest_cards)} != expected {expected_count}")
    geometry = manifest.get("geometry", {})
    if geometry.get("horizontalPageOverflow"):
        errors.append("Manifest reports body-level horizontal overflow")
    if geometry.get("overflowing"):
        errors.append(f"Manifest reports overflowing elements: {geometry['overflowing']}")
    if manifest.get("consoleErrors"):
        errors.append(f"Browser console errors: {manifest['consoleErrors']}")
    checks.append({
        "name": "browser_render",
        "browser": manifest.get("browser"),
        "user_agent": manifest.get("userAgent"),
        "horizontal_overflow": geometry.get("horizontalPageOverflow"),
        "overflowing": geometry.get("overflowing", []),
        "console_errors": manifest.get("consoleErrors", []),
    })

    pngs = sorted(args.cards.glob("*.png"))
    other_files = sorted(path.name for path in args.cards.iterdir() if path.is_file() and path.suffix.lower() != ".png")
    if len(pngs) != expected_count:
        errors.append(f"PNG count {len(pngs)} != expected {expected_count}")
    if other_files:
        errors.append(f"Non-PNG files in delivery directory: {other_files}")
    actual_sizes = {path.name: png_size(path) for path in pngs}
    expected_sizes = {
        item["name"]: (item["outputPixels"]["width"], item["outputPixels"]["height"])
        for item in manifest_cards
    }
    if actual_sizes != expected_sizes:
        errors.append("PNG names/dimensions do not match the render manifest")
    checks.append({
        "name": "png_delivery",
        "count": len(pngs),
        "other_files": other_files,
        "min_width": min((size[0] for size in actual_sizes.values()), default=None),
        "max_height": max((size[1] for size in actual_sizes.values()), default=None),
        "matches_manifest": actual_sizes == expected_sizes,
    })

    if args.zip_path:
        if not args.zip_path.exists():
            errors.append(f"Missing ZIP: {args.zip_path}")
        else:
            with zipfile.ZipFile(args.zip_path) as archive:
                bad_crc = archive.testzip()
                zip_names = sorted(Path(name).name for name in archive.namelist() if not name.endswith("/"))
                png_names = [path.name for path in pngs]
                compression_methods = sorted({item.compress_type for item in archive.infolist() if not item.is_dir()})
            if bad_crc:
                errors.append(f"ZIP CRC failed at: {bad_crc}")
            if zip_names != png_names:
                errors.append("ZIP file list does not match the card delivery directory")
            if compression_methods != [zipfile.ZIP_DEFLATED]:
                errors.append(f"Unexpected ZIP compression methods: {compression_methods}")
            checks.append({
                "name": "zip_package",
                "count": len(zip_names),
                "crc": "PASS" if bad_crc is None else f"FAIL:{bad_crc}",
                "matches_cards": zip_names == png_names,
                "compression_methods": compression_methods,
            })

    verdict = "PASS" if not errors else "FAIL"
    print(json.dumps({"verdict": verdict, "errors": errors, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Translate AIOS Kit Chinese Markdown docs to English using an OpenAI-compatible API.

Secrets are read from environment variables or a private env file. The script
never prints API key values.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SECRET_FILE = Path.home() / "aios" / "config" / "secrets" / "aios-kit-translation.env"
DEFAULT_TARGET_LANG = "English"
DEFAULT_TARGET_CODE = "en"
SOURCE_FILES = [Path("README.md")]
SOURCE_GLOBS = ["docs/*.md"]
GENERATED_MARKER = "<!-- AUTO-GENERATED FILE. DO NOT EDIT. -->"

SYSTEM_PROMPT = """You are a careful technical documentation translator.
Translate Simplified Chinese Markdown documentation into natural, concise English.
Preserve Markdown structure, frontmatter keys, code fences, inline code, links, HTML comments, tables, and command examples.
Do not add new sections. Do not remove content. Translate prose only.
Keep product names and file paths unchanged unless they are natural language labels.
""".strip()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        value = value.replace("'\\''", "'")
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def api_config() -> dict[str, str]:
    return {
        "base_url": require_env("TRANSLATE_BASE_URL").rstrip("/"),
        "api_key": require_env("TRANSLATE_API_KEY"),
        "model": require_env("TRANSLATE_MODEL"),
        "api_mode": os.environ.get("TRANSLATE_API_MODE", "chat_completions").strip().lower() or "chat_completions",
    }


def request_json(url: str, api_key: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"API HTTP {exc.code} from {url}: {detail}") from exc


def extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        text = c.get("text") or c.get("content")
                        if isinstance(text, str):
                            parts.append(text)
            elif isinstance(content, str):
                parts.append(content)
        if parts:
            return "\n".join(parts).strip()
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
    raise RuntimeError(f"Could not extract text from API response keys: {sorted(data.keys())}")


def call_model(prompt: str, user_text: str, cfg: dict[str, str]) -> str:
    mode = cfg["api_mode"]
    if mode in {"responses", "codex_responses", "openai_responses"}:
        url = cfg["base_url"] + "/responses"
        payload = {
            "model": cfg["model"],
            "input": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_text},
            ],
        }
    else:
        url = cfg["base_url"] + "/chat/completions"
        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.2,
        }
    return extract_response_text(request_json(url, cfg["api_key"], payload))


def source_files() -> list[Path]:
    files = [ROOT / p for p in SOURCE_FILES if (ROOT / p).exists()]
    for pattern in SOURCE_GLOBS:
        files.extend(sorted(ROOT.glob(pattern)))
    return [p for p in files if p.is_file() and not any(part in {"en", "translations"} for part in p.relative_to(ROOT).parts)]


def target_path(source: Path, target_code: str) -> Path:
    rel = source.relative_to(ROOT)
    if rel == Path("README.md"):
        return ROOT / "translations" / target_code / "README.md"
    return ROOT / "translations" / target_code / rel


def chinese_link_for(target: Path) -> str:
    rel = target.relative_to(ROOT)
    if rel == Path("translations/en/README.md"):
        return "../../README.md"
    if rel.parts[:2] == ("translations", "en"):
        source_rel = Path(*rel.parts[2:])
        return os.path.relpath(ROOT / source_rel, target.parent).replace(os.sep, "/")
    return "../../README.md"


def generated_header(target: Path) -> str:
    zh = chinese_link_for(target)
    return f"{GENERATED_MARKER}\n\n[简体中文]({zh}) | **English**\n\n> This file is automatically generated from the Chinese source. Please edit the Chinese source file instead.\n\n"


def strip_existing_generated_header(text: str) -> str:
    if not text.startswith(GENERATED_MARKER):
        return text
    # Remove marker plus the small generated notice block up to the first blank line after blockquote.
    lines = text.splitlines()
    idx = 1
    while idx < len(lines) and idx < 8:
        idx += 1
        if idx >= 4 and idx < len(lines) and lines[idx - 1] == "" and not lines[idx:idx+1]:
            break
    # Simpler robust path: remove fixed notice if present.
    joined = "\n".join(lines)
    m = re.search(r"^<!-- AUTO-GENERATED FILE\. DO NOT EDIT\. -->\n\n.*?edit the Chinese source file instead\.\n\n", joined, re.S)
    return joined[m.end():] if m else text


def translate_file(source: Path, cfg: dict[str, str], target_code: str, target_lang: str) -> tuple[Path, str]:
    original = source.read_text(encoding="utf-8")
    rel = source.relative_to(ROOT).as_posix()
    user = f"Translate this Markdown file to {target_lang}. File path: {rel}\n\n{original}"
    translated = call_model(SYSTEM_PROMPT, user, cfg)
    target = target_path(source, target_code)
    translated = strip_existing_generated_header(translated).strip() + "\n"
    return target, generated_header(target) + translated


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def check_api(cfg: dict[str, str]) -> None:
    text = call_model(
        "You are a health-check endpoint for a documentation translation workflow. Reply with exactly: ok",
        "Reply with exactly: ok",
        cfg,
    )
    normalized = re.sub(r"[^a-z]", "", text.lower())
    if "ok" not in normalized:
        raise RuntimeError(f"Unexpected API health-check response shape: {text[:80]!r}")
    host_hint = re.sub(r"//([^/@:]+)(:[0-9]+)?", r"//<host>\2", cfg["base_url"])
    print("API check passed")
    print(f"- base_url_host_hint: {host_hint}")
    print(f"- model: {cfg['model']}")
    print(f"- api_mode: {cfg['api_mode']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_FILE)
    parser.add_argument("--target-code", default=DEFAULT_TARGET_CODE)
    parser.add_argument("--target-language", default=DEFAULT_TARGET_LANG)
    parser.add_argument("--check-api", action="store_true")
    parser.add_argument("--write", action="store_true", help="write translated files")
    parser.add_argument("--dry-run", action="store_true", help="show planned files without calling translation for all files")
    parser.add_argument("--limit", type=int, default=0, help="limit number of files translated; useful for smoke tests")
    parser.add_argument("--only", action="append", default=[], help="relative source path to translate; may be repeated")
    args = parser.parse_args()

    load_env_file(args.secret_file)
    cfg = api_config()

    if args.check_api:
        check_api(cfg)

    files = source_files()
    if args.only:
        wanted = {Path(x) for x in args.only}
        files = [ROOT / p for p in wanted if (ROOT / p).exists()]
    if args.limit:
        files = files[: args.limit]

    planned = [(p, target_path(p, args.target_code)) for p in files]
    print(f"Translation source files: {len(planned)}")
    for src, dst in planned:
        print(f"- {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")

    if args.dry_run and not args.write:
        return 0
    if not args.write:
        print("No files written. Pass --write to generate translations.")
        return 0

    changed = 0
    started = time.time()
    for idx, src in enumerate(files, 1):
        print(f"Translating {idx}/{len(files)}: {src.relative_to(ROOT)}")
        dst, content = translate_file(src, cfg, args.target_code, args.target_language)
        if write_if_changed(dst, content):
            changed += 1
            print(f"  wrote {dst.relative_to(ROOT)}")
        else:
            print(f"  unchanged {dst.relative_to(ROOT)}")
    print(f"Translation complete: changed_files={changed}, elapsed_seconds={time.time() - started:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

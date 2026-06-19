#!/usr/bin/env python3
"""Export AIOS Kit translation credentials from Hermes config without printing values.

This script intentionally prints only keys/status/path metadata. It reads the
current Hermes profile config in-process and writes a translation-specific env
file with restricted permissions.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required to parse Hermes config.yaml") from exc


DEFAULT_CONFIG = Path.home() / ".hermes" / "config.yaml"
DEFAULT_ENV = Path.home() / ".hermes" / ".env"
DEFAULT_OUTPUT = Path.home() / "aios" / "config" / "secrets" / "aios-kit-translation.env"


def flatten_keys(obj: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.append(path)
            keys.extend(flatten_keys(value, path))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            keys.extend(flatten_keys(value, f"{prefix}[{idx}]"))
    return keys


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def shell_quote_env(value: str) -> str:
    # Single-quote style safe for POSIX env files sourced by bash.
    return "'" + value.replace("'", "'\\''") + "'"


def normalize_api_mode(value: str | None) -> str:
    if not value:
        return "chat_completions"
    lowered = value.strip().lower()
    if lowered in {"codex_responses", "responses", "openai_responses"}:
        return "responses"
    if lowered in {"chat", "chat_completions", "openai_chat_completions"}:
        return "chat_completions"
    return lowered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--public-base-url",
        help=(
            "optional public OpenAI-compatible base URL to write instead of the "
            "Hermes-local model.base_url; useful when Hermes points at localhost "
            "but Caddy exposes the same upstream through HTTPS"
        ),
    )
    parser.add_argument("--force", action="store_true", help="overwrite existing output")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    env = parse_dotenv(args.env)
    all_config_keys = flatten_keys(config)

    model = config.get("model") or {}
    delegation = config.get("delegation") or {}

    # Prefer the live/default Hermes model config, fallback to delegation, then env.
    provider = str(model.get("provider") or delegation.get("provider") or env.get("TRANSLATE_PROVIDER") or "custom")
    model_name = str(model.get("default") or delegation.get("model") or env.get("TRANSLATE_MODEL") or "")
    base_url = str(model.get("base_url") or delegation.get("base_url") or env.get("TRANSLATE_BASE_URL") or "")
    if args.public_base_url:
        base_url = args.public_base_url.strip().rstrip("/")
    api_mode = normalize_api_mode(str(model.get("api_mode") or delegation.get("api_mode") or env.get("TRANSLATE_API_MODE") or ""))
    credential_value = str(model.get("api_key") or delegation.get("api_key") or env.get("TRANSLATE_API_KEY") or "")

    missing = [name for name, value in {
        "TRANSLATE_API_KEY": credential_value,
        "TRANSLATE_BASE_URL": base_url,
        "TRANSLATE_MODEL": model_name,
    }.items() if not value]
    if missing:
        raise SystemExit(f"Missing required translation secret values: {', '.join(missing)}")

    if args.output.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing file without --force: {args.output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join([
        "# AIOS Kit translation secrets. Do not commit or print values.",
        "# Generated from the current Hermes Agent config by scripts/export_translation_secrets.py.",
        f"TRANSLATE_PROVIDER={shell_quote_env(provider)}",
        f"TRANSLATE_BASE_URL={shell_quote_env(base_url)}",
        f"TRANSLATE_MODEL={shell_quote_env(model_name)}",
        f"TRANSLATE_API_MODE={shell_quote_env(api_mode)}",
        "TRANSLATE_" + "API_KEY=" + shell_quote_env(credential_value),
        "",
    ])
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(args.output, 0o600)

    mode = stat.S_IMODE(args.output.stat().st_mode)
    print("Exported AIOS Kit translation secret env file")
    print(f"- output: {args.output}")
    print(f"- mode: {oct(mode)}")
    print(f"- parsed_config_key_count: {len(all_config_keys)}")
    print("- written_keys: TRANSLATE_PROVIDER, TRANSLATE_BASE_URL, TRANSLATE_MODEL, TRANSLATE_API_MODE, TRANSLATE_API_KEY")
    print(f"- provider: {provider}")
    print(f"- model: {model_name}")
    base_url_hint = re.sub(r"//([^/@:]+)(:[0-9]+)?", r"//<host>\2", base_url)
    print(f"- base_url_host_hint: {base_url_hint}")
    print(f"- api_mode: {api_mode}")
    print(f"- api_key: present len={len(credential_value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

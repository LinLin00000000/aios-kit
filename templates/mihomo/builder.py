#!/usr/bin/env python3
"""Low-complexity Mihomo/Clash config builder.

Safe agent contract:
- Reads process environment and, when present, secrets/.env.
- Writes generated sensitive config only on `build`.
- `preview` and `doctor` redact secret values and are safe for Agent inspection.
- Does not call AIOS Secret directly; `aios secret run -- ...` can inject env externally.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = Path("secrets/.env")
OUTPUT_FILE = Path("secrets/config.yaml")
PROVIDER_DIR = Path("secrets/providers")
PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

URL_TEST = "https://www.gstatic.com/generate_204"

BASE_RULES = [
    "DOMAIN-SUFFIX,tailscale.com,DIRECT",
    "DOMAIN-SUFFIX,ts.net,DIRECT",
    "IP-CIDR,100.64.0.0/10,DIRECT,no-resolve",
    "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
    "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,169.254.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
    "GEOSITE,private,DIRECT",
    "GEOSITE,ads,REJECT",
    "GEOSITE,trackerslist,REJECT",
    "GEOSITE,microsoft-cn,DIRECT",
    "GEOSITE,apple-cn,DIRECT",
    "GEOSITE,google-cn,DIRECT",
    "GEOSITE,games-cn,DIRECT",
    "GEOSITE,ai,AI",
    "GEOSITE,networktest,DIRECT",
    "GEOSITE,tld-proxy,PROXY",
    "GEOSITE,proxy,PROXY",
    "GEOSITE,cn,DIRECT",
    "GEOIP,private,DIRECT,no-resolve",
    "GEOIP,cn,DIRECT",
    "GEOIP,telegram,PROXY,no-resolve",
    "MATCH,PROXY",
]

QUICKSTART = """
No subscription provider configured.

Quick start, single subscription:
  mkdir -p secrets
  cp .env.example secrets/.env
  chmod 700 secrets
  chmod 600 secrets/.env
  # edit secrets/.env and set MIHOMO_SUB_URL=...
  python3 builder.py build
  python3 builder.py check

Or inject env without creating a file:
  MIHOMO_SUB_URL='https://example.invalid/sub' python3 builder.py preview
""".strip()


class BuilderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    id: str
    url: str
    env_key: str
    role: str
    order: int
    filter: str | None = None
    exclude_filter: str | None = None
    ai_filter: str | None = None
    ai_exclude_filter: str | None = None


def parse_dotenv(path: Path) -> dict[str, str]:
    """Tiny .env parser; enough for KEY=VALUE and quoted values."""
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise BuilderError(f"Invalid .env line {lineno}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise BuilderError(f"Invalid .env line {lineno}: empty key")
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
        data[key] = value
    return data


def load_env(base_dir: Path) -> dict[str, str]:
    # Process environment wins over secrets/.env, so a one-off env injection can override file state.
    merged = parse_dotenv(base_dir / ENV_FILE)
    merged.update({k: v for k, v in os.environ.items() if v is not None})
    return merged


def require_provider_id(value: str, source: str) -> str:
    if not value or not PROVIDER_ID_RE.match(value):
        raise BuilderError(
            f"Invalid provider id from {source!r}: {value!r}; allowed: [A-Za-z0-9_-]"
        )
    if value in {"DIRECT", "REJECT", "GLOBAL", "PROXY", "AI"}:
        raise BuilderError(f"Provider id {value!r} is reserved")
    return value


def nonempty(env: dict[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def discover_providers(env: dict[str, str]) -> list[Provider]:
    numbered = []
    for n in range(1, 100):
        url_key = f"MIHOMO_PROVIDER_{n}_URL"
        url = nonempty(env, url_key)
        if not url:
            continue
        pid = require_provider_id(nonempty(env, f"MIHOMO_PROVIDER_{n}_ID") or f"provider{n}", f"MIHOMO_PROVIDER_{n}_ID")
        role = nonempty(env, f"MIHOMO_PROVIDER_{n}_ROLE") or ("primary" if not numbered else "backup")
        numbered.append(
            Provider(
                id=pid,
                url=url,
                env_key=url_key,
                role=role,
                order=n,
                filter=nonempty(env, f"MIHOMO_PROVIDER_{n}_FILTER"),
                exclude_filter=nonempty(env, f"MIHOMO_PROVIDER_{n}_EXCLUDE_FILTER"),
                ai_filter=nonempty(env, f"MIHOMO_PROVIDER_{n}_AI_FILTER"),
                ai_exclude_filter=nonempty(env, f"MIHOMO_PROVIDER_{n}_AI_EXCLUDE_FILTER"),
            )
        )

    providers: list[Provider]
    if numbered:
        providers = sorted(numbered, key=lambda p: p.order)
    else:
        url = nonempty(env, "MIHOMO_SUB_URL")
        if not url:
            return []
        providers = [
            Provider(
                id=require_provider_id(nonempty(env, "MIHOMO_SUB_ID") or "airport", "MIHOMO_SUB_ID"),
                url=url,
                env_key="MIHOMO_SUB_URL",
                role="primary",
                order=1,
                filter=nonempty(env, "MIHOMO_SUB_FILTER"),
                exclude_filter=nonempty(env, "MIHOMO_SUB_EXCLUDE_FILTER"),
                ai_filter=nonempty(env, "MIHOMO_SUB_AI_FILTER"),
                ai_exclude_filter=nonempty(env, "MIHOMO_SUB_AI_EXCLUDE_FILTER"),
            )
        ]

    seen: set[str] = set()
    for p in providers:
        if p.id in seen:
            raise BuilderError(f"Duplicate provider id: {p.id}")
        if f"{p.id}-ai" in seen:
            raise BuilderError(f"Provider id conflicts with generated AI provider id: {p.id}")
        seen.add(p.id)
    return providers


def provider_path(pid: str) -> str:
    return f"./secrets/providers/{pid}.yaml"


def redacted_url(provider: Provider) -> str:
    return f"<REDACTED:{provider.env_key}>"


def provider_config(
    provider: Provider,
    *,
    url: str,
    ai: bool = False,
    global_ai_filter: str | None = None,
    global_ai_exclude_filter: str | None = None,
) -> dict[str, Any]:
    pid = f"{provider.id}-ai" if ai else provider.id
    cfg: dict[str, Any] = {
        "type": "http",
        "url": url,
        "interval": 86400,
        "path": provider_path(pid),
        "health-check": {
            "enable": True,
            "url": URL_TEST,
            "interval": 300,
            "timeout": 5000,
            "lazy": True,
            "expected-status": 204,
        },
    }
    include_filter = provider.ai_filter if ai else provider.filter
    exclude_filter = provider.ai_exclude_filter if ai else provider.exclude_filter
    if ai and not include_filter:
        include_filter = global_ai_filter
    if ai and not exclude_filter:
        exclude_filter = global_ai_exclude_filter
    if include_filter:
        cfg["filter"] = include_filter
    if exclude_filter:
        cfg["exclude-filter"] = exclude_filter
    return cfg


def url_test_group(name: str, use: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "type": "url-test",
        "use": use,
        "url": URL_TEST,
        "interval": 300,
        "tolerance": 100,
        "lazy": True,
    }


def fallback_group(name: str, proxies: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "type": "fallback",
        "proxies": proxies,
        "url": URL_TEST,
        "interval": 300,
        "lazy": True,
    }


def make_config(providers: list[Provider], *, redact: bool = False, env: dict[str, str] | None = None) -> dict[str, Any]:
    if not providers:
        raise BuilderError(QUICKSTART)

    env = env or {}
    global_ai_filter = nonempty(env, "MIHOMO_AI_FILTER")
    global_ai_exclude_filter = nonempty(env, "MIHOMO_AI_EXCLUDE_FILTER")

    proxy_providers: dict[str, Any] = {}
    for p in providers:
        url = redacted_url(p) if redact else p.url
        proxy_providers[p.id] = provider_config(p, url=url, ai=False)
        proxy_providers[f"{p.id}-ai"] = provider_config(
            p,
            url=url,
            ai=True,
            global_ai_filter=global_ai_filter,
            global_ai_exclude_filter=global_ai_exclude_filter,
        )

    groups: list[dict[str, Any]] = []
    if len(providers) == 1:
        p = providers[0]
        groups.append(url_test_group("Auto", [p.id]))
        groups.append({"name": "PROXY", "type": "select", "proxies": ["Auto", "DIRECT"]})
        groups.append({"name": "GLOBAL", "type": "select", "proxies": ["PROXY", "DIRECT", "REJECT"]})
        groups.append(url_test_group("AI", [f"{p.id}-ai"]))
        mode = "single-provider"
    else:
        auto_names = []
        ai_auto_names = []
        for p in providers:
            auto_name = f"{p.id}-Auto"
            ai_auto_name = f"{p.id}-AI-Auto"
            auto_names.append(auto_name)
            ai_auto_names.append(ai_auto_name)
            groups.append(url_test_group(auto_name, [p.id]))
            groups.append(url_test_group(ai_auto_name, [f"{p.id}-ai"]))
        groups.append(fallback_group("Tiered-Auto", auto_names))
        groups.append(fallback_group("AI-Tiered-Auto", ai_auto_names))
        groups.append(
            {
                "name": "PROXY",
                "type": "select",
                "proxies": ["Tiered-Auto", *auto_names, "DIRECT"],
            }
        )
        groups.append({"name": "GLOBAL", "type": "select", "proxies": ["PROXY", "DIRECT", "REJECT"]})
        groups.append({"name": "AI", "type": "select", "proxies": ["AI-Tiered-Auto", *ai_auto_names, "PROXY", "DIRECT"]})
        mode = "multi-provider"

    return {
        "mixed-port": 7890,
        "allow-lan": True,
        "bind-address": "*",
        "mode": "rule",
        "log-level": "info",
        "unified-delay": True,
        "tcp-concurrent": True,
        "external-controller": "127.0.0.1:9090",
        "external-ui": "./ui",
        "external-ui-url": "https://cdn.gh-proxy.org/https://github.com/MetaCubeX/metacubexd/archive/refs/heads/gh-pages.zip",
        "geodata-mode": True,
        "geo-auto-update": True,
        "geo-update-interval": 24,
        "geox-url": {
            "geosite": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/geosite.dat",
            "geoip": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/geoip.dat",
            "mmdb": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/Country.mmdb",
            "asn": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/Country-ASN.mmdb",
        },
        "profile": {"store-selected": True, "store-fake-ip": True},
        "tun": {
            "enable": True,
            "stack": "mixed",
            "dns-hijack": ["any:53", "tcp://any:53"],
            "auto-route": True,
            "auto-detect-interface": True,
            "strict-route": False,
            "endpoint-independent-nat": True,
        },
        "dns": {
            "enable": True,
            "listen": "0.0.0.0:1053",
            "ipv6": False,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "fake-ip-filter-mode": "blacklist",
            "fake-ip-filter": ["geosite:fakeip-filter", "tailscale.com", "*.tailscale.com", "*.ts.net"],
            "respect-rules": True,
            "default-nameserver": ["223.5.5.5", "119.29.29.29"],
            "proxy-server-nameserver": ["223.5.5.5", "119.29.29.29"],
            "direct-nameserver": ["https://doh.pub/dns-query", "https://dns.alidns.com/dns-query"],
            "nameserver": ["https://8.8.8.8/dns-query", "https://1.1.1.1/dns-query"],
        },
        "proxies": [],
        "proxy-providers": proxy_providers,
        "proxy-groups": groups,
        "rules": BASE_RULES,
        "x-builder-meta": {
            "mode": mode,
            "provider-order": [p.id for p in providers],
            "ai-provider-order": [f"{p.id}-ai" for p in providers],
            "secret-values-exposed": False if redact else "written-to-sensitive-config",
        },
    }


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def to_yaml(value: Any, indent: int = 0) -> str:
    sp = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for k, v in value.items():
            key = str(k)
            if isinstance(v, (dict, list)):
                lines.append(f"{sp}{key}:")
                lines.append(to_yaml(v, indent + 2))
            else:
                lines.append(f"{sp}{key}: {yaml_scalar(v)}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{sp}[]"
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{sp}-")
                lines.append(to_yaml(item, indent + 2))
            elif isinstance(item, list):
                lines.append(f"{sp}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{sp}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{sp}{yaml_scalar(value)}"


def output_path(base_dir: Path) -> Path:
    return base_dir / OUTPUT_FILE


def write_secure_config(base_dir: Path, content: str) -> Path:
    secrets_dir = base_dir / "secrets"
    providers_dir = base_dir / PROVIDER_DIR
    secrets_dir.mkdir(mode=0o700, exist_ok=True)
    providers_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(secrets_dir, 0o700)
    os.chmod(providers_dir, 0o700)
    out = output_path(base_dir)
    tmp = out.with_suffix(".yaml.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(out)
    os.chmod(out, 0o600)
    env_path = base_dir / ENV_FILE
    if env_path.exists():
        os.chmod(env_path, 0o600)
    return out


def find_binary(base_dir: Path) -> Path | None:
    for name in ("clash", "mihomo"):
        p = base_dir / name
        if p.exists() and os.access(p, os.X_OK):
            return p
    return None


def binary_supports_flags(binary: Path) -> bool:
    try:
        proc = subprocess.run([str(binary), "-h"], cwd=str(binary.parent), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
    except Exception:
        return False
    return "-f" in proc.stdout and "-t" in proc.stdout


def run_config_test(base_dir: Path, config_path: Path) -> int:
    binary = find_binary(base_dir)
    if not binary:
        print("binary_found: false")
        return 0
    cmd = [str(binary), "-t", "-d", str(base_dir), "-f", str(config_path)]
    proc = subprocess.run(cmd, cwd=str(base_dir), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    # Mihomo test output should not include subscription URLs, but keep output minimal anyway.
    print(f"config_test_command: {binary.name} -t -d {base_dir} -f {config_path}")
    print(f"config_test_exit_code: {proc.returncode}")
    if proc.returncode != 0:
        safe_lines = [line for line in proc.stdout.splitlines() if "http" not in line.lower() and "token" not in line.lower()]
        print("config_test_output_redacted:")
        print("\n".join(safe_lines[-40:]))
    return proc.returncode


def cmd_preview(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    env = load_env(base_dir)
    providers = discover_providers(env)
    print(to_yaml(make_config(providers, redact=True, env=env)))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    env = load_env(base_dir)
    providers = discover_providers(env)
    rendered = to_yaml(make_config(providers, redact=False, env=env)) + "\n"
    out = write_secure_config(base_dir, rendered)
    print("Built Mihomo config")
    print(f"- mode: {'single-provider' if len(providers) == 1 else 'multi-provider'}")
    print(f"- providers: {', '.join(p.id for p in providers)}")
    print(f"- output: {out}")
    print("- secret_values_exposed: false")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    env = load_env(base_dir)
    providers = discover_providers(env)
    _ = make_config(providers, redact=True, env=env)
    print("env_shape: ok")
    print(f"provider_count: {len(providers)}")
    print(f"provider_order: {', '.join(p.id for p in providers)}")
    out = output_path(base_dir)
    if out.exists():
        mode = stat.S_IMODE(out.stat().st_mode)
        print(f"generated_config_present: yes")
        print(f"generated_config_mode: {mode:04o}")
        return run_config_test(base_dir, out)
    print("generated_config_present: no")
    print("config_test_skipped: run `python3 builder.py build` first")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    env_path = base_dir / ENV_FILE
    out = output_path(base_dir)
    providers: list[Provider] = []
    env_ok = True
    env_error = ""
    try:
        providers = discover_providers(load_env(base_dir))
    except Exception as exc:  # keep doctor non-secret and non-fatal
        env_ok = False
        env_error = str(exc).splitlines()[0]
    binary = find_binary(base_dir)
    print(f"base_dir: {base_dir}")
    print(f"builder_py_present: {Path(__file__).exists()}")
    print(f"secrets_env_present: {env_path.exists()}")
    print(f"env_shape_ok: {env_ok}")
    if not env_ok:
        print(f"env_shape_error_redacted: {env_error}")
    print(f"provider_count: {len(providers)}")
    print(f"provider_order: {', '.join(p.id for p in providers) if providers else '<none>'}")
    print(f"generated_config_present: {out.exists()}")
    if out.exists():
        print(f"generated_config_mode: {stat.S_IMODE(out.stat().st_mode):04o}")
    print(f"provider_dir_present: {(base_dir / PROVIDER_DIR).exists()}")
    print(f"binary_found: {binary.name if binary else '<none>'}")
    print(f"binary_supports_f_and_t: {binary_supports_flags(binary) if binary else False}")
    print("secret_values_exposed: false")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build redaction-safe Mihomo/Clash config from env/secrets/.env")
    parser.add_argument("--base-dir", default=str(BASE_DIR), help="module directory; defaults to builder.py directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview", help="print redacted generated YAML; writes nothing").set_defaults(func=cmd_preview)
    sub.add_parser("build", help="write secrets/config.yaml with mode 0600").set_defaults(func=cmd_build)
    sub.add_parser("check", help="validate env shape and test generated config when present").set_defaults(func=cmd_check)
    sub.add_parser("doctor", help="redacted status probe safe for agents").set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BuilderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

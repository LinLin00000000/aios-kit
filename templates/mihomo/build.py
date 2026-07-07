#!/usr/bin/env python3
"""Low-complexity Mihomo/Clash config build script.

Safe agent contract:
- Reads process environment and, when present, secrets/.env as the private runtime layer.
- Reads public policy.toml when present as the auditable strategy layer.
- Provider IDs/order/URLs always come from MIHOMO_PROVIDERS_ORDER and MIHOMO_PROVIDER_<ID>_URL.
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
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = Path("policy.toml")
ENV_FILE = Path("secrets/.env")
OUTPUT_FILE = Path("secrets/config.yaml")
PROVIDER_DIR = Path("secrets/providers")
PROVIDER_ID_RE = re.compile(r"^[a-z0-9_]+$")
PROVIDER_URL_KEY_RE = re.compile(r"^MIHOMO_PROVIDER_([A-Z0-9_]+)_URL$")
LEGACY_NUMBERED_PROVIDER_RE = re.compile(r"^MIHOMO_PROVIDER_\d+(_|$)")

URL_TEST = "https://www.gstatic.com/generate_204"

# Default rules are intentionally generic. Advanced groups add rules through
# policy.toml [rules].prepend so no feature-specific group is implicit.
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
    "GEOSITE,ai,PROXY",
    "GEOSITE,networktest,DIRECT",
    "GEOSITE,tld-proxy,PROXY",
    "GEOSITE,proxy,PROXY",
    "GEOSITE,cn,DIRECT",
    "GEOIP,private,DIRECT,no-resolve",
    "GEOIP,cn,DIRECT",
    "GEOIP,telegram,PROXY,no-resolve",
    "MATCH,PROXY",
]

RULE_MODES = {"geox", "rule-set"}

# AIOS keeps Tailscale and private LAN/CIDR direct rules in front of both rule
# engines. The rule-set mode below otherwise follows the DustinWin mihomo-ruleset
# categories from the user-provided template, without copying provider URLs or
# proxy-group policy from that template.
AIOS_DIRECT_RULES = [
    "DOMAIN-SUFFIX,tailscale.com,DIRECT",
    "DOMAIN-SUFFIX,ts.net,DIRECT",
    "IP-CIDR,100.64.0.0/10,DIRECT,no-resolve",
    "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
    "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
    "IP-CIDR,169.254.0.0/16,DIRECT,no-resolve",
    "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
]

RULESET_BASE_URL = "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-ruleset"
RULESET_PROVIDER_SPECS = [
    ("fakeip-filter", "domain", "mrs", "fakeip-filter.mrs"),
    ("ads", "domain", "mrs", "ads.mrs"),
    ("private", "domain", "mrs", "private.mrs"),
    ("trackerslist", "domain", "mrs", "trackerslist.mrs"),
    ("applications", "classical", "text", "applications.list"),
    ("microsoft-cn", "domain", "mrs", "microsoft-cn.mrs"),
    ("apple-cn", "domain", "mrs", "apple-cn.mrs"),
    ("google-cn", "domain", "mrs", "google-cn.mrs"),
    ("games-cn", "domain", "mrs", "games-cn.mrs"),
    ("games", "domain", "mrs", "games.mrs"),
    ("netflix", "domain", "mrs", "netflix.mrs"),
    ("disney", "domain", "mrs", "disney.mrs"),
    ("max", "domain", "mrs", "max.mrs"),
    ("primevideo", "domain", "mrs", "primevideo.mrs"),
    ("appletv", "domain", "mrs", "appletv.mrs"),
    ("youtube", "domain", "mrs", "youtube.mrs"),
    ("tiktok", "domain", "mrs", "tiktok.mrs"),
    ("bilibili", "domain", "mrs", "bilibili.mrs"),
    ("spotify", "domain", "mrs", "spotify.mrs"),
    ("media", "domain", "mrs", "media.mrs"),
    ("ai", "domain", "mrs", "ai.mrs"),
    ("networktest", "domain", "mrs", "networktest.mrs"),
    ("tld-proxy", "domain", "mrs", "tld-proxy.mrs"),
    ("gfw", "domain", "mrs", "gfw.mrs"),
    ("proxy", "domain", "mrs", "proxy.mrs"),
    ("cn", "domain", "mrs", "cn.mrs"),
    ("privateip", "ipcidr", "mrs", "privateip.mrs"),
    ("cnip", "ipcidr", "mrs", "cnip.mrs"),
    ("telegramip", "ipcidr", "mrs", "telegramip.mrs"),
    ("netflixip", "ipcidr", "mrs", "netflixip.mrs"),
    ("mediaip", "ipcidr", "mrs", "mediaip.mrs"),
]

RULESET_RULES = [
    *AIOS_DIRECT_RULES,
    "RULE-SET,private,DIRECT",
    "RULE-SET,ads,REJECT",
    "RULE-SET,trackerslist,REJECT",
    "RULE-SET,applications,DIRECT",
    "RULE-SET,microsoft-cn,DIRECT",
    "RULE-SET,apple-cn,DIRECT",
    "RULE-SET,google-cn,DIRECT",
    "RULE-SET,games-cn,DIRECT",
    "RULE-SET,games,PROXY",
    "RULE-SET,netflix,PROXY",
    "RULE-SET,disney,PROXY",
    "RULE-SET,max,PROXY",
    "RULE-SET,primevideo,PROXY",
    "RULE-SET,appletv,PROXY",
    "RULE-SET,youtube,PROXY",
    "RULE-SET,tiktok,PROXY",
    "RULE-SET,bilibili,DIRECT",
    "RULE-SET,spotify,PROXY",
    "RULE-SET,media,PROXY",
    "RULE-SET,ai,AI",
    "RULE-SET,networktest,DIRECT",
    "RULE-SET,tld-proxy,PROXY",
    "RULE-SET,gfw,PROXY",
    "RULE-SET,proxy,PROXY",
    "RULE-SET,cn,DIRECT",
    "RULE-SET,privateip,DIRECT,no-resolve",
    "RULE-SET,cnip,DIRECT",
    "RULE-SET,telegramip,PROXY,no-resolve",
    "RULE-SET,netflixip,PROXY",
    "RULE-SET,mediaip,PROXY",
    "MATCH,PROXY",
]

QUICKSTART = """
No subscription provider configured.

Quick start:
  mkdir -p secrets
  cp .env.example secrets/.env
  chmod 700 secrets
  chmod 600 secrets/.env
  # edit secrets/.env and set MIHOMO_PROVIDERS_ORDER plus MIHOMO_PROVIDER_<ID>_URL
  python3 build.py build
  python3 build.py check

Advanced mode:
  keep provider IDs/order/URLs in secrets/.env
  edit policy.toml only for public strategy groups/rules
""".strip()


class BuilderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    id: str
    url: str | None
    env_key: str
    order: int
    filter: str | None = None
    exclude_filter: str | None = None


@dataclass(frozen=True)
class BuildSpec:
    source: str
    providers: list[Provider]
    extra_groups: list[dict[str, Any]] = field(default_factory=list)
    rules_prepend: list[str] = field(default_factory=list)
    rules_append: list[str] = field(default_factory=list)
    base_proxy: bool = True
    base_rules: bool = True
    rules_mode: str = "geox"
    tun_enable: bool = True


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
    # Process environment wins over secrets/.env, so secret managers can inject values externally.
    merged = parse_dotenv(base_dir / ENV_FILE)
    merged.update({k: v for k, v in os.environ.items() if v is not None})
    return merged


def require_provider_id(value: str, source: str) -> str:
    if not value or not PROVIDER_ID_RE.match(value):
        raise BuilderError(
            f"Invalid provider id from {source!r}: {value!r}; allowed: lowercase [a-z0-9_]"
        )
    if value.upper() in {"DIRECT", "REJECT", "GLOBAL", "PROXY", "AI"}:
        raise BuilderError(f"Provider id {value!r} is reserved")
    return value


def require_group_name(value: str, source: str) -> str:
    if not value or not isinstance(value, str):
        raise BuilderError(f"Invalid group name from {source!r}: expected non-empty string")
    if value in {"DIRECT", "REJECT", "GLOBAL", "PROXY"}:
        raise BuilderError(f"Group name {value!r} is reserved by generated base groups")
    return value


def nonempty(env: dict[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def toml_bool(data: dict[str, Any], key: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    raise BuilderError(f"policy.toml {key} must be true/false")


def toml_choice(data: dict[str, Any], key: str, *, default: str, allowed: set[str], source: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise BuilderError(f"{source} must be a string")
    value = value.strip()
    if value not in allowed:
        options = ", ".join(sorted(allowed))
        raise BuilderError(f"{source} must be one of: {options}")
    return value


def require_list(value: Any, source: str) -> list[Any]:
    if not isinstance(value, list):
        raise BuilderError(f"{source} must be a list")
    return value


def require_str_list(value: Any, source: str) -> list[str]:
    items = require_list(value, source)
    for item in items:
        if not isinstance(item, str) or not item:
            raise BuilderError(f"{source} must contain only non-empty strings")
    return list(items)


def legacy_env_keys(env: dict[str, str]) -> list[str]:
    """Return legacy configuration keys without inspecting their values."""
    keys: list[str] = []
    for key in env:
        if LEGACY_NUMBERED_PROVIDER_RE.match(key) or key.startswith("MIHOMO_SUB_") or key == "MIHOMO_AI_ENABLED":
            keys.append(key)
    return sorted(keys)


def provider_env_key(pid: str) -> str:
    return f"MIHOMO_PROVIDER_{pid.upper()}_URL"


def parse_provider_order(env: dict[str, str]) -> list[str]:
    order_raw = nonempty(env, "MIHOMO_PROVIDERS_ORDER")
    if not order_raw:
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for pos, raw_id in enumerate(order_raw.split(","), 1):
        pid = require_provider_id(raw_id.strip(), f"MIHOMO_PROVIDERS_ORDER[{pos}]")
        if pid in seen:
            raise BuilderError(f"Duplicate provider id in MIHOMO_PROVIDERS_ORDER: {pid}")
        seen.add(pid)
        ids.append(pid)
    if not ids:
        raise BuilderError("MIHOMO_PROVIDERS_ORDER must list at least one provider id")
    return ids


def discover_env_providers(env: dict[str, str], *, require_secrets: bool) -> list[Provider]:
    legacy = legacy_env_keys(env)
    if legacy:
        sample = ", ".join(legacy[:8])
        suffix = " ..." if len(legacy) > 8 else ""
        raise BuilderError(
            "Legacy env keys are no longer supported: "
            f"{sample}{suffix}. Use MIHOMO_PROVIDERS_ORDER=id1,id2 and "
            "MIHOMO_PROVIDER_<ID>_URL instead."
        )

    ordered_ids = parse_provider_order(env)
    if not ordered_ids:
        unmanaged_url_keys = sorted(key for key in env if PROVIDER_URL_KEY_RE.match(key))
        if unmanaged_url_keys:
            raise BuilderError(
                "MIHOMO_PROVIDER_<ID>_URL keys are present, but MIHOMO_PROVIDERS_ORDER is missing. "
                f"Set MIHOMO_PROVIDERS_ORDER to include: {', '.join(unmanaged_url_keys)}"
            )
        return []

    order_set = set(ordered_ids)
    unmanaged_url_keys: list[str] = []
    for key in env:
        match = PROVIDER_URL_KEY_RE.match(key)
        if not match:
            continue
        pid = match.group(1).lower()
        if pid not in order_set:
            unmanaged_url_keys.append(key)
    if unmanaged_url_keys:
        raise BuilderError(
            "Provider URL keys exist but are not listed in MIHOMO_PROVIDERS_ORDER: "
            f"{', '.join(sorted(unmanaged_url_keys))}"
        )

    providers: list[Provider] = []
    for idx, pid in enumerate(ordered_ids, 1):
        env_key = provider_env_key(pid)
        url = nonempty(env, env_key)
        if require_secrets and not url:
            raise BuilderError(f"Missing provider URL for {pid!r}: set {env_key}")
        providers.append(
            Provider(
                id=pid,
                url=url,
                env_key=env_key,
                order=idx,
            )
        )

    validate_providers(providers)
    return providers


def validate_providers(providers: list[Provider]) -> None:
    seen: set[str] = set()
    for p in providers:
        if p.id in seen:
            raise BuilderError(f"Duplicate provider id: {p.id}")
        seen.add(p.id)


def provider_path(pid: str) -> str:
    return f"./secrets/providers/{pid}.yaml"


def redacted_url(provider: Provider) -> str:
    return f"<REDACTED:{provider.env_key}>"


def provider_config(provider: Provider, *, url: str) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "type": "http",
        "url": url,
        "interval": 86400,
        "path": provider_path(provider.id),
        "health-check": {
            "enable": True,
            "url": URL_TEST,
            "interval": 300,
            "timeout": 5000,
            "lazy": True,
            "expected-status": 204,
        },
    }
    if provider.filter:
        cfg["filter"] = provider.filter
    if provider.exclude_filter:
        cfg["exclude-filter"] = provider.exclude_filter
    return cfg


def url_test_group(name: str, use: list[str], *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    group: dict[str, Any] = {
        "name": name,
        "type": "url-test",
        "use": use,
        "url": URL_TEST,
        "interval": 300,
        "tolerance": 100,
        "lazy": True,
    }
    if overrides:
        group.update(overrides)
        group["name"] = name
        group["type"] = overrides.get("type", "url-test")
        group["use"] = use
    return group


def fallback_group(name: str, proxies: list[str], *, url: str = URL_TEST, interval: int = 300, lazy: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "type": "fallback",
        "proxies": proxies,
        "url": url,
        "interval": interval,
        "lazy": lazy,
    }


def normal_proxy_groups(providers: list[Provider]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    if len(providers) == 1:
        p = providers[0]
        groups.append(url_test_group("Auto", [p.id]))
        groups.append({"name": "PROXY", "type": "select", "proxies": ["Auto", "DIRECT"]})
        groups.append({"name": "GLOBAL", "type": "select", "proxies": ["PROXY", "DIRECT", "REJECT"]})
        return groups

    auto_names = []
    for p in providers:
        auto_name = f"{p.id}-Auto"
        auto_names.append(auto_name)
        groups.append(url_test_group(auto_name, [p.id]))
    groups.append(fallback_group("Tiered-Auto", auto_names))
    groups.append({"name": "PROXY", "type": "select", "proxies": ["Tiered-Auto", *auto_names, "DIRECT"]})
    groups.append({"name": "GLOBAL", "type": "select", "proxies": ["PROXY", "DIRECT", "REJECT"]})
    return groups


def load_spec(base_dir: Path, env: dict[str, str], *, require_secrets: bool) -> BuildSpec:
    providers = discover_env_providers(env, require_secrets=require_secrets)
    if not providers:
        raise BuilderError(QUICKSTART)

    config_path = base_dir / CONFIG_FILE
    if config_path.exists():
        return load_toml_spec(config_path, providers)
    return BuildSpec(source="env", providers=providers)


def load_toml_spec(config_path: Path, providers: list[Provider]) -> BuildSpec:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BuilderError(f"Invalid policy.toml: {exc}") from exc

    defaults = data.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise BuilderError("policy.toml [defaults] must be a table")
    base_proxy = toml_bool(defaults, "base_proxy", default=True)
    base_rules = toml_bool(defaults, "base_rules", default=True)
    tun_enable = toml_bool(defaults, "tun_enable", default=True)

    if "providers" in data:
        raise BuilderError(
            "policy.toml [[providers]] is no longer supported. "
            "Move provider IDs/order to MIHOMO_PROVIDERS_ORDER and URLs to MIHOMO_PROVIDER_<ID>_URL."
        )

    provider_ids = {p.id for p in providers}
    extra_groups: list[dict[str, Any]] = []
    for idx, row in enumerate(require_list(data.get("groups", []), "policy.toml [[groups]]"), 1):
        if not isinstance(row, dict):
            raise BuilderError(f"policy.toml [[groups]] item {idx} must be a table")
        extra_groups.extend(expand_toml_group(row, idx=idx, provider_ids=provider_ids, default_provider_order=[p.id for p in providers]))

    rules_table = data.get("rules", {})
    if rules_table is None:
        rules_table = {}
    if not isinstance(rules_table, dict):
        raise BuilderError("policy.toml [rules] must be a table")
    rules_mode = toml_choice(
        rules_table,
        "mode",
        default="geox",
        allowed=RULE_MODES,
        source="policy.toml rules.mode",
    )
    rules_prepend = require_str_list(rules_table.get("prepend", []), "policy.toml rules.prepend")
    rules_append = require_str_list(rules_table.get("append", []), "policy.toml rules.append")

    return BuildSpec(
        source="env+toml",
        providers=providers,
        extra_groups=extra_groups,
        rules_prepend=rules_prepend,
        rules_append=rules_append,
        base_proxy=base_proxy,
        base_rules=base_rules,
        rules_mode=rules_mode,
        tun_enable=tun_enable,
    )


def load_local_policy_spec(base_dir: Path) -> BuildSpec:
    """Load only policy pieces that are meaningful for local raw proxy YAML."""
    config_path = base_dir / CONFIG_FILE
    if not config_path.exists():
        return BuildSpec(source="local-proxies", providers=[], base_proxy=False)
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BuilderError(f"Invalid policy.toml: {exc}") from exc

    defaults = data.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise BuilderError("policy.toml [defaults] must be a table")
    base_rules = toml_bool(defaults, "base_rules", default=True)
    tun_enable = toml_bool(defaults, "tun_enable", default=True)

    rules_table = data.get("rules", {})
    if rules_table is None:
        rules_table = {}
    if not isinstance(rules_table, dict):
        raise BuilderError("policy.toml [rules] must be a table")
    rules_mode = toml_choice(
        rules_table,
        "mode",
        default="geox",
        allowed=RULE_MODES,
        source="policy.toml rules.mode",
    )
    rules_prepend = require_str_list(rules_table.get("prepend", []), "policy.toml rules.prepend")
    rules_append = require_str_list(rules_table.get("append", []), "policy.toml rules.append")

    return BuildSpec(
        source="local-proxies+toml",
        providers=[],
        rules_prepend=rules_prepend,
        rules_append=rules_append,
        base_proxy=False,
        base_rules=base_rules,
        rules_mode=rules_mode,
        tun_enable=tun_enable,
    )


def optional_str(row: dict[str, Any], key: str, source: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BuilderError(f"{source} must be a string")
    return value or None


def validate_group_provider_ids(ids: list[str], *, provider_ids: set[str], source: str) -> list[str]:
    for pid in ids:
        if pid not in provider_ids:
            raise BuilderError(f"{source} references unknown provider id {pid!r}")
    return ids


def expand_toml_group(row: dict[str, Any], *, idx: int, provider_ids: set[str], default_provider_order: list[str]) -> list[dict[str, Any]]:
    name = require_group_name(str(row.get("name", "")).strip(), f"policy.toml groups[{idx}].name")
    strategy = str(row.get("strategy", "direct")).strip()
    if strategy in {"direct", ""}:
        group = {k: v for k, v in row.items() if k != "strategy"}
        group["name"] = name
        if "providers" in group and "use" not in group:
            group["use"] = validate_group_provider_ids(require_str_list(group.pop("providers"), f"policy.toml groups[{idx}].providers"), provider_ids=provider_ids, source=f"policy.toml groups[{idx}].providers")
        elif "use" in group:
            group["use"] = validate_group_provider_ids(require_str_list(group["use"], f"policy.toml groups[{idx}].use"), provider_ids=provider_ids, source=f"policy.toml groups[{idx}].use")
        return [group]

    if strategy != "tiered-url-test":
        raise BuilderError(f"Unsupported policy.toml groups[{idx}].strategy: {strategy!r}")

    selected_providers = row.get("providers", default_provider_order)
    selected_ids = validate_group_provider_ids(
        require_str_list(selected_providers, f"policy.toml groups[{idx}].providers"),
        provider_ids=provider_ids,
        source=f"policy.toml groups[{idx}].providers",
    )
    if not selected_ids:
        raise BuilderError(f"policy.toml groups[{idx}].providers must not be empty")

    inner_type = str(row.get("type", "url-test")).strip() or "url-test"
    if inner_type != "url-test":
        raise BuilderError("tiered-url-test currently requires type = 'url-test'")
    component_suffix = str(row.get("component_suffix", "Auto")).strip() or "Auto"
    visible_type = str(row.get("visible_type", "fallback")).strip() or "fallback"
    if visible_type != "fallback":
        raise BuilderError("tiered-url-test currently supports visible_type = 'fallback' only")

    inner_overrides = {
        k: v
        for k, v in row.items()
        if k not in {"name", "strategy", "providers", "component_suffix", "visible_type"}
    }
    inner_overrides["type"] = "url-test"

    expanded: list[dict[str, Any]] = []
    component_names: list[str] = []
    for pid in selected_ids:
        component_name = f"{name}-{pid}-{component_suffix}"
        component_names.append(component_name)
        expanded.append(url_test_group(component_name, [pid], overrides=inner_overrides))

    expanded.append(
        fallback_group(
            name,
            component_names,
            url=str(row.get("url", URL_TEST)),
            interval=int(row.get("interval", 300)),
            lazy=bool(row.get("lazy", True)),
        )
    )
    return expanded


def group_names(groups: list[dict[str, Any]]) -> set[str]:
    return {str(group.get("name", "")) for group in groups if isinstance(group.get("name"), str)}


def ai_rule_target(groups: list[dict[str, Any]]) -> str:
    return "AI" if "AI" in group_names(groups) else "PROXY"


def mode_rules(spec: BuildSpec, groups: list[dict[str, Any]]) -> list[str]:
    ai_target = ai_rule_target(groups)
    if spec.rules_mode == "geox":
        return [f"GEOSITE,ai,{ai_target}" if rule == "GEOSITE,ai,PROXY" else rule for rule in BASE_RULES]
    if spec.rules_mode == "rule-set":
        return [f"RULE-SET,ai,{ai_target}" if rule == "RULE-SET,ai,AI" else rule for rule in RULESET_RULES]
    raise BuilderError(f"Unsupported rules mode: {spec.rules_mode}")


def build_rules(spec: BuildSpec, groups: list[dict[str, Any]]) -> list[str]:
    rules: list[str] = []
    rules.extend(spec.rules_prepend)
    if spec.base_rules:
        rules.extend(mode_rules(spec, groups))
    rules.extend(spec.rules_append)
    return rules


def ruleset_providers() -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for name, behavior, fmt, filename in RULESET_PROVIDER_SPECS:
        providers[name] = {
            "type": "http",
            "interval": 86400,
            "behavior": behavior,
            "format": fmt,
            "path": f"./ruleset/{filename}",
            "url": f"{RULESET_BASE_URL}/{filename}",
        }
    return providers


def dns_config(rules_mode: str) -> dict[str, Any]:
    fake_ip_filter = [
        "rule-set:fakeip-filter" if rules_mode == "rule-set" else "geosite:fakeip-filter",
        "tailscale.com",
        "*.tailscale.com",
        "*.ts.net",
    ]
    return {
        "enable": True,
        "listen": "0.0.0.0:1053",
        "ipv6": False,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "fake-ip-filter-mode": "blacklist",
        "fake-ip-filter": fake_ip_filter,
        "respect-rules": True,
        "default-nameserver": ["223.5.5.5", "119.29.29.29"],
        "proxy-server-nameserver": ["223.5.5.5", "119.29.29.29"],
        "direct-nameserver": ["https://doh.pub/dns-query", "https://dns.alidns.com/dns-query"],
        "nameserver": ["https://8.8.8.8/dns-query", "https://1.1.1.1/dns-query"],
    }


def provider_mode(providers: list[Provider]) -> str:
    if not providers:
        return "local-proxies"
    return "single-provider" if len(providers) == 1 else "multi-provider"


def make_config_sections(
    spec: BuildSpec,
    *,
    proxy_providers: dict[str, Any],
    proxy_groups: list[dict[str, Any]],
    redact: bool,
) -> dict[str, Any]:
    config: dict[str, Any] = {
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
    }
    if spec.rules_mode == "geox":
        config.update(
            {
                "geodata-mode": True,
                "geo-auto-update": True,
                "geo-update-interval": 24,
                "geox-url": {
                    "geosite": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/geosite.dat",
                    "geoip": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/geoip.dat",
                    "mmdb": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/Country.mmdb",
                    "asn": "https://cdn.gh-proxy.org/https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata/Country-ASN.mmdb",
                },
            }
        )
    elif spec.rules_mode == "rule-set":
        config["rule-providers"] = ruleset_providers()
    else:
        raise BuilderError(f"Unsupported rules mode: {spec.rules_mode}")

    config.update(
        {
            "profile": {"store-selected": True, "store-fake-ip": True},
            "tun": {
                "enable": spec.tun_enable,
                "stack": "mixed",
                "dns-hijack": ["any:53", "tcp://any:53"],
                "auto-route": True,
                "auto-detect-interface": True,
                "strict-route": False,
                "endpoint-independent-nat": True,
            },
            "dns": dns_config(spec.rules_mode),
            "proxies": [],
            "proxy-providers": proxy_providers,
            "proxy-groups": proxy_groups,
            "rules": build_rules(spec, proxy_groups),
            "x-build-meta": {
                "source": spec.source,
                "mode": provider_mode(spec.providers),
                "provider-order": [p.id for p in spec.providers],
                "extra-group-count": len(spec.extra_groups),
                "rules-mode": spec.rules_mode,
                "tun-enable": spec.tun_enable,
                "secret-values-exposed": False if redact else "written-to-sensitive-config",
            },
        }
    )
    return config


def make_config(spec: BuildSpec, *, redact: bool = False) -> dict[str, Any]:
    if not spec.providers:
        raise BuilderError(QUICKSTART)

    proxy_providers: dict[str, Any] = {}
    for p in spec.providers:
        if redact:
            url = redacted_url(p)
        else:
            if not p.url:
                raise BuilderError(f"Missing secret env value for {p.env_key!r}")
            url = p.url
        proxy_providers[p.id] = provider_config(p, url=url)

    groups: list[dict[str, Any]] = []
    if spec.base_proxy:
        groups.extend(normal_proxy_groups(spec.providers))
    groups.extend(spec.extra_groups)
    return make_config_sections(spec, proxy_providers=proxy_providers, proxy_groups=groups, redact=redact)


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


def read_local_proxies_block(proxies_file: Path) -> tuple[str, list[str]]:
    raw = proxies_file.read_text(encoding="utf-8").rstrip() + "\n"
    if re.search(r"^\s*proxies\s*:", raw, re.M):
        proxies_block = raw
    else:
        indented = "".join(("  " + line if line.strip() else line) + "\n" for line in raw.splitlines())
        proxies_block = "proxies:\n" + indented

    node_names: list[str] = []
    for match in re.finditer(r'^\s*-\s*name\s*:\s*["\']?([^"\'\n#]+)', raw, re.M):
        name = match.group(1).strip()
        if name and name not in node_names:
            node_names.append(name)
    return proxies_block, node_names


def make_local_proxy_groups(node_names: list[str]) -> list[dict[str, Any]]:
    nodes = node_names if node_names else ["DIRECT"]
    proxy_select: list[str] = []
    for item in ["Auto", "DIRECT", *node_names]:
        if item and item not in proxy_select:
            proxy_select.append(item)
    return [
        {
            "name": "Auto",
            "type": "url-test",
            "interval": 300,
            "tolerance": 100,
            "lazy": True,
            "proxies": nodes,
            "url": URL_TEST,
        },
        {"name": "PROXY", "type": "select", "proxies": proxy_select},
        {"name": "GLOBAL", "type": "select", "proxies": ["PROXY", "DIRECT", "REJECT"]},
    ]


def make_local_proxies_yaml(base_dir: Path, proxies_file: Path) -> tuple[str, BuildSpec, list[str]]:
    spec = load_local_policy_spec(base_dir)
    proxies_block, node_names = read_local_proxies_block(proxies_file)
    config = make_config_sections(
        spec,
        proxy_providers={},
        proxy_groups=make_local_proxy_groups(node_names),
        redact=False,
    )
    rendered = to_yaml(config) + "\n"
    rendered = re.sub(r"(?m)^proxies: \[\]$", proxies_block.rstrip(), rendered, count=1)
    return rendered, spec, node_names


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
    spec = load_spec(base_dir, env, require_secrets=False)
    print(to_yaml(make_config(spec, redact=True)))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    env = load_env(base_dir)
    spec = load_spec(base_dir, env, require_secrets=True)
    rendered = to_yaml(make_config(spec, redact=False)) + "\n"
    out = write_secure_config(base_dir, rendered)
    print("Built Mihomo config")
    print(f"- source: {spec.source}")
    print(f"- mode: {provider_mode(spec.providers)}")
    print(f"- rules_mode: {spec.rules_mode}")
    print(f"- providers: {', '.join(p.id for p in spec.providers)}")
    print(f"- output: {out}")
    print("- secret_values_exposed: false")
    return 0


def cmd_build_local(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    proxies_file = Path(args.proxies_file).expanduser().resolve()
    if not proxies_file.exists():
        raise BuilderError(f"local proxies file not found: {proxies_file}")
    rendered, spec, node_names = make_local_proxies_yaml(base_dir, proxies_file)
    out = write_secure_config(base_dir, rendered)
    print("Built Mihomo config from local proxies YAML")
    print(f"- source: {spec.source}")
    print(f"- mode: local-proxies")
    print(f"- rules_mode: {spec.rules_mode}")
    print(f"- proxy_count: {len(node_names)}")
    print(f"- output: {out}")
    print("- secret_values_exposed: false")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    env = load_env(base_dir)
    out = output_path(base_dir)
    try:
        spec = load_spec(base_dir, env, require_secrets=True)
    except BuilderError as exc:
        if out.exists() and str(exc).startswith("No subscription provider configured"):
            print("env_shape: skipped_no_provider")
            print("config_source: existing-generated-config")
            print("provider_count: 0")
            print("provider_order: <none>")
            print("extra_group_count: 0")
            print("rules_mode: <from-generated-config>")
            mode = stat.S_IMODE(out.stat().st_mode)
            print("generated_config_present: yes")
            print(f"generated_config_mode: {mode:04o}")
            return run_config_test(base_dir, out)
        raise
    _ = make_config(spec, redact=True)
    print("env_shape: ok")
    print(f"config_source: {spec.source}")
    print(f"provider_count: {len(spec.providers)}")
    print(f"provider_order: {', '.join(p.id for p in spec.providers)}")
    print(f"extra_group_count: {len(spec.extra_groups)}")
    print(f"rules_mode: {spec.rules_mode}")
    if out.exists():
        mode = stat.S_IMODE(out.stat().st_mode)
        print(f"generated_config_present: yes")
        print(f"generated_config_mode: {mode:04o}")
        return run_config_test(base_dir, out)
    print("generated_config_present: no")
    print("config_test_skipped: run `python3 build.py build` first")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    env_path = base_dir / ENV_FILE
    config_path = base_dir / CONFIG_FILE
    out = output_path(base_dir)
    spec: BuildSpec | None = None
    env = load_env(base_dir)
    env_ok = True
    env_error = ""
    try:
        spec = load_spec(base_dir, env, require_secrets=False)
    except Exception as exc:  # keep doctor non-secret and non-fatal
        env_ok = False
        env_error = str(exc).splitlines()[0]
    providers = spec.providers if spec else []
    binary = find_binary(base_dir)
    print(f"base_dir: {base_dir}")
    print(f"build_py_present: {Path(__file__).exists()}")
    print(f"policy_toml_present: {config_path.exists()}")
    print(f"config_source: {spec.source if spec else '<none>'}")
    print(f"secrets_env_present: {env_path.exists()}")
    print(f"env_shape_ok: {env_ok}")
    if not env_ok:
        print(f"env_shape_error_redacted: {env_error}")
    print(f"provider_count: {len(providers)}")
    print(f"provider_order: {', '.join(p.id for p in providers) if providers else '<none>'}")
    print(f"extra_group_count: {len(spec.extra_groups) if spec else 0}")
    print(f"rules_mode: {spec.rules_mode if spec else '<none>'}")
    print(f"generated_config_present: {out.exists()}")
    if out.exists():
        print(f"generated_config_mode: {stat.S_IMODE(out.stat().st_mode):04o}")
    print(f"provider_dir_present: {(base_dir / PROVIDER_DIR).exists()}")
    print(f"binary_found: {binary.name if binary else '<none>'}")
    print(f"binary_supports_f_and_t: {binary_supports_flags(binary) if binary else False}")
    print("secret_values_exposed: false")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build redaction-safe Mihomo/Clash config from private env provider registry plus optional policy.toml strategy")
    parser.add_argument("--base-dir", default=str(BASE_DIR), help="module directory; defaults to build.py directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview", help="print redacted generated YAML; writes nothing").set_defaults(func=cmd_preview)
    sub.add_parser("build", help="write secrets/config.yaml with mode 0600").set_defaults(func=cmd_build)
    local = sub.add_parser("build-local", help="write secrets/config.yaml from a private local proxies YAML snippet")
    local.add_argument("--proxies-file", required=True, help="private YAML file containing either a proxies: block or a bare proxy list")
    local.set_defaults(func=cmd_build_local)
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

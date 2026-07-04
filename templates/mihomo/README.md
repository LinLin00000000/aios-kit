# AIOS Mihomo Builder Template

This public template is a low-complexity starting point for agent-assisted Mihomo/Clash networking.

It is intentionally file-based:

- `builder.py` is the dynamic config generator.
- `.env.example` documents the local sensitive inputs.
- `secrets/.env` is created only on the target machine.
- `secrets/config.yaml` is generated on the target machine.
- `secrets/providers/<id>.yaml` is derived from provider IDs.

No private subscription URL, node UUID/password, provider cache, generated config, or `.env` belongs in `aios-kit`.

## Quick start on a target machine

```bash
cd <mihomo-dir>
mkdir -p secrets
cp .env.example secrets/.env
chmod 700 secrets
chmod 600 secrets/.env
$EDITOR secrets/.env
python3 builder.py preview
python3 builder.py build
python3 builder.py check
```

`preview` and `doctor` redact secret values and are safe for Agents to inspect.

## Single subscription

```bash
MIHOMO_SUB_URL=https://example.invalid/sub
MIHOMO_SUB_ID=airport
```

## Multiple providers

```bash
MIHOMO_PROVIDER_1_ID=zjk
MIHOMO_PROVIDER_1_URL=https://example.invalid/zjk
MIHOMO_PROVIDER_1_ROLE=primary

MIHOMO_PROVIDER_2_ID=bywave
MIHOMO_PROVIDER_2_URL=https://example.invalid/bywave
MIHOMO_PROVIDER_2_ROLE=paid_backup
```

Provider numbering is the explicit fallback priority. This is a deliberate convention: simple for the operator and easy for an Agent to audit.

## Independent AI filters

The Builder generates normal providers and separate `<id>-ai` providers. AI traffic can therefore use stricter include/exclude filters without changing the normal `PROXY` path.

```bash
MIHOMO_AI_EXCLUDE_FILTER='(?i)(Hong Kong|HK|Russia|RU)'
```

Per-provider AI filters override global AI filters.

## Service command shape

A Linux systemd service should point at the generated config explicitly:

```ini
ExecStart=<mihomo-dir>/mihomo -d <mihomo-dir> -f <mihomo-dir>/secrets/config.yaml
```

or, for a `clash` binary:

```ini
ExecStart=<mihomo-dir>/clash -d <mihomo-dir> -f <mihomo-dir>/secrets/config.yaml
```

Switching service files and restarting networking are operational steps, not template-generation steps. Confirm with the operator first.

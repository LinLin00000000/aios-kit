# Agent rules for Mihomo module

This directory is a Mihomo/Clash config module.

## Safe to read/edit

- `build.py`
- `policy.toml`
- `.env.example`
- `README.md`
- `AGENTS.md`
- service template/content, if the task is about service wiring
- File metadata for `secrets/**`, provider caches, generated configs, and archives

## Do not read or print by default

Do not read, print, copy into reports, or commit:

- `secrets/.env`
- `secrets/config.yaml`
- `secrets/providers/**`
- provider cache files
- old/generated `config.yaml` files
- any subscription URL, node UUID, password, token, or provider cache content

Use safe probes:

```bash
python3 build.py doctor
python3 build.py preview
python3 build.py check
```

`preview` and `doctor` are redacted. Do not put real subscription URLs directly in shell commands; use `secrets/.env` or `aios secret run`.

Fake one-off test only:

```bash
MIHOMO_PROVIDERS_ORDER=main MIHOMO_PROVIDER_MAIN_URL=https://example.invalid/sub python3 build.py preview
```

## Configuration model

- `secrets/.env` or process env is the private runtime layer: provider IDs/order and provider URL values.
- `policy.toml` is the public strategy layer: groups, rules, defaults.
- `[defaults].tun_enable` controls generated TUN mode. Keep AIOS Kit default `true`; private/local overlays may set it to `false` without forking `build.py`.
- `[defaults].dns_mode` controls `fake-ip` vs `redir-host`; use `redir-host` when Mihomo is a system DNS upstream and consumers require real public addresses for SSRF checks.
- `[rules].mode` selects the base rule engine: `geox` (default, fewer bootstrap moving parts) or `rule-set` (DustinWin MRS/list rule-providers, finer categories).
- `aios secret run --consumer <id> -- python3 build.py build` works because process env overrides `secrets/.env`.
- Do not add feature-specific env flags; AI/streaming/etc. should be normal `policy.toml` groups.

## Service safety

Do not run service reload/restart/proxy switching commands without explicit user confirmation.

Config tests are allowed when they do not print secrets:

```bash
/path/to/mihomo/mihomo -t -d /path/to/mihomo -f /path/to/mihomo/secrets/config.yaml
```

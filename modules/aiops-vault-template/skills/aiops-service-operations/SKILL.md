---
name: aiops-service-operations
description: Use this skill with aiops-vault when the user asks an agent to deploy, inspect, restart, monitor, troubleshoot, migrate, back up, or expose a small self-hosted service. It provides a portable operations workflow for Docker Compose, systemd, reverse proxies, service cards, backup checks, and consumer-side validation without duplicating the user's private inventory.
version: 1.0.0
license: MIT
---

# AIOps Service Operations

This optional skill complements `aiops-vault`. It describes the operations workflow after the vault has supplied current facts.

## Scope

Use for small services and agent-operated infrastructure:

- Docker Compose projects.
- systemd services.
- reverse proxy routes.
- service data directories.
- backup/restore checks.
- health checks and log triage.
- service-card updates.

Do not store service facts in this skill. Use the AIOps vault and live inspection.

## Operation workflow

1. Load `aiops-vault` first when available.
2. Identify the target service and host through `aiops.py service <name>` or `resources --section`.
3. Read the service card or project README if present.
4. Inspect runtime state safely:
   - Docker: `docker ps`, `docker compose ps`, `docker compose logs --tail`.
   - systemd: `systemctl status`, `journalctl --since`, `systemctl cat`.
   - HTTP: `curl -I` or a real health endpoint.
   - proxy: read route config without printing secrets.
5. Separate desired change from risky side effects.
6. Execute the smallest reversible step.
7. Verify from the consumer side, not just the process side.
8. Update current docs and append a maintenance-log entry.

## Deployment defaults

For small cloud-hosted services, prefer:

- deployment files under `/opt/<service>/`;
- persistent data under `/data/<service>/`;
- app ports bound to `127.0.0.1` behind Caddy/Nginx when public HTTPS is needed;
- SSH/admin access on a private network when possible;
- explicit backup and restore notes before trusting a service with important data.

Adjust these defaults to the user's platform and existing conventions.

## Troubleshooting lens

Classify failures by layer:

1. DNS / client route.
2. reverse proxy.
3. app listener / container / systemd unit.
4. upstream API/provider.
5. storage / permissions / disk.
6. authentication / secret location.

Use logs and real probes to distinguish layers. Do not guess from the service name.

## Documentation write-back

- If host, URL, port, runtime, config path, data path, backup boundary, security boundary, or status changed: update `resources.md` or the service card.
- If local runbook details changed: update the service card or service README.
- If the event matters for future recovery: append `maintenance-log.jsonl`.
- If a secret moved: update `secrets-location.md` with location metadata only.

## Final report shape

End with:

- target and resource pool;
- files changed;
- commands run and important output summaries;
- verification result;
- maintenance-log entry status;
- follow-ups or blockers.

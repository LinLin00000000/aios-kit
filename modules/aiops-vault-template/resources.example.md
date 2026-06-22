# Current Resource State

This is a fictional example. Replace it with your own current state. Do not put secret values here.

## Notes

- Current facts should live here or in service cards.
- History belongs in `maintenance-log.jsonl`.
- Unknowns are allowed; mark them explicitly instead of guessing.

## Data Quality Checks

| Check | Status | Notes |
|---|---|---|
| Secrets excluded | ok | Secret values belong in a password manager, not this vault. |
| Backup status recorded | needs-review | Fill after the first backup check. |
| Public exposure reviewed | needs-review | Confirm before exposing services to the internet. |

## Resource Pool Boundaries

| Pool | Scope | Default permission |
|---|---|---|
| personal | Resources you own/control | Agent may inspect and operate within task scope. |
| team | Shared team resources | Confirm authority and blast radius first. |
| third-party | Friend/client/provider resources | Do not operate unless explicitly authorized. |

## Hosts

| Host | Pool | Kind | Address / entrypoint | Access | Status | Notes |
|---|---|---|---|---|---|---|
| demo-vps | personal | cloud VM | 203.0.113.10 / demo-vps.example.com | SSH alias `demo-vps` | example | Reserved documentation IP. |
| home-lab | personal | local server | home-lab.local | LAN / VPN | example | Replace with your own host. |

## Domains and DNS

| Domain | Provider | Purpose | Target | Status | Notes |
|---|---|---|---|---|---|
| example.com | example registrar | documentation only | 203.0.113.10 | example | Replace with your domain. |

## Reverse Proxies

| Proxy | Host | Config path | Public ports | Status | Notes |
|---|---|---|---|---|---|
| caddy | demo-vps | `/etc/caddy/Caddyfile` | 80,443 | example | Keep app ports bound to localhost when possible. |

## Service Inventory

| Service | Host | Runtime | URL / Port | Project path | Data path | Config path | Backup | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| example-api | demo-vps | Docker Compose | https://api.example.com | `/opt/example-api` | `/data/example-api` | `/opt/example-api/docker-compose.yml` | TODO | example | Fictional service. |
| notes-web | home-lab | systemd | http://notes.local:8080 | `/srv/notes-web` | `/srv/notes-web/data` | `/etc/notes-web/config.toml` | TODO | example | Fictional local service. |

## SSH Configuration

| Alias | Host | User | Key location reference | Notes |
|---|---|---|---|---|
| demo-vps | 203.0.113.10 | ops-user | See `secrets-location.md` | Do not store private key content here. |

## Docker / Compose

| Host | Project | Compose path | Data volumes | Notes |
|---|---|---|---|---|
| demo-vps | example-api | `/opt/example-api/docker-compose.yml` | `/data/example-api` | Example only. |

## Common Tools

| Tool | Scope | Notes |
|---|---|---|
| docker | service runtime | Verify with `docker ps` on the target host. |
| systemd | process manager | Use user/system units as appropriate. |
| caddy | reverse proxy | Public HTTPS entrypoint in this example. |

## Backup Strategy

| Scope | Method | Frequency | Last verified | Restore notes |
|---|---|---|---|---|
| example-api data | TODO | TODO | never | Fill after testing restore. |

## Automation Scripts

| Script | Purpose | Schedule | Status | Notes |
|---|---|---|---|---|
| `scripts/aiops.py` | Query/check this vault | manual | active | Standard library only. |

## Archive Index

| Item | Location | Reason | Notes |
|---|---|---|---|
| old-example | `archive/old-example.md` | example | Optional. |

## TODO / Unknowns

- Replace fictional hosts/services with your real inventory.
- Decide backup verification method.
- Decide which services need service cards.

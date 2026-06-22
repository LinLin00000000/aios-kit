# Security Boundaries

The vault is designed to make operations easier without turning your agent context into a secret dump.

## Secrets

Never store secret values in this repository or in your AIOps vault Markdown/JSONL files:

- API keys and tokens
- Passwords
- Private keys
- Cookies and sessions
- Recovery codes
- Subscription URLs
- OAuth refresh tokens

Use `secrets-location.md` only to record where a secret lives and how to rotate it.

## High-risk operations

Agents should ask for confirmation before actions that are hard to reverse or widen exposure:

- Delete or overwrite persistent data.
- Restore backups over live data.
- Rotate credentials.
- Change DNS or public reverse proxy routes.
- Open public ports.
- Disable backups or monitoring.
- Operate third-party/friend/client resources.

## Public sharing

Before sharing a vault or publishing a derivative template:

```bash
python3 scripts/aiops.py check
python3 -m unittest discover -s tests
```

Then inspect for environment-specific facts: real hostnames, public IPs, private IPs, domains, usernames, home paths, provider account names, and secret-like strings.

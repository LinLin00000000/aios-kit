# Security and privacy policy

## Public repo rule

Public `aios-kit` files should be portable:

- Commit examples, schemas, templates, reusable scripts, and generic docs.
- Do not commit machine-specific manifests, live vault data, state files, logs, secrets, tokens, private hostnames, private IPs, or private agent skill contents.

## Local overrides

These files are intentionally ignored:

```text
skillpack.local.yaml
manifests/local-assets.local.json
manifests/local-assets.json
registries/*.local.*
```

Use them for local paths, private skills, current device names, and non-public repositories.

## Audit checklist before public push

Run:

```bash
python3 scripts/audit_public.py
./aios doctor
```

Then inspect:

```bash
git status --short --branch
git ls-files
```

For a repository that accidentally committed private local paths, rewrite history while the repo is new or rotate/delete anything sensitive if a real secret was exposed.

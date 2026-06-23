# Docker smoke and skillpack sync for AIOS Secret work

Use when changing `aios secret`, `skillpack.yaml`, first-party skills, installer paths, or any AIOS Kit distribution surface.

## Clean-room shape

Run Docker with:

- fresh `HOME`
- fresh `AIOS_ROOT`
- fake/dummy secret values only
- no real host `$AIOS_ROOT/vault/secrets/values` mounted
- public/distribution skillpack only; exclude machine-local overlays such as `skillpack.local.yaml`

A good smoke covers:

1. `install.sh --dry-run --non-interactive ...` in the container.
2. `./aios --home "$HOME" init --root "$HOME/aios" --skills-dir "$HOME/.agents/skills"`.
3. `AIOS_ROOT="$HOME/aios" ./aios --home "$HOME" secret layout init`.
4. request creation/show + intake dry-run.
5. app-owned native index/verify using human-output checks.
6. `./aios --home "$HOME" skillpack list` and `skillpack sync --dry-run`, grepping for the relevant first-party skill entry.
7. dummy metadata/value backend for `secret list/show/verify/sync --dry-run/run` plumbing.
8. project dry-run and public audit.
9. compile Python files with pyc output redirected to `/tmp` if the repo is mounted read-only.

## Common test-environment pitfalls

- If the container repo is a tar copy without `.git`, `scripts/audit_public.py` will fail because it uses `git ls-files`. Either initialize a temporary git repo and `git add .`, or run the audit in a real checkout.
- If the repo is bind-mounted from the host, Git inside the container may reject it as dubious ownership. Run `git config --global --add safe.directory /repo` inside the container.
- If the repo is read-only, normal `python3 -m py_compile` may fail writing `__pycache__`; use `py_compile.compile(src, cfile='/tmp/name.pyc', doraise=True)`.
- `skillpack.local.yaml` can include machine-specific first-party skills that do not exist in fresh HOME. Exclude it for public clean-room distribution tests.
- Some `aios secret` commands emit human-readable text, not JSON; do not pipe every command into `python3 -m json.tool`.

## Minimal assertion pattern

- grep `aios-secret-management` in `skillpack list` and `skillpack sync --dry-run` output when testing Secret skill distribution.
- assert `source_values_read: false` for GitHub sync dry-runs.
- assert `secret_values_exposed: false` for intake/verify outputs.
- for `secret run`, print only a non-sensitive field and a boolean such as `api_key_set=True`, not the value.

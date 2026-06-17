# aios-kit

Portable scaffolding for a personal AIOS / digital-twin operating environment.

`aios-kit` is the **main control and assembly repository**. A skillpack is only one module inside it.

It manages reusable/public parts:

- curated agent skills (`skillpack.yaml` + optional ignored `skillpack.local.yaml`);
- first-party skill development patterns;
- local asset manifests using committed examples + ignored local overrides;
- Resource Registry / Context Resolver architecture for AIOS;
- thin, auditable sync scripts that call existing tools instead of replacing them.

## Layers

| Layer | Example path | Git truth source? | Purpose |
|---|---|---:|---|
| Source / assembly | `~/projects/aios-kit` | Yes | Manifests, scripts, docs, reusable templates |
| Independent project source | `~/projects/lins-living-loop`, `~/projects/aiops-vault-template` | Yes | Independently published projects used by the kit |
| Real assets | `~/ai-ops` | No | Live operational facts, logs, resource registry, secret locations |
| Runtime skills | `~/.agents/skills`, `~/.hermes/skills` | No | What agents actually load |
| Local state | `~/.agents/skillpacks/state/aios-kit` | No | What this kit installed/linked and can safely prune |

## Quick start

```bash
cd ~/projects/aios-kit
./aios doctor
./aios skillpack list
./aios skillpack sync --dry-run
```

Optional author-local overlay files are ignored by Git:

```text
skillpack.local.yaml
manifests/local-assets.local.json
```

## Important boundaries

- `~/ai-ops` is the live operational vault. Do **not** copy it into this repo.
- `aiops-vault-template` is the reusable public template. Keep it separate from the live vault.
- Runtime skill directories are install targets, not source-of-truth by default.
- For first-party skills you actively iterate, use symlinks from runtime dirs to Git worktrees so `git status` catches changes.
- External skills remain sourced from their upstream repositories through `npx skills`.
- Public repo content should be examples/schemas/templates/docs only; machine-specific paths belong in ignored local overlays.

## Architecture docs

- [`docs/aios-resource-architecture.md`](docs/aios-resource-architecture.md)
- [`docs/security-and-privacy.md`](docs/security-and-privacy.md)
- [`docs/local-structure.md`](docs/local-structure.md)
- [`docs/authoring.md`](docs/authoring.md)

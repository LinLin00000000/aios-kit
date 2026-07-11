---
name: aios-resource-resolver
description: Resolve user-mentioned AIOS resources—projects, devices, services, data assets, workflows, skills, vaults—through registries and aliases before searching blindly. Facts live in registries; this skill only defines the lookup and permission workflow.
version: 0.1.2
author: Lin
license: MIT
---

# AIOS Resource Resolver

Use this skill when the user refers to a project, repo, service, device, vault, data asset, workflow, skill, or ambiguous personal resource such as “LLL 项目”, “那个 bot”, “Windows 边缘节点”, “OPS vault”, “数字花园”, or “之前那个 GitHub 项目”.

## Principle

```text
Skill = how to resolve and act
Registry = what exists and where it lives
```

Do not store large project/resource facts in this skill.

## Lookup order

1. Locate the active AIOS registry root:
   - local/private project truth source: `~/aios/vault/ops/projects/`;
   - explicit personal-data Source records: `~/aios/vault/ops/sources/`;
   - public examples only: `registries/*.example.*` inside `aios-kit`.
2. Read `registry.jsonl` and `aliases.yaml` if available.
3. Match against `id`, `name`, `aliases`, GitHub repo name, local path basename, and notes.
4. If there is exactly one match, resolve to its canonical `id`.
5. Prefer permitted local locations for inspection; use GitHub/remote/device locations only when local is missing or the resource lives elsewhere.
6. Respect permissions:
   - `agent_write: ask-first` means ask before editing;
   - `agent_write: read-only` means inspect only;
   - `external_model: no` means do not send substantive private contents to external models/tools;
   - sensitive/private resources should not be published or copied into public repos.
7. If multiple resources match, show the top candidates and ask the user to choose.
8. If no registry exists or no match is found, then use targeted discovery; do not start with full-disk search.

## AIOS kit commands

When `aios-kit` is available locally, use its CLI instead of hand-editing instance files unless the CLI is missing or broken.

Common instance commands:

```bash
cd ~/aios/modules/aios-kit  # friend/new-machine install
# or: cd ~/projects/aios-kit  # Lin's author machine

./aios status
./aios doctor
./aios update
./aios update --dry-run
./aios update modules
./aios update modules lins-living-loop
./aios update skills
./aios update ops
```

Skillpack commands are lower-level manifest reconciliation tools. Prefer `./aios update skills` for normal skill refreshes; use these when debugging or changing the pack itself:

```bash
./aios skillpack list
./aios skillpack sync --dry-run
./aios skillpack sync --apply
./aios skillpack dev-link --apply  # author/dev only: symlink first-party skills one-by-one
```

External skill installs use the `skills` CLI under the hood, shaped like:

```bash
npx --yes skills@latest add <repo-or-url> --skill <skill> -g -y --agent universal --copy
```

Important boundaries:

- AIOS does not symlink the whole `~/.agents/skills` directory.
- Friends/Windows default to copy.
- Lin's dev machine may use per-skill symlinks for first-party/modified skills.
- `~/aios/modules/*` are updateable source/template checkouts; runtime skills are still loaded from `~/.agents/skills` or `~/.hermes/skills`.

## AIOS project registry commands

When `aios-kit` is available locally, use its CLI instead of hand-editing the registry unless the CLI is missing or broken.

Common commands:

```bash
cd ~/aios/modules/aios-kit  # friend/new-machine install
# or: cd ~/projects/aios-kit  # Lin's author machine

./aios status
./aios project list
./aios project get <id-or-alias>
./aios project add --id <id> --name "<name>" --path <path> --github <url> --alias <alias> --role <role>
./aios project alias <alias> <id>
./aios project validate
```

Example:

```bash
./aios project add \
  --id aios-kit \
  --name "AIOS Kit" \
  --path ~/aios/modules/aios-kit \
  --github https://github.com/LinLin00000000/aios-kit \
  --alias kit \
  --role distribution-hub
```

The registry files are still the truth source:

```text
~/aios/vault/ops/projects/registry.jsonl
~/aios/vault/ops/projects/aliases.yaml
```

## Updating the registry

A Project record requires a durable project identity and its own execution/source lifecycle. Do not promote a module nested inside another registered project, a one-off report, an absorbed research package, or an archive directory merely because it has a path. Keep modules under the owning Project and keep research/design assets in the appropriate docs, vault asset, Worksite, or archive boundary.

When a stable new project/resource fact is discovered:

1. Prefer `./aios project add ...` or `./aios project alias ...`.
2. Run `./aios project validate`.
3. If the resource belongs to the private/live instance, keep it in `~/aios/vault/ops/projects/` and do not copy it into public repo examples.
4. If it is a reusable public example/schema, update `aios-kit/registries/` instead.

Do not put project facts in this skill unless they are reusable lookup rules.

## AIOS Source view commands

Use this existing resolver skill rather than creating a separate skill merely for data lookup. The CLI is the deterministic actuator; natural-language intent remains the normal human interface.

```bash
cd ~/projects/aios-kit
./aios source list --json
./aios source get <id-or-alias>
./aios source add --id <id> --name "<name>" --kind data_root --path <path> \
  --access-mode read_only_reference --sync-mode device_authoritative_mirror \
  --backup-status planned --sensitivity private
./aios source validate
```

`source list` compiles explicit Source records together with Project Registry projections. Do not duplicate a Project's local/GitHub locations in the explicit Source Registry. An inventory/index is derived evidence, not authority; visibility/indexing never grants write permission.

## Output shape

For ordinary users, report the resolution in plain language first: what was found or saved, whether the original changed, where/how it can be found, and whether the action is reversible. Do not expose canonical ids, Source/Registry/Managed Zone vocabulary, permission enums, or projection mechanics unless the user asks for technical detail or needs them to make a real risk/authority decision.

For nontrivial technical resolutions or advanced/audit views, report:

- canonical id;
- matched aliases/evidence;
- chosen location and device;
- permission boundary;
- next action.

# aios-kit

Portable scaffolding for a personal AIOS / digital-twin operating environment.

`aios-kit` is currently the **AIOS distribution and install hub**: it assembles a small set of core modules into a deployed AIOS instance. It may evolve toward a broader AIOS core monorepo later, but live private instance state stays outside the public repo.

Its current job is simple:

- create a unified local AIOS instance root, defaulting to `~/aios`;
- install/sync a portable agent skill pack into the instance;
- include first-party core skills such as `aios-resource-resolver` and `lins-living-loop`;
- bootstrap a fresh OPS vault from `aiops-vault-template` for a friend/new machine;
- create a minimal project registry for resource/project resolution;
- keep public examples, scripts, docs, and install flow in one Git-managed place;
- point to private/live resources without copying them into the public repo.

## Friend install: one command

Remote one-liner:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

More auditable flow:

```bash
curl -fsSLo /tmp/aios-kit-install.sh https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh
bash /tmp/aios-kit-install.sh
```

Clone-and-run flow:

```bash
git clone https://github.com/LinLin00000000/aios-kit.git ~/aios/modules/aios-kit
bash ~/aios/modules/aios-kit/install.sh
```

What this does by default:

1. creates a unified AIOS instance root at `~/aios`;
2. clones/updates `aios-kit` under `~/aios/modules/aios-kit`;
3. initializes instance directories such as `vault/ops`, `work`, `skills`, `modules`, `config`, `state`, `logs`, and `cache`;
4. creates compatibility symlinks when safe:
   - `~/ai-ops -> ~/aios/vault/ops`;
   - `~/lll-work -> ~/aios/work`;
   - `~/.agents/skills -> ~/aios/skills`;
5. runs `aios skillpack sync --apply --mode copy --target universal`;
6. installs skills into `~/aios/skills`;
7. clones/updates `aiops-vault-template` under `~/aios/modules/aiops-vault-template`;
8. creates/updates the OPS vault at `~/aios/vault/ops` using the public template installer;
9. creates a minimal project registry at `~/aios/vault/ops/projects/`;
10. runs validation checks.

Useful installer options:

```bash
bash install.sh --dry-run                 # show actions only
bash install.sh --root ~/my-aios          # choose a different AIOS instance root
bash install.sh --no-aiops                # install instance + skills only, skip OPS vault template
bash install.sh --vault ~/my-aios/vault/ops # choose a different OPS vault path
bash install.sh --skills-dir ~/my-aios/skills # choose a different universal skills path
bash install.sh --target hermes           # install skills for Hermes profile skills dir
bash install.sh --target both             # install universal + Hermes targets
bash install.sh --mode symlink            # author/dev mode only; friends should use copy
```

## Deployed instance layout

Default friend/new-machine instance:

```text
~/aios/
  README.md
  config/
    instance.yaml
  vault/
    ops/                    # current OPS / operational asset vault
      resources.md
      maintenance-log.jsonl
      secrets-location.md
      projects/
        README.md
        registry.jsonl
        aliases.yaml
  work/                     # LLL / agent workdirs; legacy ~/lll-work may point here
  skills/                   # runtime skills; legacy ~/.agents/skills may point here
  modules/                  # reusable module checkouts, including aios-kit and templates
  state/                    # local install/runtime state
  logs/
  cache/
```

Compatibility paths:

```text
~/ai-ops   -> ~/aios/vault/ops
~/lll-work -> ~/aios/work
```

The compatibility links are created only when the legacy path does not already exist. The installer refuses to overwrite an existing real directory/file so it does not destroy private user state.

## What gets installed today?

### Skill pack

Portable base skills in `skillpack.yaml`:

- document/productivity: `docx`, `pptx`, `xlsx`, `pdf`;
- discovery/authoring: `find-skills`, `skill-creator`, `awesome-mcp-servers-discovery`, `github-repo-search`;
- first-party AIOS core skills:
  - `aios-resource-resolver` from this repo;
  - `lins-living-loop` from its independent repo `LinLin00000000/lins-living-loop`.

For now, `lins-living-loop` is a default-installed core package. It does **not** need to physically live inside `aios-kit` to be part of the install flow.

### OPS vault

`install.sh` installs a new OPS vault at `~/aios/vault/ops` from the public `aiops-vault-template`.

It does **not** copy Lin's private live OPS vault into a friend's machine. A friend's vault starts from the reusable template and then gets filled with their own resources.

### Project management / Project Graph MVP

Current state: **minimal project registry implemented, full Project Graph not yet implemented**.

What exists today:

- architecture notes in `docs/aios-resource-architecture.md`;
- public example registries in `registries/`;
- the thin resolver skill `skills/aios-resource-resolver/SKILL.md`;
- installed instance registry at `~/aios/vault/ops/projects/`;
- CLI commands under `aios project ...`.

What does not exist yet:

- a dedicated `project-graph` skill;
- dependency graph/lifecycle automation;
- GitHub issue/PR and LLL workdir linkage.

Keep this simple for now: use `aios-resource-resolver` + the project registry as the umbrella. Split out `project-graph` only after the registry behavior becomes real and repetitive.

## Common commands

From this repo:

```bash
./aios init                            # create/update ~/aios instance layout
./aios status                          # show AIOS root, OPS vault, work, skills, modules, project counts
./aios doctor                          # check instance + skillpack + local asset wiring
./aios skillpack list                  # show enabled skills
./aios skillpack doctor --target both  # validate skill sources and target dirs
./aios skillpack sync --dry-run        # preview install/sync
./aios skillpack sync --apply          # install/update skills
./aios skillpack sync --prune --apply  # remove stale skills managed by this pack
./aios assets doctor                   # check local asset manifest
./aios assets link --apply             # create local discovery symlinks if configured
python3 scripts/audit_public.py        # check tracked public files for obvious leaks
```

For friend deployment:

```bash
bash install.sh
bash install.sh --dry-run
bash install.sh --no-aiops
```

For the installed OPS vault:

```bash
python3 ~/aios/vault/ops/scripts/aiops.py index
python3 ~/aios/vault/ops/scripts/aiops.py check
python3 ~/aios/vault/ops/scripts/aiops.py log --tail 20 --summary
# legacy-compatible if symlink exists:
python3 ~/ai-ops/scripts/aiops.py check
```

For the project registry:

```bash
./aios project list
./aios project add --id aios-kit --name "AIOS Kit" --path ~/aios/modules/aios-kit --github https://github.com/LinLin00000000/aios-kit --alias kit --role distribution-hub
./aios project get aios-kit
./aios project alias lll lins-living-loop
./aios project validate
```

## Author workflow

Use symlinks locally so edits made by agents land in Git-visible worktrees:

```bash
cd ~/projects/aios-kit
./aios skillpack dev-link --apply
./aios doctor
```

Before committing/pushing:

```bash
cd ~/projects/aios-kit
python3 scripts/audit_public.py
./install.sh --dry-run
./aios doctor
git status --short
git diff -- README.md install.sh skillpack.yaml scripts/aios.py skills/aios-resource-resolver/SKILL.md
```

Commit and push kit changes:

```bash
git add README.md install.sh skillpack.yaml scripts/aios.py docs registries skills manifests
git commit -m "feat: add unified AIOS instance root"
git push
```

If the changed skill lives in its own repo, commit that repo separately.

## How to ask an AI to add a future module

Use this wording when you have made or found another module and want it included in the portable install flow:

```text
我做了一个新模块：<模块名>。
本地路径：<path>。
如果它是 skill，请把它加入 aios-kit 的 skillpack；如果它是模板/脚本/项目，请加入 aios-kit 的可迁移安装流程或 modules manifest。
要求：不要复制我的私有数据或密钥；更新 README 的安装/更新命令；运行 dry-run、doctor、smoke install 和 public audit；如果通过就帮我 commit 并 git push。
```

Decision rule:

- reusable skill → add to `skillpack.yaml` or a separate first-party repo entry;
- friend/new-machine vault starter → add to `aiops-vault-template` and make `install.sh` call it;
- live private facts → keep in the deployed instance vault, e.g. `~/aios/vault/ops`, do not publish;
- project/resource index → keep as local registry in `~/aios/vault/ops/projects/`; public repo only carries examples/schemas/docs;
- modules with independent lifecycle → keep separate repos and register/install them through `aios-kit` until repeated cross-repo atomic changes justify a monorepo.

## Layers

| Layer | Example path | Git truth source? | Purpose |
|---|---|---:|---|
| Distribution / assembly | `~/projects/aios-kit` or `~/aios/modules/aios-kit` | Yes | Installer, manifests, CLI, docs, reusable examples |
| Independent module source | `~/projects/lins-living-loop`, `~/projects/aiops-vault-template` | Yes | Independently published core packages used by the distribution |
| Deployed instance root | `~/aios` | No | One local AIOS instance boundary |
| OPS vault / live facts | `~/aios/vault/ops` | No | Live operational facts, logs, secret locations, resource/project registry |
| Work memory | `~/aios/work` | No | LLL/agent workdirs and recoverable task traces |
| Runtime skills | `~/aios/skills`, `~/.hermes/skills` | No | What agents actually load |
| Local state | `~/aios/state`, `~/aios/vault/ops/state/aios-kit` | No | Runtime/install state and safe pruning metadata |

## Important boundaries

- `~/aios` is the deployed local instance root. Do **not** commit it wholesale into this public repo.
- `~/aios/vault/ops` is the live OPS vault. Do **not** copy private facts into this repo.
- `aiops-vault-template` is the reusable public template. Keep it separate from live instance data.
- Runtime skill directories are instance capability state, not source-of-truth by default.
- For first-party skills you actively iterate, use symlinks from runtime dirs to Git worktrees so `git status` catches changes.
- External skills remain sourced from their upstream repositories through `npx skills`.
- Public repo content should be examples/schemas/templates/docs only; machine-specific paths belong in ignored local overlays.

## Architecture docs

- [`docs/aios-resource-architecture.md`](docs/aios-resource-architecture.md)
- [`docs/security-and-privacy.md`](docs/security-and-privacy.md)
- [`docs/local-structure.md`](docs/local-structure.md)
- [`docs/authoring.md`](docs/authoring.md)

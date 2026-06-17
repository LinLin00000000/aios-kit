# aios-kit

Portable scaffolding for a personal AIOS / digital-twin operating environment.

`aios-kit` is the **main control and assembly repository**. It is not the whole AIOS, and it should not swallow every related project into one folder.

Its current job is simple:

- install/sync a portable agent skill pack;
- include first-party skills such as `aios-resource-resolver` and `lins-living-loop` by reference;
- bootstrap a fresh `~/ai-ops` vault from `aiops-vault-template` for a friend/new machine;
- keep public examples, scripts, docs, and install flow in one Git-managed place;
- point to private/live resources without copying them into the public repo.

## Friend install: one command

After cloning this repo:

```bash
git clone https://github.com/LinLin00000000/aios-kit.git ~/.agents/skillpacks/aios-kit
bash ~/.agents/skillpacks/aios-kit/install.sh
```

After `install.sh` is available on GitHub, a remote one-liner can be used:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

What this does by default:

1. clones/updates `aios-kit` under `~/.agents/skillpacks/aios-kit`;
2. runs `aios skillpack sync --apply --mode copy --target universal`;
3. installs the skills into `~/.agents/skills`;
4. clones/updates `aiops-vault-template` under `~/.agents/templates/aiops-vault-template`;
5. creates/updates `~/ai-ops` using the template installer;
6. runs validation checks.

Useful installer options:

```bash
bash install.sh --dry-run                 # show actions only
bash install.sh --no-aiops                # install skills only, skip ~/ai-ops
bash install.sh --vault ~/my-ai-ops       # choose a different AIOps vault path
bash install.sh --target hermes           # install skills for Hermes profile skills dir
bash install.sh --target both             # install universal + Hermes targets
bash install.sh --mode symlink            # author/dev mode only; friends should use copy
```

## What gets installed today?

### Skill pack

Portable base skills in `skillpack.yaml`:

- document/productivity: `docx`, `pptx`, `xlsx`, `pdf`;
- discovery/authoring: `find-skills`, `skill-creator`, `awesome-mcp-servers-discovery`, `github-repo-search`;
- first-party AIOS skills:
  - `aios-resource-resolver` from this repo;
  - `lins-living-loop` from its independent repo `LinLin00000000/lins-living-loop`.

Important: `lins-living-loop` does **not** need to live inside `aios-kit` to be part of the install flow. `aios-kit` treats it as an independent first-party project and installs it through the skillpack manifest.

### AIOps vault

`install.sh` installs a new `~/ai-ops` from the public `aiops-vault-template`.

It does **not** copy Lin's private live `~/ai-ops` into a friend's machine. A friend's vault starts from the reusable template and then gets filled with their own resources.

### Project management / Project Graph

Current state: **not a full deployed module yet**.

What exists today:

- architecture notes in `docs/aios-resource-architecture.md`;
- public example registries in `registries/`;
- the thin resolver skill `skills/aios-resource-resolver/SKILL.md`.

What does not exist yet:

- a real `~/ai-ops/projects/registry.jsonl` installer step;
- a dedicated `project-graph` skill;
- a full project-management CLI/module.

Keep this simple for now: use `aios-resource-resolver` as the umbrella skill. Split out `project-graph` only after the registry behavior becomes real and repetitive.

## Common commands

From this repo:

```bash
./aios doctor                         # check skillpack + local asset wiring
./aios skillpack list                 # show enabled skills
./aios skillpack doctor --target both # validate skill sources and target dirs
./aios skillpack sync --dry-run       # preview install/sync
./aios skillpack sync --apply         # install/update skills
./aios skillpack sync --prune --apply # remove stale skills managed by this pack
./aios assets doctor                  # check local asset manifest
./aios assets link --apply            # create local discovery symlinks if configured
python3 scripts/audit_public.py       # check tracked public files for obvious leaks
```

For friend deployment:

```bash
bash install.sh
bash install.sh --dry-run
bash install.sh --no-aiops
```

For the installed AIOps vault:

```bash
python3 ~/ai-ops/scripts/aiops.py index
python3 ~/ai-ops/scripts/aiops.py check
python3 ~/ai-ops/scripts/aiops.py log --tail 20 --summary
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
git diff -- README.md install.sh skillpack.yaml scripts/aios.py
```

Commit and push kit changes:

```bash
git add README.md install.sh skillpack.yaml scripts/aios.py docs registries skills manifests
git commit -m "feat: simplify friend install flow"
git push
```

If the changed skill lives in its own repo, commit that repo separately. Example:

```bash
git -C ~/projects/lins-living-loop status
git -C ~/projects/lins-living-loop add SKILL.md references/
git -C ~/projects/lins-living-loop commit -m "improve LLL skill"
git -C ~/projects/lins-living-loop push
```

## How to ask an AI to add a future module

Use this wording when you have made or found another module and want it included in the portable install flow:

```text
我做了一个新模块：<模块名>。
本地路径：<path>。
如果它是 skill，请把它加入 aios-kit 的 skillpack；如果它是模板/脚本/项目，请加入 aios-kit 的可迁移安装流程。
要求：不要复制我的私有数据或密钥；更新 README 的安装/更新命令；运行 dry-run、doctor 和 public audit；如果通过就帮我 commit 并 git push。
```

Decision rule:

- reusable skill → add to `skillpack.yaml` or a separate first-party repo entry;
- friend/new-machine vault starter → add to `aiops-vault-template` and make `install.sh` call it;
- live private facts → keep in `~/ai-ops`, do not publish;
- project/resource index → start as registry examples, later promote to `~/ai-ops/projects/registry.jsonl` when actually used.

## Layers

| Layer | Example path | Git truth source? | Purpose |
|---|---|---:|---|
| Source / assembly | `~/projects/aios-kit` | Yes | Manifests, scripts, docs, reusable templates |
| Independent project source | `~/projects/lins-living-loop`, `~/projects/aiops-vault-template` | Yes | Independently published projects used by the kit |
| Real assets | `~/ai-ops` | No | Live operational facts, logs, resource registry, secret locations |
| Runtime skills | `~/.agents/skills`, `~/.hermes/skills` | No | What agents actually load |
| Local state | `~/.agents/skillpacks/state/aios-kit` | No | What this kit installed/linked and can safely prune |

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

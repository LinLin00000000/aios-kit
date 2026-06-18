# aios-kit

Portable scaffolding for a personal AIOS / digital-twin operating environment.

`aios-kit` 现在的定位是 **AIOS distribution / install hub（分发与安装中枢）**：它不试图把所有东西塞进一个仓库，而是把一组精选 skills、OPS vault 模板、LLL 工作流和最小项目 registry 装配成一个可迁移的本地 AIOS 实例。

## 核心原则

- `~/aios` 是 AIOS 实例根目录：放本机的 vault、work、modules、state、logs、cache。
- Agent 真正加载的 skills 仍放在 Agent 自己的真实目录中，例如 `~/.agents/skills` 或 Hermes profile 的 `~/.hermes/skills`。
- `aios-kit` 只逐个安装/复制/软链接它管理的 skill，不接管整个 `~/.agents/skills` 目录。
- 默认给朋友安装用 `copy`，跨 Linux / Windows 更稳；作者本机开发 first-party skill 时可用逐个 `symlink`。
- 公开安装默认不创建历史兼容软链接；`~/ai-ops`、`~/lll-work` 这类兼容链接只适合作者本机迁移时手动处理。
- 私有 live state 不进入公开仓库；公开仓库只放安装器、manifest、模板、示例和文档。

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
3. clones/updates `lins-living-loop` under `~/aios/modules/lins-living-loop`;
4. initializes instance directories such as `vault/ops`, `work`, `skills`, `modules`, `config`, `state`, `logs`, and `cache`;
5. installs only the selected skills one-by-one into the real agent skills directory, defaulting to `~/.agents/skills`;
6. does **not** symlink the whole `~/.agents/skills` directory;
7. clones/updates `aiops-vault-template` under `~/aios/modules/aiops-vault-template`;
8. creates/updates the OPS vault at `~/aios/vault/ops` using the public template installer;
9. creates a minimal project registry at `~/aios/vault/ops/projects/`;
10. runs validation checks.

Useful installer options:

```bash
bash install.sh --dry-run                    # show actions only
bash install.sh --root ~/my-aios             # choose a different AIOS instance root
bash install.sh --lll-dir ~/my-aios/modules/lins-living-loop # choose LLL module checkout path
bash install.sh --no-aiops                   # install instance + skills only, skip OPS vault template
bash install.sh --vault ~/my-aios/vault/ops  # choose a different OPS vault path
bash install.sh --skills-dir ~/.agents/skills # choose agent runtime skills path
bash install.sh --target universal           # install universal agent skills, default
bash install.sh --target hermes              # install skills for Hermes profile skills dir
bash install.sh --target both                # install universal + Hermes targets
bash install.sh --mode copy                  # default; best for friends / Windows / stable installs
bash install.sh --mode symlink               # author/dev mode only; links individual first-party skills
```

## Naming: what does `kit` mean?

`aios-kit` 中的 `kit` 指“安装套件 / 分发套件”，不是说它只是一个随手工具包。

更准确地说：

```text
AIOS = deployed instance + conventions + selected modules/skills
aios-kit = AIOS distribution/install component
```

所以 `aios-kit` 是 AIOS 的一个核心组件：它负责安装、更新、装配和记录，不负责承载所有 live 私有数据。

## `AIOS_ROOT` and paths

`AIOS_ROOT=~/aios` is an optional install-time override, not something the user must export permanently.

The installer derives paths from it:

```text
AIOS_ROOT=~/aios
OPS vault = ~/aios/vault/ops
work      = ~/aios/work
skills    = ~/aios/skills        # AIOS skill metadata/cache area, not the whole agent skills dir
modules   = ~/aios/modules       # reusable component checkouts/templates
```

Agent runtime skills are separate:

```text
universal skills = ~/.agents/skills/<skill>
Hermes skills    = ~/.hermes/skills/<category>/<skill> or ~/.hermes/skills/<skill>
```

`modules/` means “AIOS needs these reusable components to install/update itself”, for example:

```text
~/aios/modules/aios-kit
~/aios/modules/aiops-vault-template
~/aios/modules/lins-living-loop
```

If this name feels too abstract later, it can be renamed, but for now it gives us a clean place for updateable source/template checkouts without mixing them into live vault data.

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
  work/                     # LLL / agent workdirs for this AIOS instance
  skills/                   # AIOS skill metadata/cache, not the agent runtime dir
  modules/                  # reusable module checkouts, including aios-kit and templates
  state/                    # local install/runtime state
  logs/
  cache/
```

Compatibility paths such as below are **not public-install defaults**:

```text
~/ai-ops   -> ~/aios/vault/ops
~/lll-work -> ~/aios/work
```

They are local migration choices for Lin's own machine or an advanced user who explicitly wants legacy path compatibility.

## What gets installed today?

### Skill pack

Portable base skills in `skillpack.yaml`:

- document/productivity: `docx`, `pptx`, `xlsx`, `pdf`;
- discovery/authoring: `find-skills`, `skill-creator`, `awesome-mcp-servers-discovery`;
- design/frontend: `frontend-design`, `ui-ux-pro-max`, `vercel-composition-patterns`, `web-design-guidelines`;
- first-party AIOS-managed skills:
  - `aios-resource-resolver` from this repo;
  - `github-repo-search` from this repo (Lin-customized version);
  - `lins-living-loop` from its independent repo `LinLin00000000/lins-living-loop`.

For now, `lins-living-loop` is a default-installed core package. It lives as an independent module checkout under `~/aios/modules/lins-living-loop` on installed machines, and it does **not** need to physically live inside `aios-kit` to be part of the install/update flow.

### Skill install/update strategy

| Skill kind | Friend / Windows default | Lin's dev machine | Update path |
|---|---|---|---|
| external curated skills | copy/install via `npx skills` | copy/install via `npx skills` | `./aios update` or `./aios skillpack sync --apply`; upstream handled by skills CLI |
| first-party stable skills | copy from `~/aios/modules/*` or `aios-kit/skills/*` into real agent skills dir | optional symlink per skill | `./aios update`; module git pull + skill sync |
| active first-party development | copy unless user asks otherwise | symlink `~/.agents/skills/<skill>` -> Git worktree | edit repo, commit/push, rerun doctor |
| OPS skills | installed by `aiops-vault-template` installer | symlink to `~/projects/aiops-vault-template` on Lin's machine | module update + template reinstall/symlink |

Important: AIOS does **not** replace the whole `~/.agents/skills` directory. It only manages the skills recorded in its install state.

### OPS vault

`install.sh` installs a new OPS vault at `~/aios/vault/ops` from the public `aiops-vault-template`.

The OPS template also installs two operation skills into the real agent skills directory:

- `aiops-vault`;
- `aiops-service-operations`.

So a default AIOS friend deployment currently installs 16 portable skills total: 14 from `skillpack.yaml` plus these 2 OPS skills.

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
./aios status                          # show AIOS root, OPS vault, work, runtime skills, modules, project counts
./aios doctor                          # check instance + skillpack + local asset wiring
./aios update                          # git-pull modules, reinstall/update managed skills, refresh OPS template
./aios update --dry-run                # preview update actions
python3 scripts/audit_public.py        # check tracked public files for obvious leaks
```

Skillpack:

```bash
./aios skillpack list                  # show enabled skills
./aios skillpack doctor --target universal
./aios skillpack sync --dry-run        # preview install/sync
./aios skillpack sync --apply          # install/update managed skills
./aios skillpack sync --prune --apply  # remove stale skills managed by this pack
./aios skillpack dev-link --apply      # dev only: symlink first-party skills one-by-one

# Under the hood, external skills use commands like:
npx --yes skills@latest add <repo-or-url> --skill <skill> -g -y --agent universal --copy
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
```

For the project registry:

```bash
./aios project list
./aios project add --id aios-kit --name "AIOS Kit" --path ~/aios/modules/aios-kit --github https://github.com/LinLin00000000/aios-kit --alias kit --role distribution-hub
./aios project get aios-kit
./aios project alias lll lins-living-loop
./aios project validate
```

Local assets:

```bash
./aios assets doctor
./aios assets link --apply
```

## Author workflow

Use one-by-one symlinks locally for first-party skills you actively edit, so edits made by agents land in Git-visible worktrees:

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
git diff -- README.md install.sh skillpack.yaml scripts/aios.py skills/aios-resource-resolver/SKILL.md skills/github-repo-search/SKILL.md
```

Commit and push kit changes:

```bash
git add README.md install.sh skillpack.yaml scripts/aios.py docs registries skills manifests
git commit -m "feat: add AIOS skill update flow"
git push
```

If the changed skill lives in its own repo, commit that repo separately.

## How to update skills later

To update the AIOS modules and curated skill set on a machine:

```bash
cd ~/aios/modules/aios-kit  # or ~/projects/aios-kit on Lin's machine
./aios update
./aios doctor
```

`aios update` does three things:

1. runs `git pull --ff-only` for Git modules under `~/aios/modules/*`;
2. re-runs the OPS vault template installer when `aiops-vault-template` is present;
3. re-runs `aios skillpack sync --apply`, so external skills are refreshed through `npx skills` and first-party skills are copied/symlinked again according to the manifest.

If you want to do it manually:

```bash
cd ~/aios/modules/aios-kit
git pull --ff-only
git -C ~/aios/modules/lins-living-loop pull --ff-only
git -C ~/aios/modules/aiops-vault-template pull --ff-only
./aios skillpack sync --apply
./aios doctor
```

To add a new selected skill to the AIOS install flow:

1. add it to `skillpack.yaml`;
2. document why it belongs in the portable base pack;
3. run `./aios skillpack sync --dry-run`;
4. run a fresh temp-HOME smoke install before publishing;
5. commit and push.

## How to ask an AI to add a future module

Use this wording when you have made or found another module and want it included in the portable install flow:

```text
我做了一个新模块：<模块名>。
本地路径：<path>。
如果它是 skill，请把它加入 aios-kit 的 skillpack；如果它是模板/脚本/项目，请加入 aios-kit 的可迁移安装流程或 modules manifest。
要求：不要复制我的私有数据或密钥；不要接管朋友已有的整个 skills 目录；更新 README 的安装/更新命令和相关 skill 的操作范例；运行 dry-run、doctor、smoke install 和 public audit；如果通过就帮我 commit 并 git push。
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
| Independent module source | `~/projects/lins-living-loop`, `~/projects/aiops-vault-template` or installed `~/aios/modules/*` checkouts | Yes | Independently published core packages used by the distribution |
| Deployed instance root | `~/aios` | No | One local AIOS instance boundary |
| OPS vault / live facts | `~/aios/vault/ops` | No | Live operational facts, logs, secret locations, resource/project registry |
| Work memory | `~/aios/work` | No | LLL/agent workdirs and recoverable task traces |
| Agent runtime skills | `~/.agents/skills`, `~/.hermes/skills` | No | What agents actually load |
| AIOS skill metadata/cache | `~/aios/skills` | No | AIOS-local skill notes/cache/state; not the runtime directory by default |
| Local state | `~/aios/state`, `~/aios/vault/ops/state/aios-kit` | No | Runtime/install state and safe pruning metadata |

## Important boundaries

- `~/aios` is the deployed local instance root. Do **not** commit it wholesale into this public repo.
- `~/aios/vault/ops` is the live OPS vault. Do **not** copy private facts into this repo.
- `aiops-vault-template` is the reusable public template. Keep it separate from live instance data.
- Runtime skill directories are instance capability state, not source-of-truth by default.
- For first-party skills you actively iterate, use one-by-one symlinks from runtime dirs to Git worktrees so `git status` catches changes.
- External skills remain sourced from their upstream repositories through `npx skills`.
- Public repo content should be examples/schemas/templates/docs only; machine-specific paths belong in ignored local overlays.

## Architecture docs

- [`docs/aios-resource-architecture.md`](docs/aios-resource-architecture.md)
- [`docs/security-and-privacy.md`](docs/security-and-privacy.md)
- [`docs/local-structure.md`](docs/local-structure.md)
- [`docs/authoring.md`](docs/authoring.md)

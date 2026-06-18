# aios-kit

**中文**：`aios-kit` 是一个轻量、可迁移的 Personal AIOS 安装与分发套件。它把精选 Agent skills、LLL 工作流、OPS vault 模板、项目注册表和本地实例目录组织成一个可以在新机器上快速部署的 AIOS 基础环境。

**English**: `aios-kit` is a lightweight, portable installation and distribution kit for a Personal AIOS. It assembles curated agent skills, the LLL workflow, an OPS vault template, a project registry, and a local instance layout into a deployable AIOS base environment.

---

## What it installs / 安装内容

**中文**：默认安装会创建一个统一的本地 AIOS 实例根目录：

**English**: The default install creates a unified local AIOS instance root:

```text
~/aios/
  bin/                     # aios command shim
  config/                  # instance configuration
  vault/ops/               # operational vault initialized from aiops-vault-template
  work/                    # LLL / agent work directories
  skills/                  # AIOS skill metadata/cache, not the runtime skills dir
  modules/                 # updateable module checkouts
  state/
  logs/
  cache/
```

**中文**：Agent 真正加载的 skills 仍然安装在 Agent 自己的 runtime skills 目录，例如 `~/.agents/skills` 或 Hermes profile 的 `~/.hermes/skills`。`aios-kit` 只逐个安装它管理的 skills，不接管整个 skills 目录。

**English**: Agent-loadable skills are still installed into the agent's real runtime skills directory, such as `~/.agents/skills` or a Hermes profile's `~/.hermes/skills`. `aios-kit` installs only the selected managed skills one by one; it does not take over the whole skills directory.

---

## Quick install / 快速安装

**中文**：一行安装：

**English**: One-line install:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

**中文**：更可审计的安装方式：

**English**: More auditable install flow:

```bash
curl -fsSLo /tmp/aios-kit-install.sh https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh
bash /tmp/aios-kit-install.sh
```

**中文**：从 Git 仓库安装：

**English**: Clone-and-run install:

```bash
git clone https://github.com/LinLin00000000/aios-kit.git ~/aios/modules/aios-kit
bash ~/aios/modules/aios-kit/install.sh
```

**中文**：安装后可通过以下路径调用 CLI：

**English**: After installation, the CLI is available at:

```bash
~/aios/bin/aios status
```

**中文**：如果你希望直接运行全局命令 `aios`，可以把 `~/aios/bin` 加入 `PATH`：

**English**: To run `aios` as a global command, add `~/aios/bin` to your `PATH`:

```bash
export PATH="$HOME/aios/bin:$PATH"
aios status
```

**中文**：也可以在安装时安全地链接到已有 PATH 目录，例如 `~/.local/bin`。安装器会拒绝覆盖已有冲突文件。

**English**: You can also link the command into an existing PATH directory such as `~/.local/bin`. The installer refuses to overwrite conflicting files.

```bash
bash install.sh --global-bin ~/.local/bin
```

---

## Installer options / 安装选项

**中文**：常用安装选项：

**English**: Common installer options:

```bash
bash install.sh --dry-run                     # preview actions / 预览操作
bash install.sh --root ~/my-aios              # choose instance root / 指定实例根目录
bash install.sh --no-aiops                    # skip OPS vault template / 跳过 OPS vault 模板
bash install.sh --vault ~/my-aios/vault/ops   # choose OPS vault path / 指定 OPS vault 路径
bash install.sh --skills-dir ~/.agents/skills # choose runtime skills dir / 指定 runtime skills 目录
bash install.sh --target universal            # default target / 默认目标
bash install.sh --target hermes               # install for Hermes / 安装到 Hermes skills
bash install.sh --target both                 # install to both targets / 两边都安装
bash install.sh --mode copy                   # default; best for portable installs / 默认，最适合迁移
bash install.sh --mode symlink                # dev mode for first-party skills / 开发模式
bash install.sh --global-bin ~/.local/bin     # optional global command link / 可选全局命令链接
```

---

## Common commands / 常用命令

**中文**：安装后推荐直接使用 `aios`。如果没有配置 PATH，也可以使用 `~/aios/bin/aios` 或在仓库中运行 `./aios`。

**English**: After installation, use `aios` directly. If PATH is not configured, use `~/aios/bin/aios` or run `./aios` inside the repository.

```bash
aios status                 # show instance summary / 查看实例摘要
aios doctor                 # validate wiring / 检查实例与 skillpack
aios update                 # update modules, OPS template, and managed skills / 全量更新
aios update --dry-run       # preview update / 预览更新
```

**中文**：按类型更新：

**English**: Update by subject:

```bash
aios update modules                         # update all module Git checkouts / 更新全部模块
aios update modules lins-living-loop        # update one module / 只更新某个模块
aios update skills                          # refresh managed runtime skills / 刷新托管 skills
aios update ops                             # refresh OPS vault template / 刷新 OPS vault 模板
```

**中文**：项目注册表命令：

**English**: Project registry commands:

```bash
aios project list
aios project add --id aios-kit --name "AIOS Kit" --path ~/aios/modules/aios-kit --github https://github.com/LinLin00000000/aios-kit --alias kit --role distribution-hub
aios project get aios-kit
aios project alias kit aios-kit
aios project validate
```

**中文**：底层 skillpack 命令适合开发者或调试使用。普通用户通常只需要 `aios update skills`。

**English**: Low-level skillpack commands are mainly for developers and debugging. Most users should use `aios update skills`.

```bash
aios skillpack list
aios skillpack doctor --target universal
aios skillpack sync --dry-run
aios skillpack sync --apply
aios skillpack sync --prune --apply
aios skillpack dev-link --apply       # dev only: symlink first-party skills one by one
```

---

## Modules and skills / 模块与 skills

**中文**：`~/aios/modules` 保存可更新的模块源码或模板 checkout，例如：

**English**: `~/aios/modules` stores updateable module source/template checkouts, for example:

```text
~/aios/modules/aios-kit
~/aios/modules/lins-living-loop
~/aios/modules/aiops-vault-template
```

**中文**：runtime skills 是 Agent 实际加载的能力，通常位于：

**English**: Runtime skills are the capabilities the agent actually loads, usually under:

```text
~/.agents/skills/<skill>
~/.hermes/skills/<skill>
```

**中文**：默认 portable 安装使用 copy，更适合朋友机器、Windows 和稳定环境。first-party 开发可以使用逐个 symlink，让修改直接落在 Git worktree 中。

**English**: Portable installs use copy mode by default, which is safer for friends' machines, Windows, and stable environments. First-party development can use per-skill symlinks so edits land directly in Git worktrees.

---

## Included skills / 内置 skill set

**中文**：`skillpack.yaml` 中的 portable base pack 包括：

**English**: The portable base pack in `skillpack.yaml` includes:

- **Documents / 文档**: `docx`, `pptx`, `xlsx`, `pdf`
- **Skill discovery and authoring / skill 发现与创作**: `find-skills`, `skill-creator`, `awesome-mcp-servers-discovery`
- **Design and frontend / 设计与前端**: `frontend-design`, `ui-ux-pro-max`, `vercel-composition-patterns`, `web-design-guidelines`
- **AIOS first-party / AIOS 第一方**: `aios-resource-resolver`, `github-repo-search`, `lins-living-loop`

**中文**：OPS vault 模板还会安装两个 operation skills：`aiops-vault` 和 `aiops-service-operations`。

**English**: The OPS vault template also installs two operation skills: `aiops-vault` and `aiops-service-operations`.

---

## OPS vault / 运维资料库

**中文**：`aios-kit` 会从公开模板 `aiops-vault-template` 初始化一个新的 OPS vault：

**English**: `aios-kit` initializes a new OPS vault from the public `aiops-vault-template`:

```text
~/aios/vault/ops/
  README.md
  resources.md
  maintenance-log.jsonl
  secrets-location.md
  projects/
  scripts/aiops.py
```

**中文**：它不会复制维护者的私人 live vault。新机器会从模板开始，然后记录自己的资源、服务和维护日志。

**English**: It does not copy the maintainer's private live vault. A new machine starts from the template and records its own resources, services, and maintenance history.

---

## Project registry / 项目注册表

**中文**：当前实现的是最小项目注册表，而不是完整 Project Graph。它适合记录本机 AIOS 需要识别的项目、路径、GitHub URL、别名和角色。

**English**: The current implementation is a minimal project registry, not a full Project Graph. It records projects, paths, GitHub URLs, aliases, and roles that the local AIOS instance needs to resolve.

```text
~/aios/vault/ops/projects/
  registry.jsonl
  aliases.yaml
```

---

## Boundaries / 边界

**中文**：几个重要边界：

**English**: Important boundaries:

- **中文**：`~/aios` 是本机部署实例，不应该整体提交到公开仓库。  
  **English**: `~/aios` is a local deployed instance and should not be committed wholesale.
- **中文**：`~/aios/vault/ops` 是 live operational vault，不应该把私人事实或密钥写进本仓库。  
  **English**: `~/aios/vault/ops` is a live operational vault; private facts and secrets should not be committed here.
- **中文**：`~/.agents/skills` 和 `~/.hermes/skills` 是 Agent runtime 目录，`aios-kit` 不接管整个目录。  
  **English**: `~/.agents/skills` and `~/.hermes/skills` are runtime directories; `aios-kit` does not take them over.
- **中文**：机器专属、本地专属、私有基础设施相关内容应放在 local overlay，而不是 portable base pack。  
  **English**: Machine-specific, local-only, or private-infrastructure-specific assets belong in local overlays, not the portable base pack.

---

## Development / 开发

**中文**：开发、贡献、新增 module/skill、本机 overlay 的规则见：

**English**: Development, contribution, module/skill addition, and local overlay rules are documented in:

- [`docs/development.md`](docs/development.md)
- [`docs/security-and-privacy.md`](docs/security-and-privacy.md)
- [`docs/aios-resource-architecture.md`](docs/aios-resource-architecture.md)

**中文**：发布前建议运行：

**English**: Before publishing, run:

```bash
python3 scripts/audit_public.py
bash install.sh --dry-run
aios update --dry-run
aios doctor
git status --short
```

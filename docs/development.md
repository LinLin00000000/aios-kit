# Development Guide / 开发指南

**中文**：本文档面向维护者、贡献者和后续协作的 AI Agent。公开首页 README 只保留项目介绍、安装和常用命令；新增模块、skill、local overlay 和发布验证规则放在这里。

**English**: This document is for maintainers, contributors, and future collaborating AI agents. The public README stays focused on project introduction, installation, and common commands; module, skill, local overlay, and release validation rules live here.

---

## Product surface rule / 产品表面规则

**中文**：README 是大众入口，不是维护日志、个人解释或决策草稿。只放：项目定位、安装、常用命令、核心目录、边界和开发文档入口。

**English**: README is the public entry point, not a maintenance log, personal explanation, or decision notebook. Keep it to positioning, installation, common commands, core layout, boundaries, and links to developer docs.

**中文**：复杂背景、为什么这么设计、如何新增模块、私有/本机 overlay、AI 协作提示词，放在 `docs/` 或 LLL 工作区报告中。

**English**: Complex background, design rationale, module addition rules, private/local overlays, and AI collaboration prompts belong in `docs/` or LLL workdir reports.

---

## CLI design / CLI 设计

**中文**：CLI 分两层：

**English**: The CLI has two layers:

| Layer | User-facing examples | Purpose |
|---|---|---|
| Product commands / 产品命令 | `aios status`, `aios doctor`, `aios update`, `aios update skills`, `aios update modules lins-living-loop` | Stable commands for normal users |
| Expert subdomains / 专家子域 | `aios skillpack sync --apply`, `aios skillpack dev-link --apply`, `aios assets doctor` | Manifest reconciliation, development, debugging |

**中文**：`skillpack sync` 这个名字是故意保留的，因为它表达的是“按 `skillpack.yaml` 对 runtime skills 做对账/收敛”，不是普通意义上的 update。普通用户入口应优先使用：

**English**: `skillpack sync` is intentionally retained because it means “reconcile runtime skills against `skillpack.yaml`”, not just a generic update. Normal users should prefer:

```bash
aios update skills
```

**中文**：`aios update` 默认等价于 `aios update all`。需要粒度时使用：

**English**: `aios update` defaults to `aios update all`. For finer control:

```bash
aios update modules
aios update modules lins-living-loop
aios update skills
aios update ops
```

**中文**：只有当某个更新对象有独立生命周期、耗时、失败风险或用户明确意图时，才值得成为独立 subject。现在 `modules`、`skills`、`ops` 足够，不要过早拆出更多子命令。

**English**: Add an update subject only when it has an independent lifecycle, runtime cost, failure mode, or user intent. For now, `modules`, `skills`, and `ops` are enough.

---

## Global command installation / 全局命令安装

**中文**：安装器总会创建：

**English**: The installer always creates:

```text
~/aios/bin/aios -> ~/aios/modules/aios-kit/aios
```

**中文**：推荐用户把 `~/aios/bin` 加入 PATH：

**English**: Users are encouraged to add `~/aios/bin` to PATH:

```bash
export PATH="$HOME/aios/bin:$PATH"
```

**中文**：如果用户想直接写入已有 PATH 目录，可使用：

**English**: To link into an existing PATH directory:

```bash
bash install.sh --global-bin ~/.local/bin
```

**中文**：安装器不会覆盖已有冲突的 `~/.local/bin/aios`。

**English**: The installer refuses to overwrite an existing conflicting `~/.local/bin/aios`.

---

## Adding a portable skill / 新增 portable skill

**中文**：适合加入 portable base pack 的 skill 应满足至少一个条件：

**English**: A skill belongs in the portable base pack when it satisfies at least one of these conditions:

- **中文**：大多数 AIOS 用户都会高频需要；  
  **English**: Most AIOS users are likely to need it frequently.
- **中文**：能明显提升安装后默认能力，而且副作用小；  
  **English**: It significantly improves default capability with low side effects.
- **中文**：与 AIOS 核心流程强相关，如 skill discovery、document workflows、LLL、resource/project resolution。  
  **English**: It is strongly related to core AIOS workflows such as skill discovery, document workflows, LLL, or resource/project resolution.

**中文**：步骤：

**English**: Steps:

1. **中文**：把条目加入 `skillpack.yaml`，写清 `source`、`skill`、`reason`。  
   **English**: Add an entry to `skillpack.yaml` with `source`, `skill`, and `reason`.
2. **中文**：运行 dry-run。  
   **English**: Run a dry-run.

   ```bash
   aios skillpack sync --dry-run
   aios update skills --dry-run
   ```

3. **中文**：实际安装并验证。  
   **English**: Install and verify.

   ```bash
   aios update skills
   aios doctor
   ```

4. **中文**：做 fresh HOME smoke install，避免本机已有文件污染结果。  
   **English**: Run a fresh-HOME smoke install to avoid contamination from local state.
5. **中文**：通过 public audit 后 commit/push。  
   **English**: Commit and push after public audit passes.

---

## Adding a first-party skill / 新增 first-party skill

**中文**：如果 skill 是 AIOS 自己维护的，优先选择以下真源位置：

**English**: If the skill is maintained by AIOS, choose one of these truth-source locations:

| Case | Truth source | Runtime install |
|---|---|---|
| Small AIOS-specific skill / 小型 AIOS 专属 skill | `aios-kit/skills/<skill>` | copy for users, symlink for dev |
| Independent product-like skill / 独立产品型 skill | separate repo under `~/aios/modules/<repo>` | copy for users, symlink for dev |
| Subskill inside a template repo / 模板仓库内子 skill | `<repo>/skills/<skill>` | copy for users, symlink for dev |

**中文**：不要把 runtime skills 目录当真源。开发机可以逐个 symlink runtime skill 到 Git worktree，但公开安装默认 copy。

**English**: Do not treat runtime skill directories as the source of truth. Development machines may use per-skill symlinks to Git worktrees, but public installs default to copy mode.

---

## Adding a module / 新增 module

**中文**：module 是 `~/aios/modules/<name>` 下可更新的源码或模板 checkout。适合 module 的对象通常有独立生命周期，例如 LLL、OPS vault template、未来多设备互联模块。

**English**: A module is an updateable source/template checkout under `~/aios/modules/<name>`. Good module candidates have independent lifecycles, such as LLL, the OPS vault template, or a future multi-device connectivity module.

**中文**：新增 module 时考虑：

**English**: When adding a module, decide:

- **中文**：它是公开 portable base，还是本机 local overlay？  
  **English**: Is it part of the portable base or a local overlay?
- **中文**：安装器是否需要 clone 它？  
  **English**: Should the installer clone it?
- **中文**：`aios update modules <name>` 是否足够，还是需要额外 refresh 步骤？  
  **English**: Is `aios update modules <name>` enough, or does it need an extra refresh step?
- **中文**：是否提供 runtime skill？如果有，runtime skill 应 copy/symlink 到哪里？  
  **English**: Does it provide runtime skills? If yes, where should they be copied/symlinked?

**中文**：如果只是单个 skill，不要过早做成 module。先放 `skillpack.yaml` 或 `aios-kit/skills/<skill>`。

**English**: If it is only a single skill, do not turn it into a module too early. Start with `skillpack.yaml` or `aios-kit/skills/<skill>`.

---

## Local overlay policy / 本机 overlay 策略

**中文**：local overlay 用于维护者自己的机器、私有基础设施、中央控制面或实验模块。它们可以属于“Lin 的 AIOS”，但不属于公开 portable base pack。

**English**: Local overlays are for the maintainer's own machines, private infrastructure, central control plane, or experimental modules. They can belong to “Lin's AIOS” without belonging to the public portable base pack.

**中文**：当前 local overlay 示例：

**English**: Current local overlay examples:

| Skill | Location | Why local-only now |
|---|---|---|
| `cloud-server-ssh-assets` | `skillpack.local.yaml` | Bound to Lin's cloud server inventory and SSH/resource conventions |
| `central-agent-control-plane` | `skillpack.local.yaml` / Hermes profile | Bound to Lin's central Hermes/control-plane operations |

**中文**：未来如果多设备互联、中央 Agent、远程执行成为 AIOS 的公开核心能力，应抽象出 portable module/skill，例如 `aios-device-mesh` 或 `aios-control-plane`，并只公开通用流程、schema 和模板，不公开私人资源事实。

**English**: If multi-device connectivity, central agent operations, or remote execution become public AIOS core capabilities, extract a portable module/skill such as `aios-device-mesh` or `aios-control-plane`, publishing only generic workflows, schemas, and templates—not private resource facts.

---

## AIOps skills distinction / AIOps skills 的区别

**中文**：`aiops-vault` 是 OPS vault 的入口/伴随 skill。它定义如何读取 vault、遵守密钥边界、维护 `resources.md`、`maintenance-log.jsonl`、`secrets-location.md` 等。它的 `SKILL.md` 位于 `aiops-vault-template` 仓库根目录，所以开发机 runtime symlink 指向仓库根目录：

**English**: `aiops-vault` is the entry/companion skill for the OPS vault. It defines how to read the vault, respect secret boundaries, and maintain `resources.md`, `maintenance-log.jsonl`, `secrets-location.md`, etc. Its `SKILL.md` lives at the root of the `aiops-vault-template` repository, so the development runtime symlink points to the repository root:

```text
~/.agents/skills/aiops-vault -> ~/projects/aiops-vault-template
```

**中文**：`aiops-service-operations` 是更窄的服务运维 workflow skill，位于模板仓库的子目录：

**English**: `aiops-service-operations` is a narrower service-operations workflow skill located under a subdirectory of the template repo:

```text
~/.agents/skills/aiops-service-operations -> ~/projects/aiops-vault-template/skills/aiops-service-operations
```

---

## How to ask an AI to add a module / 如何让 AI 添加模块

**中文**：可以这样要求：

**English**: You can ask like this:

```text
我做了一个新模块：<模块名>。
本地路径：<path>。
目标：把它纳入 AIOS 的可迁移安装/更新流程。
请判断它应该是 portable base、first-party skill、independent module，还是 local overlay。
要求：不要复制我的私有数据或密钥；不要接管朋友已有的整个 skills 目录；README 只写大众需要的信息；开发规则写到 docs/development.md；运行 dry-run、doctor、public audit、fresh HOME smoke install；通过后 commit 并 push。
```

**English**:

```text
I made a new module: <module name>.
Local path: <path>.
Goal: include it in the portable AIOS install/update flow.
Please decide whether it should be portable base, first-party skill, independent module, or local overlay.
Requirements: do not copy private data or secrets; do not take over an existing whole skills directory; keep README public-facing; put development rules in docs/development.md; run dry-run, doctor, public audit, and fresh-HOME smoke install; commit and push if validation passes.
```

---

## Release checklist / 发布检查清单

**中文**：发布前至少运行：

**English**: Before publishing, run at least:

```bash
bash -n install.sh
python3 -m py_compile scripts/aios.py scripts/audit_public.py
python3 scripts/audit_public.py
aios update --dry-run
aios update skills --dry-run
aios update modules --dry-run
aios doctor
git status --short
```

**中文**：涉及安装器、skillpack、模块 clone、runtime skills 路径时，必须做 fresh HOME smoke install。

**English**: When changing the installer, skillpack, module clone behavior, or runtime skills paths, run a fresh-HOME smoke install.

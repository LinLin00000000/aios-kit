# aios-kit 架构

`aios-kit` 是一个装配/控制仓库，不是把所有资产都吞进来的 monorepo。它的默认形态是 **Agent-first 的上下文工程骨架**：先按当前意图加载最小必要上下文，再把动作交给真正的 owner；只有跨会话、跨任务或安全边界确实需要时，才保留显式事实记录。

## 核心决策

保持独立项目的独立性，用 manifest、module、registry 和本地链接把它们连接起来：

- `aios-kit`：安装器、CLI、公开 manifest、选定的一方 skills 和文档。
- `lins-living-loop`：独立的一方 workflow skill / project。
- `aiops-vault-template`：内置于 `aios-kit/modules/aiops-vault-template` 的公开 OPS vault 模板模块。
- `~/aios/vault/ops`：新 AIOS 实例默认且唯一的 live OPS vault。

## Agent-first / Human fallback

AIOS 的架构假设是：**Agent 是默认操作者，人类是授权者、目标设定者和兜底操作者**。普通用户不需要记住低层命令；低层命令存在，是为了让 Agent 有稳定、可验证、可恢复的执行面。

AIOS 的进一步设计原则是：**管理本身就是上下文工程**。数据资产、服务器、服务资源、云服务、项目、Skill 和行动能力，不默认对应一套传统管理平台；它们首先是不同 owner 提供的分层上下文。Agent 先加载紧凑候选，再按语义选择 owner，最后只在真实动作边界绑定稳定资源和安全事实。

```text
Human Intent
  -> Bootstrap Context
  -> Compact Candidate Context
  -> Agent Semantic Route
  -> Owner Context
  -> Action/Resource Context
  -> Owner Actuator
  -> Minimal State/Evidence
```

精确 ID、路径、remote、版本和 consumer 仍可存在，但它们是最终 binding、幂等和审计句柄，不是用户必须先记住的发现入口。

| 层 | 负责内容 | 典型载体 |
|---|---|---|
| Human Intent | 用户用自然语言表达目标、约束、授权和验收标准 | 对话、确认、偏好 |
| Agent Policy | Agent 判断应该怎么做、是否安全、是否需要询问、用哪个工具 | skills、compact catalog、本地项目上下文、owner 文档、必要时的 registry/vault facts、LLL mission |
| Machine Actuation | 执行确定性动作，尽量可 dry-run、doctor、validate、JSON 化、幂等 | `aios` CLI、owner CLI、scripts、MCP tools、官方 API、文件操作 |
| State/Evidence | 长期事实、变更证据、安装状态、维护记录和可恢复工作上下文 | 只有必要时的 manifest/registry、vault、install-state、logs、LLL workdir |

这不是“把所有东西自动化”的口号，而是具体影响仓库边界和命令设计：

1. **上下文优先，登记从严**：先加载当前意图所需的 compact catalog、项目/服务本地上下文和 owner 文档；只有需要稳定跨任务事实、资源边界或安全回读时才登记对象。
2. **官方能力优先**：新增接入先查官方 CLI、官方 Skill、官方 MCP 和官方文档，再考虑 AIOps service card、薄引导 Skill、窄脚本，传统 API 直连最后考虑。
3. **入口不要求精确字符串**：Agent 负责语义选择候选；精确 ID、路径、remote、版本和 consumer 只在最终安全 binding、执行和审计时出现。
4. **分层动态上下文**：Bootstrap → compact candidates → owner context → action/resource context；每层只加载下一层所需内容，不建立全文常驻或递归上下文平台。
5. **稳定探针优先**：每个长期模块都应尽量暴露 `doctor`、`status`、`validate` 和 `--json`，方便 Agent 判断能否继续，但不因此制造统一健康中心。
6. **人类命令是 fallback**：文档中的 shell 命令需要可复制，但主要价值是让 Agent 有明确操作面；正常情况下人类不需要逐条理解。
7. **控制面不吞状态机**：AIOS 可以代理 `aios lll ...`，但 LLL 的队列、lease、runner、artifacts 仍归 LLL 协议/CLI 管理。
8. **文件化治理**：真正需要持久化的事实才进入 vault、必要的 registry、安装状态、维护日志和 LLL workdir；可由 owner 上下文即时恢复的内容不重复登记。
9. **公开可恢复**：公开仓库必须能在 fresh clone / Docker / 新机器上恢复关键能力，不能只依赖作者机器上的隐式 symlink。
10. **自迭代优先**：Agent 在 AIOS 相关任务中发现反复失败、流程冗长、验证缺口或工具边界不清时，应主动提出或执行对 skill、文档、CLI、验证脚本和工作流的改进。

## 渐进式演化

AIOS 的架构演化遵循广度优先、渐进增强和模块同步演化。单个模块不应脱离整体成熟度过早变重；高级机制先进入演化地图，只有真实摩擦和触发条件满足后才实现。

完整规则见 [AIOS 演化协议](./evolution.md)。

## Upstream 与用户实例的融合

`aios-kit` 是 seed/upstream，不是长期覆盖用户实例的唯一真源。用户越长期使用 AIOS，实例越会积累自己的习惯、local overlays、runtime skill 编辑、私有 registry、OPS 记录和 Agent 自迭代改进。因此更新必须是 reconciliation，而不是传统软件式的盲目覆盖。

```text
aios-kit upstream = 默认骨架 + 可复用改进
user instance = 长期演化的本地有机体
update = propose / reconcile / merge / validate，而不是 reset
```

更新时先分类对象：

| 类型 | 更新策略 |
|---|---|
| upstream-managed copy | 用 install-state/hash 判断本地是否改过；未改可自动更新，改过则提出 merge/force 选项 |
| user-owned / local overlay | 属于实例，不被公开 upstream 覆盖，不发布真实私人事实 |
| runtime skill local edits | 视为可能的用户/Agent 自迭代；应尝试与 upstream 三方合并或明确提示冲突 |
| generated/cache | 可重建，按状态记录安全清理 |
| external/app-owned | AIOS 只索引/检查，不移动、不接管 |

未来 AIOS 更新工具应优先提供 `status`、`diff`、`doctor`、`propose`、`reconcile` 这类语义，而不是扩大破坏性的 `update --force`。

### GitHub Source Acquisition Cache

AIOS 可以在 `~/aios/cache/github/` 保留公开 GitHub 仓库的可重建获取缓存，减少不同调研 Worksite 对同一 Git objects/refs 的重复下载：

```text
~/aios/cache/github/
├── repos/<owner>/<repo>.git/   # 每个 canonical owner/repo 一个共享 bare cache
└── locks/<owner>/<repo>.lock   # 持久 lockfile；内核 advisory lock 只在共享写入期间持有
```

边界保持明确：

- GitHub upstream 是外部源码真源；cache 的 authority 为 none，可以重建。
- 当前 LLL Worksite 仍拥有 query、判断、receipt、pinned full SHA、cited paths 和必要证据。
- 不为每个被调研的公共仓库新增长期 Project/Source 记录；Managed Zone 不接收原始完整 clone。
- 搜索/README evidence 不自动触发 clone；只有选定仓库需要完整源码时才调用 `scripts/github_source_cache.py`。
- 共享 cache 不作为可写工作树；实验/阅读从 pinned SHA 派生 cache root 外的 task-local detached worktree。
- cache 是 Linux/WSL 上的 bare partial clone；本地状态探针禁止 lazy fetch，只有显式 fetch/refresh 或 worktree hydrate 才可联网。首次 cache 仅在完整验证后 no-replace 原子发布。
- cache 不默认进入备份，不自动 GC/prune，不迁移/删除旧 clone，也不处理 private/LFS/submodule/跨设备共享。

外部组件、adapter/overlay、patch queue 与 maintained fork 的详细对象模型、风险门禁和最小文件契约见 [上游协调与开源二开维护协议](./upstream-reconciliation.md)。

### Federated search boundary

- AIOS 只统一 task semantics 与 provenance：Search Request、run-scoped Route、Run Evidence、Worksite Receipt。
- 稳定 Source identity/owner/location 仍由现有 Source 记录与动作边界 ResourceRef 绑定；动作直接跟随 `owner_ref` 到 domain/provider Skill 或 service card，account/Secret/health 归实际执行器 owner。
- Provider adapter 拥有 query translation、pagination、error/freshness 与可选 acquisition；cache 可重建且 authority=none。
- `github_repo_search.py` 与 `github_source_cache.py` 继续是 GitHub-specific adapters；搜索结果不自动 clone，acquisition receipt/full SHA/cited paths 回到当前 Worksite。
- 当前不建立全局 Search Registry、通用 cache key/API、数据库、daemon、route catalog 或顶层 `aios search` 命令。
- 只有真实 Worksite 同时暴露多协议路由、重复 acquisition/freshness 成本、权限/隐私差异、恢复缺口或并发竞争时，才提出共享抽象 change set。

## Source、runtime 与 state

不要把所有 repo 都移动到 `aios-kit` 下面。边界应清晰：

| 层级 | 负责内容 | 示例 |
|---|---|---|
| 分发源 | 安装器、CLI、公开文档/manifest | `~/projects/aios-kit` 或 `~/aios/modules/aios-kit` |
| Modules | 可更新的 checkout / template | `~/aios/modules/lins-living-loop` |
| Runtime skills | agent 实际加载的 skills | `~/.agents/skills`、`~/.hermes/skills` |
| Live vault | 私有/当前运维事实 | `~/aios/vault/ops` |
| Skillpack state | 安全更新/裁剪记录 | `~/aios/vault/ops/state/aios-kit/install-state.json` |

外部 skills 通过 `npx skills` 安装。一方 skills 对普通用户可以复制安装，对作者开发机可以 symlink。

## 安装模式与开发模式

当前公开安装处于维护者预览，不向朋友或普通用户提供远程一行安装入口。Agent 或维护者应先 checkout 并审查仓库，再从 dry-run 开始：

```bash
bash install.sh --non-interactive -y --dry-run
```

作者开发时使用逐个 skill symlink，让 runtime 里的编辑能落到 Git 可见的 worktree：

```bash
cd ~/projects/aios-kit
./aios skillpack dev-link --apply
./aios skillpack doctor
```

不要 symlink 或替换整个 agent skills 目录。公开安装默认逐个复制/同步选定 skills。

## 本地结构与链接策略

标准开发路径有意和 runtime 安装路径分离：

| 对象 | 路径 | 策略 |
|---|---|---|
| 主套件 | `~/projects/aios-kit` | 装配脚本、manifest、文档的真源 |
| LLL | `~/projects/lins-living-loop` | 独立一方源项目 |
| AIOps 模板 | `~/projects/aios-kit/modules/aiops-vault-template` | 公开可复用模板 |
| Live AIOps vault | `~/aios/vault/ops` | 默认实例 vault；私有/当前事实 |
| Universal skills | `~/.agents/skills` | runtime 安装目标，不自动等于真源 |
| Hermes skills | `~/.hermes/skills` | Hermes profile runtime skills |

规则：

1. 模板不是 live 资产。
2. Runtime 目录只有在明确提升后才成为真源。
3. 活跃的一方 skills 应该能被 Git 追踪。
4. Symlink 用于作者本地开发；copy/install 是公开默认行为。
5. 只有当前 install-state 记录过的路径才允许自动 prune。

## 关键决策

- **主项目名**：使用 `aios-kit`；skillpack 是模块，不是 repo 边界。
- **LLL 保持独立**：`aios-kit` 引用、链接或复制它，但不 vendor 它。
- **OPS 模板与 live vault 分离**：模板是可复用起点；live vault 是用户/私有状态。
- **作者开发用 symlink，公开分发用 copy**：作者机器优化可编辑性；公开安装优化可迁移性。
- **Manifest + 薄脚本，不做新包管理器**：`aios-kit` 读取 `skillpack.yaml`，对外部 skills 调用 `npx skills`，对一方 skills 直接 copy/symlink。

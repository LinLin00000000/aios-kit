# aios-kit

**简体中文** | [English](./translations/en/README.md)

`aios-kit` 是一个轻量、可迁移、Agent-friendly 的 Personal AIOS 安装与分发套件。

它不是“再装几个 AI 工具”，而是给你的项目、知识、服务、脚本、skills 和长期任务建立一个可被 Agent 理解的本地底座：人类表达目标，Agent 制定策略，CLI/API 执行确定性动作，文件化状态留下事实和证据。

## 当前阶段

`aios-kit` 仍处于快速迭代和维护者预览阶段。公开一键安装入口暂时撤下；当前不面向普通用户承诺稳定安装、升级或跨平台兼容性。

仓库中的安装器与安装文档继续作为开发和验证材料保留。若要评估或参与开发，请先阅读 [开发指南](docs/development.md)、[安全与隐私边界](docs/security-and-privacy.md) 和 [演化路线图](docs/evolution.md)，在隔离环境中从源码审查与 dry-run 开始。

### 通过 Agent 评估与安装（当前推荐入口）

把仓库链接和下面的目标交给你信任的终端 Agent（如 Hermes、Codex 或 Claude Code）。Agent 应读取项目文件并根据当前平台自适应，不应盲目复制固定命令：

```text
请评估并协助安装 aios-kit：https://github.com/LinLin00000000/aios-kit
先阅读仓库中的 README、安装、安全、开发和演化文档，识别当前平台与仍在开发中的能力边界。
先审查安装脚本并执行 dry-run，说明将修改的路径、系统配置、平台限制和回滚方式；得到我确认后再实际安装。
不要读取、打印或提交 secret value、订阅 URL、token、密钥或私人配置。
```

<details>
<summary>当前能力概览（维护者参考）</summary>

## 当前能力概览

### 核心模块与目录

| 模块 / 能力 | 安装位置 | 默认平台 | 作用 | 备注 |
|---|---|---|---|---|
| AIOS 实例根目录 | `~/aios` | Linux / Windows；macOS 可 dry-run 探路 | 把个人 AIOS 的状态、模块、工作目录和缓存收束到一个可迁移边界内 | 可用 `--root` 改路径 |
| `aios-kit` 模块 | `~/aios/modules/aios-kit` | Linux / Windows | 安装器、`aios` CLI、skillpack manifest、文档与模板的来源 | Linux/WSL 可 `aios update modules` 更新 |
| LLL 模块 | `~/aios/modules/lins-living-loop` | Linux / Windows | 文件化长期任务/Agent 工作流底座 | Windows 原生会安装模块；完整 `lll` CLI 当前仍建议 Git Bash/WSL/Linux |
| 命令入口 | `~/aios/bin/aios`、`~/aios/bin/lll`；Windows 为 `.ps1/.cmd` shim | Linux / Windows | 给 Agent 和人类提供稳定入口，不依赖记住 repo 路径 | 可选择加入 PATH |
| 工作目录 | `~/aios/work` | 全平台设计 | LLL / Agent 工作目录，承接长任务、调研、验证、交付物 | 对话外的持久工作层 |
| Matter 派生索引与视图 | `~/aios/state/matters`、`~/aios/view/matters` | Linux / Windows | 跨 Worksite 查询 active/paused/closed/archived 事务，并只读展示精选交付物 | 可重建，不替代 Worksite 文件真源 |
| 配置/状态/日志/缓存 | `~/aios/config`、`state`、`logs`、`cache` | 全平台设计 | 保存实例配置、安装状态、日志和缓存 | 避免散落在多个隐式位置 |
| 私有 vault 边界 | `~/aios/vault/ops` | Linux 默认初始化；Windows 创建核心目录 | 放置 OPS vault、少数长期项目/Source 事实和维护记录等私有 owner context | 公共模板与真实私有数据分离；不要求所有对象登记 |
| runtime skills 目标目录 | 默认 `~/.agents/skills`，可选 Hermes 目标 | Linux / WSL 完整同步；Windows 原生先初始化目标 | Agent 实际加载 skills 的位置 | 不接管整个 skills 目录，只逐个安装托管 skill |

### 默认托管 skills

| 类别 | Skills | 用途 |
|---|---|---|
| 文档处理 | `docx`、`pptx`、`xlsx`、`pdf` | 让 Agent 能读写/检查常见办公文档与 PDF |
| Skill 生态 | `find-skills`、`skill-governance`、`install-skill` | 发现、治理、安装和维护可复用 Agent skills；创建规则按需加载治理 Skill 的 reference |
| MCP / 工具发现 | `awesome-mcp-servers-discovery` | 调研和筛选 MCP server |
| 前端与设计 | `frontend-design`、`ui-ux-pro-max`、`vercel-composition-patterns`、`web-design-guidelines` | UI/UX、前端架构和 Web 设计审查 |
| 领域建模 | `domain-modeling` | 澄清领域术语、维护领域模型，并在必要时记录 ADR |
| AIOS 一等能力 | `aios-agent`、`aios-resource-resolver`、`aios-secret-management`、`lins-living-loop`、`github-repo-search` | AIOS Agent 策略入口、已选资源的动作边界绑定、秘密控制面、长期任务工作流、GitHub 项目搜索推荐 |

### `aios` CLI 能力

| 命令 | 作用 | 典型使用者 |
|---|---|---|
| `aios status` | 查看实例根目录、vault、work、skills、modules 等摘要 | 人类 / Agent |
| `aios doctor` / `aios doctor --json` | 校验实例、skillpack 与本地资产配置；JSON 模式输出 versioned `aios.doctor.v1` 机器契约 | Agent 优先 |
| `aios update` | 更新模块、OPS 模板和托管 skills | Agent / 维护者 |
| `aios project ...` | 读取/维护少数需要长期稳定边界的项目事实（兼容入口；live help 仍写 registry）；普通项目优先由 Agent 加载本地上下文，不要求先注册 | Agent / 维护者 |
| `aios matter ...` | 重建/查询派生 Matter 索引与 View，并对注册来源资料执行显式 attach/list/只读 verify；详见 [Matter 生命周期](docs/matter-lifecycle.md) 与 [Matter materials](docs/matter-materials.md) | Agent 优先 |
| `aios lll ...` | 发现、创建、打开、检查 LLL workdir，生成 closeout change set，并以可恢复 quarantine 代替直接删除 | Agent 优先 |
| `aios promotion ...` | 对已明确授权的长期资产提升做 dry-run、copy-if-absent 执行、校验与只读撤销检查 | Agent 优先 |
| `aios skillpack ...` | 列出、同步、检查托管 runtime skills；维护者可用 `adopt` 把本地新建 skill 接管进 Git 真源 | 维护者 / Agent |
| `aios assets ...` | 检查或链接本地资产发现 manifest | 维护者 |

现场 `aios --help` 仍把 `project` 写成 “manage the minimal AIOS project registry”，把 `resource` 写成 resolve existing Project/Source records。它们是兼容/只读绑定 actuator 的残留措辞，不是中央注册表产品模型。

### Linux/server 附加能力

| 附加能力 | 安装位置 / 影响范围 | 适用场景 | Windows 原生策略 |
|---|---|---|---|
| Mihomo 网络引导 | `~/aios/network/mihomo`、可选 shell proxy / TUN | 新服务器访问 GitHub、模型/API、包管理器不稳定时 | 不显示；需要时用 WSL/Linux |
| TUN / systemd 服务 | Linux systemd service | 云服务器 24/7 运行、全局透明代理 | 不显示 |
| dev/runtime bootstrap | Python/UV、NVM/Node、Docker、Caddy | 新 Ubuntu/Debian 服务器快速补齐基础运行环境 | 不显示 |
| Hermes Agent 安装/配置 | 用户环境与 Hermes skills target | 把 Hermes 作为默认 Agent 中心 | Windows 原生暂不做；可用 WSL/Linux |
| OPS vault 模板 | `~/aios/vault/ops` | 生成公开模板结构，真实私有事实仍留本地 | Windows 原生只创建核心目录 |
| Ubuntu 源恢复 | apt/npm/pip/Docker source 配置 | 修复被镜像/旧配置污染的新服务器 | 不显示 |

</details>

## 愿景与设计哲学

Personal AIOS 的目标很简单：让 AI 从“临时聊天助手”变成“能围绕你的真实数字世界持续工作的操作层”。它需要知道项目在哪里、服务怎么检查、资料和密钥边界是什么、哪些工作能自动化、哪些必须确认。

`aios-kit` 只做这个操作层的最小骨架：统一入口、托管 skills、按需加载上下文、必要的长期事实、OPS vault、LLL 工作流入口、安装/更新/检查命令。它不试图吞并所有工具，也不要求所有项目、服务、数据资产或能力先进入一个中央管理表；它给不同 Agent 和工具提供共同现实锚点，并让真正的 owner 保留自己的上下文和执行器。

设计取舍：

| 原则 | 取舍 |
|---|---|
| Agent-first | 命令、Skill、compact catalog、本地项目上下文和 vault 事实要让 Agent 容易发现、解析和恢复；人类命令是 fallback。 |
| 管理即上下文工程 | 数据资产、服务器、服务、云资源、项目和能力默认通过多层动态上下文加载，不先建传统管理平台；只有稳定边界和安全事实才持久化。 |
| 官方能力优先 | 新接入先查官方 CLI、官方 Skill、官方 MCP 和官方文档；AIOps card、薄引导 Skill、窄脚本和传统 API 依次后置。 |
| 动态发现，精确绑定 | Agent 负责从候选上下文中语义选择 owner；精确 ID、路径、remote、版本和 consumer 只在最终执行和审计边界绑定。 |
| 文件是真源 | 需要跨任务恢复的重要事实沉淀到 owner 文件、必要的 vault/registry、workdir 或 manifest，不把可即时恢复的上下文重复登记。 |
| 薄控制面 | `aios` 负责提供上下文入口、必要的结构检查和窄 actuator；LLL、Hermes、Mihomo 等仍保持自己的状态机。CLI/API 是 Agent actuator，不是让普通用户背命令。 |
| 私有与公开分离 | 公开 repo 只放模板、脚本、skills 和结构；真实资产、密钥、订阅、维护日志和 local overlays 留在本地 vault/state。 |
| 渐进演化 | 模块广度优先、点到为止；新增能力必须证明减少的系统复杂度大于引入的复杂度，详见 [docs/evolution.md](docs/evolution.md)。 |
| 自迭代 | Agent 在使用 AIOS 时发现失败模式、冗长路径或验证缺口，应主动提出或沉淀对 skill、文档、CLI、验证脚本和工作流的改进。 |
| 可迁移而非平台锁定 | 默认路径清晰、可备份、可重装；Hermes 是默认中心，但不是唯一 Agent。 |

<details>
<summary>维护者技术参考</summary>

## 能力分层

| 层级 | 内容 | 平台策略 |
|---|---|---|
| 核心特性 | 本地 AIOS 实例、`aios-kit` 与 LLL 模块、`aios` 命令入口、work/config/vault/skills/state/logs/cache 目录、runtime skills 目标目录 | 设计为全平台支持；当前优先支持 Ubuntu 与 Windows。适合“本地开机时使用”，不要求 24 小时运行。Windows 原生会安装 LLL 模块，但完整 `lll` CLI 暂需 Git Bash/WSL。 |
| 附加特性 | Mihomo/TUN、Docker/Caddy/Node/UV bootstrap、Hermes 安装配置、OPS vault 模板、Ubuntu 源恢复、systemd/24x7 服务化运行 | Linux/server 推荐；Windows 原生安装默认隐藏不支持项。如需完整 Linux/server 能力，请用 WSL 或云服务器。 |

## 默认目录结构

```text
~/aios/
  bin/                     # aios / lll 命令入口
  config/                  # 实例配置
  vault/ops/               # OPS vault 边界：模板结构 + 私有事实入口
  work/                    # LLL / agent 工作目录
  skills/                  # AIOS 元数据/缓存，不是 runtime skills 目录
  modules/                 # 可更新的模块 checkout
  network/mihomo/          # 可选 Mihomo 网络组件
  state/ logs/ cache/
```

Agent 真正加载的 runtime skills 仍安装到 agent 自己的目录，例如 `~/.agents/skills/<skill>` 或 `~/.hermes/skills/<skill>`。Linux/WSL 后端会逐个安装托管 skills，不接管整个 skills 目录；Windows 原生安装目前先初始化 skills 目标目录，managed skillpack sync 仍建议通过 WSL/Linux 执行。

## LLL 工作流入口

LLL（Lin's Living Loop）是 AIOS 的工作流基底之一，但仍保持独立一等 CLI。`aios-kit` 负责发现、安装、更新和治理 LLL，不吞并 LLL 的核心状态机。

```bash
./aios update modules lins-living-loop
./aios lll doctor --json
./aios lll list --json
./aios lll new demo --objective "..."
./aios lll status <workdir-or-name> --json
```

`aios lll ...` 的边界：默认只定位 `lll` CLI/helper、列出 AIOS work root 下的 LLL workdirs、创建新 workdir，或把 status/validate 代理给 `lll`；任务队列、runner、lease、reaper、artifacts 仍由 LLL CLI/协议负责。标准安装会在 `~/aios/bin/` 暴露 `aios` 与 `lll` 两个命令；`aios lll doctor --json` 会优先检查 AIOS module 内的 LLL，避免被 PATH 上的旧版本误导。

## 网络与 Mihomo

安装器会先在不设置代理环境变量的情况下测试外网。如果直连失败，交互式会询问是否安装 Mihomo，默认 yes；非交互 `--proxy auto` 会自动安装。

Mihomo 默认安装到 `~/aios/network/mihomo`，TUN 默认开启；Linux/systemd 上会写入 `aios-mihomo.service`。TUN 配置不是跨 Windows/macOS/Linux 的绝对通用配置，当前默认值主要面向 Ubuntu/Debian 云服务器。详情见：[docs/mihomo-network.md](docs/mihomo-network.md)。

## 常用命令

Agent 优先使用 JSON/doctor/status 探针；人类只在需要兜底排障时手动执行：

```bash
aios status                 # 查看实例摘要（human-readable）
aios doctor                 # 校验安装与链接状态（human-readable）
aios doctor --json          # compact aios.doctor.v1；ok 与 exit code 对齐，诊断内容集中脱敏
aios update --dry-run       # 预览更新
aios update                 # 更新模块、OPS 模板和托管 skills
aios update skills          # 刷新托管 runtime skills
aios project list           # 兼容入口：少数长期项目事实（help 仍写 registry）
aios source list            # 兼容入口：显式 Source + Project 联邦投影（help 仍写 federated view）
aios source validate        # 校验 Source identity / policy / locator 结构
aios lll doctor --json      # Agent-first: 检查 LLL/Code Loop 能力
aios lll list --json        # Agent-first: 枚举 LLL workdirs
```

维护/调试入口：`aios skillpack doctor`、`aios skillpack sync --dry-run`、`aios assets doctor`。如果没有配置 PATH，可用 `~/aios/bin/aios status` 或 `~/aios/bin/lll --version`。

</details>

## 文档索引

| 文档 | 用途 |
|---|---|
| [docs/installation.md](docs/installation.md) | 维护者安装流程、dry-run、交互选项与参数参考 |
| [docs/mihomo-network.md](docs/mihomo-network.md) | Mihomo 配置、TUN 兼容性、订阅/节点输入 |
| [docs/architecture.md](docs/architecture.md) | repo 边界、本地结构、source/runtime 模型、关键决策 |
| [docs/upstream-reconciliation.md](docs/upstream-reconciliation.md) | 外部组件、adapter/overlay、patch queue 与 maintained fork 的上游协调协议 |
| [docs/evolution.md](docs/evolution.md) | AIOS 演化协议、模块成熟度地图和复杂度预算 |
| [docs/aios-resource-architecture.md](docs/aios-resource-architecture.md) | AIOS 资源、动态上下文与最终 binding |
| [docs/security-and-privacy.md](docs/security-and-privacy.md) | 安全与隐私边界、公开发布审计 |
| [docs/development.md](docs/development.md) | 维护者开发、skillpack、发布流程 |

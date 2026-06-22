# aios-kit

**简体中文** | [English](./translations/en/README.md)

`aios-kit` 是一个轻量、可迁移、Agent-friendly 的 Personal AIOS 安装与分发套件。

它不是“再装几个 AI 工具”，而是给你的项目、知识、服务、脚本、skills 和长期任务建立一个可被 Agent 理解的本地底座：文件是真源，CLI 是控制面，Agent 是默认操作者，人类负责目标、边界和验收。

## 安装

当前最推荐只记住两个入口：

### 方式 1：一行交互式安装

Ubuntu/Debian Linux：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

Windows PowerShell（原生核心安装）：

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.ps1 | iex
```

脚本启动后会先问是否使用现代 CLI 向导（默认 yes）。确认后才会下载向导；如果向导不可用，会自动回退到原生 Bash 交互。Windows 原生入口只安装核心能力；如果需要 Linux/server 附加能力，请使用 WSL 或 Linux 服务器上的 `install.sh`。

如果 GitHub 访问不稳定，可以换成你信任的镜像：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

### 方式 2：让已有 Agent 辅助安装

把下面几行发给 Codex、Claude Code、OpenClaw、Hermes 等终端 Agent：

```text
请帮我安装 aios-kit：https://github.com/LinLin00000000/aios-kit
请先阅读 README.md、docs/installation.md、docs/security-and-privacy.md，并查看 install.sh --help。
先生成并运行 dry-run 安装命令，说明会改哪些系统配置；我确认后再执行正式安装。
安装后请运行 ~/aios/bin/aios status 和 ~/aios/bin/aios doctor。
不要泄露或提交我的订阅 URL、token、密钥或私人配置。
```

更多平台、参数、非交互和排障细节见：[docs/installation.md](docs/installation.md)。

## 安装后会得到什么

### 核心模块与目录

| 模块 / 能力 | 安装位置 | 默认平台 | 作用 | 备注 |
|---|---|---|---|---|
| AIOS 实例根目录 | `~/aios` | Linux / Windows；macOS 可 dry-run 探路 | 把个人 AIOS 的状态、模块、工作目录和缓存收束到一个可迁移边界内 | 可用 `--root` 改路径 |
| `aios-kit` 模块 | `~/aios/modules/aios-kit` | Linux / Windows | 安装器、`aios` CLI、skillpack manifest、文档与模板的来源 | Linux/WSL 可 `aios update modules` 更新 |
| LLL 模块 | `~/aios/modules/lins-living-loop` | Linux / Windows | 文件化长期任务/Agent 工作流底座 | Windows 原生会安装模块；完整 `lll` CLI 当前仍建议 Git Bash/WSL/Linux |
| 命令入口 | `~/aios/bin/aios`、`~/aios/bin/lll`；Windows 为 `.ps1/.cmd` shim | Linux / Windows | 给 Agent 和人类提供稳定入口，不依赖记住 repo 路径 | 可选择加入 PATH |
| 工作目录 | `~/aios/work` | 全平台设计 | LLL / Agent 工作目录，承接长任务、调研、验证、交付物 | 对话外的持久工作层 |
| 配置/状态/日志/缓存 | `~/aios/config`、`state`、`logs`、`cache` | 全平台设计 | 保存实例配置、安装状态、日志和缓存 | 避免散落在多个隐式位置 |
| 私有 vault 边界 | `~/aios/vault/ops` | Linux 默认初始化；Windows 创建核心目录 | 放置 OPS vault、项目注册表、维护记录等私有事实 | 公共模板与真实私有数据分离 |
| runtime skills 目标目录 | 默认 `~/.agents/skills`，可选 Hermes 目标 | Linux / WSL 完整同步；Windows 原生先初始化目标 | Agent 实际加载 skills 的位置 | 不接管整个 skills 目录，只逐个安装托管 skill |

### 默认托管 skills

| 类别 | Skills | 用途 |
|---|---|---|
| 文档处理 | `docx`、`pptx`、`xlsx`、`pdf` | 让 Agent 能读写/检查常见办公文档与 PDF |
| Skill 生态 | `find-skills`、`skill-creator`、`install-skill` | 发现、安装、创建和维护可复用 Agent skills |
| MCP / 工具发现 | `awesome-mcp-servers-discovery` | 调研和筛选 MCP server |
| 前端与设计 | `frontend-design`、`ui-ux-pro-max`、`vercel-composition-patterns`、`web-design-guidelines` | UI/UX、前端架构和 Web 设计审查 |
| 方案打磨 | `grilling`、`grill-me`、`grill-with-docs`、`domain-modeling` | 追问需求、打磨计划、沉淀领域模型和 ADR |
| AIOS 一等能力 | `aios-resource-resolver`、`lins-living-loop`、`github-repo-search` | 资源解析、长期任务工作流、GitHub 项目搜索推荐 |

### `aios` CLI 能力

| 命令 | 作用 | 典型使用者 |
|---|---|---|
| `aios status` | 查看实例根目录、vault、work、skills、modules 等摘要 | 人类 / Agent |
| `aios doctor` | 校验实例、skillpack 与本地资产配置 | Agent 优先 |
| `aios update` | 更新模块、OPS 模板和托管 skills | Agent / 维护者 |
| `aios project ...` | 管理最小项目/资源注册表与 alias | Agent / 维护者 |
| `aios lll ...` | 发现、创建、打开、检查 LLL workdir，并代理部分 LLL 命令 | Agent 优先 |
| `aios skillpack ...` | 列出、同步、检查托管 runtime skills | 维护者 / Agent |
| `aios assets ...` | 检查或链接本地资产发现 manifest | 维护者 |

### Linux/server 附加能力

| 附加能力 | 安装位置 / 影响范围 | 适用场景 | Windows 原生策略 |
|---|---|---|---|
| Mihomo 网络引导 | `~/aios/network/mihomo`、可选 shell proxy / TUN | 新服务器访问 GitHub、模型/API、包管理器不稳定时 | 不显示；需要时用 WSL/Linux |
| TUN / systemd 服务 | Linux systemd service | 云服务器 24/7 运行、全局透明代理 | 不显示 |
| dev/runtime bootstrap | Python/UV、NVM/Node、Docker、Caddy | 新 Ubuntu/Debian 服务器快速补齐基础运行环境 | 不显示 |
| Hermes Agent 安装/配置 | 用户环境与 Hermes skills target | 把 Hermes 作为默认 Agent 中心 | Windows 原生暂不做；可用 WSL/Linux |
| OPS vault 模板 | `~/aios/vault/ops` | 生成公开模板结构，真实私有事实仍留本地 | Windows 原生只创建核心目录 |
| Ubuntu 源恢复 | apt/npm/pip/Docker source 配置 | 修复被镜像/旧配置污染的新服务器 | 不显示 |

## 愿景与设计哲学

Personal AIOS 的目标很简单：让 AI 从“临时聊天助手”变成“能围绕你的真实数字世界持续工作的操作层”。它需要知道项目在哪里、服务怎么检查、资料和密钥边界是什么、哪些工作能自动化、哪些必须确认。

`aios-kit` 只做这个操作层的最小骨架：统一目录、托管 skills、资源注册表、OPS vault、LLL 工作流入口、安装/更新/检查命令。它不试图吞并所有工具，而是给不同 Agent 和工具一套共同现实锚点。

设计取舍：

| 原则 | 取舍 |
|---|---|
| Agent-first | 命令、文档、registry、vault 和日志要让 Agent 容易发现、解析和恢复；人类命令是 fallback。 |
| 文件是真源 | 重要事实沉淀到 vault / registry / workdir / manifest，不困在一次对话里。 |
| 薄控制面 | `aios` 负责发现、安装、更新和健康检查；LLL、Hermes、Mihomo 等仍保持自己的状态机。 |
| 私有与公开分离 | 公开 repo 只放模板、脚本、skills 和结构；真实资产、密钥、订阅、维护日志留在本地 vault。 |
| 可迁移而非平台锁定 | 默认路径清晰、可备份、可重装；Hermes 是默认中心，但不是唯一 Agent。 |

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
aios update --dry-run       # 预览更新
aios update                 # 更新模块、OPS 模板和托管 skills
aios update skills          # 刷新托管 runtime skills
aios project list           # 查看项目/资源注册表
aios lll doctor --json      # Agent-first: 检查 LLL/Code Loop 能力
aios lll list --json        # Agent-first: 枚举 LLL workdirs
```

维护/调试入口：`aios skillpack doctor`、`aios skillpack sync --dry-run`、`aios assets doctor`。如果没有配置 PATH，可用 `~/aios/bin/aios status` 或 `~/aios/bin/lll --version`。

## 文档索引

| 文档 | 用途 |
|---|---|
| [docs/installation.md](docs/installation.md) | 安装流程、交互选项、非交互参数 |
| [docs/mihomo-network.md](docs/mihomo-network.md) | Mihomo 配置、TUN 兼容性、订阅/节点输入 |
| [docs/architecture.md](docs/architecture.md) | repo 边界、本地结构、source/runtime 模型、关键决策 |
| [docs/aios-resource-architecture.md](docs/aios-resource-architecture.md) | AIOS 资源、项目注册表与 resolver 结构 |
| [docs/security-and-privacy.md](docs/security-and-privacy.md) | 安全与隐私边界、公开发布审计 |
| [docs/development.md](docs/development.md) | 维护者开发、skillpack、发布流程 |

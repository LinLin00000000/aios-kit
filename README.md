# aios-kit

**简体中文** | [English](./translations/en/README.md)

`aios-kit` 是一个轻量、可迁移、Agent-friendly 的 Personal AIOS 安装与分发套件。

它想解决的不是“怎么多装几个 AI 工具”，而是一个更长期的问题：当 AI 开始替你读文档、跑命令、维护服务、整理知识、延续项目时，你需要一个属于自己的操作系统层，把记忆、工具、资源、工作流和边界组织起来。

## 愿景

Personal AIOS 不是一个聊天窗口，也不是某个单一 agent。它更像个人数字世界的底座：知道你有哪些项目、资产、服务和习惯；知道什么能公开、什么必须留在本地；知道怎样把一次性的 AI 对话沉淀成可复用的工作流。

`aios-kit` 是这个底座的安装包和分发骨架。它先把最小可用的 AIOS 搭起来：目录、技能、OPS vault、项目注册表、网络引导和更新命令。之后它可以继续长成：多设备协作、个人知识与运维图谱、长期任务循环、数字分身的上下文层，以及让不同 agent 共享同一套现实锚点的基础设施。

核心方向：

- **从聊天到操作系统**：AI 不只回答问题，而是能围绕你的项目、设备、资料和服务持续行动。
- **从临时上下文到长期结构**：重要信息不困在某次对话里，而沉淀为 vault、registry、skills 和可审计日志。
- **从单 Agent 到 Agent 生态**：Hermes 是默认中心，但 Codex、Claude Code、OpenClaw 或未来的 agent 都应能读懂同一套结构。
- **从工具堆叠到个人主权**：公开模板可以复制，私人事实留在本地；系统应该帮助你迁移和扩展，而不是把你锁进某个平台。
- **从人类手动操作到 Agent-first**：默认让 agent 读取结构、调用 CLI、执行检查和修复；人类主要表达目标、边界和验收标准，手动命令只是 agent 不可用时的 fallback。

今天的 `aios-kit` 还只是起点：先让一台新机器获得可迁移、可维护、可被 agent 理解的 AIOS 骨架。路线图不是把所有东西塞进一个仓库，而是逐步形成一个清晰的个人 AI 基础设施协议。

## 设计哲学：Agent 优先，人类 Fallback

AIOS 的默认使用者不是“熟练记命令的人”，而是能持续替你工作的 agent。人类的主要输入应该是目标、约束、权限边界和验收标准；具体命令、路径、健康检查、更新、日志读取、错误恢复和文档查阅，应该由 agent 根据稳定结构自行完成。

这带来几条设计约束：

| 原则 | 含义 |
|---|---|
| **Agent-first** | CLI、文档、registry、vault 和日志都要让 agent 容易发现、调用、解析和恢复。 |
| **Human fallback** | README 仍给出可复制命令，但这些命令是 agent 操作面与紧急手动入口，不是默认交互方式。 |
| **机器可读优先** | 关键命令应提供 `--json`、`doctor`、`status`、`validate` 之类稳定探针；不要只输出给人看的长文本。 |
| **文件是真源** | 私有事实、项目注册、运维状态和长任务记录应落到 vault/registry/LLL workdir，而不是停留在聊天上下文。 |
| **薄控制面** | AIOS 负责发现、安装、更新和治理；具体状态机由对应工具负责，例如 LLL 管自己的任务队列和 runner。 |
| **可审计可迁移** | 公开模板和私有状态分离，变更可检查，fresh clone / 新机器应能恢复同等能力。 |

所以，文档里的命令示例可以直接给人执行，但更推荐复制给 Hermes/Codex/Claude Code/OpenClaw 等 agent，让 agent 先运行 `doctor/status`，再根据机器环境选择安全路径。

## LLL 工作流入口

LLL（Lin's Living Loop）是 AIOS 的工作流基底之一，但仍保持独立一等 CLI。`aios-kit` 负责发现、安装、更新和治理 LLL，不吞并 LLL 的核心状态机。这里同样以 Agent 为默认操作者：人类表达目标，Agent 调用 `aios lll ...` 发现 workdir、检查健康状态、创建新任务空间并交给 `lll` runner 执行；命令示例是 Agent 操作面和人类 fallback。

```bash
./aios update modules lins-living-loop
./aios lll doctor --json
./aios lll list --json
./aios lll new demo --objective "..."
./aios lll status <workdir-or-name> --json
```

`aios lll ...` 的边界：默认只定位 `lll` CLI/helper、列出 AIOS work root 下的 LLL workdirs、创建新 workdir，或把 status/validate 代理给 `lll`；任务队列、runner、lease、reaper、artifacts 仍由 LLL CLI/协议负责。标准安装会在 `~/aios/bin/` 暴露 `aios` 与 `lll` 两个命令；`aios lll doctor --json` 会优先检查 AIOS module 内的 LLL，避免被 PATH 上的旧版本误导。

## 安装

当前安装器主要在 Ubuntu/Debian 系云服务器上验证过；其他发行版建议先 `--dry-run` 或使用 agent-assisted 安装。

### 方式 1：让已有 agent 辅助安装

如果你已经有 Codex、Claude Code、OpenClaw、Hermes 等 agent，推荐先让 agent 读仓库、检测机器，再把你的选择转换成非交互安装命令。

<details>
<summary>复制给 agent 的精简提示词</summary>

```text
请帮我安装这个项目：https://github.com/LinLin00000000/aios-kit

不要直接盲跑安装脚本。请先浏览 README.md 和 docs/installation.md、docs/mihomo-network.md、docs/security-and-privacy.md，再运行或阅读 bash install.sh --help 获取完整参数，并检测当前 OS、网络、权限、systemd、sudo、Python、git、curl、node/npx、Docker、Caddy、Hermes、HOME 和 PATH。

请把安装选项整理成确认清单，并给默认值和建议：AIOS root；是否安装 Mihomo/Clash；是否开启 TUN；是否恢复 apt/npm/pip/Docker 官方源；代理订阅 URL 或本地 proxies YAML；GitHub 镜像前缀；是否安装 dev env；是否安装 Hermes；是否安装 OPS vault；是否加入 PATH；skillpack target/mode。若跳过 dev env 但仍要安装 skillpack，请先确认已有 node/npx。

等我确认后，把配置转换成 install.sh 的非交互参数执行。私人订阅 URL 建议先 export 到环境变量，再用双引号传入，例如：`export AIOS_PROXY_SUBSCRIPTION_URL='...'`，然后使用 `--proxy-subscription-url "$AIOS_PROXY_SUBSCRIPTION_URL"`。不要把真实 URL 写进可分享记录，也不要用单引号包住需要展开的环境变量。安装完成后运行 ~/aios/bin/aios status 和 ~/aios/bin/aios doctor；如果安装了 Mihomo，再检查 systemd service 或平台等价状态。不要泄露或提交我的订阅 URL、UUID、token、密钥或私人配置。
```

</details>

### 方式 2：一行交互式安装

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

如果想使用上下键选择、空格复选的现代 CLI 向导，可以加 `--wizard`：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --wizard

# 已经在 repo checkout 里时
bash install.sh --wizard
# 或先只查看它会如何调用 install.sh
aios-install --no-wizard --script ./install.sh --print-command --dry-run
```

`aios-install` 是交互前端，不复制安装逻辑；它收集选择后生成并执行 `install.sh --non-interactive ...`。`install.sh --wizard` 会优先使用本地 `aios-install`，其次使用 checkout 内的 `go run`，最后在干净 Linux/macOS 机器上下载 GitHub Release 预编译二进制并校验 `aios-install_checksums.txt`。如果向导不可用，会回退到原 Bash 交互。

如果新机器暂时无法直连 GitHub，可以用你信任的 raw/release 镜像：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

### 方式 3：非交互自动安装

还没有 clone repo 时：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- \
  --non-interactive -y \
  --root ~/aios \
  --proxy auto \
  --reset-sources \
  --add-to-path yes \
  --target universal \
  --mode copy
```

已经在 repo checkout 里时，把第一行替换为 `bash install.sh`。dev env、Hermes、OPS vault 默认开启；如需跳过用 `--no-dev-env` / `--no-hermes` / `--no-aiops`。

如果你已经使用其他 agent，不想安装 Hermes：

```bash
bash install.sh --non-interactive -y --no-hermes --target universal --mode copy
```

详细流程、交互问题和非交互参数见：[docs/installation.md](docs/installation.md)。

## 默认会安装什么

```text
~/aios/
  bin/                     # aios 命令入口
  config/                  # 实例配置
  vault/ops/               # 从公开模板初始化的 OPS vault
  work/                    # LLL / agent 工作目录
  skills/                  # AIOS 元数据/缓存，不是 runtime skills 目录
  modules/                 # 可更新的模块 checkout
  network/mihomo/          # 可选 Mihomo 网络组件
  state/ logs/ cache/
```

Agent 真正加载的 runtime skills 仍安装到 agent 自己的目录，例如 `~/.agents/skills/<skill>` 或 `~/.hermes/skills/<skill>`。`aios-kit` 只逐个安装托管 skills，不接管整个 skills 目录。

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

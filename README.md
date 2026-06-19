# aios-kit

`aios-kit` 是一个轻量、可迁移、Agent-friendly 的 Personal AIOS 安装与分发套件。

它以 Hermes Agent 为默认中心，但不把你锁死在单一 agent 里。你也可以用 Codex、Claude Code、OpenClaw 或任何能读文档、执行命令、检查结果的 agent 来安装和维护它。

`aios-kit` is a lightweight, portable, agent-friendly distribution kit for a Personal AIOS. Hermes Agent is the default center, but the layout, skills, OPS vault, and workflow pieces are designed to remain useful with other agents too.

---

## 核心理念 / Philosophy

AIOS 不是一个“大而全平台”，而是一组清晰、可迁移、可组合的基础件：

- **文件系统优先**：重要状态尽量落在目录、manifest、vault 和日志里。
- **保守幂等**：先检测，再执行；已存在的组件不重复安装；本地改动不默认覆盖。
- **Agent-friendly**：文档既给人读，也给 agent 读。已有 agent 可以根据环境动态安装，而不是盲跑脚本。
- **可迁移**：新机器从公开仓库和模板生成，不复制维护者私人路径、订阅、密钥或 live vault。
- **可组合**：Hermes 是默认中心；Codex、Claude Code、OpenClaw 等也可以复用通用 skills、OPS vault、LLL 和 registry。

更多理念见：[docs/philosophy.md](docs/philosophy.md)。

---

## 安装 / Install

当前安装器主要在 Ubuntu/Debian 系云服务器上验证过；其他发行版建议先 `--dry-run` 或使用 agent-assisted 安装。

### 方式 1：让已有 agent 辅助安装 / Agent-assisted install

如果你已经有 Codex、Claude Code、OpenClaw、Hermes 等 agent，推荐先用 agent 读仓库并按你的环境动态安装。复制下面这段给你的 agent：

```text
请帮我安装这个项目：https://github.com/LinLin00000000/aios-kit

不要直接盲跑安装脚本。请先浏览 README.md 和 docs/，检测当前 OS、网络、权限、systemd、sudo、Python、git、curl、node/npx、Docker、Caddy、Hermes 等状态。

然后把每个安装组件作为一个确认项列给我，并给默认值和建议：AIOS root、是否安装 Mihomo、是否开启 TUN、是否恢复 apt/npm/pip/Docker 官方源、代理订阅 URL 或本地 proxies YAML、GitHub 镜像前缀、是否安装 dev env、是否安装 Hermes、是否安装 OPS vault、是否加入 PATH、skillpack target/mode。

等我确认后，把配置转换成 install.sh 的非交互参数执行。安装后运行 ~/aios/bin/aios status、~/aios/bin/aios doctor；如果安装了 Mihomo，再检查 systemd service 或平台等价状态。不要泄露或提交我的订阅 URL、UUID、token、密钥。
```

完整 agent prompt 见：[docs/agent-assisted-install.md](docs/agent-assisted-install.md)。

### 方式 2：一行交互式安装 / One-line interactive install

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

如果新机器暂时无法直连 GitHub，可以用你信任的 raw/release 镜像：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

### 方式 3：非交互自动安装 / Non-interactive install

```bash
bash install.sh --non-interactive -y \
  --root ~/aios \
  --proxy auto \
  --reset-sources \
  --proxy-tun \
  --with-dev-env \
  --with-hermes \
  --with-aiops \
  --add-to-path yes \
  --target universal \
  --mode copy
```

如果你已经使用其他 agent，不想安装 Hermes：

```bash
bash install.sh --non-interactive -y --no-hermes --target universal --mode copy
```

详细安装步骤见：[docs/installation.md](docs/installation.md)。所有交互式选项和非交互参数见：[docs/installer-options.md](docs/installer-options.md)。

---

## 默认会安装什么 / What it installs

默认布局：

```text
~/aios/
  bin/                     # aios command shim
  config/                  # instance configuration
  vault/ops/               # OPS vault from public template
  work/                    # LLL / agent work directories
  skills/                  # AIOS metadata/cache, not runtime skills dir
  modules/                 # updateable module checkouts
  network/mihomo/          # optional Mihomo network component
  state/
  logs/
  cache/
```

Agent 真正加载的 runtime skills 仍然安装到 agent 自己的目录，例如：

```text
~/.agents/skills/<skill>
~/.hermes/skills/<skill>
```

`aios-kit` 只逐个安装托管 skills，不接管整个 skills 目录。

---

## 网络与 Mihomo / Network and Mihomo

安装器会先在不设置代理环境变量的情况下测试外网。如果直连失败，交互式会询问是否安装 Mihomo，默认 yes；非交互 `--proxy auto` 会自动安装。

Mihomo 默认：

- 安装到 `~/aios/network/mihomo`；
- TUN 默认开启；
- Linux/systemd 上写入 `/etc/systemd/system/aios-mihomo.service`；
- 支持供应商订阅 URL 或本地 `proxies` YAML 片段；
- 支持 `--github-mirror` 处理 GitHub release、UI、geodata 下载。

Mihomo/TUN 配置不是跨 Windows/macOS/Linux 的绝对通用配置。当前默认值主要面向 Ubuntu/Debian 云服务器；Windows/macOS 更适合用 agent-assisted 安装或平台原生客户端适配。

详情见：[docs/mihomo-network.md](docs/mihomo-network.md)。

---

## 文档索引 / Docs index

给人和 agent 的入口：

| 文档 | 用途 |
|---|---|
| [docs/philosophy.md](docs/philosophy.md) | 项目理念、边界、为什么 Hermes first 但不 Hermes only |
| [docs/installation.md](docs/installation.md) | 安装流程逐步说明，每个组件安装什么 |
| [docs/installer-options.md](docs/installer-options.md) | 交互式问题、默认值、非交互参数对照 |
| [docs/agent-assisted-install.md](docs/agent-assisted-install.md) | 给已有 agent 的安装 prompt 与流程 |
| [docs/mihomo-network.md](docs/mihomo-network.md) | Mihomo 配置、TUN 兼容性、订阅/节点输入 |
| [docs/local-structure.md](docs/local-structure.md) | 本地目录布局 |
| [docs/architecture.md](docs/architecture.md) | 架构说明 |
| [docs/aios-resource-architecture.md](docs/aios-resource-architecture.md) | AIOS resource / OPS vault 结构 |
| [docs/security-and-privacy.md](docs/security-and-privacy.md) | 安全与隐私边界 |
| [docs/development.md](docs/development.md) | 维护者开发流程 |
| [docs/authoring.md](docs/authoring.md) | skill / 模块创作说明 |
| [docs/decisions.md](docs/decisions.md) | 设计决策记录 |

---

## 常用命令 / Common commands

```bash
aios status                 # show instance summary
aios doctor                 # validate wiring
aios update                 # update modules, OPS template, and managed skills
aios update --dry-run       # preview update
aios update skills          # refresh managed runtime skills
aios update modules         # update module Git checkouts
aios update ops             # refresh OPS vault template
```

如果没有配置 PATH：

```bash
~/aios/bin/aios status
```

---

## Skillpack 更新语义 / Skillpack update semantics

`aios-kit` 比普通 “重新 add 一遍” 更保守：

- 每个托管 skill 记录安装路径和本地内容 hash；
- 更新前如果发现 runtime skill 被用户本地改动，默认拒绝覆盖；
- 只有显式 `--force` 才覆盖；
- stale skill 只在 `--prune --apply` 时移除。

---

## 隐私边界 / Privacy boundary

公开仓库不应该包含：

- 私人订阅 URL；
- UUID、token、密钥；
- 维护者 live OPS vault；
- 本地 overlay；
- 机器专属绝对路径。

公共 installer 使用模板和运行时输入生成本机配置。

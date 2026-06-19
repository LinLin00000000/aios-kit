# aios-kit

`aios-kit` 是一个轻量、可迁移、Agent-friendly 的 Personal AIOS 安装与分发套件。

它不是“大而全平台”，而是一组清晰、可组合的基础件：AIOS layout、runtime skills、OPS vault、LLL/workflow、项目/资源 registry，以及必要的安装脚本。Hermes Agent 是默认中心，但 Codex、Claude Code、OpenClaw 或任何能读文档、执行命令、检查结果的 agent 也可以使用它。

## 核心理念 / Philosophy

- **文件系统优先**：重要状态落在目录、manifest、vault 和日志里，便于审计、迁移和备份。
- **保守幂等**：先检测，再执行；已存在组件不重复安装；本地改动不默认覆盖。
- **Agent-friendly**：文档既给人读，也给 agent 读；已有 agent 可以先理解环境，再调用安装器。
- **干净分发**：公开安装只使用模板和运行时输入，不导出维护者私人路径、订阅、密钥或 live vault。

## 安装 / Install

当前安装器主要在 Ubuntu/Debian 系云服务器上验证过；其他发行版建议先 `--dry-run` 或使用 agent-assisted 安装。

### 方式 1：让已有 agent 辅助安装 / Agent-assisted install

如果你已经有 Codex、Claude Code、OpenClaw、Hermes 等 agent，推荐先让 agent 读仓库、检测机器，再把你的选择转换成非交互安装命令。

<details>
<summary>复制给 agent 的精简 prompt / Copyable prompt</summary>

```text
请帮我安装这个项目：https://github.com/LinLin00000000/aios-kit

不要直接盲跑安装脚本。请先浏览 README.md 和 docs/installation.md、docs/mihomo-network.md、docs/security-and-privacy.md，再运行或阅读 bash install.sh --help 获取完整参数，并检测当前 OS、网络、权限、systemd、sudo、Python、git、curl、node/npx、Docker、Caddy、Hermes、HOME 和 PATH。

请把安装选项整理成确认清单，并给默认值和建议：AIOS root；是否安装 Mihomo/Clash；是否开启 TUN；是否恢复 apt/npm/pip/Docker 官方源；代理订阅 URL 或本地 proxies YAML；GitHub 镜像前缀；是否安装 dev env；是否安装 Hermes；是否安装 OPS vault；是否加入 PATH；skillpack target/mode。

等我确认后，把配置转换成 install.sh 的非交互参数执行。安装完成后运行 ~/aios/bin/aios status 和 ~/aios/bin/aios doctor；如果安装了 Mihomo，再检查 systemd service 或平台等价状态。不要泄露或提交我的订阅 URL、UUID、token、密钥或私人配置。
```

</details>

### 方式 2：一行交互式安装 / One-line interactive install

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

如果新机器暂时无法直连 GitHub，可以用你信任的 raw/release 镜像：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

### 方式 3：非交互自动安装 / Non-interactive install

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

## 默认会安装什么 / What it installs

```text
~/aios/
  bin/                     # aios command shim
  config/                  # instance configuration
  vault/ops/               # OPS vault from public template
  work/                    # LLL / agent work directories
  skills/                  # AIOS metadata/cache, not runtime skills dir
  modules/                 # updateable module checkouts
  network/mihomo/          # optional Mihomo network component
  state/ logs/ cache/
```

Agent 真正加载的 runtime skills 仍安装到 agent 自己的目录，例如 `~/.agents/skills/<skill>` 或 `~/.hermes/skills/<skill>`。`aios-kit` 只逐个安装托管 skills，不接管整个 skills 目录。

## 网络与 Mihomo / Network and Mihomo

安装器会先在不设置代理环境变量的情况下测试外网。如果直连失败，交互式会询问是否安装 Mihomo，默认 yes；非交互 `--proxy auto` 会自动安装。

Mihomo 默认安装到 `~/aios/network/mihomo`，TUN 默认开启；Linux/systemd 上会写入 `aios-mihomo.service`。TUN 配置不是跨 Windows/macOS/Linux 的绝对通用配置，当前默认值主要面向 Ubuntu/Debian 云服务器。详情见：[docs/mihomo-network.md](docs/mihomo-network.md)。

## 常用命令 / Common commands

```bash
aios status                 # show instance summary
aios doctor                 # validate wiring
aios update                 # update modules, OPS template, and managed skills
aios update --dry-run       # preview update
aios update skills          # refresh managed runtime skills
aios project list           # inspect project/resource registry
```

维护/调试入口：`aios skillpack doctor`、`aios skillpack sync --dry-run`、`aios assets doctor`。如果没有配置 PATH，可用 `~/aios/bin/aios status`。

## 文档索引 / Docs index

| 文档 | 用途 |
|---|---|
| [docs/installation.md](docs/installation.md) | 安装流程、交互选项、非交互参数 |
| [docs/mihomo-network.md](docs/mihomo-network.md) | Mihomo 配置、TUN 兼容性、订阅/节点输入 |
| [docs/architecture.md](docs/architecture.md) | repo 边界、本地结构、source/runtime 模型、关键决策 |
| [docs/aios-resource-architecture.md](docs/aios-resource-architecture.md) | AIOS resource / project registry / resolver 结构 |
| [docs/security-and-privacy.md](docs/security-and-privacy.md) | 安全与隐私边界、公开发布 audit |
| [docs/development.md](docs/development.md) | 维护者开发、skillpack、发布流程 |

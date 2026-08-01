# 安装指南

当前安装器处于维护者预览阶段，按“能力分层”继续开发。以下内容是 Agent 和维护者的评估参考，不是面向普通用户的稳定安装承诺。任何平台都应先让 Agent 阅读当前仓库、识别能力边界，并在隔离环境中执行 `--dry-run`。

## 能力分层

| 层级 | 内容 | 安装策略 |
|---|---|---|
| 核心特性 | AIOS instance root、`aios-kit` 模块、LLL 模块、`aios` 命令入口、work/config/vault/skills/state/logs/cache 目录、runtime skills 目标目录 | 全平台设计；适合本地开机时使用，不要求 24 小时运行。Ubuntu 由 `install.sh` 安装，Windows 由 `install.ps1` 原生安装。Windows 完整 `lll` CLI 与 managed skillpack sync 暂建议通过 Git Bash/WSL/Linux 执行。 |
| 附加特性 | Mihomo/TUN、开发/运行环境 bootstrap、Hermes、OPS vault 模板、Ubuntu 软件源恢复、systemd/24x7 服务化运行 | Linux/server 推荐；Windows 原生安装不显示不支持项。如需这些能力，请使用 Linux 或 WSL。 |


## 当前入口：Agent 辅助评估

把仓库交给你信任的终端 Agent，让它根据当前平台和仓库内容生成方案，而不是执行远程一行安装命令：

```text
请评估并协助安装 aios-kit：https://github.com/LinLin00000000/aios-kit
先阅读仓库中的 README、安装、安全、开发和演化文档，检查当前平台、安装脚本和参数帮助。
先执行 dry-run，说明将修改的路径、系统配置、平台限制和回滚方式；得到我确认后再实际安装。
不要读取、打印或提交 secret value、订阅 URL、token、密钥或私人配置。
```

Agent 或维护者从已审查的本地 checkout 开始：

```bash
bash install.sh --non-interactive -y --dry-run
# 用户确认后才执行：
bash install.sh --non-interactive -y
```

交互式向导和完整参数仍在开发中；Agent 应通过 `bash install.sh --help` 获取当前行为，不依赖旧文档中的固定命令组合。

## Windows PowerShell 原生核心安装（实验性）

Windows 入口现在是原生 PowerShell 核心安装器：它会创建 `~/aios`，安装/更新 `aios-kit` 与 LLL 模块，生成 `aios.ps1`/`aios.cmd`，并在检测到 Git Bash/WSL 时提供 `lll.ps1`/`lll.cmd` 代理，初始化 work/config/vault/skills/state/logs/cache 等核心目录，并可把 `~/aios/bin` 加入用户 PATH。它会检查 Python 3，因为 `aios` 命令依赖 Python。

Windows 原生入口不会显示 Linux/server 不支持的附加能力，例如 systemd 24/7 服务、Mihomo TUN service、Ubuntu 源恢复、Docker/Caddy bootstrap、managed skillpack sync。需要完整 Linux/server 能力时，请在 WSL 或云服务器中运行 `install.sh`。

请从已审查的本地 checkout 运行 dry-run：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -DryRun -PrintPlan
```

非交互核心安装示例：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NonInteractive -Yes -Root "$HOME\aios"
```

如只想打印 WSL/Git Bash 后端命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -UseBashBackend -DryRun
```

## 现代向导启动顺序

`install.sh` 启动现代向导时会按顺序尝试：

1. PATH 上已有 `aios-install`：直接调用；
2. repo checkout 中有 Go 工具链：使用 `go run ./cmd/aios-install`；
3. 下载 GitHub Release 中当前 OS/arch 对应的 `aios-install_<os>_<arch>.tar.gz`，校验 `aios-install_checksums.txt` 后启动；
4. 如果以上都不可用，回退到原生 Bash 交互。

可通过环境变量覆盖 release 来源：

```bash
AIOS_INSTALL_RELEASE_TAG=v0.1.0
AIOS_INSTALL_RELEASE_BASE_URL=https://github.com/LinLin00000000/aios-kit/releases
```

## GitHub 镜像

当测试环境不能直连 GitHub 时，已审查的本地安装器可显式传入你信任的镜像：

```bash
bash install.sh --dry-run --github-mirror https://gh-proxy.com/
```

`--github-mirror` 会给 GitHub/raw URL 添加前缀，包括 aios-kit、LLL、OPS template clone，Hermes/NVM installer，以及 Mihomo release/UI/geodata 中的 GitHub URL。

## 安装器做什么

安装器尽量幂等：先检测，再执行。主流程：

1. 检查最小依赖：`git`、`python3`、`curl` 等。
2. 测试直连 GitHub/外网；失败时可安装 Mihomo。
3. 创建 AIOS root，默认 `~/aios`，以及 `modules/`、`bin/`、`config/`、`state/`、`logs` 等目录。
4. 准备 `aios-kit` checkout：从 repo 内运行时使用当前 repo，否则默认 `~/aios/modules/aios-kit`。
5. 写入 `~/aios/bin/aios` command shim，并可选择加入 PATH。
6. 可选安装 Mihomo/Clash：生成配置、下载内核，Linux/systemd 上写入并启动 `aios-mihomo.service`。
7. 可选恢复官方源：npm、pip、Docker；Ubuntu apt 会备份旧 source 并写入官方 deb822 source。
8. 可选安装开发环境：Python venv 支持、UV、NVM + Node 24、Docker、Caddy。
9. 初始化 AIOS instance 配置。
10. clone/update LLL 等 modules。
11. 可选安装/检测 Hermes Agent；其他 Agent 用户可用 `--no-hermes` 跳过。
12. 安装 skillpack：默认 target `universal`，mode `copy`，保护用户本地改动。
13. 从公开模板初始化 OPS vault，默认 `~/aios/vault/ops`；不复制维护者私人 live vault。

## 交互选项与非交互参数

| 交互问题 | 默认值 | 非交互参数 | 说明 |
|---|---:|---|---|
| 是否使用现代 CLI 向导 | yes | `--wizard` / `--no-wizard` | 默认先询问，确认后才下载/启动 |
| AIOS 安装根目录 | `~/aios` | `--root PATH` | AIOS 实例根目录 |
| 代理设置 | `auto` | `--proxy auto|yes|no` | 先直连检测，失败后安装 Mihomo |
| 是否开启 Mihomo TUN 模式 | `1` | `--proxy-tun` / `--no-proxy-tun` | TUN 默认开启 |
| 是否恢复 apt/npm/pip/Docker 官方源 | `1` | `--reset-sources` / `--no-reset-sources` | Ubuntu apt 会备份旧 source |
| 代理订阅 URL | 空 | `--proxy-subscription-url URL` | 私有 provider 订阅 URL；安装器会写入 `~/aios/network/mihomo/secrets/.env` |
| provider id | `main` | `--proxy-provider-id ID` | 写入 `MIHOMO_PROVIDERS_ORDER`；只用小写字母、数字、下划线 |
| 本地代理 YAML 片段路径 | 空 | `--proxy-proxies-file PATH` | 自建节点 YAML 片段，属于私有配置 |
| 是否安装/检查 Python+UV、Node 24、Docker、Caddy | `1` | `--with-dev-env` / `--no-dev-env` | skillpack 的外部安装依赖 `npx`；跳过 dev env 时请确保已有 Node/npx |
| 是否安装/检查 Hermes Agent | `1` | `--with-hermes` / `--no-hermes` | Hermes 默认安装，但可跳过 |
| 是否安装/更新 OPS vault 模板 | `1` | `--with-aiops` / `--no-aiops` | 初始化运维资料库 |
| 是否把 AIOS bin 加入 PATH | 交互默认 yes | `--add-to-path yes|no|ask` | 非交互建议显式传 `yes` 或 `no` |

私人订阅 URL 建议先 export 到环境变量，再用双引号传入：

```bash
export AIOS_PROXY_SUBSCRIPTION_URL='...'
bash install.sh --non-interactive -y \
  --proxy yes \
  --proxy-subscription-url "$AIOS_PROXY_SUBSCRIPTION_URL"
```

安装后可在 `~/aios/network/mihomo` 看到脱敏友好的构建模块：`build.py`、`policy.toml`、`.env.example`。真实 URL 只应存在于 `secrets/.env` 或 AIOS Secret Runtime 中，不要写进可分享记录，也不要用单引号包住需要展开的环境变量。

## 完整参数

本文只列常用参数。完整、实时的参数说明以安装器为准：

```bash
bash install.sh --help
```

常见高级参数：

| 参数 | 用途 |
|---|---|
| `--kit-dir PATH` / `--lll-dir PATH` / `--vault PATH` | 覆盖 checkout 或 OPS vault 位置 |
| `--skills-dir PATH` | 覆盖 agent runtime skills 目录 |
| `--global-bin DIR` | 把 `aios` 链接到已有 PATH 目录，遇到冲突会拒绝覆盖 |
| `--proxy-auto-env auto|yes|no` | 控制 shell proxy helpers 是否自动启用 |
| `--mihomo-url URL` / `--mihomo-version VERSION` | 覆盖 Mihomo 内核下载来源或版本 |
| `--force` | 覆盖被本地修改过的 managed skill copy |
| `--interactive` / `--dry-run` | 强制交互或只打印动作 |

## 官方源恢复

默认 `--reset-sources`。当前行为：

- npm：删除自定义 registry。
- pip：删除 `global.index-url`。
- Docker：由 Docker 官方安装脚本配置官方 repository。
- apt：Ubuntu 上备份旧 sources，并写入官方 `archive.ubuntu.com` / `security.ubuntu.com` deb822 source；非 Ubuntu 暂时只提示。

apt 恢复会备份到：

```text
/etc/apt/sources.list.d/aios-backup-YYYYmmdd-HHMMSS/
```

并禁用旧 `.list` / `.sources` 文件为 `.aios-disabled`。

## 安装后检查

```bash
aios status
aios doctor
aios update --dry-run
systemctl status aios-mihomo.service  # 如果安装了 Mihomo
proxy_test                             # 如果安装了代理辅助命令
```

如果没有把 `aios` 加入 PATH：

```bash
~/aios/bin/aios status
```

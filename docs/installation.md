# 安装指南

当前安装器主要在 Ubuntu/Debian 系云服务器上验证。macOS/Windows 与其他发行版建议先使用 `--dry-run`，或让已有 Agent 读源码和文档后辅助安装。

## 推荐入口

### 一行交互式安装

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

默认行为：脚本先用原生 Bash 问一句是否启用现代 CLI 向导，默认 yes。只有选择 yes 后，才会下载或启动 `aios-install`。

`aios-install` 是 Go/huh 写的现代 CLI 前端，提供上下键选择、空格复选和安装计划预览。它不复制真实安装逻辑，只把你的选择转换成稳定的：

```bash
install.sh --non-interactive ...
```

如果你想强制使用或跳过现代向导：

```bash
bash install.sh --wizard
bash install.sh --no-wizard
```

### Agent 辅助安装

如果你已经有 Codex、Claude Code、OpenClaw、Hermes 等终端 Agent，推荐让 Agent 先生成 dry-run 计划，再执行正式安装：

```text
请帮我安装 aios-kit：https://github.com/LinLin00000000/aios-kit
请先阅读 README.md、docs/installation.md、docs/security-and-privacy.md，并查看 install.sh --help。
先生成并运行 dry-run 安装命令，说明会改哪些系统配置；我确认后再执行正式安装。
安装后请运行 ~/aios/bin/aios status 和 ~/aios/bin/aios doctor。
不要泄露或提交我的订阅 URL、token、密钥或私人配置。
```

Agent/CI 的稳定入口不是交互式向导，而是：

```bash
bash install.sh --non-interactive -y --dry-run
bash install.sh --non-interactive -y
```

还没有 clone repo 时：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- \
  --non-interactive -y \
  --root ~/aios \
  --proxy auto \
  --add-to-path yes
```

## Windows PowerShell bootstrap（预览）

Windows 入口是薄 bootstrap：下载 `aios-install.exe`、校验 checksum、下载 `install.sh` 作为后端，然后启动向导。它依赖 GitHub Release 中已经存在 `aios-install_windows_*.tar.gz` 和 `aios-install_checksums.txt`；如果当前版本还没有发布 release assets，请先使用 Git Bash/WSL 运行 `install.sh`，或等待 release 发布后再用 PowerShell 入口。

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.ps1 | iex
```

当前真实安装后端仍是 `install.sh`，所以正式执行安装需要 Git Bash 或 WSL。没有 Bash 时，PowerShell bootstrap 会打印可复制的持久命令，避免假装完成安装。

更可审计的方式：

```powershell
$script = "$env:TEMP\aios-kit-install.ps1"
iwr -UseBasicParsing https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.ps1 -OutFile $script
powershell -ExecutionPolicy Bypass -File $script -DryRun
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

当新机器不能直连 GitHub 时，可以使用：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
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
| 代理订阅 URL | 空 | `--proxy-subscription-url URL` | 供应商/机场订阅 URL，属于私有配置 |
| 本地代理 YAML 片段路径 | 空 | `--proxy-proxies-file PATH` | 自建节点 YAML 片段，属于私有配置 |
| 是否安装/检查 Python+UV、Node 24、Docker、Caddy | `1` | `--with-dev-env` / `--no-dev-env` | skillpack 的外部安装依赖 `npx`；跳过 dev env 时请确保已有 Node/npx |
| 是否安装/检查 Hermes Agent | `1` | `--with-hermes` / `--no-hermes` | Hermes 默认安装，但可跳过 |
| 是否安装/更新 OPS vault 模板 | `1` | `--with-aiops` / `--no-aiops` | 初始化运维资料库 |
| 是否把 AIOS bin 加入 PATH | 交互默认 yes | `--add-to-path yes|no|ask` | 非交互建议显式传 `yes` 或 `no` |

私人订阅 URL 建议先 export 到环境变量，再用双引号传入：

```bash
export AIOS_PROXY_SUBSCRIPTION_URL='...'
bash install.sh --non-interactive -y --proxy-subscription-url "$AIOS_PROXY_SUBSCRIPTION_URL"
```

不要把真实 URL 写进可分享记录，也不要用单引号包住需要展开的环境变量。

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

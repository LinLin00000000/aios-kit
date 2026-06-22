# 安装指南

当前安装器主要在 Ubuntu/Debian 系云服务器上验证。其他发行版建议先使用 `--dry-run`，或让已有 agent 读源码和文档后辅助安装。

## 快速安装

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

## 现代安装向导（Go/huh）

`aios-kit` 正在采用两阶段安装器：

1. `install.sh` / 未来的 `install.ps1` 保持极薄 bootstrap 与稳定后端参数面；
2. `aios-install` 是 Go/huh 交互前端，负责现代 CLI 向导，然后生成并执行 `install.sh --non-interactive ...`。

在 repo checkout 中可以直接试用：

```bash
# 启动交互向导；没有 aios-install 二进制时会尝试 go run 或下载 release binary
bash install.sh --wizard

# 干净 Linux/macOS 机器也可直接从 raw installer 启动 wizard
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --wizard

# Agent/CI 友好：不进入向导，只打印将执行的后端命令
aios-install --no-wizard --script ./install.sh --print-command --dry-run

# 机器可读计划
aios-install --no-wizard --script ./install.sh --json --dry-run
```

`--wizard` 的启动顺序：

1. 如果 PATH 上已有 `aios-install`，直接调用；
2. 如果在 repo checkout 中且有 Go 工具链，使用 `go run ./cmd/aios-install`；
3. 否则按当前 OS/arch 下载 GitHub Release 中的 `aios-install_<os>_<arch>.tar.gz`，校验 `aios-install_checksums.txt` 后启动；
4. 如果以上都不可用，则安全回退到原 Bash 交互。

可通过环境变量覆盖 release 来源：`AIOS_INSTALL_RELEASE_TAG=v0.1.0` 或 `AIOS_INSTALL_RELEASE_BASE_URL=<mirror/releases>`。`--github-mirror` 会同时影响 release 下载 URL 和后续安装中用到的 GitHub/raw URL。

如果新机器暂时无法直连 GitHub，可以用你信任的 raw/release 镜像：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

## 安装器做什么

安装器尽量幂等：先检测，再执行。主流程：

1. 检查最小依赖：`git`、`python3`、`curl` 等。
2. 测试直连 GitHub/外网；失败时可安装 Mihomo。
3. 创建 AIOS root，默认 `~/aios`，以及 `modules/`、`bin/`、`config/`、`state/`、`logs/` 等目录。
4. 准备 `aios-kit` checkout：从 repo 内运行时使用当前 repo，否则默认 `~/aios/modules/aios-kit`。
5. 写入 `~/aios/bin/aios` command shim，并可选择加入 PATH。
6. 可选安装 Mihomo/Clash：生成配置、下载内核，Linux/systemd 上写入并启动 `aios-mihomo.service`。
7. 可选恢复官方源：npm、pip、Docker；Ubuntu apt 会备份旧 source 并写入官方 deb822 source。
8. 可选安装开发环境：Python venv 支持、UV、NVM + Node 24、Docker、Caddy。
9. 初始化 AIOS instance 配置。
10. clone/update LLL 等 modules。
11. 可选安装/检测 Hermes Agent；其他 agent 用户可用 `--no-hermes` 跳过。
12. 安装 skillpack：默认 target `universal`，mode `copy`，保护用户本地改动。
13. 从公开模板初始化 OPS vault，默认 `~/aios/vault/ops`；不复制维护者私人 live vault。

## 交互选项与非交互参数

| 交互问题 | 默认值 | 非交互参数 | 说明 |
|---|---:|---|---|
| AIOS 安装根目录 | `~/aios` | `--root PATH` | AIOS 实例根目录 |
| 代理设置 | `auto` | `--proxy auto|yes|no` | 先直连检测，失败后安装 Mihomo |
| 是否开启 Mihomo TUN 模式 | `1` | `--proxy-tun` / `--no-proxy-tun` | TUN 默认开启 |
| 是否恢复 apt/npm/pip/Docker 官方源 | `1` | `--reset-sources` / `--no-reset-sources` | Ubuntu apt 会备份旧 source |
| 代理订阅 URL | 空 | `--proxy-subscription-url URL` | 供应商/机场订阅 URL，属于私有配置；建议先 `export AIOS_PROXY_SUBSCRIPTION_URL='...'`，再用 `--proxy-subscription-url "$AIOS_PROXY_SUBSCRIPTION_URL"` |
| 本地代理 YAML 片段路径 | 空 | `--proxy-proxies-file PATH` | 自建节点 YAML 片段，属于私有配置 |
| 是否安装/检查 Python+UV、Node 24、Docker、Caddy | `1` | `--with-dev-env` / `--no-dev-env` | skillpack 的外部安装依赖 `npx`；跳过 dev env 时请确保已有 Node/npx |
| 是否安装/检查 Hermes Agent | `1` | `--with-hermes` / `--no-hermes` | Hermes 默认安装，但可跳过 |
| 是否安装/更新 OPS vault 模板 | `1` | `--with-aiops` / `--no-aiops` | 初始化运维资料库 |
| 是否把 AIOS bin 加入 PATH | 交互默认 yes | `--add-to-path yes|no|ask` | 非交互建议显式传 `yes` 或 `no` |

常用非交互命令：

```bash
bash install.sh --non-interactive -y \
  --root ~/aios \
  --proxy auto \
  --reset-sources \
  --add-to-path yes \
  --target universal \
  --mode copy
```

还没有 clone repo 时，可使用 remote installer：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- \
  --non-interactive -y \
  --root ~/aios \
  --proxy auto \
  --add-to-path yes
```

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

## GitHub 镜像

当新服务器不能直连 GitHub 时，可以使用：

```bash
--github-mirror https://gh-proxy.com/
```

它会给 GitHub/raw URL 添加前缀，包括 aios-kit、LLL、OPS template clone，Hermes/NVM installer，以及 Mihomo release/UI/geodata 中的 GitHub URL。

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

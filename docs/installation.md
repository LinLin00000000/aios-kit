# 安装指南 / Installation Guide

当前安装器主要在 Ubuntu/Debian 系云服务器上验证。其他发行版建议先使用 `--dry-run`，或让已有 agent 读源码和文档后辅助安装。

## 快速安装 / Quick install

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

如果新机器暂时无法直连 GitHub，可以用你信任的 raw/release 镜像：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

## 安装器做什么 / What the installer does

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

## 交互选项与非交互参数 / Options

| 交互问题 | 默认值 | 非交互参数 | 说明 |
|---|---:|---|---|
| AIOS install root | `~/aios` | `--root PATH` | AIOS 实例根目录 |
| Proxy setup | `auto` | `--proxy auto|yes|no` | 先直连检测，失败后安装 Mihomo |
| Enable Mihomo TUN mode? | `1` | `--proxy-tun` / `--no-proxy-tun` | TUN 默认开启 |
| Restore apt/npm/pip/Docker sources? | `1` | `--reset-sources` / `--no-reset-sources` | Ubuntu apt 会备份旧 source |
| Proxy subscription URL | 空 | `--proxy-subscription-url URL` | 供应商/机场订阅 URL，属于私有配置；建议先 `export AIOS_PROXY_SUBSCRIPTION_URL='...'`，再用 `--proxy-subscription-url "$AIOS_PROXY_SUBSCRIPTION_URL"` |
| Local proxies YAML snippet path | 空 | `--proxy-proxies-file PATH` | 自建节点 YAML 片段，属于私有配置 |
| Install/check Python+UV, Node 24, Docker, Caddy? | `1` | `--with-dev-env` / `--no-dev-env` | skillpack 的外部安装依赖 `npx`；跳过 dev env 时请确保已有 Node/npx |
| Install/check Hermes Agent? | `1` | `--with-hermes` / `--no-hermes` | Hermes 默认安装，但可跳过 |
| Install/update OPS vault template? | `1` | `--with-aiops` / `--no-aiops` | 初始化运维资料库 |
| Add AIOS bin to PATH? | 交互默认 yes | `--add-to-path yes|no|ask` | 非交互建议显式传 `yes` 或 `no` |

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

## 完整参数 / Full option reference

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

## GitHub 镜像 / GitHub mirror

当新服务器不能直连 GitHub 时，可以使用：

```bash
--github-mirror https://gh-proxy.com/
```

它会给 GitHub/raw URL 添加前缀，包括 aios-kit、LLL、OPS template clone，Hermes/NVM installer，以及 Mihomo release/UI/geodata 中的 GitHub URL。

## 官方源恢复 / Official source reset

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

## 安装后检查 / Post-install checks

```bash
aios status
aios doctor
aios update --dry-run
systemctl status aios-mihomo.service  # if Mihomo was installed
proxy_test                             # if proxy helpers were installed
```

如果没有把 `aios` 加入 PATH：

```bash
~/aios/bin/aios status
```

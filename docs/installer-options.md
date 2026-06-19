# 安装器选项 / Installer Options

本文列出交互式问题、默认值，以及对应的非交互参数。

## 交互式问题 / Interactive prompts

| 交互问题 | 默认值 | 非交互参数 | 说明 |
|---|---:|---|---|
| AIOS install root | `~/aios` | `--root PATH` | AIOS 实例根目录 |
| Proxy setup | `auto` | `--proxy auto|yes|no` | 先直连检测，失败后安装 Mihomo |
| Enable Mihomo TUN mode? | `1` | `--proxy-tun` / `--no-proxy-tun` | TUN 默认开启 |
| Restore apt/npm/pip/Docker sources? | `1` | `--reset-sources` / `--no-reset-sources` | 交互式现在会明确询问 |
| Proxy subscription URL | 空 | `--proxy-subscription-url URL` | 供应商/机场订阅 URL |
| Local proxies YAML snippet path | 空 | `--proxy-proxies-file PATH` | 自建节点 YAML 片段 |
| Install/check Python+UV, Node 24, Docker, Caddy? | `1` | `--with-dev-env` / `--no-dev-env` | 开发/运行环境 |
| Install/check Hermes Agent? | `1` | `--with-hermes` / `--no-hermes` | Hermes 默认安装，但可跳过 |
| Install/update OPS vault template? | `1` | `--with-aiops` / `--no-aiops` | 初始化运维资料库 |
| Add AIOS bin to PATH? | `yes` | `--add-to-path yes|no|ask` | 写入 shell PATH block |

## 非交互常用参数 / Common non-interactive flags

```bash
bash install.sh \
  --non-interactive -y \
  --root ~/aios \
  --proxy auto \
  --reset-sources \
  --add-to-path yes \
  --target universal \
  --mode copy
```

## 组件开关 / Component switches

| 组件 | 默认 | 跳过 |
|---|---:|---|
| Mihomo/Clash | auto | `--proxy no` |
| source reset | yes | `--no-reset-sources` |
| dev env | yes | `--no-dev-env` |
| Hermes Agent | yes | `--no-hermes` |
| OPS vault | yes | `--no-aiops` |
| skillpack | yes | 暂无总开关；可用 `--target` / `--mode` 控制目标和模式 |

## GitHub 镜像 / GitHub mirror

当新服务器不能直连 GitHub 时，可以使用：

```bash
--github-mirror https://gh-proxy.com/
```

它会给以下 GitHub/raw release URL 添加前缀：

- aios-kit / LLL / OPS template git clone；
- Hermes installer raw URL；
- NVM installer raw URL；
- Mihomo release asset；
- Mihomo UI/geodata URL。

## 官方源恢复 / Official source reset

默认 `--reset-sources`。

当前行为：

- npm：`npm config delete registry`。
- pip：`python3 -m pip config unset global.index-url`。
- Docker：由 Docker 官方安装脚本配置官方 repository。
- apt：Ubuntu 上备份旧 sources，并写入官方 `archive.ubuntu.com` / `security.ubuntu.com` deb822 source；非 Ubuntu 暂时只提示。

apt 恢复会备份到：

```text
/etc/apt/sources.list.d/aios-backup-YYYYmmdd-HHMMSS/
```

并禁用旧 `.list` / `.sources` 文件为 `.aios-disabled`。

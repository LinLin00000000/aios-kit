# Mihomo 网络配置

AIOS 的网络 bootstrap 目标是：新云服务器如果不能直连外网，可以快速得到一个可控、可恢复、可审计的代理层。

## 当前定位

当前 installer 主要面向 Ubuntu/Debian 云服务器：

- systemd 服务单元：`/etc/systemd/system/aios-mihomo.service`
- 二进制：`~/aios/network/mihomo/mihomo`
- 配置：`~/aios/network/mihomo/config.yaml`
- shell 辅助命令：`proxy_on`、`proxy_off`、`proxy_test`、`proxy_restart`

Windows/macOS 不应直接假设同一套 systemd/CAP_NET_ADMIN/TUN 行为可用。可以使用本文档和 agent-assisted installation 作为适配参考。

## 配置输入

AIOS Kit 保留两个层次：

1. installer 的 `--proxy yes` 是最低摩擦 bootstrap，适合单机快速装好网络。
2. `templates/mihomo/builder.py` 是面向真实多节点/多 provider 运维的通用模板，适合 Agent 分发到边缘节点后在目标机本地生成配置。

### Builder 模板（推荐用于多边缘节点）

公开仓库只提供模板，不保存任何私有配置：

```text
templates/mihomo/
  builder.py
  .env.example
  README.md
  AGENTS.md
  config.yaml
```

目标机上的运行形态：

```text
<mihomo-dir>/
  builder.py
  secrets/.env              # 本机敏感输入，不提交
  secrets/config.yaml       # 生成版 Mihomo 配置，不提交
  secrets/providers/<id>.yaml
```

Builder 默认读取当前进程环境变量和 `secrets/.env`。缺少订阅时会提示快速启动；`preview` / `doctor` 只输出脱敏信息，适合 Agent 检查。

快速启动：

```bash
cd <mihomo-dir>
mkdir -p secrets
cp .env.example secrets/.env
chmod 700 secrets
chmod 600 secrets/.env
$EDITOR secrets/.env
python3 builder.py preview
python3 builder.py build
python3 builder.py check
```

单订阅：

```bash
MIHOMO_SUB_URL=https://example.invalid/sub
MIHOMO_SUB_ID=airport
```

多 provider：

```bash
MIHOMO_PROVIDER_1_ID=zjk
MIHOMO_PROVIDER_1_URL=https://example.invalid/zjk
MIHOMO_PROVIDER_1_ROLE=primary
MIHOMO_PROVIDER_2_ID=bywave
MIHOMO_PROVIDER_2_URL=https://example.invalid/bywave
MIHOMO_PROVIDER_2_ROLE=paid_backup
```

编号顺序就是 fallback 优先级。AI 分组使用独立的 `<id>-ai` provider，可通过 `MIHOMO_AI_EXCLUDE_FILTER` 或 per-provider `MIHOMO_PROVIDER_<N>_AI_EXCLUDE_FILTER` 排除无法访问 AI 站点的地区节点。

Linux systemd 服务建议显式指定生成配置：

```ini
ExecStart=<mihomo-dir>/mihomo -d <mihomo-dir> -f <mihomo-dir>/secrets/config.yaml
```

当前不新增 `install.sh --proxy-builder`：先保持 installer 低复杂度，用模板 + Agent/Ansible 分发验证真实工作流；等跨节点复用稳定后再考虑把它产品化为安装参数。

### 供应商订阅 URL（installer 快速 bootstrap）

```bash
# 在 aios-kit 仓库 checkout 内执行
bash install.sh --proxy yes --proxy-subscription-url 'https://example.com/sub?token=...'
```

安装器生成：

```yaml
proxy-providers:
  airport: { type: http, url: "...", interval: 86400, path: ./providers/airport.yaml }
```

并让 `AI`、`Auto`、`PROXY` groups 使用 provider。

### 自建节点 YAML 片段

```bash
bash install.sh --proxy yes --proxy-proxies-file ./nodes.yaml
```

`nodes.yaml` 可以是裸 list：

```yaml
- name: freya
  type: vless
  server: example.com
  port: 443
  uuid: 00000000-0000-0000-0000-000000000000
  network: tcp
  tls: true
```

也可以是：

```yaml
proxies:
  - name: freya
    type: vless
    server: example.com
```

安装器会自动提取 `name` 并加入 `AI`、`Auto`、`PROXY` groups。

## TUN 配置是否通用

当前模板：

```yaml
tun:
  enable: true
  stack: mixed
  dns-hijack:
    - any:53
    - tcp://any:53
  auto-route: true
  auto-detect-interface: true
  strict-route: false
  endpoint-independent-nat: true
```

判断：**适合作为 Linux 服务器默认值，但不是跨 Windows/macOS/Linux 的绝对通用配置。**

### Linux 云服务器

相对适合，但需要：

- root 或 systemd capability；
- `CAP_NET_ADMIN`；
- 内核支持 TUN；
- 注意和 Docker、Tailscale、CNI、WireGuard 等路由规则的交互。

AIOS systemd 服务单元已设置：

```text
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
```

### macOS

不建议直接照搬：

- 没有 systemd；
- TUN/utun 权限和启动方式不同；
- DNS hijack 和路由接管可能需要用户授权或 GUI 客户端协作；
- 更适合通过 Mihomo-party、Clash Verge Rev 等客户端管理。

### Windows

也不建议直接照搬：

- 无 systemd；
- TUN 依赖 wintun/service/管理员权限；
- DNS hijack 行为与 Windows 网络栈、Hyper-V/WSL/VPN 共存复杂；
- 更适合用 Windows 原生 Mihomo/Clash 客户端或由 agent 按本机环境安装。

## 当前优化点

模板已经加入：

- `allow-lan: true`，方便局域网设备使用；
- Tailscale/MagicDNS/fake-ip 例外；
- 私有网络直连；
- geodata 自动更新；
- `AI`、`Auto`、`PROXY`、`GLOBAL` 分组；
- `external-ui` 和 UI/geodata mirror URL；
- `fake-ip-filter` 规避 Tailscale；
- `GEOSITE,ai,AI` 让 AI 相关流量走单独测速组。

## 不够通用的地方

- `allow-lan: true`：服务器场景方便，但在不可信局域网有暴露风险。后续可以加 `--mihomo-allow-lan yes|no`。
- `stack: mixed`：在 Linux 上通常可用，但不同 Mihomo 版本/平台可能表现不同。必要时改 `system` 或平台推荐值。
- `dns-hijack`：对服务器透明代理有用，但桌面系统可能和系统 DNS/VPN 冲突。
- `strict-route: false`：更宽松，减少新手断网概率；高隔离场景可能希望 true。
- geodata URL 使用 GitHub 镜像：方便无代理启动，但镜像可用性取决于服务商。

## 后续可加选项

- `--mihomo-allow-lan yes|no`
- `--mihomo-stack mixed|system|gvisor`
- `--mihomo-strict-route yes|no`
- `--mihomo-external-ui-url URL`
- 多 provider 名称，而不是统一 `airport`

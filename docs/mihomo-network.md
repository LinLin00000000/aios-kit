# Mihomo 网络配置 / Mihomo Network Bootstrap

AIOS 的网络 bootstrap 目标是：新云服务器如果不能直连外网，可以快速得到一个可控、可恢复、可审计的代理层。

## 当前定位 / Scope

当前 installer 主要面向 Ubuntu/Debian 云服务器：

- systemd unit：`/etc/systemd/system/aios-mihomo.service`
- 二进制：`~/aios/network/mihomo/mihomo`
- 配置：`~/aios/network/mihomo/config.yaml`
- shell helpers：`proxy_on`、`proxy_off`、`proxy_test`、`proxy_restart`

Windows/macOS 不应直接假设同一套 systemd/CAP_NET_ADMIN/TUN 行为可用。可以使用本文档和 agent-assisted installation 作为适配参考。

## 配置输入 / Configuration inputs

推荐两种输入方式。

### 供应商订阅 URL

```bash
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

## TUN 配置是否通用 / Is the TUN config universal?

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

AIOS systemd unit 已设置：

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

## 当前优化点 / Why this template

模板已经加入：

- `allow-lan: true`，方便局域网设备使用；
- Tailscale/MagicDNS/fake-ip 例外；
- private network direct；
- geodata auto update；
- AI / Auto / PROXY / GLOBAL groups；
- `external-ui` 和 UI/geodata mirror URL；
- `fake-ip-filter` 规避 Tailscale；
- `GEOSITE,ai,AI` 让 AI 相关流量走单独测速组。

## 不够通用的地方 / Non-universal parts

- `allow-lan: true`：服务器场景方便，但在不可信局域网有暴露风险。后续可以加 `--mihomo-allow-lan yes|no`。
- `stack: mixed`：在 Linux 上通常可用，但不同 Mihomo 版本/平台可能表现不同。必要时改 `system` 或平台推荐值。
- `dns-hijack`：对服务器透明代理有用，但桌面系统可能和系统 DNS/VPN 冲突。
- `strict-route: false`：更宽松，减少新手断网概率；高隔离场景可能希望 true。
- geodata URL 使用 GitHub 镜像：方便无代理启动，但镜像可用性取决于服务商。

## 后续可加选项 / Future options

- `--mihomo-allow-lan yes|no`
- `--mihomo-stack mixed|system|gvisor`
- `--mihomo-strict-route yes|no`
- `--mihomo-external-ui-url URL`
- 多 provider 名称，而不是统一 `airport`

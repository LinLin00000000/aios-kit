# Mihomo 网络配置

AIOS 的网络 bootstrap 目标是：新 Linux 服务器如果不能直连外网，可以快速得到一个可控、可恢复、可审计的代理层。

## 当前定位

默认安装位置：

```text
~/aios/network/mihomo/
  build.py          # 生成配置的脚本
  policy.toml       # 非敏感策略配置
  .env.example      # 私有 env 示例
  secrets/.env      # 私有 provider 顺序与订阅 URL
  secrets/config.yaml
  secrets/providers/
```

Linux/systemd 服务：

```text
/etc/systemd/system/aios-mihomo.service
ExecStart=<mihomo-bin> -d ~/aios/network/mihomo -f ~/aios/network/mihomo/secrets/config.yaml
```

Windows/macOS 不应直接套用 systemd/TUN/CAP_NET_ADMIN 行为；可以参考模板，由 Agent 按本机环境适配。

## 最快启动

安装时直接录入单个 provider：

```bash
bash install.sh --proxy yes \
  --proxy-subscription-url "$PRIVATE_SUBSCRIPTION_URL"
```

安装器会：

1. 复制 `templates/mihomo` 模块到 `~/aios/network/mihomo`；
2. 写入 `secrets/.env`：

   ```bash
   MIHOMO_PROVIDERS_ORDER=main
   MIHOMO_PROVIDER_MAIN_URL=...
   ```

3. 调用：

   ```bash
   python3 build.py build
   ```

4. 让 systemd 服务显式使用 `secrets/config.yaml`。

如果想指定 provider id：

```bash
bash install.sh --proxy yes \
  --proxy-provider-id primary \
  --proxy-subscription-url "$PRIVATE_SUBSCRIPTION_URL"
```

## 安装后手动配置

```bash
cd ~/aios/network/mihomo
cp .env.example secrets/.env
$EDITOR secrets/.env
python3 build.py preview
python3 build.py build
python3 build.py check
```

`secrets/.env` 示例：

```bash
MIHOMO_PROVIDERS_ORDER=main,backup
MIHOMO_PROVIDER_MAIN_URL=...
MIHOMO_PROVIDER_BACKUP_URL=...
```

`policy.toml` 只放非敏感策略：分组、规则、默认开关。provider 清单、顺序和订阅 URL 不写进 `policy.toml`。

规则底座可通过 `[rules].mode` 选择：

- `geox`：使用 `geosite.dat` / `geoip.dat`，文件少、启动面小，适合作为 AIOS Kit 网络引导默认值。
- `rule-set`：使用 DustinWin `mihomo-ruleset` 的 MRS/list `rule-providers`，分类更细，适合长期日常代理配置。

如果用 `--proxy-proxies-file` 或安装后有自建节点片段，安装器会调用 `python3 build.py build-local --proxies-file <path>`，继续写入 `secrets/config.yaml`，不再依赖单独的旧版 YAML 模板。

## AIOS Secret Runtime

`build.py` 会先读 `secrets/.env`，再用当前进程环境变量覆盖。因此它天然支持 AIOS Secret Runtime：

```bash
cd ~/aios/network/mihomo
aios secret run --consumer network.mihomo.default -- python3 build.py build
aios secret run --consumer network.mihomo.default -- python3 build.py check
```

consumer 的核心是把 secret 字段映射到 Mihomo build 所需 env：

```yaml
runtime:
  kind: env
  env_map:
    MIHOMO_PROVIDERS_ORDER: providers_order
    MIHOMO_PROVIDER_MAIN_URL: main_url
```

Agent 可以帮助生成 request/consumer metadata，但不能读取或粘贴真实订阅 URL。

## Agent 辅助配置

给 Agent 的安全入口：

```bash
python3 build.py doctor
python3 build.py preview
python3 build.py check
```

不要让 Agent 读取或打印：

```text
secrets/.env
secrets/config.yaml
secrets/providers/**
provider cache
任何订阅 URL、UUID、password、token
```

`preview` 会脱敏 URL，适合审查策略结构；`build` 才会写入敏感生成物。

## TUN 配置是否通用

当前模板适合作为 Linux 服务器默认值，但不是跨平台绝对通用配置：

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

Linux 云服务器通常可用，但需要 root/systemd capability、`CAP_NET_ADMIN` 和内核 TUN 支持。macOS/Windows 更适合通过本机客户端或专门适配流程配置。

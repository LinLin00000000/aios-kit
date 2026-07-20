# Mihomo 配置模块

最快路径：填一个私有 env，生成一个 Mihomo 配置。

```bash
cd /path/to/mihomo
mkdir -p secrets
cp .env.example secrets/.env
chmod 700 secrets
chmod 600 secrets/.env
$EDITOR secrets/.env
python3 build.py preview
python3 build.py build
python3 build.py check
```

`secrets/.env` 最小内容：

```bash
MIHOMO_PROVIDERS_ORDER=main
MIHOMO_PROVIDER_MAIN_URL=你的订阅链接
```

文件分工：

| 文件 | 用途 |
|---|---|
| `secrets/.env` | 私有 provider 顺序和订阅 URL，不提交、不打印 |
| `policy.toml` | 非敏感策略：分组、规则、默认开关 |
| `secrets/config.yaml` | 生成的 Mihomo 配置，不提交、不打印 |

`policy.toml` 的 `[defaults].tun_enable` 控制生成配置是否开启 TUN。AIOS Kit 默认开启；私有 overlay 或本地/Ansible 部署可设为 `false`。

`policy.toml` 的 `[defaults].dns_mode` 控制 DNS 增强模式：

- `fake-ip`：默认值，适合 TUN/透明代理；会返回 `198.18.0.0/16` 合成地址。
- `redir-host`：返回上游解析的公开地址，适合把 Mihomo `1053` 作为系统 DNS 上游，或需要通过 SSRF 公网地址检查的 Agent 工具。

当 TUN 关闭且 Mihomo 只作为显式 HTTP/SOCKS 代理时，通常优先 `redir-host`；不要通过放宽 Agent 的私网 URL 安全策略来兼容 fake IP。

`policy.toml` 的 `[rules].mode` 可在两种基础规则之间切换：

- `geox`：使用 `geosite.dat` / `geoip.dat`，下载对象少，适合 AIOS Kit 网络引导默认值。
- `rule-set`：使用 DustinWin `mihomo-ruleset` 的 MRS/list `rule-providers`，分类更细，适合长期日常配置。

自建节点 YAML 片段仍可用：`python3 build.py build-local --proxies-file /path/to/nodes.yaml` 会生成 `secrets/config.yaml`，但不会把节点内容打印出来。

常用命令：

```bash
python3 build.py preview   # 脱敏预览，不写文件
python3 build.py build     # 生成 secrets/config.yaml
python3 build.py check     # 检查配置；有 mihomo/clash 二进制时会测试配置
python3 build.py doctor    # 给 Agent/人类看的脱敏状态
```

AIOS Secret Runtime 注入也可用：

```bash
aios secret run --consumer network.mihomo.default -- python3 build.py build
aios secret run --consumer network.mihomo.default -- python3 build.py check
```

对应 consumer 只需要把字段映射到这些环境变量：

```yaml
runtime:
  kind: env
  env_map:
    MIHOMO_PROVIDERS_ORDER: providers_order
    MIHOMO_PROVIDER_MAIN_URL: main_url
```

真实订阅值只应进入 `secrets/.env` 或 AIOS Secret Runtime，不要写进命令行、聊天记录、README 或 Git。

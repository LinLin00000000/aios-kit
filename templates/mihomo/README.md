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

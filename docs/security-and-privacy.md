# 安全与隐私策略

## 公开仓库规则

公开的 `aios-kit` 文件必须可迁移：

- 可以提交示例、schema、模板、可复用脚本和通用文档。
- 不要提交机器专属 manifest、live vault 数据、state 文件、日志、secrets、tokens、私有主机名、私有 IP 或私有 agent skill 内容。
- 不要把私人服务卡、资源行、维护事件或用户完整原话仅做改名/脱敏后放进公开 fixture；应从可复用的不变量重新构造纯虚构测试数据。隐私审计既检查字符串，也检查内容来源。
- 不要提交代理订阅 URL、包含 UUID/password 的节点 YAML、服务商 token，或包含私人节点的生成版 Mihomo 配置。
- Mihomo 模块只允许提交 `build.py`、`policy.toml`、`.env.example`、README/AGENTS 和不含私有节点的通用模板；`policy.toml` 只包含非敏感策略（分组、规则、默认开关），provider 顺序和订阅 URL 属于目标机上的 `secrets/.env` 或 AIOS Secret Runtime；`secrets/.env`、`secrets/config.yaml`、`secrets/providers/**` 必须保持私有。

## 本地覆盖文件

这些文件会被有意忽略：

```text
skillpack.local.yaml
manifests/local-assets.local.json
manifests/local-assets.json
registries/*.local.*
profiles/*.local.*
profiles/local-*.yaml
profiles/local-*.json
secrets/
```

它们用于本地路径、私有 skills、当前设备名、非公开仓库和临时/历史 secret materialization。AIOS Secret 模块的正式实例状态在 `$AIOS_ROOT/vault/secrets`，不应提交到 `aios-kit` 公开仓库。

## 公开推送前审计清单

先运行：

```bash
python3 scripts/audit_public.py
./aios doctor
```

再检查：

```bash
git status --short --branch
git ls-files
```

如果仓库曾误提交私有本地路径，在仓库还新、影响面可控时应重写历史；如果真实 secret 已暴露，则应立即轮换或删除相关凭据。

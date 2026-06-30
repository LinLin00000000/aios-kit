# Secret 管理 MVP

AIOS Secret 模块当前是一个轻量的 **Secret Registry + Minimal Secret Runtime**，不是通用密码管理器，也不是常驻凭证代理。

- **Secret Registry**：登记 secret 的身份、用途、consumer、external replica、request、receipt 和 audit，让 Agent 能安全理解“有什么能力、谁能用、同步到哪里”。
- **Secret Runtime**：在运行时安全使用 secret。当前 MVP 唯一支持的 runtime 是 `aios secret run`，即把指定 consumer 需要的字段注入到一个子进程环境变量中。

现阶段暂不实现常驻 broker、HTTP proxy、MCP secret tools、provider plugin 或 session lease。它们只有在多个 AI API consumer 高频使用、env 注入出现真实风险、或多 Agent 需要短期授权时，才进入实现讨论。

## 边界

- Secret 状态属于 AIOS instance：`$AIOS_ROOT/vault/secrets`，默认是 `~/aios/vault/secrets`。
- `items/`、`consumers/`、`replicas/` 是长期 YAML metadata。
- `requests/pending|done|expired/` 是短生命周期 intake transaction，不是长期真源。
- `receipts/` 和 `audit.jsonl` 只记录状态、字段名和验证结果，不包含 secret value。
- `values/` 是本地值后端，权限收紧为 `0600` / `0700`；Agent 不应直接读取它。
- SSH、Caddy 等 app/OS-owned secrets 保持原生路径，AIOS 只索引和校验，不迁移、不软链接。

## CLI

```bash
aios secret layout init
aios secret request init-translation
aios secret request create --manifest ./request.yaml --dry-run --json
aios secret request show req_ai_api_translation_default
aios secret intake req_ai_api_translation_default --dry-run
aios secret intake req_ai_api_translation_default
aios secret list --json
aios secret validate --json
aios secret doctor --json
aios secret show ai-api.translation.default --metadata
aios secret verify ai-api.translation.default --offline
aios secret sync github ai-api.translation.default --replica github.aios-kit.translation --dry-run
aios secret run --consumer aios-kit.translation -- python3 scripts/translate_docs.py --dry-run
aios secret index native --ssh --caddy
```

`aios secret intake` 必须在真实 shell/TTY 中运行。password 字段用 hidden input；CLI 不提供 `--value` 参数，也不会把值写进 receipt、audit、Markdown 或聊天记录。

所有 Agent 可读的 JSON/状态输出都应包含或等价表达：

```json
{"secret_values_exposed": false}
```

## Request manifest

动态 secret intake 应优先使用 manifest，而不是让用户在聊天里粘贴 value，或临时创建长期 `.env` 文件。

最小 manifest 形状：

```yaml
schema_version: 1
request_id: req_example_api_default
kind: secret_intake
secret_id: example.api.default
title: Example API token
created_by: agent
fields:
  - name: api_key
    label: API Key
    type: password
    secret: true
    required: true
    confirm: true
item:
  kind: api_token
  intended_use: [example-api]
  metadata:
    agent_can_read_plaintext: false
consumers:
  - id: example.consumer
    kind: consumer
    uses_secret: example.api.default
    runtime:
      kind: env
      env_map:
        EXAMPLE_API_KEY: api_key
replicas: []
```

创建前可以让 CLI 只校验、不写入：

```bash
aios secret request create --manifest ./request.yaml --dry-run --json
```

CLI 会拒绝明显包含 secret value 的 request manifest。manifest 是短生命周期交易文件；长期真源仍是 intake 后生成的 `items/`、`consumers/`、`replicas/`、`receipts/` 和 `audit.jsonl`。

## Consumer runtime

Consumer 应显式声明运行时投递方式：

```yaml
runtime:
  kind: env
  env_map:
    TRANSLATE_API_KEY: api_key
```

当前只支持：

```yaml
runtime.kind: env
```

为了兼容早期 metadata，顶层 `env_map` 仍可作为 mirror 保留：

```yaml
env_map:
  TRANSLATE_API_KEY: api_key
runtime:
  kind: env
  env_map:
    TRANSLATE_API_KEY: api_key
```

未来如果真实需求出现，可以新增 `runtime.kind: proxy` 或 lease，但它们必须保持可选层，不能污染默认路径。

## 翻译 API profile

默认 request 会创建：

- item：`ai-api.translation.default`
- consumer：`aios-kit.translation`
- replica：`github.aios-kit.translation`

本地翻译工作流推荐通过 consumer 注入环境变量：

```bash
aios secret run --consumer aios-kit.translation -- python3 scripts/translate_docs.py --check-api --dry-run
```

GitHub Actions 仍读取 repo secrets：

- `TRANSLATE_PROVIDER`
- `TRANSLATE_BASE_URL`
- `TRANSLATE_MODEL`
- `TRANSLATE_API_MODE`
- `TRANSLATE_API_KEY`

同步前先 dry-run：

```bash
aios secret sync github ai-api.translation.default --replica github.aios-kit.translation --dry-run
```

确认无误后，用户可以在可信 shell 中执行带 `--yes` 的实际同步。该操作会通过 `gh secret set` 写入 GitHub，不打印 values。

## Validate / doctor

`validate` 和 `doctor` 是给 Agent 使用的低风险探针。它们不读 `values/*.json` 内容，只检查 registry 结构、引用和权限边界。

```bash
aios secret validate --json
aios secret doctor --json
```

它们会检查：

- item / consumer / replica 是否能互相引用；
- consumer `runtime.kind` 是否仍是 MVP 支持的 `env`；
- `runtime.env_map` 和 replica `keys` 是否引用了存在的 item field；
- request manifest 是否没有 value 字段、字段名是否重复、secret field 是否没有默认值；
- app/OS-owned secret 是否声明 `do_not_move` / `do_not_symlink`；
- metadata、receipt、audit 是否没有声明暴露 secret value；
- secret 目录、audit、value backend 是否不是 group/world accessible。

## 旧 env 文件

`~/aios/config/secrets/aios-kit-translation.env` 只是历史 materialization，不是长期真源。`scripts/translate_docs.py` 现在默认只读取环境变量；如需临时兼容旧文件，必须显式传入：

```bash
python3 scripts/translate_docs.py --secret-file ~/aios/config/secrets/aios-kit-translation.env --dry-run
```

当 `ai-api.translation.default` 完成 intake、`aios-kit.translation` 本地运行验证通过、GitHub replica 同步确认后，可以删除旧 env 文件并在 ops 记录中标记为已清理。

## Agent 操作纪律

- 不要要求用户把 API key 粘贴进聊天。
- 不要用 Agent 工具读取 `values/*.json` 或旧 env 文件内容。
- 优先读取 `receipt`、`item`、`consumer`、`replica`、`validate --json`、`doctor --json` 这些 redacted 输出。
- 高风险操作（删除旧 env、修改权限、实际 GitHub sync）先 dry-run，再由用户确认。
- 对外报告只包含 key name、repo、receipt path、metadata path、status，不包含 value。

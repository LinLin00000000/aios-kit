# Secret 管理 MVP

AIOS Secret 模块当前是一个轻量的 **Secret Registry + Minimal Secret Runtime**，不是通用密码管理器，也不是常驻凭证代理。

- **Secret Registry**：登记 secret 的身份、用途、consumer、external replica、request、receipt 和 audit，让 Agent 能安全理解“有什么能力、谁能用、同步到哪里”。
- **Secret Runtime**：在运行时安全使用 secret。当前 MVP 唯一支持的 runtime 是 `aios secret run`，即把指定 consumer 需要的字段注入到一个子进程环境变量中。

现阶段暂不实现常驻 broker、HTTP proxy、MCP secret tools、provider plugin 或 session lease。它们只有在多个 AI API consumer 高频使用、env 注入出现真实风险、或多 Agent 需要短期授权时，才进入实现讨论。

## 边界

- Secret 状态属于 AIOS instance：`$AIOS_ROOT/vault/secrets`，默认是 `~/aios/vault/secrets`。
- `items/`、`consumers/`、`replicas/` 是长期 YAML metadata。item/consumer 新文件默认使用 `<id>.yaml`，发现、查询、校验、run 和登记冲突预检也兼容已有 `<id>.yml` / `<id>.json`；metadata 的规范 `id` 必须与文件名 stem 一致。同一 ID 存在多个兼容文件时拒绝选择或覆盖，不按扩展名优先级挑选；已有单一 alternate 文件复用/替换时不会新增平行 `.yaml`。
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
aios secret generate req_machine_secret --dry-run --json
aios secret generate req_machine_secret --json
aios secret list --json
aios secret validate --json
aios secret doctor --json
aios secret show ai-api.translation.default --metadata
aios secret verify ai-api.translation.default --offline
aios secret sync github ai-api.translation.default --replica github.aios-kit.translation --dry-run
aios secret run --consumer aios-kit.translation -- python3 scripts/translate_docs.py --dry-run
aios secret index native --ssh --caddy
```

`aios secret intake` 必须在真实 shell/TTY 中运行。password 字段用 hidden input；CLI 不提供 `--value` 参数，也不会把值写进 receipt、audit、Markdown 或聊天记录。二次确认默认关闭：一般从网页或密码管理器复制粘贴的 API key、token 等，不需要重复粘贴；只有 request 明确设置 `confirm: true` 时才会启用。

人提供、需要记住或已经存在的凭据走 `intake`；Postgres、Redis、`SESSION_SECRET` 这类不需要人记住的机器随机凭据走 `generate`。`generate` 只处理 pending 的 `secret_intake` request：secret 字段默认用本机 `secrets` 模块生成 32 字节 hex（可用 `generate: true` 和 `length` 明确调整），非 secret 字段必须有 `default`；明显的人类凭据必须显式 `generate: true`，否则 fail closed。它可以在非 TTY、Agent 工具中运行，并沿用 intake 的落盘、receipt 和 audit 路径，但任何输出都不包含明文；不要让 Agent 执行 `openssl rand` 再把结果带入工具输出。

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
    confirm: false
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

`confirm` 是显式 opt-in 开关，默认值为 `false`。只有用户明确要求、凭据特别机密，或其他特殊场景需要降低手工输入错误风险时，才设置 `confirm: true`。创建前可以让 CLI 只校验、不写入：

```bash
aios secret request create --manifest ./request.yaml --dry-run --json
```

CLI 会拒绝明显包含 secret value 的 request manifest。写入预检直接检查原始 `secret_id` 与 `consumers[].id`：必须是非空规范字符串，不会把空白、标点或非字符串 ID 默默清洗/强转后落盘。consumer 省略 `uses_secret` 时仍默认 request 的 `secret_id`；显式给出时必须是非空规范字符串并与 `secret_id` 精确一致，`null`、空字符串或数字都不是省略的替代写法。field 的 `type` 若存在必须为字符串，与 metadata 分类读端采用相同结构规则。`request create --dry-run`、直接 pending 的 generate/intake 均复用这套预检，在生成值或任何 intake prompt 之前拒绝不符合合同的请求，不发布 item/consumer/values/完成 receipt、不消耗 pending；写命令的布局初始化/权限行为仍可能发生，不应把预检失败理解成绝对无 I/O。manifest 是短生命周期交易文件；长期真源仍是 intake 后生成的 `items/`、`consumers/`、`replicas/`、`receipts/` 和 `audit.jsonl`。

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

### 共享 consumer schema，单次选择一个 binding

`item` 不等于“一条密码”：一个 item 可以有多个独立命名字段，固定 consumer 的 `env_map` 可以只映射其中一部分。适合同账户、同信任和生命周期的多字段凭据；Runtime 仍会在本进程内读取所选 item 的整个值后端，因此跨站总包不是字段级存储隔离。不要为了减少 YAML 数量而把所有站点秘密默认注入同一子进程。

多个已有 item 如果使用同一注入 schema，可以登记一份共享 consumer metadata，而不复制多个 consumer 文件：

```yaml
schema_version: 1
id: example.account-api
kind: consumer
bindings:
  site-a:
    uses_secret: example.site-a.account
  site-b:
    uses_secret: example.site-b.account
  historical:
    uses_secret: example.site-old.account
    enabled: false
    status: retired
runtime:
  kind: env
  env_map:
    EXAMPLE_PAT: pat
    EXAMPLE_ACCOUNT: account
```

上例的每个 item 都必须声明 `pat`、`account` 字段，映射字段的 metadata 必须是对象并明确给出布尔 `secret`：例如 `pat: {type: password, secret: true}`、`account: {type: string, secret: false}`。`password`/`secret`/`token` 类型不能标为 `secret: false`；`secret: true` 的 metadata 不能携带 `value`。run 在读取值后端前检查所映射字段，validate 复用同一规则，不把缺分类的 metadata 当成安全兼容。该字段分类要求对所有 consumer 模式生效，不只是共享 schema：旧固定 `uses_secret` consumer 若映射字段的 metadata 缺少显式布尔 `secret`（或类型与分类冲突、结构畸形），升级后 run 会拒绝、validate 报错。这是有意的 fail-closed 收紧，AIOS 不会替用户改写已有 item，需要时由用户补齐 metadata 或调整 `env_map`。binding 只选择来源，不允许覆盖共享 `runtime.env_map`。条目只允许 `uses_secret`、可选布尔值 `enabled` 和可选 `status`（`active`/`configured`/`retired`/`disabled`）。默认启用且状态为 `active`；`enabled: false` 或退休/禁用状态拒绝运行。binding key 和来源 ID 必须是规范标识，选择时精确匹配，不会把未知 key 清洗成另一个已登记 key。

```bash
aios secret run --consumer example.account-api --binding site-a -- python3 account_job.py
```

- 多个 bindings **必须**显式传 `--binding`，即使其中只有一个启用；唯一 binding 可省略，仍检查其启用状态。每次只加载一个 item，并只注入该 item 的映射字段。没有任意 `--secret` 覆盖入口。
- `uses_secret` 固定模式和 `bindings` 模式互斥。旧固定 consumer 的 `runtime.env_map` 或顶层 `env_map` 用法不变（上面那条字段分类要求对旧固定模式同样生效），但不能传 `--binding`。
- 共享 binding 模式只允许 `item.status: configured`；缺失、`null`、空状态及显式 `retired`、`disabled` 或其他状态都在读取值前拒绝。只有旧固定 `uses_secret` 模式保留未声明/`null`/空状态的兼容例外。退休记录和秘密无需删除。
- 运行审计记录最终 `secret_id`、`consumer_id`、所选 `binding`、命令名和退出码，不包含值；固定模式的审计形状不变。输出继续经过脱敏。子进程沿用父进程环境，这不是环境沙箱或额外的命令/身份授权层。
- 共享 consumer 本轮只支持 `run`，不支持 `rotate`；带 `bindings` 的 rotation 配置会被 validate/doctor 报错，rotate 明确拒绝。既有固定 consumer 的字段 rotation 白名单不扩权。

### 单 item request 与共享 consumer 的登记边界

Intake/generate request 仍是一个 `secret_id` 的事务，只能创建固定 consumer；request 中出现任何 `bindings` 都会拒绝。共享 consumer 需独立维护在 `consumers/` 的 metadata 中，不通过各站 request 反复创建同名 consumer。新站 request 可以使用 `consumers: []`，随后把 item 加入已有 consumer 的 binding 白名单。

已有固定 consumer 只有在规范化后的 metadata 语义完全一致时才能被 request 复用（忽略创建/更新时间），并且不会重写该文件。不同来源、不同 env_map、额外 metadata 或共享 consumer 都会触发冲突；`--force` 也不能绕过。CLI 在提示/生成值之前检查全部 consumer 冲突，并在写入路径再次检查。重复登记同一个 consumer 也会拒绝；新 consumer 使用排他创建，不能覆盖并发出现的不同登记。新 consumer 在排他创建前先完成 JSON 序列化（文件仍是有效 YAML 1.2）；写入失败只会尽力删除仍属于本次 inode 的未完成文件，不删除已被并发替换的文件。该预检不是整个 request 的跨进程事务锁，也没有批量 consumer 回滚：若第二个 consumer 在预检后才发生竞争冲突，首个新 consumer 的 metadata 可能留下，但该失败路径不改既有 values、保留 pending request、且无完成 receipt。metadata 的并发编辑仍应避免。

`intake --force`/`generate --force` 是整体替换该 item 的字段和值，不是增量追加。已有多字段 item 的局部更新应保留固定 consumer 的明确 rotation 字段白名单，不能以共享 schema 为由放宽。

共享 schema 真正减少了 consumer registry 对象，不只是省去手写 YAML；它不要求复制或迁移已有 item/秘密。`secret list --json` 和 `secret show --metadata` 的 `consumers` 当前视图只从 consumer 的固定引用和 bindings 派生；item 内旧记录单列为 `declared_consumers`（声明/历史，不是当前关系或授权），不改写或删除原 item。`consumer_bindings` 展示 binding key、启用状态和状态（包括禁用/退休条目），不读取值后端。consumer 反向扫描逐文件隔离解析、结构、空 bindings 和重复文件错误，保留健康文件的关联；`secret list --json` 返回 `consumer_reference_problems`（安全的 path/code/message，不回显坏内容）以及全局和每个 item 的 `consumer_references_complete`，`secret show --metadata` 只给该 item 的 `consumer_references_complete` 和同一诊断列表、没有全局键。标记为 false 的关联只是部分视图，不能把缺失关联理解成没有 consumer；文本 list 也显示完整性和诊断。注意两侧策略不对称：item 侧不做逐文件隔离，item metadata 解析失败、同一 ID 存在多个兼容文件、或 metadata `id` 与文件名 stem 不一致时，`list`/`show`/`validate` 直接 fail closed（错误退出，不返回 JSON 结果），不会跳过坏记录继续列出其他 item；升级前应先用 validate 找出并修正这类历史记录。run 对所选 consumer/item 继续 fail closed，validate/doctor 对坏登记报错。validate/doctor 增加 `binding_consumers`、`consumer_bindings` 数量，并检查 pending request 的登记冲突；done/expired 历史只做 manifest 结构校验，不要求历史 consumer 与当前登记一致。

`show --metadata` 对敏感类型（复用 `password` / `secret` / `token` 分类）、缺失或非布尔 `secret`、类型冲突、畸形 type/字段对象保守脱敏；异常单字段替换为 `value_status: redacted_invalid_metadata`，异常 fields 容器替换为空对象并标记 `fields_status`，不把原始坏内容用于诊断。仅明确 `secret: false` 且类型非敏感、结构合法的字段允许保留 metadata `value`；因此该输出仍是 secret-adjacent，不应无需要地存档非秘密值。查询不读取值后端。

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

`list`、`show --metadata`、`validate` 和 `doctor` 不读 `values/*.json` 内容；这些查询/报告不创建布局或 audit、不 chmod 现有路径。缺失实例的 list 返回空 item 列表，show 报 metadata 不存在，validate/doctor 报缺失 root；未使用/缺失的其他布局路径给出 warning，而不是在校验时自动补齐。布局创建与权限收紧仍由显式初始化或写入操作承担。validate/doctor 检查全部 item 字段的分类规则、item/consumer 文件 ID 约定及重复文件，并保持失败返回码；坏 metadata 解析诊断不包含原始内容。

```bash
aios secret validate --json
aios secret doctor --json
```

它们会检查：

- item / consumer / replica 是否能互相引用；
- consumer `runtime.kind` 是否仍是 MVP 支持的 `env`；
- consumer 固定来源或每个 binding（包括禁用/退休条目）是否引用存在的 item，以及共享 `runtime.env_map` 是否在各 item 上有对应 field；
- 固定来源和 bindings 是否互斥，binding 条目是否合法，是否误配置共享 consumer rotation；
- replica `keys` 是否引用了存在的 item field；
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

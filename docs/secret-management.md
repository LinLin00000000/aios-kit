# Secret 管理 MVP

AIOS Secret 模块提供一个轻量的 credential control plane：Agent 可以管理 secret 的身份、用途、consumer、external replica 和 receipt，但默认不读取、不打印、不记录密钥明文。

## 边界

- Secret 状态属于 AIOS instance：`$AIOS_ROOT/vault/secrets`，默认是 `~/aios/vault/secrets`。
- `items/`、`consumers/`、`replicas/` 是长期 YAML metadata。
- `requests/pending|done|expired/` 是短生命周期 intake transaction。
- `receipts/` 和 `audit.jsonl` 只记录状态、字段名和验证结果，不包含 secret value。
- `values/` 是本地值后端，权限收紧为 `0600` / `0700`；Agent 不应直接读取它。
- SSH、Caddy 等 app/OS-owned secrets 保持原生路径，AIOS 只索引和校验，不迁移、不软链接。

## CLI

```bash
aios secret layout init
aios secret request init-translation
aios secret request show req_ai_api_translation_default
aios secret intake req_ai_api_translation_default
aios secret list --json
aios secret show ai-api.translation.default --metadata
aios secret verify ai-api.translation.default --offline
aios secret sync github ai-api.translation.default --replica github.aios-kit.translation --dry-run
aios secret run --consumer aios-kit.translation -- python3 scripts/translate_docs.py --dry-run
aios secret index native --ssh --caddy
```

`aios secret intake` 必须在真实 shell/TTY 中运行。password 字段用 hidden input；CLI 不提供 `--value` 参数，也不会把值写进 receipt、audit、Markdown 或聊天记录。

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

## 旧 env 文件

`~/aios/config/secrets/aios-kit-translation.env` 只是历史 materialization，不是长期真源。`scripts/translate_docs.py` 现在默认只读取环境变量；如需临时兼容旧文件，必须显式传入：

```bash
python3 scripts/translate_docs.py --secret-file ~/aios/config/secrets/aios-kit-translation.env --dry-run
```

当 `ai-api.translation.default` 完成 intake、`aios-kit.translation` 本地运行验证通过、GitHub replica 同步确认后，可以删除旧 env 文件并在 ops 记录中标记为已清理。

## Agent 操作纪律

- 不要要求用户把 API key 粘贴进聊天。
- 不要用 Agent 工具读取 `values/*.json` 或旧 env 文件内容。
- 高风险操作（删除旧 env、修改权限、实际 GitHub sync）先 dry-run，再由用户确认。
- 对外报告只包含 key name、repo、receipt path、metadata path、status，不包含 value。

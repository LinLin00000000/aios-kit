# Matter 索引、生命周期与交付物视图

AIOS 将单个 Worksite 的文件协议与跨事务管理分开：

```text
Worksite files                    # 真源
  internal/matter.json
  mission.md
  internal/recovery.json
        ↓ 扫描生成
~/aios/state/matters/index.json   # 可重建派生索引
        ↓ 生成
~/aios/view/matters/              # 只读的人类交付物视图
```

## 状态模型

统一索引使用四种生命周期状态：

- `active`：Matter 仍在推进；
- `paused`：当前不占注意力，但准备继续；
- `closed`：目标已结束，默认不再续作；
- `archived`：工作现场已进入长期归档。

`reopenable` 是独立维度。一个重要 Matter 可以保持 `active`，同时把 `attention` 设为 `paused`，表示“现在不执行，但自然语言提到时应重新打开”。

Worksite 中可显式声明：

```json
{
  "lifecycle": {
    "state": "active",
    "attention": "paused",
    "reopenable": true,
    "current_phase": "dogfooding"
  }
}
```

没有 `internal/matter.json` 的历史 LLL Worksite 会以 `inferred_worksite` 进入索引，方便发现和后续分类；索引不会反向成为状态真源。

## 查询与续作

```bash
aios matter index
aios matter list --reopenable
aios matter list --state active --query workflow
aios matter get "工作流设计"
```

Agent 收到“继续工作流这个事务”时，应优先检索 `active` / `paused` 且 `reopenable` 的记录，然后从该 Worksite 的 Mission 和 Recovery 恢复。

`matter list/get` 每次从 Worksite 文件现场编译当前结果，但不写 `index.json`；它们可以安全用于只读 reviewer。只有显式 `aios matter index` 持久化派生索引，`matter view build` 在生成 View 时也会刷新索引。

## Current Worksite rollover

`aios matter rollover <exact-matter-id>` 是窄范围的 Current Worksite 事务执行器，只接受正式 Matter 的精确 ID。默认是零写入 dry-run；真实写入必须同时提供 `--apply` 和 durable `--authorization-ref`。计划必须冻结并传入：

- 完整 expected-current 对象（ID、绝对路径、role；owner/binding/recovery 字段由协议补齐）；
- `internal/matter.json` SHA-256；
- `internal/matter.events.jsonl` SHA-256 和非空行数；
- 目标 Worksite ID、绝对路径和 role；
- idempotency key 与绑定完整 pass-1 candidate 的 `sha256:<digest>` fence token。

```bash
aios matter rollover <exact-matter-id> \
  --expected-current-id <id> \
  --expected-current-path /absolute/current/worksite \
  --expected-current-role latest_completed_baseline \
  --expected-matter-sha256 <sha256> \
  --expected-events-sha256 <sha256> \
  --expected-event-line-count <n> \
  --to-worksite /absolute/target/worksite \
  --to-worksite-id <mission-id> \
  --to-role current_canonical \
  --idempotency-key <stable-key> \
  --fence-token sha256:<candidate-digest> \
  --json
```

目标 `mission.md` 的 `mission_id` / `parent_matter_id` / `parent_worksite` 和 `internal/recovery.json` 必须可验证，lifecycle status 必须一致且只能为 `active` 或 `completed`。正式 current Worksite 绑定统一使用生命周期中性的 `current_canonical`；Worksite 后续 closeout 不触发第二次 role-only rollover。另一正式 Matter 已认领目标时 fail closed。正式 Matter owner discovery 只遍历每个声明 root 的实体直接子目录，跳过顶层 symlink，并要求 child realpath 保持在 root realpath 内。

`--authorization-ref` 不是任意标签：apply 与 rollback apply 都要求它指向存在、可读的 durable JSON，schema 必须为 `aios.phase_b.authorization.v1`；`scope.worksite` 必须等于本次 full-chain current Worksite，`scope.parent_worksite` / `scope.parent_matter` 必须分别匹配目标 Mission 的父 Worksite / exact Matter，并且 `authorized` 必须包含 exact B6 rollover operation。引用不存在返回 `AUTHORIZATION_REF_NOT_FOUND`，scope/operation 不匹配返回 `AUTHORIZATION_SCOPE_MISMATCH`；两者都在 lock、receipt 和 canonical write 之前 fail closed。

apply 在 `~/aios/state/matters/locks/` 获取 Matter-scoped non-blocking `fcntl` lock，并在锁内重做 target fence 与 expected-current/CAS。Matter 与 event stream 每次原子替换都在**紧邻 replace 之前**再次核对 exact expected-current hash；检查/使用窗口内出现并发事实时返回 `CANONICAL_CAS_MISMATCH`，不覆盖该事实。receipt 位于 `~/aios/state/matters/change-sets/`，状态依次为 `prepared` → `canonical_committed` → `projections_committed`。receipt digest 覆盖 replay 会读取的 state、冻结 candidate/canonical guards、authorization binding 和 rollback digest；任何 tamper 都必须先返回 `RECEIPT_INTEGRITY_MISMATCH`，不能走成功短路。

同 key、同计划重试会从 receipt 恢复 snapshot/event split commit 或只重建 projection；同 key 或同 target receipt slot 的不同计划返回 `IDEMPOTENCY_CONFLICT`。canonical 已成功但 index/View 失败时状态为 `projection_pending`，不会自动逆转 canonical Matter，必须使用同 key 重试。该 post-commit retry 在锁下直接加载并验证原 receipt binding/digest，核对当前 canonical Matter/event receipt guards 和目标 identity/status，然后按 receipt 冻结的 target snapshot 重建派生 projection；它不从已变化的 target recovery bytes 重新生成 candidate，因此无关 recovery churn 不会错误返回 `FENCE_TOKEN_MISMATCH`。

compiler 先收集正式 owner claims，再编译记录：正式 Matter 指向另一个 Worksite 时，目标不会同时生成 `inferred_worksite` duplicate。View 先完整写入 sibling staging tree；已有 View 通过 Linux `renameat2(RENAME_EXCHANGE)` 一次交换新旧完整 generation，避免“先删旧 View”窗口。

guarded rollback 只接受默认 change-set 目录中的精确 receipt 路径和 `--expected-receipt-id`；默认仍为 dry-run，apply 仍要求 authorization ref：

```bash
aios matter rollover <exact-matter-id> \
  --rollback ~/aios/state/matters/change-sets/<receipt>.json \
  --expected-receipt-id <receipt-id> \
  --apply --authorization-ref <durable-ref> --json
```

只有 Matter postimage hash 与 event stream hash、行数、尾 event ID 全部仍匹配 receipt guard 才会 rollback；否则 `ROLLBACK_GUARD_MISMATCH`，不会覆盖后来的事实。成功 rollback 更新 current pointer 并追加 `worksite.migration_compensated` 事件，而不是删除 rollover 事件。

## 精简交付物视图

Matter 可以声明精选文件：

```json
{
  "delivery": {
    "featured": ["final-report.md", "decision.md"],
    "limit": 8
  }
}
```

生成静态视图：

```bash
aios matter view build
```

输出位于 `~/aios/view/matters/`。每个 Matter 只展示：

- `mission.md`；
- 显式 `delivery.featured`；
- 没有显式配置时，少量根级最终报告/摘要。

视图使用指向真源文件的软链接，不复制内容，不展示 `internal/`。HTTP 文件服务只需暴露该 View，不需要暴露整个 `~/lll-work`。

## Closeout 与回收站

先生成只读计划：

```bash
aios lll closeout-plan <matter-or-worksite>
aios lll closeout-plan <matter-or-worksite> --write
```

`--write` 将机械分类结果保存到 `~/aios/state/matters/closeout-plans/` 并返回 `plan_path`。这是 closeout plan，不是已评估、已授权或可执行的 promotion change set。

计划区分：

- `promote_candidates`：可进入语义评估的根交付物候选，不等于已判断值得沉淀；`mission.md` 只保留为工作契约/provenance，不因出现在 View 中自动成为资产候选；
- `archive_candidates`：重型过程证据，需要审阅后归档；
- `quarantine_candidates`：缓存等可回收内容；
- `requires_approval`：不能静默执行的动作。

对调研类交付物，Agent 在 closeout 自然收尾点执行一次 **Asset Retention Gate**：按复用/决策价值、重建成本、独立可读性、证据质量和 owner/维护适配度给出 `0–100` 分、置信度、时效性与具体落点建议。只有 `>=65` 且存在合理 owner 时才主动询问一次；`<65` 默认留在 Worksite，不制造保存弹窗。无论分数多高，当前都不自动 promotion：只有用户明确表达“保存为资产”等意图后，才生成并执行独立 change set。原 Worksite 文件默认保留不动。

`closeout-plan` 只负责机械分类，因此 `asset_retention_gate.status=awaiting_agent_assessment`、`semantic_score=null`。CLI 不假装能用文件名判断知识价值；语义评估由 Agent 完成，授权由 Human 完成，确定性复制/链接/校验再交给 CLI/script。

首次真实 promotion 形成了窄的只读验证面；第二次同边界 promotion 已补充最小 copy-if-absent 执行面。明确授权的 change set 先 dry-run，只有传入 `--apply` 才复制：

```bash
aios promotion apply <authorized-pending-change-set.json>
aios promotion apply <authorized-pending-change-set.json> --apply
aios promotion validate <change-set-or-receipt.json>
aios promotion undo-check <change-set-or-receipt.json>
```

`apply` 仅接受 `authorized_pending`、显式授权、Managed Zone 内、目标不存在、原 Worksite 保留的 copy-only change set；change set、Worksite 与 Asset 身份，owner、备份边界、undo、hash、文件名、目标范围，以及源/目标目录互不重叠，都必须在首次目标写入前通过。它先在目标同级 staging 复制并核对 hash，再使用 Linux 原子 no-replace 安装目录，绝不替换已有目标；随后写回 change set。若进程恰好在“目标已安装、change set 未更新”之间中断，重试会核对目标目录与 receipt 后只补完 change set，不重复复制。已完成 change set 的重复执行只重新验证。当前执行面遇到不支持原子 no-replace 的非 Linux 平台会 fail closed。它不支持 move、rename、delete、overwrite、bulk curation，也不替代语义评分与 Human 授权。

`validate` 检查 change set ↔ receipt 绑定、Source owner、Managed Zone containment、精确文件集合、源/目标/receipt hash、copy-only/no-overwrite/no-source-mutation 和 Backup Gate 边界。`undo-check` 复用同一只读检查，只报告“目标目录当前是否满足撤销前置条件”；它不删除文件，也不替代人类授权。`backup_status=planned` 时只接受“原 Worksite 独立保留”的 copy-only promotion，不放行 move/delete/overwrite/bulk curation。

整个 Worksite 只有在 `closed` 且 `reopenable=false` 时才能进入回收站：

```bash
aios lll quarantine <matter-or-worksite>          # dry-run
aios lll quarantine <matter-or-worksite> --apply
aios lll restore <token>                          # dry-run
aios lll restore <token> --apply
```

回收站位置是 `~/aios/data/quarantine/worksites/`，恢复清单位于 `~/aios/state/matters/quarantine/`。当前实现不提供永久 purge；永久删除应在备份/恢复验证与保留期之后另设审批动作。

## 边界

- LLL 负责单个 Worksite 的 task/run/recovery/validation；
- AIOS 负责跨 Worksite 的索引、查询、生命周期编译和 Viewer；
- 派生索引与 HTML View 均可删除重建；
- Asset promotion 的目标 owner 仍可能是项目文档、OPS vault、Managed Zone 或数字花园，不由索引目录替代；
- 完成一个 Task 不自动关闭 Matter；Matter closeout 与 Task closeout 必须分开。

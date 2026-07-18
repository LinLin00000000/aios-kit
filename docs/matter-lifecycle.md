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

首次真实 promotion 已形成一个窄的只读验证面。对于已应用的 `aios.asset-promotion-change-set.v0` 或目标目录内的 `aios.asset-promotion-receipt.v0`：

```bash
aios promotion validate <change-set-or-receipt.json>
aios promotion undo-check <change-set-or-receipt.json>
```

`validate` 检查 change set ↔ receipt 绑定、Source owner、Managed Zone containment、精确文件集合、源/目标/receipt hash、copy-only/no-overwrite/no-source-mutation 和 Backup Gate 边界。`undo-check` 复用同一只读检查，只报告“目标目录当前是否满足撤销前置条件”；它不删除文件，也不替代人类授权。`backup_status=planned` 时只接受“原 Worksite 独立保留”的 copy-only promotion，不放行 move/delete/overwrite/bulk curation。

当前尚不提供通用 promotion apply engine。评分、owner 判断、授权和 change set 编译继续由 Agent/Human 完成；只有第二次真实 promotion 再次复现同一机械复制/receipt 劳动或 validator 暴露 apply 不一致时，才把 copy-if-absent apply 下沉为同边界 actuator。

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

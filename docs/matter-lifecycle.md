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

计划区分：

- `promote_candidates`：精选成果；
- `archive_candidates`：重型过程证据，需要审阅后归档；
- `quarantine_candidates`：缓存等可回收内容；
- `requires_approval`：不能静默执行的动作。

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

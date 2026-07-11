# AIOS 演化协议

`aios-kit` 不是功能越多越好的工具合集，而是 Personal AIOS 的最小可迁移骨架。它的演化目标是让 Agent 能围绕用户真实数字世界持续、安全、可恢复地工作，同时尽量减少偶然复杂度。

本文档是 AIOS 演化协议、模块成熟度地图和复杂度预算的真源。README、开发文档和 skills 只做入口引用，不复制整套原则。

## 核心原则

1. **广度优先**：优先让关键模块都有最小生命体征，而不是让单个模块过早做深做全。
2. **渐进增强**：先建立共同现实层，再补执行面；先文件化状态和验证探针，再考虑 daemon、service、CI/CD 或 UI。
3. **Human / Agent / CLI 分层**：Human 负责方向、价值、风险授权和验收；Agent 负责理解、判断、协调和控制权切换；CLI/script 负责可重复、可校验、低歧义的确定性结构动作。
4. **模块同步演化**：模块之间应保持概念成熟度基本协调。某个模块只有在明显阻碍整体闭环时才继续加深。
5. **复杂度预算**：新增能力必须说明它减少了哪些重复、风险、人工步骤或泄漏面；如果只是“未来可能有用”，默认不加。
6. **证据驱动**：真实失败模式、重复摩擦、验证缺口和用户明确需求，比抽象架构完整性更重要。
7. **文档是真源，skill 是薄入口**：复杂原则放在 repo 文档；skill 只负责触发、路由和安全边界，避免多处复制同一套规则。
8. **语义层优先于平台锁定**：Matter、Decision、Approval、Artifact、Asset 等工作流概念应先作为协议语义表达，再投影到 Kanban、GitHub、runner、UI 或企业系统。

## 第一性原理

AIOS 的核心不是自动化一切，也不是功能堆叠，而是建立 Agent 可依赖的共同现实层：项目、资源、密钥、任务、服务、文档、状态和证据都能被找到、验证和恢复。

因此，每个模块优先回答三个问题：

- 它让 Agent 更容易找到什么事实？
- 它让 Agent 更安全地执行什么动作？
- 它留下了什么可恢复证据？

不能清楚回答这些问题的功能，默认不进入核心路径。

## 本质复杂度与偶然复杂度

本质复杂度只能被命名和隔离，不能假装不存在：

| 领域 | 本质复杂度 |
|---|---|
| Projects / Resources | 同一对象可能有本地路径、远程 repo、alias、状态和运行位置 |
| Secrets | Agent 不能看明文，但运行时需要可信边界使用密钥 |
| LLL | 长任务需要状态、恢复、证据和交接 |
| OPS Vault | 私有事实不能进入公开 repo，但 Agent 需要知道在哪里查 |
| Skills | Agent 需要程序性记忆，但 skill 过多会污染触发与维护 |
| Updates | upstream base 与用户实例会长期分叉，必须 reconcile |

偶然复杂度应主动删除或推迟：

- 为假想未来需求提前做 daemon、broker、runner、dashboard；
- 每个模块都做 plugin 系统；
- 每个原则都拆成新 skill；
- 同一规则在 README、docs、skill、OPS log 中重复维护；
- 用数据库隐藏本可文件化表达的状态；
- 某个模块局部做深，导致整体概念失衡；
- 巡查报告很多，但没有决策价值。

## 模块成熟度地图

成熟度不是承诺排期，而是约束“下一步最多做什么”。

| 模块 / 能力 | 当前阶段 | 已有最小闭环 | 下一步候选增强 | 暂不做 |
|---|---|---|---|---|
| Project / Resource registry | L1 | `aios project ...`、alias、registry 文件 | 更稳定的 JSON/status/doctor 输出 | 完整项目管理系统 |
| Data Sources | L1 | `aios source list/get/add/alias/validate`、显式 Source records + Project 投影、Managed Zone 目录边界 | 从真实设备接入中补 inventory/backup/sync adapter | 全盘摄取、数据库、通用文件管理器 |
| Secret management | L1.5 | request → intake → metadata/consumer/replica → run/sync/audit；`doctor`/`validate` 提供低风险探针 | 更通用的 provider preset 文档/模板；仅在真实摩擦出现后考虑可选 proxy/lease | 常驻 broker、默认 proxy、MCP secret tools、plugin 系统 |
| LLL integration | L1 | `aios lll ...` 发现、创建、状态代理 | 更清楚地表达 AIOS 只代理不吞并 LLL 状态机 | 在 `aios-kit` 中重写 LLL runner |
| OPS vault | L1 | 模板与 live vault 分离，OPS skill 入口 | 更好资源索引和维护记录模板 | 把公开 repo 变成私有 CMDB |
| Skillpack | L1 | sync/adopt/doctor/dev-link | 更好的冲突解释和 reconcile 输出 | 接管整个 runtime skills 目录 |
| Assets | L0/L1 | manifest、doctor、link | 只做发现和链接纪律 | 通用文件管理器 |
| Agent governance | L1 | `aios-agent` skill、开发文档、自迭代规则 | 用本文件统一演化判断 | 新建一堆原则 skill |

## 增强决策门槛

新增能力前，维护者或 Agent 应回答：

1. 它解决的是真实摩擦，还是想象中的未来完整性？
2. 它减少了哪些重复配置、泄漏风险、手工步骤或恢复成本？
3. 它是否能作为可选层存在，而不是污染默认路径？
4. 它是否需要新的长期状态、后台进程、权限边界或维护面？
5. 它是否应该先写进文档或 roadmap，而不是立即实现？

如果答案不清楚，默认只记录为候选增强，不实现。

## Secret 模块示例

Secret 模块当前保持 L1.5：密钥登记、录入、consumer、replica、receipt、audit、`aios secret run`、`doctor` 和 `validate` 已形成一个可诊断的最小闭环。

可以采用以下语言区分边界：

- **Secret Registry**：登记密钥身份、用途、consumer、replica、request、receipt 和 audit。
- **Secret Runtime**：在运行时安全使用密钥。当前唯一承认的最小 runtime 是 `aios secret run`。

暂不实现：常驻 broker、proxy、MCP secret tools、provider plugin、session lease。它们只有在多个 AI API consumer 高频使用、env 注入出现真实风险或多 Agent 需要短期授权时，才进入实现讨论。

## 自动化与巡查

AIOS 可以在未来引入项目健康巡查，但默认不从本地 cron 或常驻 Agent 开始。更优先的方向是 GitHub CI/CD 或其他云端工作流：检查文档漂移、public audit、skillpack 分发、模块健康和安装 smoke test。

当前阶段只记录原则，不实现巡查命令、cron、daemon 或 workflow。自动化应在流程稳定、检查项明确且能给出可执行建议后再加入。

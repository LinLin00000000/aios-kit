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
7. **一个事实一个 owner，入口保持薄**：复杂原则和协议由明确文档或配置拥有；README、skill、memory、产品说明、投影和 Worksite 只能按各自角色引用、解释或保存证据，不能手工维护多份独立正文。
8. **语义层优先于平台锁定**：Matter、Decision、Approval、Artifact、Asset 等工作流概念应先作为协议语义表达，再投影到 Kanban、GitHub、runner、UI 或企业系统。
9. **实例策略有 scope 与 lifecycle**：跨任务、可合理关闭、显著影响交互/成本/风险的本地行为，才进入 AIOS-managed policy；使用少量模式和明确退出条件，避免布尔开关与永久兼容层膨胀。
10. **管理即上下文工程**：数据资产、服务器、服务资源、云服务、项目和行动能力默认是多层 owner context，不是必须预先注册的管理对象；Agent 先加载上下文、理解和选择，只有稳定跨任务事实、资源边界或安全回读确实需要时才持久化登记。
11. **官方能力优先**：新接入先查官方 CLI、官方 Skill、官方 MCP 和官方文档，再考虑 AIOps service card、薄引导 Skill、accepted narrow script，传统 API 直连最后考虑。
12. **动态发现、最终精确绑定**：自然语言入口不要求固定字符串匹配；Agent 从 compact candidates 语义选择 owner，精确 ID、路径、remote、版本和 consumer 只在最终 action/resource binding、执行和审计边界出现。

## 第一性原理

AIOS 的核心不是自动化一切，也不是功能堆叠，而是建立 Agent 可依赖的共同现实层：项目、资源、密钥、任务、服务、文档、状态和证据都能被找到、验证和恢复。

因此，每个模块优先回答三个问题：

- 它让 Agent 更容易找到什么事实？
- 它让 Agent 更安全地执行什么动作？
- 它留下了什么可恢复证据？

不能清楚回答这些问题的功能，默认不进入核心路径。

## 上下文工程作为默认管理模型

AIOS 将“管理”理解为：在当前任务中，为 Agent 按需提供足够的上下文，让它能够理解对象、选择 owner、调用正确执行器并留下必要证据。

这适用于：

- 数据资产：数据根、敏感等级、来源和可逆边界；
- 服务器与设备：节点身份、连接入口、授权范围和运行事实；
- 服务与云资源：compact service catalog、owner card、官方入口和动作边界；
- 项目：当前目录、项目本地文档、Git remote/tree 和必要的长期 owner 事实；
- Skill 与行动能力：触发条件、操作规则、官方执行器、Secret consumer 和动作验收。

推荐的上下文梯度是：

```text
Bootstrap
  → compact candidates
  → selected owner context
  → action/resource context
  → deterministic binding and receipt
```

上下文层不是新的全局注册表。每层只加载下一步所需的内容；候选由 Agent 语义选择，最终的路径、ID、版本、consumer 和权限边界由确定性执行器或 owner contract 校验。没有稳定跨任务边界的对象，不因“未来可能需要管理”而登记。

因此，新增一个管理模块前必须先证明：

1. Agent 无法从现有 owner context 和官方入口恢复所需事实；
2. 该事实需要跨任务稳定保存，或必须作为安全/审计边界；
3. 新模块不会复制另一个 owner 的正文、状态、授权或执行器；
4. 删除它会让真实任务失败，而不是只让目录或命令看起来不完整。

## 本质复杂度与偶然复杂度

本质复杂度只能被命名和隔离，不能假装不存在：

| 领域 | 本质复杂度 |
|---|---|
| Projects / Resources | 同一对象可能有本地路径、远程 repo、alias、状态和运行位置，但不代表都需要中央登记 |
| Context loading | Agent 需要逐层加载足够上下文，同时避免全文常驻、递归加载和上下文重复 |
| Secrets | Agent 不能看明文，但运行时需要可信边界使用密钥 |
| LLL | 长任务需要状态、恢复、证据和交接 |
| OPS Vault | 私有事实不能进入公开 repo，但 Agent 需要知道在哪里查 |
| Skills | Agent 需要程序性记忆，但 skill 过多会污染触发与维护 |
| Updates | upstream base 与用户实例会长期分叉，必须 reconcile |

偶然复杂度应主动删除或推迟：

- 为假想未来需求提前做 daemon、broker、runner 或 dashboard；
- 把每个项目、服务、数据资产或动作都登记进中央 registry，只为让入口看起来统一；
- 为了替代字符串入口而新建 Context Registry、向量搜索或常驻 context compiler；
- 每个模块都做 plugin 系统；
- 每个原则都拆成新 skill；
- 同一规则在 README、docs、skill、OPS log 中重复维护；
- 用数据库隐藏本可文件化表达的状态；
- 某个模块局部做深，导致整体概念失衡；
- 巡查报告很多，但没有决策价值。

### 精简决策协议

任何精简动作都按以下顺序判断；“最少代码”不是独立的验收标准：

1. **先理解再缩短**：先读真实流程、相关调用者、事实 owner 和验收边界，不用最短实现替代理解。
2. **先问是否需要存在**：如果核心工作不依赖它，优先删除或推迟；推迟项要有具体触发条件和可逆路径。
3. **优先复用与按需加载**：在理解约束后，先检查当前 Agent/Skill context、项目本地上下文、官方 CLI/Skill/MCP、标准库、原生平台和已安装依赖，再考虑新增 registry、抽象、依赖或平台。
4. **保留承重结构**：不能为了少几行而删掉验证、安全、无障碍、错误或数据丢失处理、状态、恢复、provenance、权限、审计和显式要求。
5. **计算总成本**：把新增文件、hook、常驻 prompt/context、配置、状态、升级/卸载、调试和维护成本一起计算。为了减少局部浪费而引入更大的运行时，是反精简。
6. **留下最小闭环**：非平凡改动保留一次 focused verification；有意接受的上限或延后项写明 upgrade trigger，而不是把“以后再说”当作计划。

Bug fix 默认追到共享根因或真实边界，而不是只修复工单点名的症状；只有边界确实不同，才重复添加局部保护。

## 规则所有权与实例策略

AIOS 不要求整个系统只有一个文件，而要求**每一项事实只有一个权威 owner**。常见角色应保持分离：

| 角色 | 典型 owner |
|---|---|
| 通用产品/协议语义 | public repo 文档、协议或 ADR |
| 用户实例当前启用的跨任务策略 | AIOS Managed Zone 中的 local policy |
| Agent 触发与操作入口 | 薄 skill / sidecar，只负责加载 owner |
| 确定性执行 | CLI、script、API、runtime |
| 单次工作状态与变更证据 | Matter / LLL Worksite |
| 稳定用户偏好 | 简短 memory 声明或 policy 指针 |

实例 policy 不是新平台。初期优先一份可审计的声明式文件，不增加数据库、daemon、GUI 或通用 policy engine。只有同时满足以下大部分条件的行为才值得登记：跨多个任务反复生效、用户可能合理关闭、明显影响交互/成本/风险、带有实验或兼容生命周期、不能由通用判断自然推导。

策略模式应保持少而正交，例如 `off | compact | auto | expanded`，而不是拆成大量字段布尔开关。临时兼容行为必须声明删除条件；原生能力通过真实使用验证后，删除整个兼容策略，不保留 `native` 空壳、不迁移无意义历史状态。

默认覆盖顺序是：当前用户显式指令 > 当前 Matter/mission > 本地实例 policy > 产品默认。关闭策略只修改当前 policy 状态，不删除或回写历史 Worksite。

## 模块成熟度地图

成熟度不是承诺排期，而是约束“下一步最多做什么”。

| 模块 / 能力 | 当前阶段 | 已有最小闭环 | 下一步候选增强 | 暂不做 |
|---|---|---|---|---|
| Project / Resource facts | L0/L1 | Agent + project-local context、compact catalog；仅少数稳定 owner 事实进入 `aios project/source` | 先减少默认 registry 入口，按真实消费者收窄 ResourceRef/binding | 完整项目管理系统、默认 Project→Source 全量投影 |
| Data Sources | L1 | `aios source list/get/add/alias/validate`、显式 Source records、Managed Zone 目录边界 | 从真实设备接入中补 inventory/backup/sync adapter | 默认接管项目投影、全盘摄取、数据库、通用文件管理器 |
| Secret management | L1.5 | request → intake → metadata/consumer/replica → run/sync/audit；`doctor`/`validate` 提供低风险探针 | 更通用的 provider preset 文档/模板；仅在真实摩擦出现后考虑可选 proxy/lease | 常驻 broker、默认 proxy、MCP secret tools、plugin 系统 |
| LLL integration | L1 | `aios lll ...` 发现、创建、状态代理 | 更清楚地表达 AIOS 只代理不吞并 LLL 状态机 | 在 `aios-kit` 中重写 LLL runner |
| OPS vault | L1 | 模板与 live vault 分离，OPS skill 入口 | 更好资源索引和维护记录模板 | 把公开 repo 变成私有 CMDB |
| Skillpack | L1 | sync/adopt/doctor/dev-link | 更好的冲突解释和 reconcile 输出 | 接管整个 runtime skills 目录 |
| Assets | L0/L1 | manifest、doctor、link | 只做发现和链接纪律 | 通用文件管理器 |
| Agent governance | L1 | `aios-agent` skill、开发文档、自迭代规则 | 用本文件统一演化判断 | 新建一堆原则 skill |
| Workflow cost signals | L0/L1 | `scripts/agent_cost_snapshot.py snapshot|delta`：按需只读、固定 ledger 去重、五信号 compact JSON | 仅在 schema 漂移或重复消费出现后补 source adapter | dashboard、DB、cron、daemon、自动模型/会话切换 |

## 增强决策门槛

新增加入或管理模块前，维护者或 Agent 应回答：

1. Agent 能否从当前 bootstrap/compact/owner context 和官方入口恢复所需事实？
2. 它解决的是真实摩擦，还是想象中的未来完整性？
3. 这个事实是否需要跨任务稳定保存，或必须作为安全/审计边界？
4. 它减少了哪些重复配置、泄漏风险、手工步骤或恢复成本？
5. 它是否能作为可选层存在，而不是污染默认路径？
6. 它是否需要新的长期状态、后台进程、权限边界或维护面？
7. 它是否应该先写进 owner 文档或 roadmap，而不是立即实现？

如果 Agent 能从现有上下文完成任务，默认不新增 registry、manager、resolver 或 context platform；如果只是用户体验不够优雅，优先改善 compact context 和 owner routing，而不是增加统一数据库。

## Secret 模块示例

Secret 模块当前保持 L1.5：密钥登记、录入、consumer、replica、receipt、audit、`aios secret run`、`doctor` 和 `validate` 已形成一个可诊断的最小闭环。

可以采用以下语言区分边界：

- **Secret Registry**：登记密钥身份、用途、consumer、replica、request、receipt 和 audit。
- **Secret Runtime**：在运行时安全使用密钥。当前唯一承认的最小 runtime 是 `aios secret run`。

暂不实现：常驻 broker、proxy、MCP secret tools、provider plugin、session lease。它们只有在多个 AI API consumer 高频使用、env 注入出现真实风险或多 Agent 需要短期授权时，才进入实现讨论。

## 自动化与巡查

AIOS 可以在未来引入项目健康巡查，但默认不从本地 cron 或常驻 Agent 开始。更优先的方向是 GitHub CI/CD 或其他云端工作流：检查文档漂移、public audit、skillpack 分发、模块健康和安装 smoke test。

当前保留文档翻译与显式 release 构建等维护自动化；自动 Install smoke 暂停，不作为每次 push / pull request 的发布门禁。自动化应在流程稳定、检查项明确且能给出可执行建议后再加入。

## 公开安装路线图

当前阶段是**维护者预览**：安装器、参数文档和测试代码继续留在仓库中供开发与隔离验证，但 README 不提供一键安装命令，也不对普通用户承诺稳定安装、升级或跨平台兼容性。

重新开放公开安装引导前，应至少满足：

1. Linux 核心路径在隔离环境中可重复完成 dry-run、apply、status 和 doctor；
2. macOS、Windows 与 Linux-only 能力边界被明确记录并有 fail-closed 测试，不用平台假绿代替支持；
3. 安装器的系统改动、secret 边界、失败恢复和卸载/回滚说明与真实行为一致；
4. Install smoke 连续稳定，能够可靠传播 Bash、PowerShell、Python 和 Go 的失败；
5. 发布版本、支持范围与维护责任有明确 owner。

恢复顺序保持渐进：先允许维护者手动触发验证，再作为变更门禁运行；只有证据稳定后，README 才重新提供面向普通用户的安装入口。

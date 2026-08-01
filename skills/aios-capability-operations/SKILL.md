---
name: aios-capability-operations
description: "Use whenever an Agent must design, discover, route, verify, or govern reusable capabilities across multiple organizations, tenants, accounts, SaaS providers, apps, API keys, or Secret consumers. Keep the semantic capability stable, resolve the target binding explicitly, and never confuse credentials with capability authority."
version: 0.1.1
license: MIT
---

# AIOS Capability Operations

这是 AIOS 的跨提供商能力治理与路由 skill。它负责回答“Agent 现在能做什么、通过哪个组织/账户/应用做、是否真的被授权”，而不是替代 Feishu、GitHub、Cloudflare、Web provider 或其他平台的 API 技能。

## 何时使用

当用户提到以下任一类问题时加载本 skill：

- 同一种能力要服务多个组织、租户、账户或 workspace；
- 每个 SaaS/API 需要不同应用和 key，但上层能力应保持不变；
- 能力注册表、能力健康、能力成熟度、能力自组织、能力路由；
- 组织/账户选择、Secret consumer 绑定、API key 轮换、scope/权限边界；
- 将 Feishu、文档、搜索、GitHub、Cloudflare、基础设施等接入 AIOS 数字分身。

不要把一个组织、一个 App ID、一个 Secret value 或一个临时 endpoint 写进本 skill。

## 核心模型

```text
Capability Definition
  -> Provider Adapter
  -> Organization / Account Binding
  -> App / Integration
  -> Secret Registry Item + Consumer
  -> Matter-scoped Invocation
  -> Receipt / Evidence / Projection
```

- **Capability Definition**：稳定的语义动作，如 `approval.resolve_approver`、`content.publish`。
- **Provider Adapter**：服务商/API 的具体实现和 namespace、scope、分页、错误语义。
- **Binding**：能力在一个 provider、组织/账户和应用上的具体可用实例。
- **Integration/App**：外部应用身份，可能承载多个能力。
- **Credential/Secret**：运行时凭据；由 Secret Registry 管理，Agent 不读取 plaintext。
- **Consumer**：Secret Runtime 的受控投递路径。
- **Matter**：调用能力的目标工作；Matter 使用能力，但不拥有能力。
- **Evidence/Projection**：脱敏 receipt、健康、状态和可重建视图；不是外部系统真源的替代品。

把 Data/Information、Matter/Work、Capability 看成 AIOS 的三类基本语义：数据回答“有什么材料”，Matter 回答“正在做什么事”，Capability 回答“可以怎样行动”。

## 路由纪律

1. 先识别稳定的语义能力，再选择 provider adapter；不要从某个 endpoint 反推全局能力名。
2. 解析用户明确指定的组织、租户、账户或 workspace。
3. 若只有一个满足条件的 Binding，可使用它；若存在多个候选而目标不明确，询问或 fail closed，不能默认“当前组织”。
4. 检查 Binding 的 enabled/health/maturity、允许动作、scope 摘要、Secret item 与 Consumer metadata。
5. 加载对应 provider skill/官方文档，确认 token 类型、namespace、endpoint、分页和错误分类；不要把 provider 细节复制到本 skill。
6. 读操作先于写操作；写操作必须有 allowlist、目标范围、人类授权、幂等、read-after-write、失败分类和脱敏审计。
7. 通过 `aios secret run --consumer <consumer-id> -- ...` 或同等受控运行时投递凭据；不得读取、打印、复制或回写 Secret value。
8. 执行后把当前事实写回能力 owner/OPS/Matter/LLL 的正确层，不在 skill 或聊天中制造第二个真源。

## 多组织、多应用命名

使用稳定本地别名，不使用远端动态 ID 作为长期语义主键：

```text
integration_id: <provider>.<org_alias>.<app_alias>
secret_id:      <integration_id>.credential
consumer_id:    <integration_id>.<capability_family>
```

同一个能力可以有多个 Binding；同一个 App 也可以承载多个低风险能力。只有权限、审计、运行时或风险边界不同，才拆分 Consumer/Binding。key 轮换只更新 Secret/Binding，不复制或改写 Capability Definition。

如果现有旧 consumer 没有组织前缀，不要为形式统一而直接重命名；将其视为兼容 binding，新增组织时采用新命名，并用独立 change set 做迁移。

## 成熟度与风险

分开记录“能力是否可用”和“哪些动作已经验收”：

```text
designed -> discovered -> configured -> verified -> available
                                      \-> degraded -> disabled -> deprecated

not-accepted -> read-accepted -> isolated-write-accepted -> operational
```

`available` 不等于全部 endpoint 已验收。至少区分：

- read-only：读取、查询、健康检查；
- projection：向外部视图发布受控摘要；
- isolated-write：仅测试夹具或显式隔离对象；
- business-write：生产业务写入，需要更高 gate；
- destructive/public：删除、覆盖、公开暴露、权限扩大，默认人工确认。

不要把“API 返回 200”升级成“业务写入已授权”，也不要把读组织能力升级成完整审批生命周期。

## 能力自组织边界

### 可以自动化

- 从 skills、tool schema、Secret Registry metadata、OPS service catalog 和项目 registry 发现候选能力；
- 归类 semantic capability、provider adapter 和 Binding；
- 检查 Secret/Consumer 引用、健康、成熟度、scope 摘要和最近 evidence；
- 根据明确的目标组织/账户给出 Binding 选择；
- 建议缺少配置、停用、迁移、拆分或降级，并写入可审计状态。

### 不能自动化

- 创建外部应用、申请 scope、取得或轮换用户未提供的新 Secret；
- 在多个组织之间猜测目标或静默切换；
- 绕过 human gate、权限范围、Matter policy 或 provider resource authorization；
- 把同名部门、职务、搜索结果或旧 API ID 当成另一种组织事实；
- 把外部 SaaS 全量复制为 AIOS 的第二任务/事件/数据真源；
- 在没有幂等、read-after-write、失败分类和回滚/不可逆声明时自动编排高风险写入。

“自组织”是发现、整理、健康检查和路由建议，不是自授权。

## 真源分层与协作

- `aios-kit`：通用 skill、schema、CLI 和公开原则；不得放私人组织、App ID、Secret 或主机事实。
- AIOS Managed Zone：当前能力成熟度、产品决策和私有 binding metadata。
- Secret Registry：secret identity、consumer、replica、receipt；值只在 runtime 中使用。
- AIOps Vault：服务当前态、资源关系、维护历史和部署边界。
- Matter/LLL：用户目标、恢复、决策、验收和证据。
- Provider skill：某个平台的 API/权限/namespace/分页/错误合同。
- External SaaS：原生对象和流程真源。
- Viewer/Docs/Base/Dashboard：可重建 projection，不成为隐藏 state machine。

## 与 provider skill 的路由

遇到 Feishu/Lark 时，继续加载 `feishu-open-platform-operations`；它负责 Contact、功能角色、审批、权限和 Secret Runtime 的具体合同。遇到 Google、Notion、GitHub、Cloudflare、Web Search 或其他平台时，加载对应 provider skill/官方文档。

本 skill 不复制 provider endpoint。尤其要注意：不同 API 代际的 ID 不能混用；历史兼容路径应由 provider adapter 封装并在下线时 fail closed。

## 验证清单

完成能力操作或登记前检查：

- 目标组织/账户明确，多个候选没有静默选择；
- Capability、Adapter、Binding、App、Secret、Consumer 的边界可解释；
- Secret value 未进入 Agent、日志、报告、skill、diff 或证据；
- 当前动作成熟度与真实 evidence 一致，未把 deferred/not-accepted 写成 operational；
- 上游 mission、API 合同或验收计划中出现过的每个动作都有显式成熟度；未登记不能被当作 `not-accepted`，也不能从同一资源的其他已接受动作推导授权；
- 写操作有目标 allowlist、human gate、幂等、read-after-write、失败分类和回滚/不可逆说明；
- Provider API 事实来自 provider skill/官方文档，不凭名称猜 endpoint 或 scope；
- 当前状态写入 AIOS/AIOps/LLL 的 owning layer，历史纠偏追加记录而不是覆盖；
- 当真实 Binding 数量和路由摩擦增长前，不引入 daemon、broker、marketplace、数据库或万能 SaaS orchestrator。

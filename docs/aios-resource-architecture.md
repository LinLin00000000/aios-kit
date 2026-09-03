# AIOS 资源与上下文架构

AIOS 不是一个把所有对象预先登记起来的传统管理平台。它是一个 **Agent-first 的上下文工程骨架**：先从当前意图加载足够的上下文，理解对象和 owner，再在真实动作边界绑定稳定资源和安全事实。

Repo、source、runtime 的边界见 [architecture.md](architecture.md)。本文说明资源事实、动态上下文和最终 binding 的边界。

## 一句话架构

```text
用户意图
  → Bootstrap context
  → Compact candidate context
  → Agent 选择 owner
  → Owner context
  → Action/resource context
  → 确定性 binding
  → Owner actuator + receipt
```

用户说“LLL 项目”“飞书云盘”“那台边缘服务器”时，Agent 不应首先要求用户提供固定 ID，也不应让 CLI 自己假装理解语义。Agent 先加载当前可见的项目、服务、Skill、设备或 Source 候选；只有确定要执行动作时，才绑定 realpath、remote、canonical ID、版本、consumer 或其他可审计句柄。

## 管理即上下文工程

以下对象都采用同一原则，而不是各自建设一套传统管理层：

```text
数据资产      → 数据根、来源、敏感等级、可逆边界的上下文
服务器/设备   → 节点身份、连接入口、授权范围、运行事实的上下文
服务/云资源   → compact catalog、service card、官方入口、动作边界
项目          → 当前目录、本地文档、Git remote/tree、必要 owner 事实
Skill/能力    → 触发条件、操作规则、官方执行器、Secret consumer、动作验收
```

“管理”只在 Agent 需要这些信息时加载它们；它不自动意味着要建立项目表、能力表、统一 resolver、health registry 或 Context Registry。

## 上下文梯度

### Level 0：Bootstrap

常驻且极小，只放：

- 用户和实例的不可绕过安全/隐私边界；
- 当前 Matter/mission（如有）；
- Agent 的 owner 路由和上下文加载规则；
- Secret 不进入普通上下文正文的约束；
- 不确定身份、范围、权限或结果时 fail closed。

### Level 1：Compact candidates

只加载低成本候选：

- Skill description/catalog；
- AIOps `services --json` 的 `id/name/summary`；
- 当前目录和邻近项目的少量 repo facts；
- Matter/Worksite compact status；
- 必要时的 Source boundary 摘要。

这一层只回答“可能有哪些 owner”，不加载全部细节。

### Level 2：Owner context

Agent 选择候选后，加载该 owner 的：

- Skill 正文及 declared references；
- AIOps `service.json`、service card 和 runbook；
- 项目 `AGENTS.md`、README、CONTEXT 或本地文档；
- Source 的 current-state、policy 和 provenance；
- 官方 CLI、官方 Skill、官方 MCP 的入口与使用边界。

### Level 3：Action/resource context

真实动作需要时才加载：

- 精确资源位置、remote、对象 locator 或 profile；
- action contract、风险等级、dry-run/readback 要求；
- Secret consumer metadata；
- commit/tree、etag、version、fencing 或幂等键；
- receipt/evidence 写入位置。

Level 3 才允许进入确定性 actuator。它不产生全局 readiness 或 capability 状态。

动态上下文是有界 DAG，不是全文递归搜索。每层只返回下一层 locator 和触发条件；已加载内容可以记录 source/hash 作为本次 evidence，但不会因此成为新的 canonical。

## 什么时候需要稳定事实记录

Project/Source/Service 记录不是默认入口，而是以下情况的窄事实层：

- 对象不在当前目录或 owner context 中，且需要跨会话反复引用；
- 存在多个本地/远端位置，需要长期区分；
- 对象承担独立的备份、敏感性、授权、写入或恢复边界；
- Matter、receipt 或安全门必须绑定一个稳定 owner；
- 没有记录会导致真实任务重复消歧或不可安全回读。

否则，优先使用当前目录、项目本地上下文、官方工具和一次性 binding；不要为了目录统一而新增记录。

## 显式事实的位置

需要长期保存时，仍使用现有 owner 文件，而不是新增总表：

```text
~/aios/vault/ops/projects/registry.jsonl  # 少数长期项目 owner 事实
~/aios/vault/ops/sources/registry.jsonl   # 稳定外部 Source 边界
~/aios/vault/ops/services/<id>/           # AIOps service card 与运维事实
项目本地 README / AGENTS / CONTEXT        # 项目自身上下文
Skill package / references                 # Agent 操作知识
Matter / LLL Worksite                      # 单次工作、恢复和证据
Secret Registry                            # Secret metadata 与 runtime consumer
```

这些 owner 不应被编译成一个超级目录。projection 和 cache 可重建，不能反向成为真源。

## CLI 的职责

AIOS CLI 只保留三类职责：

1. 提供 compact context 或 owner context 的确定性读取入口；
2. 在动作边界执行 identity/path/version/permission 的结构检查和最终 binding；
3. 执行窄、可回读、可恢复的 actuator。

CLI 不负责：

- 自己理解自然语言或做假装智能的 fuzzy routing；
- 要求用户先记住 ID、alias 或精确名称；
- 为所有项目、服务、动作维护中央注册表；
- 汇总所有 provider 的 health、binding、readiness 或 capability；
- 复制官方 CLI、Skill、MCP 或服务卡的完整知识。

## 现有命令族的定位

```text
aios project       少数长期项目事实的兼容读取/窄写入，不是所有项目的入口
aios source        稳定外部 Source 边界的兼容入口，不是默认项目管理面
aios resource      最终 binding / receipt 工具，不负责前置语义发现
aios matter        Matter/Worksite 的耐久状态、恢复和证据入口
aios secret        Secret metadata、consumer 和受控 runtime 注入
aios skillpack     Skill provenance、安装投影和 install-state
aios doctor        最小结构检查与 owner-specific diagnostics，不是万能健康中心
aios lll           LLL 薄代理，不吞并 LLL 状态机
```

现场 `aios --help` 仍把 `project` 写成 “manage the minimal AIOS project registry”，把 `source` 写成 federated Source view，把 `resource` 写成 resolve existing Project/Source records。`aios source list` 默认仍会附带 Project 投影，可用 `--explicit-only` 排除。这些是兼容/只读绑定 actuator 的残留 CLI 措辞与行为；产品模型不要求所有对象先进入中央注册表，也不把这些命令当发现入口。

## 官方能力优先

新增领域接入时，顺序是：

```text
官方 CLI
  → 官方 Skill
  → 官方 MCP
  → 官方文档/官方运行入口
  → AIOps service card + runbook
  → 很薄的引导 Skill
  → accepted narrow script
  → 传统 API 直连（最后）
```

先确认 provenance、安装、认证、scope、资源范围和动作验收；“工具存在”不等于“动作 ready”。AIOps service card 负责 owner、入口、边界、依赖和 references，不复制官方工具，也不把未认证状态写成可执行。

## 安全边界

动态发现不等于授权。最终执行仍必须绑定并验证：

- realpath containment 或外部对象 locator；
- owner、profile、Secret consumer 和资源范围；
- version/etag/commit/tree/fencing；
- read-before-write、read-after-write、幂等和回滚；
- 失败分类、`NO_VERDICT` 和 receipt。

`ResourceRef` 是只读 binding/receipt，不是权限。可见、可索引、能解析或哈希匹配成功，都不能扩大写权限。

## 发展规则

先用现有 Skill catalog、AIOps catalog、项目本地上下文和官方入口解决问题。只有两个以上 owner 已出现相同的 catalog/load/containment/receipt 摩擦，且不能用普通文件或薄脚本解决时，才考虑一个极薄公共 seam；不提前建设 Context Registry、ContextBundle compiler、向量库、daemon、broker、marketplace 或统一授权平台。

# 上游协调与开源二开维护协议

本协议用于管理 AIOS 或项目对外部软件的长期采用关系，包括普通依赖、adapter、overlay、patch queue 和 maintained fork。

核心原则：

```text
Fork 是正常的协作与托管方式；
优先减少不必要的长期源码差异，而不是回避 GitHub Fork；
能用上游扩展点、adapter 或 overlay 就不扩大核心 patch 面；
形成长期差异时记录不可变 upstream base，并持续寻找缩小、上游化或退休路径；
Git 可合并不等于行为等价；
建议、授权、实施、验证、部署必须分开；
任何自动更新都必须有验证和可恢复边界。
```

## 1. 适用范围与非目标

适用：

- 外部 CLI、library、service、Web UI、MCP server、skill 或 vendored component；
- 本地 adapter、sidecar、overlay、patch queue；
- 需要持续跟踪 upstream 的长期 fork；
- 可能被上游等价能力替代的本地差异。

不强制用于：

- 没有外部 upstream 的纯 first-party 项目本体；
- 一次性临时改动；
- 无本地差异且由现有 lockfile/manifest 足够管理的普通依赖。

本协议不是新的 fork maintainer 平台、中央组件数据库或部署系统。第一版复用项目仓库、Git、现有 CI、LLL、AIOS registry 和 OPS vault。

## 2. 领域模型

### 2.1 Fork 的两个维度

“Fork”可能指 GitHub/GitLab 上的仓库托管关系，也可能指长期维护本地源码差异。两者必须分开：

- **repository topology**：代码放在哪里、如何与上游建立 Git 关系；GitHub Fork 是正常且常用的二开工作区。
- **divergence strategy**：本地是否以及如何保持行为或源码差异；真正产生持续协调成本的是长期 divergence，而不是点击 Fork 本身。

因此 `github-fork + adapter`、`github-fork + no-source-delta`、`independent-clone + maintained-source-divergence` 都是合法组合。协议不以避免 Fork 为目标，而以控制、解释和持续缩小不必要的本地差异为目标。

### 2.2 正交分类

不要用一个 `class` 同时混合来源、采用方式和重要性。

| 维度 | 示例值 | 用途 |
|---|---|---|
| provenance | `first-party` / `external-upstream` | 原始组件由谁拥有 |
| repository topology | `upstream-direct` / `github-fork` / `independent-clone` / `mirror` | 仓库托管、贡献和 fetch 关系 |
| divergence strategy | `no-source-delta` / `adapter` / `overlay` / `patch-queue` / `maintained-source-divergence` | 本地如何实现并维护差异 |
| criticality | `utility` / `infra` / `core-control-plane` | 验证、授权和更新节奏 |
| runtime ownership | `app-owned` / `aios-managed` / `user-owned` | 谁能安装、部署、重启和回滚 |
| visibility | `public` / `private` / `mixed-by-reference` | 事实应写入公共 repo 还是私有 owner |

### 2.3 核心对象

| 对象 | 职责 | 不应承担 |
|---|---|---|
| Component | 有稳定身份的上游软件或模块 | 一次同步状态机 |
| Adoption | 某本地项目/实例如何采用 Component；聚合根 | secret、完整生产 receipt |
| Base Revision | 当前已接受的不可变上游版本 | 浮动 branch/channel |
| Invariant | 协调后必须持续成立的行为、安全或边界条件 | 未验证愿望或普通偏好 |
| Local Delta | 本地有意保留的产品/行为差异 | 某次候选或决策状态 |
| Upstream Candidate | 可能影响 Adoption 的上游变化快照 | 已确认等价或已授权采用 |
| Reconciliation Case | 对 Candidate、Delta、Invariant 的一次评估 | 产品授权或部署 receipt |
| Decision Record | Human 或显式 policy 的处置授权 | 未授权机器执行 |
| Change Set | 决策后准备执行的精确修改和 undo plan | 把 proposal 当成已应用事实 |
| Validation Evidence | 针对精确 revision/change set 的检查证据 | 用一句 “CI green” 掩盖范围 |
| Deployment Projection | 项目/OPS 对验证产物的发布、健康和回滚 | 通用协调聚合的内部状态机 |

```text
Component
  └─ Adoption (owner + repository topology + divergence strategy + accepted base)
       ├─ Invariant*
       ├─ Local Delta*
       └─ Reconciliation Case*
            ├─ Upstream Candidate
            ├─ Git result + behavioral relationship
            ├─ Decision Record
            ├─ Change Set
            └─ Validation Evidence

Deployment Projection --references--> validated revision/change set
```

### 2.4 四个独立判断

| 判断 | 典型结果 | 不能推出 |
|---|---|---|
| Git applicability | `clean` / `text-conflict` / `not-applicable` / `unknown` | `clean` 不代表行为兼容；冲突不代表产品冲突 |
| behavioral relationship | `unrelated` / `complementary` / `partial-overlap` / `equivalent` / `conflicting` / `unknown` | `equivalent` 不代表必须采用上游 |
| product disposition | `accept-upstream` / `keep-local` / `hybrid` / `defer` / `retire-local` / `reject-update` | 决策不代表实现正确或已部署 |
| deployment | `not-requested` / `pending-approval` / `deploying` / `healthy` / `failed` / `rolled-back` | merge/validate 不代表生产授权 |

`equivalent` 只表示在明确声明的 API、CLI、配置、数据、权限、安全、性能或失败模式范围内，经引用证据验证，满足同一可观察契约。范围外未知仍是未知。

### 2.5 最小生命周期

- Adoption：`tracked | paused | retired`
- 当前 Adoption 契约只列出仍需维护的 active Local Delta。Delta 经 Human/Policy Decision 退休并完成验证后，从 active list 删除；最小历史证据保留在 Decision Record、Git history 或 L2 `decisions/`，稳定 ID 不复用。
- Reconciliation Case：

```text
detected → assessed → no-action | decision-required
decision-required → authorized | deferred | closed
deferred → assessed | closed
authorized → implemented → validated → closed
```

Decision Record 的 `status` 与 product disposition 是两个维度：

- `approved` 表示所选 disposition 已获授权；`accept-upstream`、`hybrid`、`retire-local` 等需要修改的结果进入 `authorized`，`keep-local`、`reject-update` 等无需修改的结果记录证据后直接 `closed`；
- `deferred` 对应 `defer`，Case 进入 `deferred` 并携带 `revisit_after` 或 `revisit_trigger`，触发后回到 `assessed`；
- `rejected` 只拒绝当前 Decision proposal，不自动等同于 `reject-update`，Case 默认保持 `decision-required`，直到新 Decision supersede 它或显式处置关闭；
- `superseded` 只表示该 Decision Record 被更精确的新记录取代，不是 Case 的业务终态。

Delta 退休必须引用 Decision；不要为历史完整性把 retired tombstone 永久堆在当前活动契约中。

## 3. 不变量

1. **基线不可含糊**：accepted base 使用 commit、digest 或等价不可变身份；branch、channel、tag 只能作为 tracking ref。
2. **Git 与行为正交**：clean merge 不自动写成 compatible、equivalent 或 safe。
3. **意图与实现分离**：Delta 的 intent/behavior contract 不因 patch 改成 adapter、文件重构或 commit squash 而丢失。
4. **等价有范围和证据**：必须引用相关 Invariant、验证、比较范围和未知项；证据不足为 `unknown`。
5. **建议不等于授权**：Agent recommendation、confidence、label、Issue 状态和 CI result 都不能代替 Human/Policy authority。
6. **应用与部署分离**：apply/merge/validate 不自动授权生产发布或服务重启。
7. **真源单一，投影可重建**：GitHub、CI、README、看板和 Viewer 只引用稳定 ID。
8. **私有事实不进入公共协议**：主机、secret、环境、deployed revision、receipt 归项目私有 owner 或 live OPS。
9. **原件与证据保留**：从 Worksite 提炼资产时默认 derive/copy，不覆盖来源。
10. **失败关闭**：缺 base、owner、Invariant、验证或授权时，只能观察、起草或报告 `unknown/blocked`。

## 4. 真源与 owner

| 位置 | 应拥有 | 不应拥有 |
|---|---|---|
| 项目 repo | Adoption 契约、accepted base、Delta、Invariant、验证入口、长期 Decision/Change refs | secret、跨实例当前部署状态 |
| `aios-kit` | 公共术语、协议、模板、审核规则、可选 validator | 用户私有运行事实、所有外部源码 |
| AIOS registry | 可发现身份、typed locator、role/status、canonical record locator | 完整 patch inventory 或第二套状态机 |
| live OPS vault | service/environment、授权边界、secret refs、deployed revision、runbook、health/rollback receipts | 公共协议的重复副本 |
| LLL Worksite | 一次 Candidate 比较、调查、临时证据、review、handoff | 长期项目契约的唯一副本 |
| GitHub/CI | PR、Issue、Checks、review、触发和协作投影 | 唯一 Delta/Decision 真源或部署健康真源 |

推荐写入顺序：

```text
LLL proposal/evidence
  → Human/Policy Decision
  → project Adoption/Delta/Decision record
  → clean CI/build validation
  → separately authorized deployment
  → runtime readback
  → OPS current state/history
  → GitHub/Viewer refresh
```

## 5. 项目接入与文件契约

### 5.1 Agent onboarding

建立 Adoption 时，Agent 先自动发现可检索事实：upstream locator、默认 branch/ref、当前 base、repository topology、manifest/lockfile、测试入口和部署引用。不要把这些机械问题转交给 Human。

Agent 只询问真正影响产品或授权边界的项目级决策，并把答案写入项目契约：

1. 更新节奏：默认 `on-demand`；首次成功协调后是否开启 weekly/monthly observation。暂停跟踪使用 Adoption `paused`，不另造与 on-demand 重叠的 `manual` cadence。
2. 合并权限：默认 `guarded-after-baseline`；第一次协调只提议并由 Human 批准，基线建立后才允许严格受限的低风险自动合并。
3. 产品边界：哪些 Invariant 不能丢、哪些 Local Delta 是有意差异、上游接近时何时需要产品取舍。
4. 部署边界：merge 后是否仍需独立部署、重启、migration 或生产审批。

默认产品倾向是 `upstream-first-with-quality-floor`：当上游能力满足已声明的行为、质量和安全边界时，优先缩小或退休本地差异；证据不足或本地仍明显更合适时继续保留。

### 5.2 L0：无本地源码差异

- 实际 version pin / accepted dependency fact 由项目 manifest、lockfile 或其明确 owner 管理。
- AIOS registry 只保存发现入口和 canonical record locator，不承载第二套版本真源。
- repository topology 可以是 GitHub Fork、独立 clone 或直接使用上游；是否 Fork 不决定是否存在源码差异。
- 不强制新增 `UPSTREAM.md`、patch queue 或 schedule workflow。

### 5.3 L1：adapter、overlay、patch 或受保护 Invariant

在项目 repo 中添加一个 canonical `UPSTREAM.md`，以 YAML front matter 承载最小机器字段，以正文解释人类语义。不要再创建内容重叠的独立 YAML 真源。

模板：[`templates/upstream-reconciliation/UPSTREAM.md`](../templates/upstream-reconciliation/UPSTREAM.md)

最小内容：

- component/adoption identity；
- upstream locator、tracking ref、accepted immutable base；
- repository topology、divergence strategy、criticality、owner、cadence 和 merge policy；
- Invariant 和 validation refs；
- Local Delta 的 intent、behavior scope、realization refs、retire condition；
- deployment impact 的 policy/runbook reference；
- unknowns、not checked 与当前 Decision 引用。

真实 secret、host、production shell 和运行态不得写入公共契约。

### 5.4 L2：多个 Delta 或机器维护压力真实出现

只有在单文件维护出现真实摩擦时才拆分：

```text
UPSTREAM.md                 # 入口、人类摘要、机器记录索引
upstream/
  adoption.yaml             # machine canonical: adoption/base/index
  deltas/D001.yaml          # machine canonical: individual deltas
  decisions/<decision-id>.md
```

升级到 L2 后，`upstream/adoption.yaml` 与 `upstream/deltas/*.yaml` 是机器 canonical 字段 owner；`UPSTREAM.md` 的重复字段必须引用或生成，不得手工维护第二份真源。

升级触发：连续多次重做同一 patch、Delta/冲突数量持续增加、验证和退休记录难以维护、多个自动化消费者需要稳定 schema。不要因假想需求提前建 validator、数据库或 daemon。

## 6. 风险与自动化

### 6.1 风险 R0–R4

| 等级 | 典型变更 | 默认门禁 |
|---|---|---|
| R0 信息性 | 非规范文档、观测元数据；无机器行为变化 | lint/link；可策略化低摩擦合并 |
| R1 低风险 | 受测试覆盖的内部重构/构建改进；不改接口、默认值、权限 | CI + diff；仅非核心项目可预授权 apply |
| R2 中风险 | 用户行为、配置默认值、minor 依赖、adapter/overlay、可逆格式变化 | Human review + 专项 Invariant/smoke；默认不 auto-merge |
| R3 高风险 | API、auth、workflow 权限、供应链、状态机、发布路径、核心 UI/控制面、schema | 明确 Decision、安全审查、staging、生产审批 |
| R4 严重/不可逆 | secret/主权边界、生产基础设施、删覆数据、不可逆 migration、root/广域 actuator | 自动化只观察/准备；每次执行显式授权 |

核心组件、测试不足、rollback 未演练、provenance 弱或 AI 修改跨越 policy/secret consumer/deployment path 时应上调。文件少、无冲突、上游知名不能降级。

### 6.2 自动化 A0–A4

| 等级 | 可以做 | 不可以做 |
|---|---|---|
| A0 Human-actuated | Human 触发，机器执行确定动作 | schedule mutation |
| A1 Observe | 发现、抓取元数据、diff、分类、提醒 | 修改 repo/service |
| A2 Propose | candidate branch/PR、Decision Card、AI draft、自动验证 | 合并保护分支、生产部署 |
| A3 Guarded apply | 显式预授权范围内自动合并 R0/R1 非核心变更 | 核心语义、secret、不可逆动作 |
| A4 Guarded actuation | 预授权 dev/staging 或精确安全 rollback | 默认生产部署、未知 rollback、AI 扩权 |

默认上限：R0/R1 可在成熟规则下 A3；R2/R3 为 A2；R4 只允许 A1/A2 准备，actuation 回到 A0。

`max_automation` 是上限，不是必须达到的目标。第一次接入、第一次 major update、第一次修改 rollback 路径时至少降一级。

新项目默认采用 `guarded-after-baseline`：

- 第一次 reconciliation 必须 proposal-only，由 Human 审阅并授权；
- 首次协调成功且 required validation 全部通过后，automation baseline 才视为 established；
- 此后只有 `R0/R1 + Git clean + behavioral=unrelated + required checks 全绿 + 无 unknown` 才可自动合并，并必须给出事后回执；
- `partial-overlap`、`equivalent`、`conflicting`、`unknown`、Invariant 风险或 Delta 范围变化均退出自动通道。

## 7. 端到端流程

```text
Trigger(on-demand | schedule | webhook)
→ Discover → Fetch → Classify → Prepare Candidate
→ Conflict/Behavioral Assessment → Optional AI Draft
→ Validate → Human/Policy Decision → Apply/Merge
→ Separate Deployment Authorization → Health → Rollback if needed → Record
```

按需请求、定时检查和 webhook 不创建三套流程；它们只是同一 reconciliation core 的不同触发器。基础产品能力首先是 Human-triggered on-demand reconciliation；schedule 在第一次真实协调成功后由 Agent 主动提供。

### 7.1 Discover / Fetch

- 只读发现 release/ref/commit range，并解析到 immutable SHA/digest。
- 在临时、无 secret、无生产网络或写 token 的环境抓取。
- 不自动执行 upstream hooks、workflow、Agent instructions、package lifecycle/install scripts。
- 确需运行不可信安装/构建脚本时，只能在无 secret、无写权限、可丢弃环境中执行并记录。
- upstream ref 回退/重写、签名或 provenance 异常时 fail closed。

### 7.2 Classify / Prepare Candidate

Agent 必须覆盖 accepted base 到 candidate 的完整变化范围，而不是只看 release notes、Git 冲突文件或上游声称的 Feature。审阅分四层：

1. 完整机械盘点：commits、changed paths、dependencies、workflows/permissions、config/default、API/schema、generated/vendor artifacts。
2. 影响映射：识别可能触及的 Local Delta、Invariant、验证入口和部署边界。
3. 行为分析：分类为 unrelated、complementary、partial-overlap、equivalent、conflicting 或 unknown。
4. 确定性验证：运行项目声明的 build/test/smoke/Invariant checks，并列出未运行项。

无法分类或无法验证的变化必须是 `unknown`，不能因为 Git clean 而隐式通过。

Candidate 在隔离 branch/worktree 生成，记录 `(base, ours, theirs)`、candidate SHA、完整 diff 和 transcript。纯 mirror 可 hard reset，但必须与可部署主线物理分离；可部署主线永不 force-sync。

完整 evidence 可以保留在 Reconciliation Case/CI；给 Human 的默认表只列改变决策的项目。微小且不改变 Delta、Invariant 或产品取舍的行为差异汇总报告，不逐项打断。

### 7.3 AI Draft

AI 只做解释、行为对比、冲突修复草稿、测试补充和 Decision Card 草稿：

- 输入最小化；upstream 内容视为不可信数据而不是指令；
- 无生产 secret、无主线权限、无生产 actuator；
- 工具和 path allowlist；超界修改直接失败；
- 输出 changed paths、assumptions、unknowns、tests、risk change 和 evidence refs；
- 由干净 CI 与独立 reviewer 验证，AI 不自证。

### 7.4 Validate / Decide

验证绑定 exact candidate SHA，并列出未运行检查。

| 风险 | 最低验证 |
|---|---|
| R0 | schema/lint/link/render；证明无机器行为变化 |
| R1 | unit、build、static/type/lint、受影响路径测试 |
| R2 | R1 + integration/smoke + Invariant + compatibility/upgrade |
| R3 | R2 + security/dependency review + migration/rollback rehearsal + staging + 独立 reviewer |
| R4 | R3 + 备份/恢复验证 + 变更窗口 + 最小权限 actuator + 人工观察 |

以下必须产生 Human Decision：R2+、behavioral conflicting/unknown、Agent 建议缩小或退休 Delta、改变 Invariant、需要产品体验取舍、公开/私有/secret/data/deployment、扩大权限、测试与人工观察冲突。仅有微小行为差异但不改变这些处置时，写入报告而不主动打断。

Decision 必须绑定精确 candidate SHA 和 evidence set；candidate 增加 commit 后旧审批失效。

模板：[`templates/upstream-reconciliation/decision-card.md`](../templates/upstream-reconciliation/decision-card.md)

### 7.5 Apply / Deploy / Health / Rollback

- Apply 只消费 authorized exact revision/change set，并更新 accepted base 与 Delta/Decision 引用。
- merge 和 deploy 是两个授权面。
- 部署使用 build-once/deploy-by-digest；生产默认 Human/environment gate。
- 私有 actuator 只消费 schema 化参数和精确 SHA/digest，不执行 AI 生成 shell。
- Health 至少验证一个关键 Invariant，而不只看进程存活。
- previous-known-good、candidate、current 三个版本必须精确可识别。
- rollback 触及不可逆数据或未知 secret 时停止并回到 Human。

## 8. GitHub Actions、自托管 Agent 与供应链

| 工作 | GitHub-hosted ephemeral | 自托管 Agent/runner | 私有 actuator | Human |
|---|---|---|---|---|
| 上游发现、diff、公共 PR CI | 默认首选，无生产 secret | 公共/不可信 PR 禁用持久 runner | 不需要 | 异常接管 |
| AI 分析/起草 | 可选，最小权限 | 私有代码可用隔离临时环境 | 不得直接调用 | 触发/审查 |
| 私网 integration/staging | 产出已批准 artifact | ephemeral/JIT 专用 runner | 受限执行 | 批准边界 |
| 生产部署 | environment gate/编排 | 不运行不可信代码 | 消费 exact digest + schema 参数 | 默认必须批准 |

安全基线：

- workflow 从 `permissions: {}` 或 `contents: read` 起步，按 job 最小提升；
- 第三方 Action pin full commit SHA，更新时复核 release、`action.yml`、runtime 和权限；
- 避免 privileged `pull_request_target` checkout；
- 跨 workflow artifact 校验 source repo、workflow、event、head SHA、run conclusion 和 digest；
- PR/Issue/upstream 文本不得直接插值进 shell 或 JavaScript；
- untrusted 与 privileged job 不共享可写 cache；
- 持久 self-hosted runner 不执行公共或未审查 PR；需要私网测试时优先 ephemeral/JIT 和专用 runner group；
- 生产优先 OIDC/短期 credential；secret value 不进入 AI prompt、artifact、cache、PR、命令参数或 health response；
- package、binary、container、submodule、LFS、generated code、release/tag 均需按项目风险检查 lock、digest、signature、SBOM/attestation 或 reproducibility。

具体 Action、AI provider 和部署 transport 都是可替换 adapter，不进入领域真源。采用前必须在 disposable repository/environment 做权限与行为验证。

## 9. 项目类型适配

| 类型 | 推荐模式 | 关键边界 |
|---|---|---|
| first-party core/distribution project | 项目自身演化；仅外部依赖逐项协调 | 不伪造 fork 关系；核心协议、安装/update 行为 Human + 独立 review |
| independent first-party module | 保持独立 owner；AIOS 只安装、发现或代理 | 不 vendor 状态机；协议变化按影响定级 |
| external core UI/service | GitHub Fork 或独立 repo 均可；adapter/managed overlay 优先于扩大核心 patch 面 | update detection 可自动；核心 UI 升级、切换、重启单独授权 |
| private actuator | OPS facts → plan/check/diff → narrow apply → readback | inventory/secret/production targets 不进公共协议；真实 apply 严格限定目标 |
| ordinary maintained fork | repository topology 与 divergence strategy 分开选择；按真实摩擦扩大或缩小源码差异 | fetch/PR/CI 可自动；行为取舍、Delta 退休和生产部署保留 Human gate |

AIOS registry 不是 patch inventory/CMDB；actuator inventory 不是资源真源；UI 数据库/session/看板不是 Matter 真源；同版本号不代表同源码/运行态；Issue closed 不代表修复已部署。

## 10. 渐进实施

### Phase 0：按需 Agent dogfood

1. 选择一个真实采用关系。
2. Agent 自动发现仓库/upstream/test 事实，只向 Human 询问 cadence、merge authority、Invariant/Delta 和部署边界。
3. 使用 L1 `UPSTREAM.md`，只登记 1–3 个真实 Invariant/Delta。
4. 用户触发第一次完整 reconciliation；Agent 生成隔离 candidate、完整影响审计和 Decision Card。
5. Human 授权后合并并验证，建立 automation baseline；此阶段不要求 schedule。

### Phase 1：基线后的受限自动合并与 schedule offer

- baseline established 后，严格满足 R0/R1、unrelated、无 unknown、required checks 全绿的更新可 guarded auto-merge，并事后回执。
- Agent 主动询问是否开启 weekly/monthly observation；不回答则保持 on-demand。
- schedule 只改变触发时机，不降低协调、验证和授权门禁。

### Phase 2：自动观察、candidate PR 与按需 AI 分析

- 低频 schedule 或 webhook 发现 immutable candidate，复用同一 reconciliation core。
- 可自动生成 candidate branch/PR、完整变化清单、Delta/Invariant 映射和验证证据。
- 仅冲突、重叠、未知或产品取舍时使用 AI 深审/起草；不自批自合。

可复用工具表面应优先围绕 `status / inspect / propose / validate / apply / record` 这类窄语义构建：读取项目契约、生成 candidate 与报告、调用现有 Git/CI/PR 能力，不另造部署系统或平行状态机。第一个真实项目仍可由 Agent 直接组合 Git、`gh` 和项目测试完成；只有重复机械摩擦出现后才下沉通用 CLI/CI helper。

### Phase 3：受控部署

- 先 staging；artifact digest、health receipt、previous-known-good rollback。
- 生产单独审批；migration 独立门禁。

如果按需 Agent 协调成本长期很低，停在 Phase 0/1 是成功。只有真实重复摩擦证明收益时，才增加通用 validator、CLI helper、CI template 或更强 runner；不要先建独立 fork maintainer 平台。

## 11. 接入清单

- [ ] Component、Adoption、Runtime、Local Delta 的 owner 已分清。
- [ ] repository topology 与 divergence strategy 已分开声明，不把 GitHub Fork 等同于长期源码分叉。
- [ ] tracking ref 与 accepted immutable base 均存在。
- [ ] Delta 包含 intent、behavior scope、Invariant、realization ref 和 retire condition。
- [ ] cadence 默认为 on-demand；第一次成功协调前 automation baseline 未建立。
- [ ] guarded auto-merge 只覆盖 established baseline 下的 R0/R1、unrelated、全绿且无 unknown 变化。
- [ ] Git applicability 与 behavioral relationship 分开记录。
- [ ] 风险 R0–R4 和自动化上限 A0–A4 已声明。
- [ ] unknown/权限/secret/workflow/data/core-control-plane 条件 fail closed。
- [ ] AI 无生产 secret、主线权限和生产 actuator。
- [ ] candidate、Decision、validation 绑定 exact SHA/digest。
- [ ] merge、deploy、healthy、rollback 是不同状态和证据。
- [ ] 项目 repo、registry、OPS、LLL、GitHub 的真源边界无重复。
- [ ] 第三方 Action pin full SHA 且已在 disposable 环境验证。
- [ ] previous-known-good 与 rollback 已验证，而不只有命令文本。

## 12. 维护规则

- 本文档是公共协议真源；skills、README 和模板只做薄入口或实例化。
- 模板中的 owner、locator、policy/runbook ref 必须使用 placeholder、公开假例或抽象路径，不得写入真实私有实例信息。
- 当前活动契约只表达仍需维护的 Delta；退休证据归 Decision/Git history，不保留冗余 tombstone。
- 第一个真实项目 dogfood 后，根据实际摩擦更新本文档；不要凭假想完整性扩 schema。
- 工具、Action 和 provider 的维护状态会变化；长期规则只保留权限、验证和替换边界，不固化短期排行榜。

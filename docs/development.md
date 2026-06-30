# 开发指南

本文档面向维护者、贡献者和后续协作的 AI Agent。README 只做大众入口；模块、skill、local overlay、发布验证和 AI 协作规则放在这里。

## 产品表面规则

README 是产品入口，不是维护日志、个人解释或决策草稿。只放：项目定位、安装、常用命令、核心目录、边界和文档入口。

复杂背景、设计细节、私有/本机 overlay、AI 协作提示词，放在 `docs/` 或 LLL 工作区报告中。

## 演化协议

维护者和 Agent 在新增模块、扩展 CLI、拆分 skill 或引入自动化前，应先阅读 [docs/evolution.md](./evolution.md)。

默认策略：先补共同现实层，再补执行面；先文件化和 doctor/status/validate，再考虑 daemon/service/CI；先 patch 现有 umbrella skill 或开发文档，再新建 skill。新增复杂度必须说明它删除了哪些重复、风险或人工步骤。

## 文档语言规则

仓库的源文档只维护简体中文：

- `README.md` 和 `docs/*.md` 使用简体中文作为唯一源语言，不在标题或正文中同时维护英文翻译。
- 英文文档只由自动翻译流程生成到 `translations/en/**`，不要手工修改生成文件。
- 如果需要改英文表达，先优化中文源文档或翻译脚本，再重新生成英文版本。
- 技术名词、命令、文件名、配置 key、产品名可以保留英文，例如 `runtime skills`、`skillpack`、`registry`、`install-state.json`。

## CLI 设计

Secret / Credential Control Plane 的一等入口是 `aios secret ...`。它只管理 request、metadata、receipt、replica、consumer 和运行时注入；secret value 只能通过真实 TTY 的 `aios secret intake <request-id>` 录入，Agent 不读取、不打印、不提交 values。详细说明见 [`docs/secret-management.md`](./secret-management.md)。

CLI 分两层：

| 层级 | 面向用户的例子 | 用途 |
|---|---|---|
| 产品命令 | `aios status`, `aios doctor`, `aios update`, `aios update skills`, `aios update modules lins-living-loop` | 面向普通用户的稳定命令 |
| 专家子域 | `aios skillpack sync --apply`, `aios skillpack dev-link --apply`, `aios assets doctor` | 清单对账、开发、调试 |

`skillpack sync` 表示“按 `skillpack.yaml` 对 runtime skills 做对账/收敛”，不是普通 update。普通用户优先使用：

```bash
aios update skills
```

`aios update` 默认等价于 `aios update all`。需要粒度时使用：

```bash
aios update modules
aios update modules lins-living-loop
aios update skills
aios update ops
```

只有当某个更新对象有独立生命周期、耗时、失败风险或用户明确意图时，才值得成为独立 subject。现在 `modules`、`skills`、`ops` 足够。

## 全局命令安装

安装器总会创建：

```text
~/aios/bin/aios -> ~/aios/modules/aios-kit/aios
```

推荐用户把 `~/aios/bin` 加入 PATH：

```bash
export PATH="$HOME/aios/bin:$PATH"
```

如果用户想直接写入已有 PATH 目录，可使用：

```bash
bash install.sh --global-bin ~/.local/bin
```

安装器不会覆盖已有冲突的 `~/.local/bin/aios`。

## 新增 portable skill

适合加入 portable base pack 的 skill 至少满足一个条件：

- 大多数 AIOS 用户都会高频需要；
- 能明显提升安装后默认能力，而且副作用小；
- 与 AIOS 核心流程强相关，如 skill discovery、document workflows、LLL、resource/project resolution。

步骤：

1. 把条目加入 `skillpack.yaml`，写清 `source`、`skill`、`reason`。
2. 运行 dry-run：

   ```bash
   aios skillpack sync --dry-run
   aios update skills --dry-run
   ```

3. 实际安装并验证：

   ```bash
   aios update skills
   aios doctor
   ```

4. 做 fresh HOME smoke install，避免本机已有文件污染结果。
5. 通过 public audit 后 commit/push。

## 新增 first-party skill

如果 skill 是 AIOS 自己维护的，优先选择以下真源位置。普通用户不需要记忆这些命令；用户只需要告诉 Agent “把这个 skill 纳入 AIOS 托管”。Agent 负责分类、dry-run、执行和验证。

如果只是当前 Agent 执行某个命令的说明，不要急着创建新 skill；先放进 umbrella skill、开发文档或现有相关 skill。只有当领域边界稳定、高频、高风险或验证模型独立时，才拆成窄 companion skill。

### Skill 拆分原则

按稳定领域边界拆 skill，不按“每个 CLI 子命令”或“一次性迁移流程”拆 skill。

| 形态 | 适合情况 | 风险 |
|---|---|---|
| Umbrella skill | 跨 AIOS 架构、更新、local/private boundary、Agent 操作策略；流程仍在演化；需要统一心智 | 过大后可能变成垃圾桶，需保持薄入口和路由职责 |
| Narrow companion skill | 高频、高风险、有独立验证模型、加载后不污染其他任务，例如 secrets、服务运维、资源解析 | 拆太多会重复原则、增加触发和维护成本 |

当前默认：`aios-agent` 作为 umbrella policy skill；`aios-resource-resolver`、`aios-secret-management`、`aiops-vault`、`aiops-service-operations` 保持窄领域 skill。

### 一方 skill 真源位置

| 场景 | 真源位置 | Runtime 安装方式 |
|---|---|---|
| 小型 AIOS 专属 skill | `aios-kit/skills/<skill>` | 用户安装用 copy，开发机用 symlink |
| 独立产品型 skill | `~/aios/modules/<repo>` 下的独立 repo | 用户安装用 copy，开发机用 symlink |
| 模板 repo 内的子 skill | `<repo>/skills/<skill>` | 用户安装用 copy，开发机用 symlink |

不要把 runtime skills 目录当真源。开发机可以逐个 symlink runtime skill 到 Git worktree，但公开安装默认 copy。

本机先用 Hermes/Agent 创建出来的 skill，如果要变成 AIOS 托管、Git 管理、可发布的 first-party skill，Agent 可以使用 `adopt` actuator 接管，而不是手工搬目录。`adopt` 是 Agent/维护者执行面，不是用户需要记忆的 UX：

```bash
cd ~/projects/aios-kit

# 预览：自动从 ~/.agents/skills 和 ~/.hermes/skills 查找同名 skill
./aios skillpack adopt <skill-name> --dry-run

# 指定来源并执行：默认移动到 skills/<skill-name>，写入 skillpack.yaml，
# 再把 ~/.agents/skills/<skill-name> 替换成指向 Git 真源的 symlink
./aios skillpack adopt <skill-name> \
  --from ~/.hermes/skills/<category>/<skill-name> \
  --apply \
  --replace-runtime \
  --reason "<为什么这是 AIOS first-party skill>"

# 如果只想复制进 repo、保留原目录，用 --copy；但接管后应避免继续编辑旧目录。
./aios skillpack adopt <skill-name> --from <path> --copy --apply --replace-runtime
```

`adopt` 的安全边界：

- 默认 dry-run；只有 `--apply` 才写文件。
- 如果 `skillpack.yaml` 已托管同名 skill，会拒绝。
- 如果自动发现多个本地候选，会要求显式 `--from`。
- 默认目标是 `skills/<skill>`；只有与某个 module 强绑定时才用 `--dest modules/<module>/skills/<skill>`。
- runtime 默认使用 `~/.agents/skills/<skill>` symlink；不要创建同名 `~/.hermes/skills` overlay，除非刻意覆盖并在完成后清理。

接管后验证：

```bash
./aios skillpack doctor --target universal
./aios skillpack dev-link --dry-run
python3 -m py_compile scripts/aios.py scripts/audit_public.py
python3 scripts/audit_public.py
```

## 新增 module

module 是 `~/aios/modules/<name>` 下可更新的源码或模板 checkout。适合 module 的对象通常有独立生命周期，例如 LLL、OPS vault template、未来多设备互联模块。

新增 module 时判断：

- 它是公开 portable base，还是本机 local overlay？
- 安装器是否需要 clone 它？
- `aios update modules <name>` 是否足够，还是需要额外 refresh 步骤？
- 是否提供 runtime skill？如果有，runtime skill 应 copy/symlink 到哪里？

如果只是单个 skill，不要过早做成 module。先放 `skillpack.yaml` 或 `aios-kit/skills/<skill>`。

## 本机 overlay 策略

local overlay 用于特定用户自己的机器、私有基础设施、中央控制面或实验模块。它们可以属于该用户的 AIOS 实例，但不属于公开 portable base pack。

公开文档不得记录真实私有 overlay 名称、私有资源别名、主机名、secret handle 或机器特定运维事实。这些事实应放在 live AIOS instance 中，例如 OPS vault、instance state、本地 registry 或 local-only Agent profile 层。

`skillpack.local.yaml` 只是一种兼容/调试模式：当某个本地 checkout 临时需要 overlay reconciliation 时可以存在，但它不是私有实例事实的长期推荐位置，且必须保持 Git ignored。

未来如果多设备互联、中央 Agent、远程执行成为 AIOS 的公开核心能力，应抽象出 portable module/skill，只公开通用流程、schema 和模板，不公开私人资源事实。

## AIOps skills 的区别

`aiops-vault` 是 OPS vault 的入口/伴随 skill。它定义如何读取 vault、遵守密钥边界、维护 `resources.md`、`maintenance-log.jsonl`、`secrets-location.md` 等。它的 `SKILL.md` 位于 `aios-kit` 内置模块 `modules/aiops-vault-template` 根目录，所以开发机 runtime symlink 指向该模块根目录：

```text
~/.agents/skills/aiops-vault -> ~/projects/aios-kit/modules/aiops-vault-template
```

`aiops-service-operations` 是更窄的服务运维 workflow skill，位于内置模板模块的子目录：

```text
~/.agents/skills/aiops-service-operations -> ~/projects/aios-kit/modules/aiops-vault-template/skills/aiops-service-operations
```

## 如何让 AI 添加模块

```text
我做了一个新模块：<模块名>。
本地路径：<path>。
目标：把它纳入 AIOS 的可迁移安装/更新流程。
请判断它应该是 portable base、first-party skill、independent module，还是 local overlay。
要求：不要复制我的私有数据或密钥；不要接管朋友已有的整个 skills 目录；README 只写大众需要的信息；开发规则写到 docs/development.md；运行 dry-run、doctor、public audit、fresh HOME smoke install；通过后 commit 并 push。
```

## AIOS 自迭代规则

AIOS 不是一次性安装包，而是长期工作的操作层。Agent 在任何 AIOS 相关任务中，都应主动观察系统自身是否出现可改进信号：

- 重复手工步骤，应变成 CLI/API actuator；
- skill 触发条件、边界、验证方式过时或含糊；
- CLI 太冗长、缺少 dry-run/doctor/validate/JSON，导致 Agent 难以安全执行；
- 公开/私有边界容易误判；
- 用户实例更新时容易覆盖本地演化；
- 验证缺口、路径硬编码、重复状态或隐藏假设。

处理策略：

1. 如果修复安全、范围清楚，直接更新相关 skill、文档、脚本或验证。
2. 如果会改变工作流、CLI surface、兼容性或架构，先向用户提出简短改进建议。
3. 如果暂不处理，把失败模式写入 LLL error/trace、OPS maintenance log 或相关 issue/todo。

不要为了仪式感自迭代；只修复真实失败模式、反复摩擦、风险歧义或经过验证的简化机会。

## Upstream / Instance 更新融合模型

`aios-kit` 是 AIOS 实例的 seed/upstream，不是长期覆盖用户实例的单一真源。用户长期使用后，runtime skills、local overlays、OPS vault、registry、工作流和 Agent 行为都会产生个性化演化。更新必须是 reconcile，而不是 reset。

更新前先分类：

| 对象 | 策略 |
|---|---|
| upstream-managed copy | 若 install-state/hash 显示未被本地修改，可自动更新；若已本地修改，提出 merge/force/skip |
| user-owned / local overlay | 属于实例，不从公开 upstream 覆盖，也不发布私人事实 |
| runtime skill local edits | 视为可能的用户/Agent 自迭代，优先三方合并：upstream 新版、上次安装基线、本地演化副本 |
| generated/cache | 可按状态安全重建或清理 |
| external/app-owned | AIOS 只索引/检查，不移动、不接管 |

未来更新工具应优先提供 `status`、`diff`、`doctor`、`propose`、`reconcile`，让 Agent 能解释“会变什么、为什么、冲突在哪里、有哪些安全选项”。

## Skillpack 更新语义

`aios-kit` 比普通“重新 add 一遍”更保守：

- 每个托管 skill 记录安装路径和本地内容 hash；
- 更新前如果发现 runtime skill 被用户本地改动，默认拒绝覆盖；
- 只有显式 `--force` 才覆盖；
- stale skill 只在 `--prune --apply` 时移除；
- prune 只删除 install-state 中记录为 `aios-kit` managed 的路径。

开发机可以使用 symlink mode 让 agent 对 runtime skill 的编辑落在 Git-visible worktree：

```bash
cd ~/projects/aios-kit
./aios skillpack dev-link --apply
./aios skillpack doctor
```

普通用户/朋友安装默认使用 copy mode：

```bash
./aios skillpack sync --apply
```

`--apply` 和 `--dry-run` 互斥；低层 skillpack/assets 命令默认只预览，只有显式传入 `--apply` 才会实际修改。

## 安装向导开发

`aios-install` 是 Go/huh 交互前端，不拥有真实安装动作。维护原则：

- `install.sh` 仍是安装后端和 automation contract；Go 只构造 `install.sh --non-interactive ...` 参数。
- 私密参数（如 `--proxy-subscription-url`）在预览/JSON 报告中默认脱敏；实际 argv 才保留真实值。
- 非 TTY/CI/Agent 场景优先使用 `--no-wizard --print-command` 或 `--json`。
- 用户不应被要求预装 Go；Go 只用于开发构建，正式分发通过 GitHub Release 提供预编译二进制。
- `install.sh --wizard` 的分发顺序是：PATH 上的 `aios-install` → checkout 中 `go run` → 下载 release asset 并校验 `aios-install_checksums.txt` → Bash fallback。

常用开发命令：

```bash
go test ./...
go build ./cmd/aios-install
scripts/build_aios_install_release.sh /tmp/aios-install-dist
./aios-install --no-wizard --script ./install.sh --print-command --dry-run --proxy no --no-dev-env --no-hermes --no-aiops
./aios-install --no-wizard --script ./install.sh --json --dry-run
```

当前 `huh` v1 需要 Go 1.23+；开发机可使用 Go toolchain auto，发布 CI 应显式安装 Go 1.23 或更新版本。

Release workflow 位于 `.github/workflows/release-aios-install.yml`。推送 `v*` tag 时会构建：

```text
aios-install_linux_amd64.tar.gz
aios-install_linux_arm64.tar.gz
aios-install_darwin_amd64.tar.gz
aios-install_darwin_arm64.tar.gz
aios-install_windows_amd64.tar.gz
aios-install_windows_arm64.tar.gz
aios-install_checksums.txt
```

## 发布检查清单

发布前至少运行：

```bash
bash -n install.sh
go test ./...
go vet ./...
go build ./cmd/aios-install
scripts/build_aios_install_release.sh /tmp/aios-install-dist
python3 -m py_compile scripts/aios.py scripts/audit_public.py
python3 scripts/audit_public.py
aios update --dry-run
aios update skills --dry-run
aios update modules --dry-run
aios doctor

tmp_home="$(mktemp -d)"
./aios --home "$tmp_home" init --dry-run
./aios --home "$tmp_home" status

git status --short
```

涉及安装器、skillpack、模块 clone、runtime skills 路径时，必须做 fresh HOME smoke install。
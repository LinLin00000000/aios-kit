# aios-kit 架构

`aios-kit` 是一个装配/控制仓库，不是把所有资产都吞进来的 monorepo。

## 核心决策

保持独立项目的独立性，用 manifest、module、registry 和本地链接把它们连接起来：

- `aios-kit`：安装器、CLI、公开 manifest、选定的一方 skills 和文档。
- `lins-living-loop`：独立的一方 workflow skill / project。
- `aiops-vault-template`：内置于 `aios-kit/modules/aiops-vault-template` 的公开 OPS vault 模板模块。
- `~/aios/vault/ops`：新 AIOS 实例默认且唯一的 live OPS vault。

## Agent-first / Human fallback

AIOS 的架构假设是：**Agent 是默认操作者，人类是授权者、目标设定者和兜底操作者**。

这不是“把所有东西自动化”的口号，而是具体影响仓库边界和命令设计：

1. **稳定探针优先**：每个长期模块都应尽量暴露 `doctor`、`status`、`validate` 和 `--json`，方便 agent 判断能否继续。
2. **人类命令是 fallback**：文档中的 shell 命令需要可复制，但主要价值是让 agent 有明确操作面；正常情况下人类不需要逐条理解。
3. **控制面不吞状态机**：AIOS 可以代理 `aios lll ...`，但 LLL 的队列、lease、runner、artifacts 仍归 LLL 协议/CLI 管理。
4. **文件化治理**：项目注册、OPS vault、安装状态、维护日志和 LLL workdir 是跨 agent 的共同事实层。
5. **公开可恢复**：公开仓库必须能在 fresh clone / Docker / 新机器上恢复关键能力，不能只依赖作者机器上的隐式 symlink。

## Source、runtime 与 state

不要把所有 repo 都移动到 `aios-kit` 下面。边界应清晰：

| 层级 | 负责内容 | 示例 |
|---|---|---|
| 分发源 | 安装器、CLI、公开文档/manifest | `~/projects/aios-kit` 或 `~/aios/modules/aios-kit` |
| Modules | 可更新的 checkout / template | `~/aios/modules/lins-living-loop` |
| Runtime skills | agent 实际加载的 skills | `~/.agents/skills`、`~/.hermes/skills` |
| Live vault | 私有/当前运维事实 | `~/aios/vault/ops` |
| Skillpack state | 安全更新/裁剪记录 | `~/aios/vault/ops/state/aios-kit/install-state.json` |

外部 skills 通过 `npx skills` 安装。一方 skills 对普通用户可以复制安装，对作者开发机可以 symlink。

## 安装模式与开发模式

给朋友或干净机器使用安装器：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

已经 checkout 仓库时：

```bash
bash install.sh
```

作者开发时使用逐个 skill symlink，让 runtime 里的编辑能落到 Git 可见的 worktree：

```bash
cd ~/projects/aios-kit
./aios skillpack dev-link --apply
./aios skillpack doctor
```

不要 symlink 或替换整个 agent skills 目录。公开安装默认逐个复制/同步选定 skills。

## 本地结构与链接策略

标准开发路径有意和 runtime 安装路径分离：

| 对象 | 路径 | 策略 |
|---|---|---|
| 主套件 | `~/projects/aios-kit` | 装配脚本、manifest、文档的真源 |
| LLL | `~/projects/lins-living-loop` | 独立一方源项目 |
| AIOps 模板 | `~/projects/aios-kit/modules/aiops-vault-template` | 公开可复用模板 |
| Live AIOps vault | `~/aios/vault/ops` | 默认实例 vault；私有/当前事实 |
| 历史 live vault | `~/ai-ops` | 已废弃；发现时迁移到 `~/aios/vault/ops`，不要新建兼容链接 |
| Universal skills | `~/.agents/skills` | runtime 安装目标，不自动等于真源 |
| Hermes skills | `~/.hermes/skills` | Hermes profile runtime skills |

规则：

1. 模板不是 live 资产。
2. Runtime 目录只有在明确提升后才成为真源。
3. 活跃的一方 skills 应该能被 Git 追踪。
4. Symlink 用于作者本地开发；copy/install 是公开默认行为。
5. 只有当前 install-state 记录过的路径才允许自动 prune。

## 关键决策

- **主项目名**：使用 `aios-kit`；skillpack 是模块，不是 repo 边界。
- **LLL 保持独立**：`aios-kit` 引用、链接或复制它，但不 vendor 它。
- **OPS 模板与 live vault 分离**：模板是可复用起点；live vault 是用户/私有状态。
- **作者开发用 symlink，公开分发用 copy**：作者机器优化可编辑性；公开安装优化可迁移性。
- **Manifest + 薄脚本，不做新包管理器**：`aios-kit` 读取 `skillpack.yaml`，对外部 skills 调用 `npx skills`，对一方 skills 直接 copy/symlink。

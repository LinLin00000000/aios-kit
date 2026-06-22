# 开发指南

本文档面向维护者、贡献者和后续协作的 AI Agent。README 只做大众入口；模块、skill、local overlay、发布验证和 AI 协作规则放在这里。

## 产品表面规则

README 是产品入口，不是维护日志、个人解释或决策草稿。只放：项目定位、安装、常用命令、核心目录、边界和文档入口。

复杂背景、设计细节、私有/本机 overlay、AI 协作提示词，放在 `docs/` 或 LLL 工作区报告中。

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

如果 skill 是 AIOS 自己维护的，优先选择以下真源位置：

| 场景 | 真源位置 | Runtime 安装方式 |
|---|---|---|
| 小型 AIOS 专属 skill | `aios-kit/skills/<skill>` | 用户安装用 copy，开发机用 symlink |
| 独立产品型 skill | `~/aios/modules/<repo>` 下的独立 repo | 用户安装用 copy，开发机用 symlink |
| 模板 repo 内的子 skill | `<repo>/skills/<skill>` | 用户安装用 copy，开发机用 symlink |

不要把 runtime skills 目录当真源。开发机可以逐个 symlink runtime skill 到 Git worktree，但公开安装默认 copy。

## 新增 module

module 是 `~/aios/modules/<name>` 下可更新的源码或模板 checkout。适合 module 的对象通常有独立生命周期，例如 LLL、OPS vault template、未来多设备互联模块。

新增 module 时判断：

- 它是公开 portable base，还是本机 local overlay？
- 安装器是否需要 clone 它？
- `aios update modules <name>` 是否足够，还是需要额外 refresh 步骤？
- 是否提供 runtime skill？如果有，runtime skill 应 copy/symlink 到哪里？

如果只是单个 skill，不要过早做成 module。先放 `skillpack.yaml` 或 `aios-kit/skills/<skill>`。

## 本机 overlay 策略

local overlay 用于维护者自己的机器、私有基础设施、中央控制面或实验模块。它们可以属于“Lin 的 AIOS”，但不属于公开 portable base pack。

当前 local overlay 示例：

| Skill | 位置 | 当前为何只放本机 |
|---|---|---|
| `cloud-server-ssh-assets` | `skillpack.local.yaml` | 绑定 Lin 的云服务器清单与 SSH/资源约定 |
| `central-agent-control-plane` | `skillpack.local.yaml` / Hermes profile | 绑定 Lin 的中央 Hermes/控制面运维 |

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
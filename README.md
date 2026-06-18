# aios-kit

`aios-kit` 是一个轻量、可迁移的 Personal AIOS 安装与分发套件。它以 Hermes Agent 为基础，把精选 Agent skills、LLL 工作流、OPS vault 模板、项目注册表和本地实例目录组织成一个可以在新机器上快速部署的 AIOS 基础环境。

当前安装器主要在 Ubuntu/Debian 系云服务器上验证过；其他 Linux 发行版还没有完整测试，建议先使用 `--dry-run` 或容器环境试跑。

`aios-kit` is a lightweight, portable installation and distribution kit for a Personal AIOS. It is built around Hermes Agent and assembles curated agent skills, the LLL workflow, an OPS vault template, a project registry, and a local instance layout into a deployable base environment.

The installer is currently tested mainly on Ubuntu/Debian-like cloud servers. Other Linux distributions have not been fully validated yet; use `--dry-run` or a container first.

---

## 快速安装 / Quick install

一行安装命令会直接进入交互式安装流程，适合新手和首次部署：

The one-line command starts an interactive installer, suitable for first-time users:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

如果当前机器还没有代理、无法直连 GitHub，可以临时使用你信任的 GitHub raw 镜像。镜像只用于取回同一份安装脚本，安装后仍建议通过代理访问官方源：

If the machine has no proxy yet and cannot reach GitHub directly, use a GitHub raw mirror you trust. The mirror is only for fetching the same installer; after proxy setup, official sources are preferred:

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

安装器会询问安装路径、是否配置代理、是否安装开发环境、是否安装 Hermes 核心组件、是否安装 OPS vault，以及是否把 `aios` 加入 PATH。默认安装根目录是 `~/aios`，TUN 默认开启，开发环境/核心组件/OPS vault 默认安装。非交互参数基本对应这些交互选择；更细的参数，例如订阅 URL、节点 YAML、GitHub 镜像、安装目标和 copy/symlink 模式，用于自动化部署时直接指定。

The installer asks for the install root, proxy setup, development environment, Hermes core components, OPS vault, and whether to add `aios` to PATH. Defaults: install root `~/aios`, TUN enabled, development environment/core components/OPS vault enabled. Non-interactive flags map to these choices; more detailed flags such as subscription URL, proxy YAML, GitHub mirror, skill target, and copy/symlink mode are supplied directly for automation.

自动化部署可以使用非交互参数：

For automated deployments, use non-interactive flags:

```bash
bash install.sh --non-interactive -y --root ~/aios --proxy auto --add-to-path yes --target universal --mode copy
```

---

## 安装内容 / What it installs

默认实例布局：

Default instance layout:

```text
~/aios/
  bin/                     # aios command shim
  config/                  # instance configuration
  vault/ops/               # operational vault initialized from aiops-vault-template
  work/                    # LLL / agent work directories
  skills/                  # AIOS skill metadata/cache, not the runtime skills dir
  modules/                 # updateable module checkouts
  network/mihomo/          # optional Mihomo/Clash config template
  state/
  logs/
  cache/
```

Agent 真正加载的 skills 仍然安装在 Agent 自己的 runtime skills 目录，例如 `~/.agents/skills` 或 Hermes profile 的 `~/.hermes/skills`。`aios-kit` 只逐个安装它管理的 skills，不接管整个 skills 目录。

Agent-loadable skills are still installed into the agent's real runtime skills directory, such as `~/.agents/skills` or a Hermes profile's `~/.hermes/skills`. `aios-kit` installs only selected managed skills one by one; it does not take over the whole skills directory.

---

## 新服务器部署流程 / New-server deployment flow

安装器按保守、幂等的顺序执行：先检测，再决定是否执行。

The installer is conservative and idempotent: it checks first, then acts only when needed.

1. **网络探测 / Network check**  
   默认在不使用代理环境变量的情况下测试外网连通性。如果直连可用，跳过代理；如果不可用，交互式安装会询问是否安装 Mihomo/Clash，默认安装。非交互模式下 `--proxy auto` 会在直连失败时自动进入 Mihomo 安装，除非显式 `--proxy no`。

   By default it tests external connectivity without proxy environment variables. If direct access works, proxy setup is skipped. If direct access fails, interactive mode asks whether to install Mihomo/Clash, defaulting to yes. In non-interactive mode, `--proxy auto` installs Mihomo when direct access fails unless `--proxy no` is set.

2. **代理配置 / Proxy setup**  
   Mihomo 默认作为 AIOS 内置网络组件安装到 `~/aios/network/mihomo`，并生成 systemd unit：`/etc/systemd/system/aios-mihomo.service`。TUN 默认开启；如果关闭 TUN，安装器会写入 `proxy_on` / `proxy_off` / `proxy_test` / `proxy_restart` 等 shell helper，并默认在 shell 中自动 `proxy_on`。Mihomo 内核在安装时下载；默认根据 `--mihomo-version` 组合 GitHub release `.gz` URL，也可以用 `--mihomo-url` 指定完整下载地址。使用 `--github-mirror` 时，GitHub release、UI/geodata 等 URL 会加镜像前缀。

   Mihomo is installed as an AIOS network component under `~/aios/network/mihomo` and wired through `/etc/systemd/system/aios-mihomo.service`. TUN is enabled by default. If TUN is disabled, the installer writes shell helpers such as `proxy_on`, `proxy_off`, `proxy_test`, and `proxy_restart`, and auto-enables proxy environment variables in shell sessions by default. The Mihomo core is downloaded at install time. By default the installer derives a GitHub release `.gz` URL from `--mihomo-version`; pass `--mihomo-url` to override it. With `--github-mirror`, GitHub release, UI, and geodata URLs are prefixed through the mirror.

   推荐两种输入方式：

   Two input styles are recommended:

   ```bash
   # 机场/供应商订阅：生成 proxy-providers.airport
   bash install.sh --proxy yes --proxy-subscription-url 'https://example.com/sub?token=...'

   # 自建节点：提供只包含 proxies 列表或 proxies: 字段的本地 YAML 片段
   bash install.sh --proxy yes --proxy-proxies-file ./my-proxies.yaml
   ```

   安装器会把订阅 URL 渲染成 `proxy-providers`，或把本地 YAML 片段合成为完整 `config.yaml`，并自动把节点名加入 `PROXY` 组。仓库中的 `templates/mihomo/config.yaml` 只作为公共安全底板，不包含私人订阅、UUID 或节点密钥。

   The installer renders a subscription URL into `proxy-providers`, or merges a local YAML proxy snippet into a complete `config.yaml` and adds node names to the `PROXY` group. The repository template is only a public-safe base; it contains no private subscription URL, UUID, or node secret.

3. **官方源恢复 / Official source reset**  
   开启代理后，安装器会尽量把 npm、pip、Docker 等源恢复到官方默认方向。当前不会自动重写 apt 镜像源：apt source 与 Ubuntu/Debian 版本、云厂商初始化策略强相关，暂时只提示并保守处理；后续可以加入明确的 Ubuntu OS profile。

   After proxy setup, the installer moves npm, pip, Docker, and similar sources toward official defaults where safe. It does not rewrite apt mirrors yet: apt sources depend on Ubuntu/Debian release and cloud-vendor initialization, so they are currently handled conservatively. A dedicated Ubuntu OS profile can be added later.

4. **开发环境 / Development environment**  
   检测并安装 Python/UV、NVM + Node 24 LTS、Docker、Caddy。已存在则跳过，不重复安装。

   It checks and installs Python/UV, NVM + Node 24 LTS, Docker, and Caddy. Existing components are skipped.

5. **核心组件 / Core components**  
   检测并安装 Hermes Agent；将 Hermes 的外部 skill 目录约定到 `~/.agents/skills`；安装 AIOS skillpack。

   It checks and installs Hermes Agent, configures the external skill directory convention as `~/.agents/skills`, and installs the AIOS skillpack.

6. **AIOps 记录 / AIOps records**  
   OPS vault 安装后，Docker 和 Caddy 会作为 AIOS 运维资源记录入口写入维护日志或模板提供的资源档案。

   After the OPS vault is installed, Docker and Caddy are recorded as AIOS operational resources via the maintenance log or the vault template's resource records.

---

## 安装选项 / Installer options

常用选项：

Common options:

```bash
bash install.sh --dry-run                                  # preview actions / 预览操作
bash install.sh --root ~/my-aios                           # choose instance root / 指定实例根目录
bash install.sh --proxy auto                               # direct test, proxy only if needed / 先测试直连
bash install.sh --github-mirror https://gh-proxy.com/       # mirror GitHub/raw release URLs / GitHub 镜像前缀
bash install.sh --proxy yes --proxy-subscription-url URL    # provider subscription / 机场订阅
bash install.sh --proxy yes --proxy-proxies-file nodes.yaml # self-hosted nodes / 自建节点片段
bash install.sh --mihomo-version v1.19.27                   # choose Mihomo core release / 指定 Mihomo 内核版本
bash install.sh --no-proxy-tun --proxy-auto-env yes         # env proxy helpers without TUN / 无 TUN 时自动 proxy_on
bash install.sh --add-to-path yes                          # add ~/aios/bin to PATH / 加入 PATH
bash install.sh --no-dev-env                               # skip Python/Node/Docker/Caddy phase / 跳过开发环境
bash install.sh --no-core                                  # skip Hermes/core phase / 跳过核心组件
bash install.sh --no-aiops                                 # skip OPS vault template / 跳过 OPS vault
bash install.sh --target universal --mode copy             # portable skill install default / 默认 portable 模式
bash install.sh --force                                    # overwrite locally modified managed skill copies / 强制覆盖托管 skill
```

查看完整帮助：

Show full help:

```bash
bash install.sh -h
```

---

## 常用命令 / Common commands

安装后推荐直接使用 `aios`。如果没有配置 PATH，也可以使用 `~/aios/bin/aios` 或在仓库中运行 `./aios`。

After installation, use `aios` directly. If PATH is not configured, use `~/aios/bin/aios` or run `./aios` inside the repository.

```bash
aios status                 # show instance summary / 查看实例摘要
aios doctor                 # validate wiring / 检查实例与 skillpack
aios update                 # update modules, OPS template, and managed skills / 全量更新
aios update --dry-run       # preview update / 预览更新
aios update skills          # refresh managed runtime skills / 刷新托管 skills
aios update modules         # update module Git checkouts / 更新模块
aios update ops             # refresh OPS vault template / 刷新 OPS vault 模板
```

底层 skillpack 命令主要用于开发和调试。普通用户通常只需要 `aios update skills`。

Low-level skillpack commands are mainly for development and debugging. Most users should use `aios update skills`.

```bash
aios skillpack list
aios skillpack doctor --target universal
aios skillpack sync --dry-run
aios skillpack sync --apply
aios skillpack sync --prune --apply
aios skillpack dev-link --apply       # dev only: symlink first-party skills one by one
```

---

## Skillpack 更新语义 / Skillpack update semantics

`npx skills update` 会根据 lock 文件记录的 upstream skill hash 判断是否有新版本，然后重新执行 `skills add` 刷新安装。它适合管理来自上游的技能，但不应假设用户本地改动一定会被自动合并。

`npx skills update` uses lock-file upstream hashes to detect newer skill versions and then reruns `skills add` to refresh installations. It is useful for upstream-managed skills, but local user edits should not be assumed to merge automatically.

`aios-kit` 的策略更保守：

`aios-kit` uses a more conservative policy:

- 每个托管 skill 在 state 中记录安装路径和本地内容 hash。
- 更新前如果发现 runtime skill 已被用户本地改动，默认跳过并提示。
- 只有显式传入 `--force` 时才覆盖本地改动。
- 第一方和第三方 skill 使用同一套保护语义。
- stale skill 只在 `--prune --apply` 时移除。

- Each managed skill records its installed path and local content hash in state.
- If a runtime skill has local edits, updates skip it by default and print a warning.
- Local edits are overwritten only with `--force`.
- First-party and third-party skills share the same protection semantics.
- Stale skills are removed only with `--prune --apply`.

---

## 模块与 skills / Modules and skills

`~/aios/modules` 保存可更新的模块源码或模板 checkout，例如：

`~/aios/modules` stores updateable module source/template checkouts, for example:

```text
~/aios/modules/aios-kit
~/aios/modules/lins-living-loop
~/aios/modules/aiops-vault-template
```

runtime skills 是 Agent 实际加载的能力，通常位于：

Runtime skills are the capabilities the agent actually loads, usually under:

```text
~/.agents/skills/<skill>
~/.hermes/skills/<skill>
```

默认 portable 安装使用 copy，更适合朋友机器、Windows 和稳定环境。first-party 开发可以使用逐个 symlink，让修改直接落在 Git worktree 中。

Portable installs use copy mode by default, which is safer for friends' machines, Windows, and stable environments. First-party development can use per-skill symlinks so edits land directly in Git worktrees.

---

## 内置 skill set / Included skills

`skillpack.yaml` 中的 portable base pack 包括：

The portable base pack in `skillpack.yaml` includes:

- **文档 / Documents**: `docx`, `pptx`, `xlsx`, `pdf`
- **skill 发现与创作 / Skill discovery and authoring**: `find-skills`, `skill-creator`, `awesome-mcp-servers-discovery`
- **设计与前端 / Design and frontend**: `frontend-design`, `ui-ux-pro-max`, `vercel-composition-patterns`, `web-design-guidelines`
- **AIOS 第一方 / AIOS first-party**: `aios-resource-resolver`, `github-repo-search`, `lins-living-loop`

OPS vault 模板还会安装两个 operation skills：`aiops-vault` 和 `aiops-service-operations`。

The OPS vault template also installs two operation skills: `aiops-vault` and `aiops-service-operations`.

---

## 运维资料库 / OPS vault

`aios-kit` 会从公开模板 `aiops-vault-template` 初始化一个新的 OPS vault：

`aios-kit` initializes a new OPS vault from the public `aiops-vault-template`:

```text
~/aios/vault/ops/
  README.md
  resources.md
  maintenance-log.jsonl
  secrets-location.md
  projects/
  scripts/aiops.py
```

它不会复制维护者的私人 live vault。新机器会从模板开始，然后记录自己的资源、服务和维护日志。

It does not copy the maintainer's private live vault. A new machine starts from the template and records its own resources, services, and maintenance history.

---

## 项目注册表 / Project registry

当前实现的是最小项目注册表，而不是完整 Project Graph。它适合记录本机 AIOS 需要识别的项目、路径、GitHub URL、别名和角色。

The current implementation is a minimal project registry, not a full Project Graph. It records projects, paths, GitHub URLs, aliases, and roles that the local AIOS instance needs to resolve.

```text
~/aios/vault/ops/projects/
  registry.jsonl
  aliases.yaml
```

---

## 设计边界 / Boundaries

- `~/aios` 是本机部署实例，不应该整体提交到公开仓库。  
  `~/aios` is a local deployed instance and should not be committed wholesale.
- `~/aios/vault/ops` 是 live operational vault，不应该把私人事实或密钥写进本仓库。  
  `~/aios/vault/ops` is a live operational vault; private facts and secrets should not be committed here.
- `~/.agents/skills` 和 `~/.hermes/skills` 是 Agent runtime 目录，`aios-kit` 不接管整个目录。  
  `~/.agents/skills` and `~/.hermes/skills` are runtime directories; `aios-kit` does not take them over.
- 机器专属、本地专属、私有基础设施相关内容应放在 local overlay，而不是 portable base pack。  
  Machine-specific, local-only, or private-infrastructure-specific assets belong in local overlays, not the portable base pack.

---

## 开发 / Development

开发、贡献、新增 module/skill、本机 overlay 的规则见：

Development, contribution, module/skill addition, and local overlay rules are documented in:

- [`docs/development.md`](docs/development.md)
- [`docs/security-and-privacy.md`](docs/security-and-privacy.md)
- [`docs/aios-resource-architecture.md`](docs/aios-resource-architecture.md)

发布前建议运行：

Before publishing, run:

```bash
python3 scripts/audit_public.py
bash install.sh --dry-run --non-interactive --no-dev-env --no-core --no-aiops
aios update --dry-run
aios doctor
git status --short
```

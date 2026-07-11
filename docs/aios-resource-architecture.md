# AIOS 资源架构

AIOS 不是一个巨大的文件夹，而是一个**资源注册表 + 上下文解析器 + 工作流层**。它指向项目、设备、服务、数据资产、skills 和 vaults，但不需要拥有它们的全部内容。

Repo、source、runtime 的边界见 [architecture.md](architecture.md)。本文只说明资源注册表语义。

## 一句话架构

当用户说“LLL 项目”时，agent 应该把这个说法解析成标准资源 ID，选择当前最合适的位置，遵守权限边界，然后再行动。

## 资源边界

```text
AIOS                 整体个人数字操作系统
├── AIOps            运维/基础设施子系统
├── Project Graph    创作/项目资产子系统
├── Data Assets      文件/数据治理子系统
├── Devices          中央服务器与边缘节点注册表
├── Workflows        LLL、Kanban、cron、agent runners
├── Identity/Self    偏好、叙事、数字自我上下文
└── Worlds           数字世界/长期创作世界层
```

AIOps 是 AIOS 的一个子系统，不是整个 AIOS。

## 注册表文件

默认项目注册表位于实例 OPS vault 内：

```text
~/aios/vault/ops/projects/registry.jsonl
~/aios/vault/ops/projects/aliases.yaml
```

个人数据 Source 的显式记录位于：

```text
~/aios/vault/ops/sources/registry.jsonl
~/aios/vault/ops/sources/aliases.yaml
```

这不是第二张全局路径总表。`aios source list` 会把显式 Source 记录与 Project Registry 投影编译成统一视图；Project 的本地 checkout 与 GitHub remote 仍由 Project Registry 拥有事实。全文件路径、hash、mtime 与检索索引只能是可重建 projection/cache。

新的公开安装把 `~/aios/vault/ops` 视为默认 live vault；不要为 OPS vault 维护额外兼容入口。

## 资源结构

项目/资源条目应显式、文件化：

```json
{
  "id": "lins-living-loop",
  "kind": "project",
  "name": "Lin's Living Loop",
  "aliases": ["LLL", "DOP", "Living Loop"],
  "locations": [
    {"kind": "local", "device": "central-hermes", "path": "~/projects/lins-living-loop"},
    {"kind": "github", "url": "https://github.com/<owner>/lins-living-loop"}
  ],
  "permissions": {
    "ai_indexable": "yes",
    "agent_write": "ask-first",
    "external_model": "yes-if-public"
  },
  "role_in_aios": "workflow-substrate",
  "status": "active"
}
```

## 资源/项目注册表 CLI

能用 CLI 时优先用 CLI，不要手工编辑：

```bash
aios project list
aios project list --json
aios project get <id-or-alias>
aios project add --id <id> --name "<name>" --path <path> --github <url> --alias <alias>
aios project alias <alias> <id>
aios project validate
```

## Source Registry CLI

Agent 通过自然语言理解目标，再使用 CLI 做确定性结构修改。人类通常不需要记命令；以下命令是 Agent actuator 和排障入口：

```bash
aios source list
aios source list --json
aios source get <id-or-alias>
aios source add --id <id> --name "<name>" --kind data_root --path <path> \
  --access-mode read_only_reference --sync-mode device_authoritative_mirror \
  --backup-status planned --sensitivity private
aios source alias <alias> <id>
aios source validate
```

`source list` 默认还显示 Project Registry 的只读投影；`--explicit-only` 只显示显式 Source records。CLI 不扫描整盘、不移动文件、不创建检索真源，也不把 indexed 等同于可写。

Source 级关键边界：

- `access_mode`：`read_only_reference` / `maintain_in_place` / `curate_reversible` / `source_specific`；
- `sync_mode`：`none` / `device_authoritative_mirror` / `managed_bidirectional` / `server_canonical_replica` / `metadata_only_remote`；
- `backup_status`：只有 `verified` 才表示通过了实际恢复证据，而不是“看起来有副本”。

## Resolver 流程

解析用户提到的资源时，agent 应该：

1. 如果资源 resolver skill 可用，先加载它；
2. 查询 registry 条目和 alias；
3. 解析出标准资源 ID；
4. 在存在且权限允许时优先使用本地路径；
5. 必要时 fallback 到 GitHub、远程设备或其他位置；
6. 遵守敏感性和写权限；
7. 只有 alias 真的歧义时才询问用户。

## Skill 策略

保持 skills 足够薄：skills 描述**如何解析和操作**，registries 存储**有哪些东西**。

先从一个 umbrella skill `aios-resource-resolver` 开始。只有当某个子系统复杂到需要独立 workflow 时，再拆出新的 skill，例如 `project-graph`、`data-governance`、`device-and-edge` 或 `digital-self-context`。

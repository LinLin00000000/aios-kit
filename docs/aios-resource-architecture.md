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

`~/ai-ops` 只作为历史路径被识别和迁移；新的公开安装应把 `~/aios/vault/ops` 视为默认 live vault，且不要新建 `~/ai-ops` 兼容链接。

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

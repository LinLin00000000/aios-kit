# AIOS Resource Architecture

AIOS is not one giant folder. It is a **resource registry + context resolver + workflow layer** that points to projects, devices, services, data assets, skills, and vaults without owning all of them.

Repo/source/runtime boundaries live in [architecture.md](architecture.md). This document focuses on resource registry semantics.

## One-sentence architecture

When the user says “LLL 项目”, an agent should resolve that phrase to a canonical resource id, choose the best available location, respect permissions, and then act.

## Resource boundaries

```text
AIOS                 overall personal digital operating system
├── AIOps            operations/infrastructure subsystem
├── Project Graph    creative/project asset subsystem
├── Data Assets      file/data governance subsystem
├── Devices          central server and edge-node registry
├── Workflows        LLL, Kanban, cron, agent runners
├── Identity/Self    preferences, narratives, digital self context
└── Worlds           digital metaverse / long-term creative world layer
```

AIOps is one subsystem of AIOS, not the whole AIOS.

## Registry files

Default project registry files live in the instance OPS vault:

```text
~/aios/vault/ops/projects/registry.jsonl
~/aios/vault/ops/projects/aliases.yaml
```

`~/ai-ops` may exist as an author/legacy compatibility path, but new public installs should treat `~/aios/vault/ops` as the default live vault.

## Resource shape

A project/resource entry is intentionally explicit and file-based:

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

## Resource/project registry CLI

Prefer the CLI over hand-editing when possible:

```bash
aios project list
aios project list --json
aios project get <id-or-alias>
aios project add --id <id> --name "<name>" --path <path> --github <url> --alias <alias>
aios project alias <alias> <id>
aios project validate
```

## Resolver flow

When resolving a user-mentioned resource, an agent should:

1. load the resource resolver skill if available;
2. query registry entries and aliases;
3. resolve a canonical resource id;
4. prefer local paths when present and permitted;
5. fall back to GitHub/remote/device locations if needed;
6. respect sensitivity and write permissions;
7. ask only when the alias is genuinely ambiguous.

## Skill strategy

Keep skills thin: skills describe **how to resolve and operate**; registries store **what exists**.

Start with one umbrella skill, `aios-resource-resolver`. Split later only when a subsystem becomes complex enough to justify its own workflow, such as `project-graph`, `data-governance`, `device-and-edge`, or `digital-self-context`.

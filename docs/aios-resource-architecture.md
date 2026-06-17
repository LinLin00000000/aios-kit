# AIOS Resource Architecture

## One-sentence architecture

AIOS is not one giant folder. It is a **resource registry + context resolver + workflow layer** that points to projects, devices, services, data assets, skills, and real vaults without owning all of them.

## Boundaries

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

AIOps is a subsystem of AIOS, not the whole AIOS. Project Graph is another subsystem.

## Source layout vs runtime layout

Do not move every repo under `aios-kit`.

Use this separation:

| Layer | Owns | Example |
|---|---|---|
| `aios-kit` | schemas, scripts, templates, skills, docs | this repo |
| independent project repos | product/source truth | `lins-living-loop`, `aiops-vault-template` |
| live asset vaults | private/current facts | `~/ai-ops` |
| registries | pointers and permissions | `projects/registry.jsonl`, `devices.jsonl` |
| indexes | generated query surfaces | SQLite/FTS later |
| runtime | installed skills/services | `~/.agents/skills`, systemd, Docker |

## Should related repos be nested under aios-kit?

Default: **no**.

`projects/lins-living-loop` and `projects/aiops-vault-template` should remain sibling repos, not subdirectories inside `projects/aios-kit`, because they have independent lifecycles, releases, issues, and installation paths.

Acceptable alternatives:

1. **Sibling repos + registry** — recommended default.
2. **Git submodules under `vendor/` or `integrations/`** — only if the kit must pin exact versions.
3. **Monorepo** — only if the projects are no longer independently useful or released.
4. **Symlinks under a local-only workspace** — okay for author convenience, never as the public source layout.

Recommended local shape:

```text
~/projects/
  aios-kit/
  lins-living-loop/
  aiops-vault-template/
  ai-ops -> ~/ai-ops   # local discovery link only
```

## aiops-vault-template vs live ai-ops

`aiops-vault-template` is a reusable starter kit. It answers:

> What should a new AIOps vault look like?

Live `ai-ops` answers:

> What is true on this machine / this user's infrastructure now?

Relationship:

```text
aiops-vault-template --instantiate--> ~/ai-ops
~/ai-ops --lessons/schema improvements--> aiops-vault-template
~/ai-ops --registered/linked by--> aios-kit
```

Rules:

- Never sync live `~/ai-ops` wholesale back into the public template.
- Extract only reusable schema/scripts/docs after scrubbing current facts.
- Keep secrets out of both; live vault may record secret locations only.
- `aios-kit` may register and validate both, but does not own their content.

## Resource Registry + Context Resolver

The core AIOS primitive is a Resource:

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

When the user says “LLL 项目”, the agent should:

1. Load the resolver skill.
2. Query registries and aliases.
3. Resolve a canonical resource id.
4. Prefer local path if available and permitted.
5. Fall back to GitHub/remote/device path if needed.
6. Respect sensitivity and write permissions.
7. Ask only when ambiguous.

## Skill strategy

Start with **one thin umbrella skill**: `aios-resource-resolver`.

It handles the common resolution flow for projects, devices, services, data assets, workflows, and skills.

Split later only when a subsystem becomes complex:

- `project-graph`: project state, repo relationships, lifecycle, GitHub/local mapping.
- `data-governance`: sensitivity, backups, RAG/indexing, external model rules.
- `device-and-edge`: central vs Windows/edge execution paths.
- `digital-self-context`: identity/narrative/long-term meaning.

Do not store large resource facts in skills. Skills describe how to resolve; registries store what exists.

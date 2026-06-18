---
name: aios-resource-resolver
description: Resolve user-mentioned AIOS resources—projects, devices, services, data assets, workflows, skills, vaults—through registries and aliases before searching blindly. Facts live in registries; this skill only defines the lookup and permission workflow.
version: 0.1.0
author: Lin
license: MIT
---

# AIOS Resource Resolver

Use this skill when the user refers to a project, repo, service, device, vault, data asset, workflow, skill, or ambiguous personal resource such as “LLL 项目”, “那个 bot”, “Windows 边缘节点”, “ai-ops”, “数字花园”, or “之前那个 GitHub 项目”.

## Principle

```text
Skill = how to resolve and act
Registry = what exists and where it lives
```

Do not store large project/resource facts in this skill.

## Lookup order

1. Locate the active AIOS registry root:
   - preferred local/private: `~/aios/vault/ops/projects/`, legacy-compatible `~/ai-ops/projects/`, or future `~/aios/vault/projects/` / `~/aios/registries/`;
   - public examples only: `registries/*.example.*` inside `aios-kit`.
2. Read `registry.jsonl` and `aliases.yaml` if available.
3. Match against `id`, `name`, `aliases`, GitHub repo name, local path basename, and notes.
4. If there is exactly one match, resolve to its canonical `id`.
5. Prefer permitted local locations for inspection; use GitHub/remote/device locations only when local is missing or the resource lives elsewhere.
6. Respect permissions:
   - `agent_write: ask-first` means ask before editing;
   - `agent_write: read-only` means inspect only;
   - `external_model: no` means do not send substantive private contents to external models/tools;
   - sensitive/private resources should not be published or copied into public repos.
7. If multiple resources match, show the top candidates and ask the user to choose.
8. If no registry exists or no match is found, then use targeted discovery; do not start with full-disk search.

## Update discipline

When a stable new project/resource fact is discovered, suggest updating the registry. Do not put it in this skill unless it is a reusable lookup rule.

## Output shape

For nontrivial resolutions, report:

- canonical id;
- matched aliases/evidence;
- chosen location and device;
- permission boundary;
- next action.

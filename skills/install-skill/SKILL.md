---
name: install-skill
description: Install Agent/Hermes-compatible skills with the `npx skills add` CLI. Use this whenever the user asks to install/add skills, compare skill source formats, choose a target agent/location, use GitHub shorthand/URLs/tree paths/git URLs/local paths, filter a multi-skill repository with `@skill` or `--skill`, or install skills from skills.sh into universal `~/.agents/skills`.
---

# Install Skill

Use this skill to install skills via the `skills` CLI, especially when the user gives a GitHub repo, skills.sh entry, URL, local path, or asks whether two install syntaxes are equivalent.

## Default policy

Default to **universal global copy install** unless the user explicitly asks for a different agent/profile:

```bash
npx --yes skills@latest add <source> -g -y --agent universal --copy
```

Expected default runtime path:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

Why this default:

- `universal` maps to `.agents`, which is shared by many agents and is the user's preferred portable/default skill location.
- `--copy` is stable for public/friend installs and avoids symlink/cache coupling.
- Profile-specific locations such as `~/.hermes/skills` should be used only when the user explicitly wants a Hermes-profile-local skill.

## First identify the target environment

Before installing, make a quick target decision:

1. **What machine/node are we operating on?**
   - For this user's central Hermes setup, local tools run on the Linux cloud server unless the task explicitly targets a Windows/edge node.
   - If the user asks to install on another machine/agent, use that machine's shell or remote execution path.
2. **Which agent should load the skill?**
   - Default: `--agent universal` -> `~/.agents/skills`.
   - If the user explicitly says Claude Code, Cursor, Codex, etc., use the `skills` CLI agent name for that agent and verify the install summary path.
   - If the user explicitly wants Hermes profile-local behavior, use the AIOS/Hermes workflow for `~/.hermes/skills`; do not silently choose it.
3. **Is this a reusable install or a development skill?**
   - Normal/user install: copy via `npx skills ... --copy`.
   - First-party local development: keep the Git repo as truth source and symlink the runtime skill to the repo worktree; do not edit a copied runtime skill as truth.

Useful preflight commands:

```bash
node --version
npm --version
npx --yes skills --help
```

If `node`/`npx` is missing, install or enable the dev environment first; do not manually copy skills as a substitute unless the user explicitly chooses a fallback.

## Source formats

### GitHub shorthand: `owner/repo`

Install skills discovered in a GitHub repository:

```bash
npx --yes skills@latest add vercel-labs/agent-skills -g -y --agent universal --copy
```

If the repo contains multiple skills, prefer explicit filters for reproducibility.

### GitHub shorthand + `--skill`

Install one skill:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines \
  -g -y --agent universal --copy
```

Install multiple skills from the same repo:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines vercel-composition-patterns \
  -g -y --agent universal --copy
```

Repeated `--skill` is also acceptable:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines \
  --skill vercel-composition-patterns \
  -g -y --agent universal --copy
```

### GitHub shorthand + `@skill`

Install exactly one skill with compact syntax:

```bash
npx --yes skills@latest add vercel-labs/agent-skills@web-design-guidelines \
  -g -y --agent universal --copy
```

This is effectively equivalent to:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines \
  -g -y --agent universal --copy
```

Use `@skill` for one source -> one selected skill. Use `--skill` for multiple skills from the same source.

### Full GitHub URL

```bash
npx --yes skills@latest add https://github.com/vercel-labs/agent-skills \
  -g -y --agent universal --copy
```

Equivalent in intent to:

```bash
npx --yes skills@latest add vercel-labs/agent-skills -g -y --agent universal --copy
```

### Full GitHub URL + `--skill`

```bash
npx --yes skills@latest add https://github.com/vercel-labs/agent-skills \
  --skill web-design-guidelines \
  -g -y --agent universal --copy
```

### GitHub tree subdirectory URL

If a skill is in a repository subdirectory, point directly at the tree path:

```bash
npx --yes skills@latest add https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines \
  -g -y --agent universal --copy
```

Use this when the exact skill directory URL is known. If installing multiple skills from the same repo, prefer one repo source with `--skill` names.

### Arbitrary git URL

```bash
npx --yes skills@latest add git@github.com:vercel-labs/agent-skills.git \
  --skill web-design-guidelines \
  -g -y --agent universal --copy
```

### GitLab URL

```bash
npx --yes skills@latest add https://gitlab.com/org/repo \
  --skill skill-name \
  -g -y --agent universal --copy
```

### Local path

Relative path:

```bash
npx --yes skills@latest add ./my-local-skills -g -y --agent universal --copy
```

Absolute path:

```bash
npx --yes skills@latest add /absolute/path/to/my-local-skills -g -y --agent universal --copy
```

With filters for a local multi-skill directory:

```bash
npx --yes skills@latest add ./my-local-skills \
  --skill skill-a skill-b \
  -g -y --agent universal --copy
```

## Agent target selection

Use this decision table:

| User intent | Preferred target | Expected location | Notes |
|---|---|---|---|
| Default / portable / AIOS / Hermes central setup | `--agent universal` | `~/.agents/skills/<skill>` | Default choice. |
| User explicitly says another supported agent | That CLI agent name | Verify from install summary | Do not guess path; trust CLI output then check file. |
| User wants all supported agents | `--agent '*'` only if asked | Many locations | High-noise; avoid as default. |
| Hermes profile-local skill | Hermes/AIOS-specific flow | `~/.hermes/skills/...` | Only when explicitly requested. |
| First-party skill development | Symlink runtime to repo | varies | Keep repo as truth source. |

When unsure, run a harmless list first:

```bash
npx --yes skills@latest add <source> --full-depth --list
```

Then install with explicit `--skill` selections.

## Default workflow

1. Normalize the requested source and selected skills.
2. If the source may contain nested skills, add `--full-depth` for discovery/listing; keep it for install when needed.
3. Prefer explicit filters for multi-skill repositories:
   - One skill: `owner/repo@skill` is concise.
   - Multiple skills from same repo: `owner/repo --skill skill-a skill-b` is clearer.
4. Use the default universal copy flags unless the user chose another target:

   ```bash
   npx --yes skills@latest add <source> --skill <skill...> -g -y --agent universal --copy
   ```

5. Verify each expected skill exists:

   ```bash
   test -f ~/.agents/skills/<skill-name>/SKILL.md
   ```

6. Inspect frontmatter or file size when equivalence matters. In Hermes, prefer `read_file` over shell-printing full contents.
7. If a test install could pollute the real machine, use isolated `HOME`:

   ```bash
   tmp_home="$(mktemp -d)"
   HOME="$tmp_home" npx --yes skills@latest add <source> --skill <skill> -g -y --agent universal --copy
   test -f "$tmp_home/.agents/skills/<skill>/SKILL.md"
   ```

## Example: install the top design skills

```bash
npx --yes skills@latest add anthropics/skills \
  --skill frontend-design \
  -g -y --agent universal --copy

npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines vercel-composition-patterns \
  -g -y --agent universal --copy

npx --yes skills@latest add nextlevelbuilder/ui-ux-pro-max-skill \
  --skill ui-ux-pro-max \
  -g -y --agent universal --copy
```

## Pitfalls

- Do not manually copy a skills repo when the user asked for `npx skills`; the CLI handles agent targets, selection, security checks, and install summaries.
- Do not assume a multi-skill repository installs the desired skill unless a filter is specified.
- Prefer `npx --yes skills@latest` over bare `npx skills` for reproducibility and non-interactive execution.
- Include `--copy` for normal installs unless there is a deliberate development symlink reason.
- Quote `owner/repo@skill` specs in shell loops.
- Avoid `--agent '*'` unless the user explicitly wants broad multi-agent installation; it writes many locations and may include unsupported global targets.
- When testing equivalence, use isolated temporary `HOME`/`HERMES_HOME` so existing runtime skills do not mask behavior.
- Verify the resulting `SKILL.md`; do not report success based only on the install command returning zero.

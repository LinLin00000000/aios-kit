---
name: install-skill
description: Install Agent/Hermes-compatible skills with the `npx skills add` CLI. Use this whenever the user asks to install/add skills, compare skill source formats, use GitHub shorthand/URLs/tree paths/git URLs/local paths, filter a multi-skill repository with `@skill` or `--skill`, or install skills from skills.sh into `~/.agents/skills`.
---

# Install Skill

Use this skill to install skills via the `skills` CLI, especially when the user gives a GitHub repo, skills.sh entry, URL, local path, or asks whether two install syntaxes are equivalent.

## Core model

Think of the command as two layers:

```bash
npx --yes skills@latest add <source> [selector/options]
```

- `<source>` identifies where skills come from.
- `--skill <name...>` or `@skill` selects one or more skills from a multi-skill source.
- For this user's common setup, install globally for universal agents so the result lands under:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

Recommended default flags for non-interactive installs:

```bash
-g -y --agent universal --copy
```

Use `--copy` by default for stable universal installs. It avoids symlink/cache coupling and matches the AIOS skillpack public-install policy.

Full recommended shape:

```bash
npx --yes skills@latest add <source> -g -y --agent universal --copy
```

## Source formats

### 1. GitHub shorthand: `owner/repo`

Install skills discovered in a GitHub repository:

```bash
npx --yes skills@latest add vercel-labs/agent-skills -g -y --agent universal
```

If the repo contains multiple skills, CLI behavior may involve selection/default discovery. Prefer explicit filters for reproducibility.

### 2. GitHub shorthand + `--skill`

Install a specific skill:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines \
  -g -y --agent universal
```

Install multiple skills from the same repo:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines vercel-composition-patterns \
  -g -y --agent universal
```

Repeated `--skill` is also acceptable:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines \
  --skill vercel-composition-patterns \
  -g -y --agent universal
```

### 3. GitHub shorthand + `@skill`

Install one specific skill from a repo with compact syntax:

```bash
npx --yes skills@latest add vercel-labs/agent-skills@web-design-guidelines \
  -g -y --agent universal
```

This is effectively equivalent to:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines \
  -g -y --agent universal
```

Use `@skill` when one source maps to one selected skill.

### 4. Full GitHub URL

```bash
npx --yes skills@latest add https://github.com/vercel-labs/agent-skills \
  -g -y --agent universal
```

Equivalent in intent to:

```bash
npx --yes skills@latest add vercel-labs/agent-skills -g -y --agent universal
```

### 5. Full GitHub URL + `--skill`

```bash
npx --yes skills@latest add https://github.com/vercel-labs/agent-skills \
  --skill web-design-guidelines \
  -g -y --agent universal
```

For GitHub repositories, this is equivalent in effect to:

```bash
npx --yes skills@latest add vercel-labs/agent-skills@web-design-guidelines \
  -g -y --agent universal
```

### 6. GitHub tree subdirectory URL

If a skill is in a repository subdirectory, point directly at the tree path:

```bash
npx --yes skills@latest add https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines \
  -g -y --agent universal
```

Use this when the exact skill directory URL is known. If installing multiple skills from the same repo, prefer one repo source with `--skill` names.

### 7. Arbitrary git URL

SSH example:

```bash
npx --yes skills@latest add git@github.com:vercel-labs/agent-skills.git \
  -g -y --agent universal
```

With a skill filter:

```bash
npx --yes skills@latest add git@github.com:vercel-labs/agent-skills.git \
  --skill web-design-guidelines \
  -g -y --agent universal
```

### 8. GitLab URL

```bash
npx --yes skills@latest add https://gitlab.com/org/repo \
  -g -y --agent universal
```

With a skill filter:

```bash
npx --yes skills@latest add https://gitlab.com/org/repo \
  --skill skill-name \
  -g -y --agent universal
```

### 9. Local path

Relative path:

```bash
npx --yes skills@latest add ./my-local-skills -g -y --agent universal
```

Absolute path:

```bash
npx --yes skills@latest add /absolute/path/to/my-local-skills -g -y --agent universal
```

With filters for a local multi-skill directory:

```bash
npx --yes skills@latest add ./my-local-skills \
  --skill skill-a skill-b \
  -g -y --agent universal
```

## Choosing `@skill` vs `--skill`

Use `@skill` when installing exactly one skill from one source and you want a compact, loop-friendly spec:

```bash
for spec in \
  "anthropics/skills@frontend-design" \
  "vercel-labs/agent-skills@web-design-guidelines" \
  "vercel-labs/agent-skills@vercel-composition-patterns" \
  "nextlevelbuilder/ui-ux-pro-max-skill@ui-ux-pro-max"
do
  npx --yes skills@latest add "$spec" -g -y --agent universal
done
```

Use `--skill` when installing multiple skills from the same source, or when the source is a full URL, git URL, or local path and explicit selection is clearer:

```bash
npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines vercel-composition-patterns \
  -g -y --agent universal
```

## Equivalence rule of thumb

For a GitHub repo and a single selected skill:

```text
owner/repo@skill
```

is effectively equivalent to:

```text
owner/repo --skill skill
```

A verified example:

```bash
npx skills add https://github.com/vercel-labs/agent-skills --skill web-design-guidelines
```

and:

```bash
npx skills add vercel-labs/agent-skills@web-design-guidelines
```

both install only `web-design-guidelines` from `vercel-labs/agent-skills`, producing:

```text
~/.agents/skills/web-design-guidelines/SKILL.md
```

## Default workflow

1. Normalize the user's requested skill(s) into one of the source forms above.
2. Prefer explicit filters for multi-skill repositories:
   - One skill: `owner/repo@skill` is concise.
   - Multiple skills from same repo: `owner/repo --skill skill-a skill-b` is cleaner.
3. Use non-interactive universal install flags by default:

   ```bash
   npx --yes skills@latest add <source> -g -y --agent universal
   ```

4. After installing, verify that each expected skill exists:

   ```bash
   test -f ~/.agents/skills/<skill-name>/SKILL.md
   ```

5. Inspect frontmatter or file size when equivalence matters:

   ```bash
   sed -n '1,20p' ~/.agents/skills/<skill-name>/SKILL.md
   wc -c ~/.agents/skills/<skill-name>/SKILL.md
   ```

   In Hermes, prefer `read_file` for inspection rather than shelling out to print file contents.

## Example: install the top design skills

Install each skill with compact `@skill` syntax:

```bash
for spec in \
  "anthropics/skills@frontend-design" \
  "vercel-labs/agent-skills@web-design-guidelines" \
  "vercel-labs/agent-skills@vercel-composition-patterns" \
  "nextlevelbuilder/ui-ux-pro-max-skill@ui-ux-pro-max"
do
  npx --yes skills@latest add "$spec" -g -y --agent universal
done
```

Or group same-repo installs with `--skill`:

```bash
npx --yes skills@latest add anthropics/skills \
  --skill frontend-design \
  -g -y --agent universal

npx --yes skills@latest add vercel-labs/agent-skills \
  --skill web-design-guidelines vercel-composition-patterns \
  -g -y --agent universal

npx --yes skills@latest add nextlevelbuilder/ui-ux-pro-max-skill \
  --skill ui-ux-pro-max \
  -g -y --agent universal
```

## Pitfalls

- Do not assume a multi-skill repository installs the desired skill unless a filter is specified.
- Prefer `npx --yes skills@latest` over bare `npx skills` for reproducibility and non-interactive execution.
- Quote `owner/repo@skill` specs in shell loops to avoid accidental shell interpretation in unusual environments.
- When testing equivalence, use an isolated temporary `HOME`/`HERMES_HOME` so the existing `~/.agents/skills` does not mask install behavior.
- Verify the resulting `SKILL.md`; do not report success based only on the install command returning zero.

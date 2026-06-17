# aios-kit architecture

`aios-kit` is not a monorepo that absorbs every asset. It is an assembly/control repo.

## Core decision

Keep independently meaningful projects independent, and connect them with manifests and local links:

- `lins-living-loop`: independent first-party skill/project with its own GitHub remote.
- `aiops-vault-template`: independent public template repo.
- `~/ai-ops`: real local operational vault, not a GitHub template and not committed here.
- `aios-kit`: the kit that documents, validates, links, and synchronizes these parts.

## Why not merge everything?

Merging LLL, ai-ops template, and live ai-ops into one repo would blur three different truth sources:

1. reusable workflow product (`lins-living-loop`),
2. reusable vault template (`aiops-vault-template`),
3. private/current operational facts (`~/ai-ops`).

The kit should know how to find and validate them, not own all of their content.

## Skillpack module

The skillpack module has three layers:

```text
skillpack.yaml                         # selected skills intent
scripts/aios.py skillpack sync         # installer/linker/pruner
~/.agents/skillpacks/state/aios-kit    # local state for safe prune/update
```

External skills are installed through `npx skills`. First-party skills can be copied or symlinked.

## Local source and runtime model

For active development:

```text
~/projects/lins-living-loop              # canonical discoverable source path
~/.agents/skills/lins-living-loop        # runtime path; may be the real worktree or a symlink
```

Long-term preferred shape:

```text
~/.agents/skills/lins-living-loop -> ~/projects/lins-living-loop
```

Current migration note: when an existing runtime clone has uncommitted changes, do not overwrite it. Promote/link it safely first, then merge histories before converting runtime to a pure symlink.

## Friend/user distribution model

For friends or clean machines, default to copy/install:

```bash
git clone https://github.com/LinLin00000000/aios-kit ~/.agents/skillpacks/aios-kit
~/.agents/skillpacks/aios-kit/aios skillpack sync --apply
```

For authors/developers, use symlink:

```bash
~/projects/aios-kit/aios skillpack dev-link --apply
```

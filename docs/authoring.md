# Skill authoring and distribution

## Author mode

Use symlinks so edits made by Hermes/Codex/other agents land in Git-visible paths.

```bash
cd ~/projects/aios-kit
./aios skillpack dev-link --apply
./aios skillpack doctor
```

Then edit first-party skills and commit their own repos:

```bash
git -C ~/projects/lins-living-loop status
git -C ~/projects/lins-living-loop add SKILL.md references/
git -C ~/projects/lins-living-loop commit -m "improve LLL skill"
git -C ~/projects/lins-living-loop push
```

Commit kit changes separately:

```bash
git -C ~/projects/aios-kit add skillpack.yaml manifests docs scripts README.md
git -C ~/projects/aios-kit commit -m "add skillpack sync and local asset mapping"
git -C ~/projects/aios-kit push
```

## User/friend mode

Use copy/install so the runtime does not depend on a live development checkout:

```bash
git clone https://github.com/LinLin00000000/aios-kit ~/.agents/skillpacks/aios-kit
~/.agents/skillpacks/aios-kit/aios skillpack sync --apply
```

## Updating and pruning

```bash
./aios skillpack sync --apply
./aios skillpack sync --prune --apply
```

Prune only deletes skills previously recorded as managed by `aios-kit`.

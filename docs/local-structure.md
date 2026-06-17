# Local structure and linking policy

## Canonical local paths

| Item | Path | Type | Policy |
|---|---|---|---|
| Main kit | `~/projects/aios-kit` | Git repo | Source of assembly scripts/manifests/docs |
| LLL | `~/projects/lins-living-loop` | Git repo or symlink to current worktree | Independent first-party source |
| AIOps template | `~/projects/aiops-vault-template` | Git repo | Public reusable template |
| Live AIOps vault | `~/ai-ops` | Real asset vault | Do not commit; can expose as `~/projects/ai-ops` symlink for discovery |
| Universal skills | `~/.agents/skills` | Runtime install target | Not primary source unless explicitly promoted |
| Hermes skills | `~/.hermes/skills` | Runtime/profile skills | Not primary source unless explicitly promoted |

## Rules

1. **Templates are not real assets.** `aiops-vault-template` is reusable; `~/ai-ops` is live state.
2. **Runtime is not automatically source.** Runtime directories become source only when intentionally linked/promoted.
3. **Active first-party skills should be Git-visible.** If an agent edits the runtime skill, the edit should appear under a known Git worktree.
4. **Soft links are for local authoring.** Copy/install is the default for friends and new machines.
5. **State controls prune.** Only paths recorded under `~/.agents/skillpacks/state/aios-kit/install-state.json` can be pruned automatically.

## Current LLL migration caveat

This machine has had multiple LLL clones. If `~/.agents/skills/lins-living-loop` contains uncommitted or unpushed changes, treat it as the temporary canonical worktree and make `~/projects/lins-living-loop` point at it until the histories are reconciled.

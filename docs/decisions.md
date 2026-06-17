# Decisions

## 0001: Main project name

Use `aios-kit` as the main project. `skillpack` is a module, not the repo boundary.

## 0002: LLL remains independent

`lins-living-loop` is a reusable product/skill and keeps its own repo. `aios-kit` references it and can link/copy it into runtime targets.

## 0003: ai-ops real vault and template stay separate

`~/ai-ops` is live operational state. `aiops-vault-template` is reusable starter content. `aios-kit` may link and validate both, but must not vendor live vault data.

## 0004: Symlink for authoring, copy for distribution

Author machines use symlink mode for first-party skills to make runtime edits Git-visible. Friend/new-machine installs use copy mode unless they opt into development.

## 0005: Manifest + thin script, not a new package manager

`aios-kit` reads `skillpack.yaml`, calls `npx skills` for external skills, directly copies/symlinks first-party local skills, and records local state for safe prune.

# Registries

Registries describe resources. They are the fact layer for AIOS resource resolution.

Public files here are examples/schemas only. Real registries can live in a private vault such as `~/aios/vault/ops/projects/` or a future `~/aios/registries/`.

Recommended first real registry:

```text
~/aios/vault/ops/projects/
  README.md
  registry.jsonl
  aliases.yaml
  views/
```

Later this can move or link into:

```text
~/aios/projects -> ~/aios/vault/ops/projects
~/aios/ops -> ~/aios/vault/ops
```

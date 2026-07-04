# Agent rules for the AIOS Mihomo template

This directory is public source. Keep it generic and secret-free.

## Allowed

- Edit `builder.py`, `.env.example`, `README.md`, `config.yaml`, and docs.
- Use fake URLs such as `https://example.invalid/sub` for tests and examples.
- Run `python3 builder.py preview`, `build`, `check`, and `doctor` in a temporary directory with fake env values.

## Forbidden

Do not commit or paste:

- real subscription URLs;
- provider cache YAML;
- generated `secrets/config.yaml`;
- `.env` files;
- node UUID/password/token values;
- private hostnames or private IPs unless already intentionally documented as examples.

## Runtime operations

This template does not authorize live service changes. On real machines, confirm before:

```bash
sudo systemctl daemon-reload
sudo systemctl restart clash
sudo systemctl restart mihomo
sudo systemctl restart aios-mihomo
```

## Design discipline

Keep the public template small and orthogonal. Prefer a Builder + example env + docs over adding installer flags or secret-management dependencies before the workflow is proven across target machines.

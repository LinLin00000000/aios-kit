# Secret Location Metadata Example

This file is a template. Your real `secrets-location.md` should stay private and ignored by Git.

Do record:

- Secret name or purpose.
- Where it is stored.
- Who/what can access it.
- Rotation and recovery notes.

Do not record:

- API key values.
- Passwords.
- Private key bodies.
- Cookies or sessions.
- Recovery codes.
- Subscription URLs.

## Example entries

| Name | Purpose | Location | Access | Rotation / recovery notes |
|---|---|---|---|---|
| demo-vps SSH key | SSH login for documentation host | Password manager item `demo-vps ssh` or `~/.ssh/demo_vps` | Owner only | Rotate if laptop is lost. Do not paste key body here. |
| example-api token | Example service API token | Password manager item `example-api token` | Owner / deployment agent | Rotate in the provider dashboard. |

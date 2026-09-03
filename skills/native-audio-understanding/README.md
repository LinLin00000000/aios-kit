# Native Audio Understanding Skill

This package provides a deterministic helper for sending a local audio file through an explicitly selected model-input protocol.

It is a compatibility bridge for hosts that expose an uploaded audio file only as a local path. It makes a separate API request; it does not add native audio support to the host's already-running conversation turn.

See `SKILL.md` for the Agent workflow and `references/protocols.md` for adapter boundaries.

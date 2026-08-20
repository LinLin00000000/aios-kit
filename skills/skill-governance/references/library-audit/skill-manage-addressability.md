# Skill Management Addressability

Use this reference when `skill_view` or `skills_list` can see a skill but `skill_manage` cannot patch it.

## Diagnosis

Readability and mutability are separate properties. A runtime skill may be:

- symlinked from another source tree;
- externally owned or installed by a hub/plugin;
- outside the active profile's curator-managed roots;
- user-owned and intentionally protected.

A successful `skill_view` therefore does not prove that the skill is safe or eligible to mutate.

## Safe response

1. Do not create a same-name replacement or duplicate.
2. Inspect the reported source/real path and ownership classification using the tools available in the current task.
3. If the target is user-owned or externally managed, leave it unchanged and recommend adoption/self-hosting if a durable local patch is needed.
4. If the lesson generalizes beyond that protected skill, patch the appropriate curator-managed class-level umbrella instead.
5. Put reproducible session detail here rather than bloating the umbrella body.
6. Report the exact boundary honestly: distinguish “readable,” “source edited,” “runtime-visible,” and “curator-managed.”

## Practical lesson

A domain skill can already contain the correct workflow while still being non-addressable by the active skill manager. The right fallback is governance guidance or a local sidecar/adoption path—not a second skill with the same name.

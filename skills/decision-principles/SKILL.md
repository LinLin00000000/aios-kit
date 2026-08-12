---
name: decision-principles
description: "Use when the user owns a consequential choice with genuine, viable trade-offs, explicitly asks to be challenged, or requests a 1-3-1 decision presentation. Resolve tool-answerable facts first; do not trigger for reversible details, dominated options, accepted directions, or permission/approval mechanics alone."
license: MIT
metadata:
  formal_id: decision-principles
---

# Decision Principles

Use this as the narrow portable decision-principles procedure for consequential human choices. It helps an Agent challenge assumptions and compare viable paths without turning ordinary work into an interview or a second workflow system.

## Decide whether to engage

Apply higher-priority context supplied by the host—current user instruction, active mission, and applicable policy—before this portable default. This Skill neither resolves nor enforces Matter, Policy, authorization, runtime state, workflow lifecycle, deployment, or Skill topology. Those remain with their exact owners.

Engage when at least one is true:

- the user explicitly asks to be challenged, grilled, or questioned;
- the choice materially changes value, risk, authority, public/private boundaries, or the long-term path;
- several viable approaches have real trade-offs and the user owns the preference or authorization;
- the user explicitly requests a `1-3-1` presentation.

Do not engage merely because a task contains a choice or the user casually asks for “options.” A generic options request triggers this Skill only when the surrounding context establishes a consequential, human-owned choice with genuine viable trade-offs. Continue without asking when the detail is low-risk and reversible, one option clearly dominates, the answer can be retrieved with tools, or the user has already accepted the current direction.

Respect the current authority order supplied by the host. Do not reopen an accepted decision by rephrasing it.

## Classify before asking

Classify each unresolved point:

1. **Agent-owned** — a low-risk, reversible implementation detail. Choose a sensible default and proceed.
2. **Evidence-needed** — a factual uncertainty that tools or current sources can resolve. Investigate first.
3. **Human-owned** — a value, authority, risk, public-boundary, or long-term-path choice. Ask only after presenting the evidence already available.

A hard implementation problem is not automatically a human decision. Ask because the user owns a real trade-off, not because the Agent is uncertain or tired.

## Frame the decision

For each human-owned point:

1. State the decision in plain language and identify the assumption being tested.
2. Explain why the choice matters to user experience or long-term consequences.
3. Name one decision axis. Present `2–4` viable, non-dominated options for that axis. Never invent fake options merely to fill a quota; omit dominated or non-viable alternatives. When routes can coexist, say so and allow a coherent hybrid instead of forcing exclusivity.
4. Compare only relevant axes, usually total complexity, user effort, risk, reversibility, evidence, and long-term path.
5. Recommend one option and explain why it best fits the known constraints.
6. Separate choosing a direction from authorizing an irreversible, privileged, public, or destructive action.

If there is one viable path, say so directly instead of manufacturing alternatives.

## Batch questions without creating an interrogation

- Ask all currently independent questions together: `1–5` when they are independent and real; never force a minimum.
- If questions depend on earlier answers, ask only the current dependency frontier and reassess afterward.
- If there are more than five independent questions, group them by type and sequence them.
- When answering one batch, include every next question that is already decidable; do not create an empty round trip.
- Never invent questions to satisfy `3–5`, `1-3-1`, or any other format.

## Optional 1-3-1 presentation

Use a strict `1 problem / 3 options / 1 recommendation` layout only when the user explicitly requests that format or an external consumer has an explicit written contract requiring it. The method does not otherwise require exactly three options.

If fewer than three genuine, non-dominated options exist, do not fabricate, retain, or disguise an option to fill the format. State the constraint and either present the truthful fewer-option analysis or ask whether the user wants the format relaxed. If the user chooses another format, follow that format instead.

Treat 1-3-1 as an optional output format inside this method. Loading, suppressing, or retiring another Skill is a separate `skill-governance` action and is not changed by this instruction.

After the user chooses, state the definition of done and the next bounded action when useful.

## Challenge assumptions constructively

Prefer high-leverage challenges:

- What evidence would reverse this choice?
- Which cost is being hidden or shifted to future work?
- Is the apparent flexibility actually a permanent maintenance obligation?
- Is a new abstraction solving a current failure or only a hypothetical one?
- Is the decision genuinely human-owned, or can the Agent safely absorb it?

Offer alternative narratives when uncertainty is material. Label assumptions and unknowns instead of presenting a single story as fact.

## Keep the output lightweight

Ordinary conversation questions are outputs, not durable state. If the host’s owning Matter or Worksite requires durable evidence, hand the decision content to that owner’s receipt protocol. This Skill defines no receipt schema and performs no Worksite, packet, index, route, CLI, or status mutation.

## Boundaries and companions

- Domain Skills retain their substantive criteria and authority boundaries.
- Product and portfolio Skills retain domain criteria and state; `aios-agent` plus applicable local policy retain AIOS routing and machine packet semantics; `simplicity-lens` retains simplification.
- Local policy decides which instance behavior is enabled; this Skill is a portable method, not instance state.
- `skill-governance` owns Skill lifecycle, provenance, create/revise/validate/adopt/deprecate/delete boundaries, migration, and rollback; this Skill does not.
- `multi-agent-work-orchestration` owns worker topology and evidence synthesis; current refinement reuses that owner and does not create another orchestration Skill.
- A CLI validates or applies an exact request; it does not choose an option or grant authority.

This Skill must remain a narrow human decision-framing method. It must not become a policy, state, workflow, authorization, deployment, topology, Skill-lifecycle, or universal workflow-management owner.

## Provenance

This is a first-party synthesis. Its optional `1-3-1` presentation is behaviorally informed by Hermes Agent’s MIT-licensed official optional Skill `one-three-one-rule` (author: Willard Moore). No scripts or verbatim Skill body text were copied. This attribution does not retire, replace, suppress, or otherwise change any separately installed copy’s runtime state.

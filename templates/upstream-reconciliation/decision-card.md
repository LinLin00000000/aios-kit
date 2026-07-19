# Decision: example-component / candidate-id

> This is a Human Decision record for one exact Reconciliation Case. It is not an AI approval, deployment receipt, or mutable discussion summary.

- Status: proposed <!-- proposed | approved | rejected | deferred | superseded -->
- Component / Adoption: `example-component`
- Case ID: `CASE-YYYYMMDD-NNN`
- Candidate SHA or digest: `REPLACE_WITH_EXACT_IMMUTABLE_ID`
- Accepted upstream base: `REPLACE_WITH_PREVIOUS_EXACT_ID`
- Observed upstream target: `REPLACE_WITH_NEW_EXACT_ID`
- Risk / maximum automation: `R2 / A2`
- Affected Local Deltas: `D001`
- Affected Invariants: `INV-001`
- Evidence refs: `diff`, `checks`, `source`, `validation`
- Supersedes: `none-or-prior-decision-id`
- Invalidated by new candidate: `false`

## Decision scope

State exactly which behavior, files, configuration, data, permissions, or deployment boundary this decision covers. Anything outside this scope remains unknown or unchanged.

## Git applicability

- Result: `clean | text-conflict | not-applicable | unknown`
- Evidence:
- Notes:

## Behavioral relationship

- Result: `unrelated | complementary | partial-overlap | equivalent | conflicting | unknown`
- Compared scope:
- Evidence:
- Unknowns / not checked:

| Surface | Local behavior | Upstream behavior | Evidence | Unknowns |
|---|---|---|---|---|
| API / CLI |  |  |  |  |
| Configuration / defaults |  |  |  |  |
| Data / migration |  |  |  |  |
| Auth / permissions / secrets |  |  |  |  |
| Failure / rollback |  |  |  |  |

## Options

- `accept-upstream`: adopt this upstream candidate as the new accepted base and retire or replace the affected Local Delta as recorded.
- `keep-local`: retain the local behavior and record why/revisit conditions.
- `hybrid`: create a new candidate combining both approaches.
- `defer`: make no change now and record the next trigger.
- `retire-local`: retire the affected Local Delta without otherwise accepting this upstream candidate; if the candidate is also adopted, use `accept-upstream` and record the retirement there.
- `reject-update`: reject this upstream candidate for the stated scope.

If this decision also changes the divergence strategy, record that as a separate strategy change between `no-source-delta`, `adapter`, `overlay`, `patch-queue`, or `maintained-source-divergence`. Repository topology remains a separate dimension; neither is an extra product disposition.

## Agent recommendation — non-authoritative

- Recommendation:
- Rationale:
- Confidence (triage hint only; never authorization):
- Assumptions and constraints:
- Counter-evidence / alternatives:

## Human or policy decision

- Product disposition: `accept-upstream | keep-local | hybrid | defer | retire-local | reject-update`
- Rationale:
- Authority / decided by:
- Decision-bound exact SHA or digest:
- Decision-bound evidence set:
- Deployment authorization: not-authorized-or-separate-policy-reference
- Revisit trigger:
- Divergence strategy change: none-or-new-strategy
- Decision date:

## Implementation and validation refs

- Change Set:
- Applied revision:
- Validation Evidence:
- Active Local Delta update / removal:
- Accepted base update:

## Invalidation rule

Any new commit, rebuilt artifact with a different digest, changed evidence set, expanded path/permission scope, or changed deployment target invalidates this approval unless an explicit policy says otherwise. Mark this record `superseded` and create a new Decision record; do not silently edit the approved subject.

# Genuine frontier evidence boundary

Status: DRAFT — SOURCE ONLY — NOT MEASUREMENT/TRAINING AUTHORITY

## Scope and decision requested

Proposal for a separate future genuine-measurement admission boundary.
Parent and independent architecture/security/Python review must settle this
contract before parser or consumer implementation.

This draft establishes no accepted persistent schema, evidence authority,
measurement plan, execution permission or training admission.
Preserve `train/frontier_inputs.py` as a synthetic-fixture-only API.
Do not reinterpret fixture flags or upgrade existing evidence formats.

## Test plan first

All checks below are proposed and UNRUN. Structural fixtures test association
and refusal, not actual generation, loaded checkpoints or external execution.

### T01: Scheduled coverage

Illustration only: 8 planned task IDs, 1 preparation exclusion, 7 eligible
tasks and G=4 produce exactly 28 scheduled sample slots.

Require all 8 planned IDs and the exact exclusion, 7 eligible IDs in admitted
order, exactly 28 distinct task/slot associations, and 0 excluded-task slots.
No redraw, replacement task or silent denominator reduction.
These values do not select production G, membership or sample limits.

### T02: Missing, duplicate and unexpected evidence

Independently remove 1 slot, duplicate 1 slot, add 1 unexpected slot, and
associate 1 outcome with the wrong task or slot.
Each prevents complete measurement disposition.
Missing evidence is not a zero score. Do not deduplicate into acceptance.
Observed intersections never replace the planned schedule.

### T03: Identity binding

Independently mutate policy revision/checkpoint inventory, draw/supplement pin,
scorer comparison/timeout/row bound, generation/runtime identity, and individual
scheduled sample association. Each refuses before 1 trainer construction.
The proposed consumer constructs trainers 0 times under every input.

### T04: Provenance separation

Without accepted independent attestations, a fully consistent synthetic fixture
presented as genuine produces 0 accepted genuine-measurement claims.
Removing or invalidating an independently supplied checkpoint or attempt
attestation prevents genuine acceptance, even when all candidate hashes match.
This does not claim structural detection of a dishonest trusted attestor.

### T05: Existing fixture boundary

Genuine evidence supplied to the existing fixture-only API remains refused.
No fixture flag, source label or fabricated provenance marker bypasses it.

### T06: Attempt and outcome semantics

Cover 6 independent cases: valid scored prediction; known provider/generation
failure; invalid gold discovered after preparation; missing attempt evidence;
pending/unknown external outcome; duplicate or second attempt for one slot.
Only the first supplies a valid scored sample under the bound scorer.
Other cases cannot silently become EX=0 or complete frontier evidence.

### T07: Original admission and drift

Changed retained preparation pins refuse before 1 generation-related action.
Observable post-operation source/database/preparation drift prevents acceptance.
The future consumer performs exactly 0 selector calls, gold-revalidation queries,
provider calls or redraws.
This tests observable drift, not temporary mutation followed by restoration.

### T08: Closed training gates

With the real native gate closed, require 0 framework imports, model loads,
output creations, trainer constructions, train/save/resume calls.
Consumer success must not alter that result.

### T09: Meaningful negative controls

After implementation is separately approved, bypass association enforcement
and require at least 1 intended call-phase assertion failure. Separately bypass
genuine-evidence admission and require at least 1 intended call-phase failure.
Restore each control and obtain the corresponding positive result.
Collection/setup errors do not satisfy RED.
Do not replay historical qualification profiles or spent execution caps.

## Proposed architecture

### Separate boundary

A future consumer receives:
1. An independently trusted measurement plan.
2. Independently retained expected raw-evidence pins.
3. Candidate evidence and its bounded associations.
4. Independently trusted checkpoint and execution attestations.

These are conceptual inputs, not an approved serialized schema or implemented
API. Return bounded validated bindings and explicit dispositions only.
Do not publish a manifest, launch a provider, construct a trainer, or authorize
subsequent actions. No standalone activation flag is proposed.

### Trusted measurement plan

The plan must bind:
- Exact policy identity, full 40-hex model source revision where required by
  the existing native contract, and the exact measured checkpoint inventory.
- Checkpoint artifact inventory and any adapter identity. A source revision
  is not a substitute for measured checkpoint or adapter identity.
- Runtime/provider identity and generation route.
- Generation settings, prompt/template/tool identities and relevant sources.
- Explicit G and existing dead-group ceiling.
- Independently retained draw and supplement pins.
- Complete planned, eligible and preparation-excluded task identities.
- Task fingerprints and applicable database identities.
- Exact scheduled task/slot associations.
- Extraction/scorer identities, comparison mode, timeout, max rows and sources.
- Explicit resource/sample limits and applicable execution-grant reference.

A label or inventory hash alone does not prove which checkpoint was loaded.
Existing defaults and fixture identities do not select these values.
The plan must be accepted and independently retained before execution.
It cannot be reconstructed from observed successful outcomes.

### Raw evidence retention

Expected pins come from custody independent of the candidate being admitted.
Computing expected hashes from candidate files is forbidden.
Pins establish byte equality to trusted expectations, not truth, authorship,
checkpoint loading, authorized execution or durable storage.

Proposal: execution authority retains original raw attempt/response evidence;
a separately identified custody authority retains expected pins and associations
outside the candidate's control.
These are trust roles. Their identities, mechanisms and independence must be
settled before genuine acceptance. This draft appoints nobody.
Candidate paths must not trigger arbitrary filesystem access.
Any future file adapter requires a reviewed bounded access contract.

## Provenance and attestation trust boundary

Genuine acceptance requires attestations from explicitly trusted authorities
capable of observing the asserted facts.

Checkpoint authority attests the exact loaded checkpoint and adapter for the
measured execution, not merely files present on disk.
Execution authority attests actual attempts, route, settings, schedule
association and returned terminal outcomes.
Scoring evidence must bind the unchanged extraction/scoring instrument and
its valid result to the corresponding attested prediction and task.

Provider receipts alone may not establish loaded checkpoint identity.
Host logs alone may not establish provider execution.
If a route cannot supply required observations, genuine acceptance blocks.
An attestation bundled with candidate evidence is insufficient unless verified
against independently established authority and expected execution identity.

The future boundary trusts accepted attestors to report observations honestly.
Labels, hashes or signatures do not create that trust.
No `measurement: true`, `fixture: false`, approval boolean, self-asserted origin
or caller-declared policy label constitutes provenance authority.
Unverifiable facts remain unverified; structural checks do not replace them.

## Scheduled slots, attempts and dispositions

A scheduled slot is a plan-bound task identity plus sample index within G.
Its identity exists independently of whether generation occurs.
An attempt has a distinct execution identity and associates with exactly one
scheduled slot and the accepted plan.

No automatic retries are permitted by this proposal.
A second distinct attempt for the same slot prevents acceptance; do not choose
the successful attempt. A future retry policy requires a separate amendment.
Repeated copies of one receipt do not establish multiple attempts or slots.

Distinguish scheduled slots, attested actual attempts, terminal outcomes, valid
scored samples, and missing/pending/unknown/failed/invalid dispositions.
A complete schedule does not prove all attempts occurred.
Complete attempt accounting is not a valid frontier measurement.

### Valid scored sample

Requires an attested successful generation outcome, exact association and a
valid result from the unchanged bound extraction/scoring instrument.
Preserve scorer-defined valid-zero prediction outcomes.
Do not invent an alternative success/failure threshold.

### Provider or generation failure

Retain actual failure identity and available raw receipt.
A failed request is not a model prediction or EX=0.
Do not score missing completion text as an empty prediction because the
provider failed.

### Invalid gold

Retain the scorer's invalid status separately from policy failure.
New invalid gold prevents complete measurement acceptance for the frozen
eligible schedule. Do not amend preparation exclusions, remove tasks, redraw
or repair the denominator inside this consumer.

### Missing, pending or unknown outcome

Do not infer terminal outcomes from timeout, disconnect or absent receipt.
Retain disposition and available attempt identity.
Do not retry, claim cancellation, remote retirement or durable ownership
resolution. Those facts require their own accepted capability.
Bounded diagnostics do not replace custody of unresolved evidence.

## Rates and retained frontier

Compute a task solve rate only when all G scheduled slots have valid scored
samples under the same accepted bindings.
Do not divide successes by observed outcomes while scheduled slots are missing,
invalid, unknown or generation-failed.
Preserve existing trainable-band/dead-group calculation and count policy.
No new retention threshold, replacement task or altered scorer policy.

Internally consistent rates are not training authority.
Ultimate manifest publication and training handoff require a separate accepted
contract, all native/lifecycle/scientific gates and fresh specific authorization.

## Non-goals and unchanged boundaries

No parser, consumer, persistent schema or code implementation now.
No provider/model/corpus/artifact acquisition, installs, experiments, training,
checkpoint restoration or publication.
No automatic persistence, retries, repair, redraws or provenance upgrades.
No legacy Trace/episode/capture schema changes.
No change to synthetic frontier consumer's genuine-evidence refusal,
`grpo_ptc.py` post-preflight `NotImplementedError`, or CPU source-only throws.
No renewal of spent metadata/native/archive/qualification grants.
No bypass of independent lifecycle, Runtime, Scope or production prerequisites.

## Blocking owner inputs

Before genuine acceptance, settle:
1. Policy source revision, measured checkpoint inventory/adapter and loaded-
   checkpoint attestor.
2. Runtime/provider/generation route and actual-attempt attestor.
3. Production G, ceiling and independently retained draw/supplement.
4. Trusted expected pins, retention custodian and original raw receipts.
5. Evidence-authority verification and execution-association mechanism.
6. Resource/sample limits and fresh specific measurement execution grant.

Native dependency/ABI/template compatibility and exclusive source isolation
remain separately closed. This draft does not resolve them.
Parent and independent reviewers must settle bindings and trust roles before
approving consumer implementation. Execution remains unauthorized.

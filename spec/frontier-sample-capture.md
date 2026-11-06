# Frontier sample capture

Status: ACCEPTED FOR OFFLINE SOURCE IMPLEMENTATION AND SYNTHETIC FIXTURE TESTS

Depends on accepted structural bindings f16ddab. Captures actual sample outputs
and original scorer returns; never manufactures samples from aggregate rates.
No provider selection, genuine-measurement acceptance, persistence or training.

## Test plan first

All proposed until parent records execution.

1. `test_capture_complete_draw`: 8 planned,1 preparation-excluded,7 eligible,G4
   gives28 generator calls and28 original probe scoring calls, eligible/slot
   order,57 evidence items. Preparation gold checks counted separately.
2. `test_original_scores`: real SQLite yields EX0/EX1; exact completion,
   extracted SQL and original ExResult fields(score,status,valid,detail,
   n_pred_rows,n_gold_rows) retained,0 rescoring.
3. `test_defaults`: omitted/None observer preserves original results,
   exceptions, gold-void behavior, generation/scorer order and bounds;
   0 observation construction/calls when disabled.
4. `test_failures`: two original generator exception instances at distinct
   slots; original extraction/scorer/observer exceptions propagate by identity,
   0 retries/later generation, permanent quarantine,no successful capture.
5. `test_invalid_observation`: observe original invalid result BEFORE original
   break. Observer exception on invalid-gold result propagates unchanged first.
   Exact gold_error/gold_timeout/gold_truncated status retained, no false EX0.
   db_missing is NOT proven invalid gold: capture quarantines with fixed reason.
6. `test_observation_association`: exactly1 observation for outstanding
   task/slot/attempt, exact retained completion; missing/duplicate/reordered/
   substituted observations refuse before result. Slot skips only from original
   documented gold-void suffixes, never silently reindex later tasks.
7. `test_limits`: reserve counts/all deterministic metadata BEFORE generation;
   B accepts/B+1 refuses for item/aggregate, no truncation. Account UTF8,
   escaping, repeated fields, both plan projections, inventory and retention
   declarations. Oversize checked before costly encoding/retention.
8. `test_drift`: changed retained preparation/database/artifact/source identity
   refuses through original admission/post-admission;0 finished capture results.
9. `test_core_join`: captured evidence satisfies structural associations.
   Producer retention pins are explicitly self-consistency pins,NOT independent
   custody. All provenance/genuine/training claims remain unverified/false.
10. `test_lifecycle`: READY->RUNNING before any admission/callback; atomic
    concurrent/reentrant reuse refuses without disturbing active invocation;
    success retires FINISHED before return,failure permanently QUARANTINED.
    No raw partial accessor or successful result after failure.
11. `test_privacy_immutability`: snapshot/error repr fixed codes/counts only,
    no raw IDs/SQL/completions/detail. Evidence/retention tuples immutable.
    Later legacy ProbeResult mutation changes0 retained bytes/pins.
12. Sensitivity: suppress observation forwarding, then separately substitute
    task/slot/prediction; corresponding valid-setup call-phase oracle fails,
    restored positives pass. No collection/setup RED or spent-profile replay.

## Minimal existing API additions

Only probe.py and draw_probe.py signatures gain keyword-only
`sample_observer=None`. No existing default changes.
Define frozen repr-disabled `SampleObservation` in probe.py:
task_id,slot_index,completion,extracted_sql,result(original frozen ExResult).

Preserve exact sequence:
completion=generate(task); prediction=extract_sql(completion);
original execution_accuracy(prediction,task,compare,timeout,max_rows);
optional synchronous observer(observation); original valid/win/break handling.
Observe invalid results before break. Do not catch observer exceptions.
When disabled,construct no observation. Draw helper forwards new kwarg only
when non-None,preserving legacy default delegate call signatures.
No writer or result schema changes.

## New producer API

`CaptureSession(plan, checkpoint_inventory, *, limits)`
`session.run(root, draw_path, supplement_path, generate, *,
 expected_draw_sha256, expected_supplement_sha256, fixture) -> CapturedProbe`
`session.snapshot`: readonly bounded status/counters,never raw partial data.

Use actual core MeasurementPlan/BindingLimits/EvidenceBatch/ExpectedEvidence
types. Exact bytes inventory must match the plan inventory SHA and core limits;
it is not loaded-checkpoint proof. All model/source/runtime/grant declarations
remain declarations.

Constructor performs pure plan/checkpoint shape/pin/budget checks through core
checkpoint-only admission. Missing sample slots are expected at this stage.
Reserve2*scheduled+1 raw/expected capacities and all deterministic metadata
before generation. Validate generated ID lengths against caller limits.
Reservations are NOT fabricated attempts or scores and never appear as evidence
or observed counters. No corpus reads/generator/SQL/framework work in ctor.

Single-use run transitions RUNNING before admission. Admit retained draw and
bind actual ordered planned/eligible/excluded membership, existing task
fingerprints and database pins, retained draw/supplement pins, comparison,
timeout,max_rows. Forward explicit plan G/ceiling unchanged. Do not claim
verification of provider/runtime/generation/checkpoint declarations.

Call original probe_validated_draw once using a producer-owned generator
wrapper and observer. Wrapper associates unique task/slot/attempt before
trusted callback,retains exact returned completion bytes before extraction.
Observer matches exact outstanding completion/task/slot and captures original
result without extraction/rescoring. No user observer or authority callback
on CaptureSession. Original helper final fresh admission remains mandatory.

## Evidence and honest result

Frozen repr-disabled `CapturedProbe` exposes:
- Original ProbeResult,explicitly legacy mutable,not deeply immutable.
- Frozen EvidenceBatch with exact captured observations.
- Frozen producer-generated retention-pin declarations.
- Structural BindingReport,always unverified/empty-attested/false-genuine/false-
  training. It is a self-consistency check,NOT independent receipt verification.

Generation payload is exact completion UTF8. Prediction SHA binds extracted
SQL. Scoring payload deterministically encodes extracted SQL,prediction SHA
and all6 original ExResult fields. This is internal in-memory encoding,not an
accepted persistent/genuine receipt schema. No raw decoding/parser/file adapter.

IDs deterministic in explicit plan/execution/task/slot/purpose namespace;
unambiguous encoding, bounded length,no truncation. They do not prove freshness,
global uniqueness, custody or real generation. Producer-generated pins are NOT
independent expectations; hashing cannot appoint trusted custody.

Retire FINISHED only after original post-admission and final core check.
Finished means capture operation returned,NOT complete coverage/measurement.
Original gold-void breaks may leave absent scheduled suffixes. Return only an
explicitly incomplete structural report for those known suffixes; never create
EX0/fake attempts. All observed records must have consistent associations and
matching bytes. Unexpected missing observations or any other mismatch quarantine.
Do not rely on truncated diagnostics as an acceptance oracle.

db_missing quarantines,retaining exact original status only internally/fixed
snapshot reason;do not map it into core invalid_gold. The3 actual gold-invalid
statuses may use normalized invalid_gold with original full status in payload.
Invalid scorer score0 is retained in raw result but normalized score remains
None; never count it as a valid declared score.

## Failure and resource rules

Every operational failure quarantines permanently,including BaseException,
without cleanup/logging that masks original exception identity.
Reentry refusal itself must not corrupt the active invocation.
Generic callback failure means unknown operational outcome,NOT observed provider
failure,cancellation,retirement or completed attempt. No automatic retry.

Size/association/state failures use bounded opaque CaptureError.
No successful CapturedProbe escapes failed run;no public raw partial accessor.
Snapshots contain only fixed states/counts/ordinal diagnostics.

Enforce actual representation budget: record counts,both plan projections,
repeated association fields,checkpoint bytes,retention pins before generation;
then charge payloads as they arrive. Check completion character/UTF8 bounds
before extraction. Bound extracted SQL,result detail and encoded scoring payload
before retaining/serializing oversized data. Escaping/duplicated text counts.
No optimistic budget relying on final rejection after unbounded allocation.

Use existing core ceilings. Source implementation is synchronous; locks may
guard lifecycle transitions but spawn0 threads/tasks/processes.
No provider/network/cleanup operations. Final core validation must run before
any result; known void suffix incompleteness is honest,not measurement acceptance.

## Explicit implemented representation

Source observation binds SHA256 of the existing preparation canonical twelve-
file digest map; extractor/scorer pins bind that map's bench/score.py entry.
This is not capture/runtime source isolation or loaded-model authentication.
Exclusion reason binds original preparation status, not category/detail.

Generated IDs use full UTF8 byte-length-prefixed plan/execution/task/slot/purpose
fields with fc1; namespace. No truncation or freshness claim. Scoring payload
uses frontier-score-v1; followed by eight length-prefixed UTF8 fields: SQL,
prediction SHA, original typed score (i:decimal or f:float.hex),status,valid,
detail,n_pred_rows,n_gold_rows. No decoder or persistent-format acceptance.

Producer reuses core private snapshot/plan/budget/membership helpers without
changing them. Future changes require joint review. Metadata reserves the12-byte
invalid_gold status then settles actual scored6-byte status. Void suffixes keep
conservative unused reservation; tight limits may refuse, never borrow space.
The budget bounds supplied representation bytes, not total Python heap use or
original scorer/preparation internals. Original exception text remains sensitive
and propagates unchanged to the explicit host; snapshots never log/encode it.

## Allowlist and non-goals

Worker writes only:
bench/frontier/probe.py
bench/frontier/draw_probe.py
bench/frontier/sample_capture.py
bench/frontier/test_sample_capture.py
bench/frontier/test_probe_observation.py
.worker-testplan.md
.backend-report.md

Parent owns this spec/task/AGENTS. No binding-core edits,fixture/native/training
consumer changes,policy/backend defaults,attestation,JSON/file consumer,
persistent formats,manifest publication,real corpus/model/provider execution,
SDK/Docker/Runtime/Scope/native activation,install/train/save/resume or spent
qualification renewal. Parent tests only synthetic fixtures/actual local SQLite.

# Owned SQL SCORER adapter

2026-10-31. Base `441f362a0b3f11755fd8ded9171ca547d138a4bc`.
Source engineering, not configured BIRD or native activation.

## Test plan, before implementation

| Gate | Numeric acceptance |
| --- | --- |
| Construction | Zero file opens, SQL, staging, native/model calls or invocations. Exact SqlTask, PilotExecutor and InstrumentSettings. |
| Settings | Inherit full InstrumentSettings validation plus ScoreRequest rules: finite exact float `0 < scorer_timeout_s <= 30`, positive non-bool row cap, `set` or `multiset`. Never impose PROGRAM's fixed 5s restriction. Invalid binding/settings: zero allocations. |
| Admission | Explicit `admit()` seals source/DB admission through existing `admit_program`; zero SQLite/staging/native calls. Every score repeats fresh admission and requires the identical sealed DB identity. Never refresh expected pins. |
| Binding | Preserve original private task, all task/settings fields, executor/profile/state-dir identities and fingerprints. Each mutation refuses before allocation. Fingerprints do not establish draw provenance. |
| Request | Two predictions produce two distinct real retained owners, two dispatches and one actual close per owner. Original host DB path stays on the owner; only scorer request task path becomes `/db.sqlite`. Gold and other task fields are unchanged. Empty prediction is accepted; extraction is outside this adapter. |
| Native results | Preserve the actual ExResult object and all fields for ten statuses: match, mismatch, pred_error, pred_timeout, pred_truncated, pred_empty, gold_error, gold_timeout, gold_truncated, db_missing. Last four stay invalid, never converted to ordinary zero reward. No reward recording. |
| Fatal branches | Invocation abort, nested abort, malformed result/completion/ACK and cleanup failure are infrastructure errors. Zero fabricated results/rewards or replay. |
| Ownership | Retain actual invocation before first await. One retained actual invocation-close task shared by operation-finally and adapter shutdown. Owner/private ACK authority, role/request/profile digests and exact completion-ACK identity all checked. Repeated close does not replay. |
| Cancellation | Three actual caller task cancellations, two during held cleanup. One dispatch, one actual invocation close, first intent unchanged; first cancellation escapes only after real ACK. Cleanup failure wins. |
| Unknown proof | Real first-intent 12s deadline plus 30ms: caller remains pending, no ACK/result, owner retained. Independent teardown cannot upgrade API outcome. |
| Multi-owner shutdown | Start/retain every known close task before awaiting any, so one unresolved owner cannot prevent cancellation of another. Closed adapter rejects new scores. Unknown proof may keep adapter close pending indefinitely. |
| Sensitivity | Retained-close and abort-to-zero bypass each hits once and fails its named intended assertion; fresh restored positives pass, source unchanged. |

Canonical fake-boundary actors establish ownership, not SQL semantics. All new
actor code requires Python/security static clearance before execution. Preserve
19.5s independent safety deadline, pre-Base creator ledger, per-owner evidence,
startup fencing and mandatory nested SAFE proof. No process-group authority.
Use actual public invocations, creator waits/joins and decoder-produced results,
not public execute/ACK stubs. Pure mapping checks alone do not qualify lifetime.

## Selected public API

New `ptc/sql_owned_score.py`:

```python
def build_owned_sql_scorer(
    *, task: SqlTask, executor: PilotExecutor,
    db_sha256: str, instrument: InstrumentSettings,
) -> OwnedSqlScorer: ...

class OwnedSqlScorer:
    def admit(self) -> None: ...
    async def score_sql(self, predicted_sql: str) -> ExResult: ...
    async def aclose(self) -> None: ...

class ScoreInfrastructureError(RuntimeError): ...
```

Builder is inert. Admission is explicit and mandatory before scoring. Repeated
admission checks the original sealed identity, never reseals changed DB bytes.
Keep stable generic error messages without private task/gold/prediction values.
Private scorer necessarily retains gold and sends it only through the canonical
SCORER request. Do not claim its host graph or SCORER wire is gold-free.

Use the existing non-native `PilotExecutor.admit_program` despite its name:
it checks both role source closures and DB identity, not PROGRAM timeout.
No core admission duplication, profile changes, or PROGRAM refactor.
Instrument metadata hashes remain supplied metadata, not independent provenance
or permission to update expected execution pins. Seal the original complete
InstrumentSettings, not only its three fields consumed by ScoreRequest.

Retain private `_jobs` with actual `invocation`, pre-execution `snapshot`,
one `close_task`, eventual `ack` and optional `completion`, for observational
checks. No await separates allocation and retention. Await public execute
directly; no replay, default executor, outer wait_for, fabricated result or ACK.
Create all shutdown close tasks before joining any. Repeated cancellation must
not detach these retained tasks or replace the first caller cancellation.
Failed cleanup remains fatal; unknown proof remains pending.

## Non-goals

No TaskData association, draw/denominator authority or manifest schema, SDK/QA
registration, Task.score override, prediction extraction, reward persistence,
host execution_accuracy execution, corpus selection/downloads, model/provider
calls, native/profile activation, repinning or policy/budget/spend selection.
Invalid-result propagation into the real SDK writer is a later contract.
Research 4/5 stay PARTIAL, 6 BLOCKED; baseline missing, not zero.

## Implementation order

1. Independent unit and canonical fixture tests; establish logical RED.
2. Implement only the owned scorer adapter, preserving current PROGRAM/core.
3. Source reviews before actor execution, then canonical gates, controls,
   affected regressions, documentation and approved publication.

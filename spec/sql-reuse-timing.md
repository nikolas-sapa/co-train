# SQL reuse outer timing contract

Status: approved scratch prototype integrated as an external caller-operation
harness, not an SDK or capture change. The test-first contract below remains the
acceptance boundary; integration changes only test imports and fixture locations.
Ownership: `bench/sql_reuse_timing.py`, `bench/test_sql_reuse_timing.py`.
No measured product benefit or native acceptance is established.

Test plan, numeric gates:
1. Eight predeclared unique pair IDs produce exactly eight rendered rows even with
   a missing arm or aborted attempt. Any incomplete/invalid/incomparable pair:
   all mean savings, scenarios and break-even unavailable. Failure duration retained.
   `analyze` requires a separate immutable
   planned_case_ids tuple. Sparse observations cannot shrink the denominator.
   Omit one whole pair or every pair: still eight rows, no aggregate claims.
   Reject duplicate/unplanned observations and duplicate/empty planned IDs.
2. Four operation kinds (candidate_prepare, qualification, reuse, baseline_full):
   injected clock 100 -> 350 yields exactly 250 integer ns. All kinds close on
   success, Exception and BaseException. Same return/exception object and cause.
   Start/end negative, bool, float, or backward clock rejected, never clamped.
   Invalid final clock during an operation error records unknown duration without
   masking the original error. Pre-operation invalid clock prevents invocation.
3. No callback runs unless allow_execution is exactly True. No implicit SDK flag,
   executor selection, fallback, approval, inference, credentials, network, native job.
4. Sum every setup attempt (including failed qualification), never failed-attempt
   filtering. Empty/incomplete/unknown setup -> unknown, not zero.
   Separate exact Fraction nanosecond arithmetic only:
   gross = mean(baseline_full) - mean(treatment_full)
   net_per_use(N) = gross - setup_full / N; N = 100, 1000, 10000 SCENARIOS.
   N is usage-unit count, not adoption prediction. Break-even = least integer
   N >= 1 with gross*N >= setup; gross <= 0 -> no finite break-even.
   Unknown cost/tokens/human time/CPU/provider latency remain unavailable.
5. Deterministic stub guard: callback includes simulated compute 7 ns, write 31 ns,
   fsync 11 ns -> 49 ns. Deliberately skip final 11 ns: same intended assertion RED.
   Deliberately drop failed qualification's 40 ns overhead: exact setup assertion RED.
6. At least one non-mocked existing file SDK workflow with tiny real SQLite fixtures:
   source EX=0, four qualifications EX=1, caller-held receipt pin, one reuse EX=1.
   Candidate creation + caller reload, all qualification writes/fsync, all reuse
   writes/fsync are bracketed. Returned paths/objects preserved. Local caller receipt
   pin is only fixture trust, not authenticated external approval.
7. Render only ordinal case references, booleans/status, numeric timing and fixed
   labels. SQL/questions/schema/observations/paths/secrets/error messages never
   rendered; malicious case identifiers absent (not merely HTML-escaped).
   No automatic file output; tests use uniquely owned temporary directories
   outside checkout, without overwriting caller assets.
8. Pure stdlib unittest, -B / PYTHONDONTWRITEBYTECODE=1, no pytest cache.
   Run all checks GREEN and two intended assertion mutation controls RED.

Span boundary:
run(kind, caller_callback, allow_execution=True) starts immediately before callback
invocation and ends after it returns/raises, including all synchronous SDK file
reads, rescore/admission/execution/score, output writes, rename and fsync performed
inside that callback. Observation finalization and caller work outside callback
are excluded. No automatic retries. Caller must include their candidate preparation/
load and full baseline or treatment operations and label them honestly; wrapper
cannot certify callback completeness. Reuse SDK alone is SDK outer wall span, NOT
model/provider/customer/team end-to-end. Concurrent spans cannot be summed as team
wall time. Measurement clock/instrumentation overhead is not subtracted.

Non-goals:
No schema/envelope/capture changes, provider adapters, CLI, registry, discovery,
search, training, native trials, SDK approval automation, production deployment,
new scientific estimator, performance benchmark, cost conversion or team-hours claim.
Existing paired statistics are not reused because none are needed for this narrow
descriptive arithmetic. Research motivation is not evidence of co-train benefit.
No monetary or token fields are accepted or invented.

## API and trust declarations

```python
from bench.sql_reuse_timing import Arm, Pair, Span, Timer, analyze, render_summary

# Trusted caller callbacks supply their own existing SDK arguments and consent.
timer = Timer()  # clock defaults to time.perf_counter_ns
result = timer.run("reuse", trusted_caller_operation, allow_execution=True)
spans = timer.observations

analysis = analyze(
    observations, setup_attempts,
    planned_case_ids=planned_case_ids, setup_complete=setup_complete,
)
summary = render_summary(analysis)
```

`run` defaults to `allow_execution=False` and preserves the callback's return or
original exception. It does not forward consent to the SDK or choose an executor,
fallback or approval. Supported operation kinds are `candidate_prepare`,
`qualification`, `reuse`, and `baseline_full`. Callers can bracket candidate file
creation plus reload, the complete `qualify_candidate_files` call, and the complete
`reuse_approved_files` call without changing those APIs or capture formats.

`Span` stores kind, integer `elapsed_ns` or `None`, callback completion and clock
validity. `Arm` supplies full integer `full_ns` or `None` and independently trusted
`solved_valid`. `Pair` supplies an opaque case ID, optional baseline/treatment arms,
and independently trusted comparability. Identifiers are never rendered, only
ordinal row numbers. Aborted/error arms must not declare valid solved status.

`setup_complete` is only the trusted caller's declaration that every setup attempt
is present, including failures; the harness cannot prove completeness or recover
omitted work. A complete known setup may include failed attempts followed by a
successful retry. Empty setup is unavailable, not an assumed zero.

At the reported break-even integer, total net savings are nonnegative, not
necessarily positive: equality means exactly zero. Scenarios use exact `Fraction`
nanoseconds, rendered as rational strings. Unknown required evidence suppresses
aggregate savings; none is converted to zero. No new scientific estimator runs.

Unavailable fields include billing, tokens, human review, CPU time, provider
latency, retrieval, semantic search, team discovery and team wall time. Separate
trusted observations would be needed for those measures; elapsed time is not a
proxy for money or tokens. Qualification/pilot internal latencies are not silently
relabeled as full outer spans. Local fixture receipt pins do not authenticate
external approval. Existing SDK trust and in-process isolation limits remain.

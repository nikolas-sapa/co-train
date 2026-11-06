# Optional RUN metrics retention

Source-only operational contract for `train/run_monitor.py` and
`train/run_metrics.py`. These requirements, including primary-failure/close
precedence, define the contract, not proof of runtime behavior or an
acceptance receipt.

## Attachment and ownership

Public monitor APIs:

```python
RunMonitor()
monitor.attach_retention(path: str) -> None
monitor.observe(log: dict) -> str | None
monitor.rows: list[dict]
monitor.aborted: str | None
monitor.finalize() -> tuple[bool, list[str]]
monitor.close() -> None
```

Retention is opt-in, with no default I/O. Caller supplies an absolute JSONL path
in an existing caller-owned directory. Attachment creates exclusively, never
overwrites an existing destination, creates no parents and adds no header.
Only one attachment attempt is allowed, before ANY observation or finalize,
including non-step observations. Late attachment refuses rather than migrating
in-memory history. No new persisted metrics/schema or verdict authority.

For the [monitored SQL builder](native-training.md#optional-rollout-capture-and-monitored-retention),
obtain the actual returned `MonitoredSqlTrainer.monitor`, then attach retention
before observations. Do not attach a separate monitor expecting the callback
to use it. Existing `on_log` forwards non-None logs to this monitor's `observe`;
the builder does not promise framework-constructor or callback-registration
quiescence. If an observation already occurred, attachment must refuse.
This ordering is not permission to construct/run a blocked native runtime.

## Raw rows and unchanged adjudication

Each observation snapshots the actual row, including nested values, non-step
rows, post-abort rows and the row causing an abort. `rows` returns a defensive
deep copy. Preserve original values without filtering, renaming, sanitizing or
inventing metrics. A row containing exact `loss` is a logged step; retention
does not turn other rows into steps.

The existing writer serializes each snapshot as one plain JSON line, performs
an unbuffered write, then flush/fsync before normal return. Legacy `NaN` and
`Infinity` serialization remains unchanged, not silently normalized to zero
or rejected under a new strict-JSON policy. A failed serialization/write/fsync
may leave the offending row in memory and an absent/partial on-disk line;
there is no transactional repair or completeness guarantee after failure.

Existing `V.load` and `V.run_verdict` semantics stay unchanged. `finalize` applies
the existing verdict to observed rows, not newly synthesized telemetry.
Retention adds no loss/logprob/step metric, healthy-run exemption, checkpoint
evidence or completion authority. A retained row is not proof that training,
an optimizer update, a checkpoint or a durable training transaction occurred.

## Failure and close contract

Attachment or retention failure is sticky and fail-closed. Propagate the
failure; no reattachment, automatic write replay or retry. Later observation/
finalization must not yield a healthy verdict after a latched retention failure.
Abort latching does not stop raw retention of later supplied rows while storage
remains healthy.

Caller explicitly closes the actual monitor's attached storage. Close releases
storage, not training resources or a run verdict. An active primary write/fsync
failure must not be masked by a secondary close failure; preserve the primary
exception. With no active primary failure, the first standalone close failure
still propagates and latches failure. This precedence is a contract requirement,
not proof of implementation behavior.
Successful close is not a retry/resume mechanism or authorization to observe
through closed storage.

## Non-goals and verification boundary

No automatic builder attachment, default file writes, headers, new schema,
metrics, estimator, framework callback loop, cleanup guarantee, transactional
repair, directory durability promise or durable training proof. No provider/
model/framework execution instructions or native CLI enablement. Existing RUN
criteria, version/source pins, runtime/scientific gates and deliberate
`grpo_ptc` refusal remain unchanged.

VERIFY_REAL: Worker checks 0, UNRUN. Source inspection only; parent owns final
source fidelity, failure-precedence verification and integration. BIRD baseline
missing, not zero; stages 4/5 PARTIAL, stage 6 BLOCKED.

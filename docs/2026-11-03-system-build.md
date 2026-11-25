# System build status, 2026-11-03

These additions advance the existing research instrument. They do not complete
co-training or establish a BIRD baseline, training result or harness-swap benefit.
Stage 4 remains PARTIAL, stage 5 PARTIAL, stage 6 BLOCKED.

## Integrated and offline-verified

### PTC evaluation and project CLI

`cotrain_ptc_qa_env.run_ptc_qa_eval(config)` runs the admitted reporting Env
through the original SDK evaluator. `cotrain_ptc_qa_eval` supplies the project
JSON `--config` CLI. This is not stock SDK CLI support.

The public configured runner retains its exact-base-Agent boundary. The private
evaluation route preserves the real episode Agent, original semaphore, task,
scoring and JSONL writer. Each run has an independent QA channel; bounded
telemetry uses `trace.info["cotrain_ptc_qa"]`. Reports do not alter reward or
verdict. Unsupported configuration and inherited activation refuse before
evaluator startup.

### Paired BIRD coordinator

`bench.paired_bird.prepare_paired_bird` admits retained draw/supplement digests.
`run_paired_bird` consumes the resulting plan once, Bash then PTC, with one
rollout per eligible task/arm. `adjudicate_paired_bird` preserves terminal voids.

The supplied async iterator is trusted host code, not a policy-facing API:
its request contains private tasks, gold SQL and database paths. Drivers must
project public inputs and enforce actual runtime/model budgets. Missing rows,
duplicates, invalid outcomes, overflow and terminal failures cannot become a
complete comparison. Disclosure retains planned, eligible and excluded counts.
All coordinator results remain `measurement=False`; cost/usage remain unknown.
Cancellation joins cooperative driver cleanup, not hostile callback containment.

### Pure training run monitor

`train.run_monitor.RunMonitor` snapshots logs, latches the first metric-health
failure and reuses existing verdict predicates. `observe(log)` checks live
health; `finalize()` calls the existing final verdict. Healthy short histories
can continue live but fail final adjudication. This is not trainer wiring or
proof of an optimizer update/checkpoint.

### Fixture frontier sidecar

`train.frontier_inputs.write_fixture_frontier_sidecar` publishes a create-only,
hash-pinned sidecar without replacing the existing manifest format.
`load_fixture_frontier_inputs` checks complete retained artifact digests before
parsing or corpus admission, preserves the existing scientific guards and joins
the exact retained tasks through fresh admissions.

Producer evidence derives aggregates from explicit sample records, including
exclusions and voids. Publication failures distinguish absent output from an
indeterminate post-commit result. These APIs accept fixtures only; neither a
sidecar nor matching hashes authenticates real measurements or unlocks training.

### SDK SQL fixture bridge

`bench.bird_sdk_driver` supplies shared public projection, effective-setting
seals and complete original-EX decoding. Unsupported/stateful configuration,
serializer callbacks, drift, unsafe output destinations, incomplete membership
and invalid/missing EX refuse. No aggregate-reward or zero-fill fallback.

Tests connect paired coordination to original SDK loaders, evaluator, episode
Agents, traces, actual SQLite actions, scoring and JSONL writer. The retained
driver and plugins are test-only. They use the disclosed first-party
ScratchRuntime/cache/foreground-transport-drain shim, not production isolation.
The Bash fixture is a SQL exchange, not the canonical production Bash channel.
Original SDK read-only Git provenance lookup remains allowed metadata.

### SQL worker and resource-lifecycle primitives

`ptc.bird_sql_worker` generates a bounded stdlib query payload with the unchanged
shared SQLite protector and refusal text. Tagged transport preserves SQLite
types and duplicate columns. Infrastructure overflow cannot become SQL refusal
or EX0. Multiple queries remain possible within an action; no SQL-count quota
or new PRAGMA restriction is introduced.

Docker arguments are static plans with explicit images/resources/context.
`ptc.bird_sql_worker_lifecycle` models pending creation, start, drain, revocation
and retirement. Neither module executes Docker or proves real resource absence.
Actual namespace, physical mapping, image/SQLite compatibility, hard retirement
and full paired capability/byte-bound parity remain unqualified.

### Single-query resource controller

`ptc.bird_sql_worker_controller.QueryWorkerController` composes the payload and
lifecycle with explicit, source-pinned CLI processes, bounded concurrent pipes
and joined local cleanup. Construction is inert. Each instance serves one
query, returning only after known successful retirement. Unknown creation or
cleanup stays Pending, never becomes SQL refusal or EX0. Retained completion
observers preserve local process ownership even if a collector is cancelled
before its first body; eventual settlement requires a live event loop.

Tests execute a temporary Docker-CLI protocol fixture and actual toy SQLite,
not the real Docker CLI/daemon. This is an unqualified library, not an SDK arm,
task broker, Bash runtime, production factory or launch permission. Shared-worker
and controller reload tests restore their module namespaces on success and failure;
production type checks remain unchanged.

### Task-local SQL broker

`ptc.bird_sql_broker.TaskSqlBroker` binds a trusted host task/database identity
to original query controllers. Its aiohttp application exposes a task-bearer
protected `/query` handler but starts no listener. One controller executes at
a time; a shared admission bound includes waiting callers and body readers.
Nine successive queries remain nine executions, not an invented SQL quota.

Requests and typed results retain the worker protocol. Direct and HTTP input
are bounded before large encoding allocations; invalid requests refuse without
revoking a healthy broker. Infrastructure failure and uncertain retirement stay
sticky. Cancellation and close retain owned cleanup; unknown work is Pending,
not successful closure. Eventual local settlement still requires a live loop.

This is fixture-verified composition, not a registered SDK Task/Env, Bash
renderer/runtime, serving endpoint or production config seal. HTTP tests use a
disclosed in-process request/transport seam; CPU database paths do not prove
opaque Docker namespaces or physical mount identity.

### Public local-settlement observation

The controller and broker expose `wait_local_settlement(timeout_s=...)`.
After revocation/close begins, an outer owner can await actual local process,
pipe and dynamic reclamation closure without private controller access.
One absolute observation deadline covers nested work. Observer cancellation
does not cancel cleanup; observation does not dispatch, retry or renew cleanup.

Normal return certifies local settlement only. Historical uncertainty, remote
Pending and sticky failure remain unchanged. Unknown local ownership still
refuses; forced loop shutdown remains outside the guarantee. This closes a
library ownership seam, not production Docker retirement or SDK activation.

## Verification

Separate parent runs against the integrated checkout:

| Selection | Result |
|---|---|
| PTC evaluation/CLI and affected Bash/PTC regressions | 402 passed |
| Paired coordinator, draw admission and affected SQL/paired regressions | 252 passed |
| Run monitor and selected pure verdict regressions | 301 passed |
| Fixture frontier producer/consumer and selected preparation guards | 373 passed |
| SDK SQL fixture bridge and selected paired/PTC admission regressions | 170 passed |
| SQL payload and pure resource-lifecycle primitives | 78 passed |
| SQL controller, shared primitives and test-isolation controls | 162 passed |
| SQL broker and coupled worker/controller regressions | 181 passed |
| Local-settlement APIs and affected worker/controller/broker regressions | 251 passed |

Final selections report zero failures, outer-run warnings or skips. Expected
optimized child-process pytest warnings were checked and retained. These are targeted receipts,
not whole-suite qualification. Python/security reviews and intended failing
controls preceded integration. Existing dirty/untracked work was preserved.
Controller, broker and settlement selections include overlapping regressions; do not add
these rows into a whole-suite total. The initial controller run exposed 34 setup
errors from test-state leakage; the repaired final selections pass, and the
failed evidence remains retained.

Detailed source pins, per-test evidence and integration receipts are retained
outside the repository in
`/Users/nikolassapalidis/scratch/cotrain-system-build-2026-11-03/`.

## Remaining work and gates

1. Bind the broker through reviewed original-SDK task/runtime ownership and a
   canonical production Bash channel. No Docker launch is authorized; fixture
   success does not establish real serving, isolation or retirement.
2. Resolve production Bash database mapping, enforced deadlines and cleanup;
   establish aggregate PTC submission-cap enforcement and owned-SDK qualification.
3. Complete reporting transport, stock CLI admission and protected training
   assembly under their own reviewed contracts.
4. Obtain selected real policy/runtime/G/draw, genuine frontier/baseline and
   runtime/template/source-isolation evidence.
5. Only then seek separately authorized training, checkpoint restoration,
   holdout, three seeds and harness swap.

Fixture code and matching hashes do not authenticate measurements or authorize
execution. Historical diagnostic/profile grants remain spent.

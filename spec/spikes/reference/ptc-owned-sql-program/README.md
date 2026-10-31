# Owned SQL adapter sensitivity controls

Status: verified in the provisioned interpreter on 2026-10-31. Six accepted
children: three intended named failures and three restored positives.
Production files were not edited. Separate reviewed fake-actor gates passed;
these controls do not themselves establish actor lifetime behavior.

## Test plan and expected results

Each case runs a fresh negative child, then a fresh restored-positive child,
using the launcher's interpreter with `-I -B`. Each child has a 20s outer limit;
body evaluation has a 5s observation limit. Pending-task cancellation gets 250ms
before refusal. A timeout is failure, never evidence of cleanup.

| Case | Negative acceptance | Restored acceptance |
| --- | --- | --- |
| `retained-close` | Exactly 1 bypass hit; actual close count 0; exact assertion `owned invocation close omitted`; real infrastructure error retained. | 0 hits; 1 actual public close; retained close task and identical real completion/ACK; infrastructure error retained. |
| `fatal-propagation` | Exactly 1 bypass hit; 2 MockPolicy requests; exact assertion `owned abort dispatched another policy request`; 1 actual close. | 0 hits; 1 MockPolicy request; real infrastructure error; 1 actual close. |
| `db-preflight` | Exactly 1 stale DB read substitution; 1 terminal-only MockPolicy request; exact assertion `DB preflight dispatched a policy request`; 0 owners. | 0 substitutions; changed bytes rejected before policy; 0 policy requests and owners. |

All six children must have 0 forbidden attempts, no pending tasks, restored
patches, unchanged SHA256 for `ptc/sql_owned_program.py`, `ptc/sql_isolation.py`
and `ptc/harness.py`, and successful independent drains for every real owner.
Launcher hashes must match each child's before/after hashes. Receipts contain
only named assertions, counters, flags and source hashes, not request bodies,
task/gold values, credentials, exception dumps or raw logs.

## Implementation

Uses actual `sql_owned_program._Runner`, concrete `core.PilotExecutor` and
existing `test_sql_owned_program._fixture` / `_build` helpers: fresh profile,
opaque non-SQLite bytes, canonical callbacks and TaskData. Ordinary harness
dispatch uses only the existing first-party Policy's `httpx.MockTransport`.

The two ownership cases delegate the real executor factory, request cancellation
before dispatch, and delegate public invocation execute/close. Public execute
creates its own real NOT_STARTED abort/completion/ACK. No completion or ACK is
constructed or substituted. No actor is created.

All mutants are local to this driver:

1. `_Runner._close_job` drops that job from `_jobs` and omits public close.
   Removing lifetime bookkeeping prevents generic runner shutdown rescuing it.
2. `_Runner.run_program` delegates first, catches only the real infrastructure
   exception, then returns declared `CONTROL infrastructure feedback`.
3. `os.read` always delegates first, identifies the actual DB descriptor by real
   `fstat` device/inode, and substitutes captured old bytes for exactly one
   nonempty read after the DB was changed. Later reads retain the real EOF.
   Real SHA256, source/pin reads, stat/path/sidecar checks remain intact.

Policy-request assertions precede exception checks in cases 2 and 3. Only the
exact intended AssertionError counts, after scenario evaluation and its safety
finally. Other exceptions, safety failures, unexpected API decisions or bypass
counts refuse acceptance.

Before any fixture/body (including restored positives), child DENY guards cover
core staging/secure-directory/native/spawn/boundary paths, creator constructor,
Popen, Thread.start, SQLite, socket connect/bind/DNS and PID/group signals.
Inert SDK imports and the event loop's anonymous self-pipe precede guards.
Independent safety drains call original public `aclose` for every allocation,
under those same guards. API observations are captured first, and cannot be
upgraded by safety teardown. Drains verify terminal NOT_STARTED ACK identity and
absence of actor resources.

Only the launcher may create six directly owned finite interpreter children,
with fixed argv and no shell or process-group operations. Timeout cleanup is
the standard subprocess direct-child kill/wait. Child stdout is bounded JSON;
other output is discarded. Artifact writes are create-only JSON receipts:
six case receipts and `controls.json`. Fixture files use temporary directories,
never the artifact directory. Existing receipt names cause refusal.

## Entry command

Use the repository's already provisioned test interpreter, no install:

```text
<qualified-python> -I -B /Users/nikolassapalidis/Developer/co-train/spec/spikes/reference/ptc-owned-sql-program/control.py --artifacts-dir /absolute/fresh/receipt-directory
```

Observed: exit 0, six accepted case receipts, accepted `controls.json`, exact
one-hit negative assertions, zero-hit restored cases, zero forbidden attempts
and unchanged production hashes. Negative children exit 0 only when their exact
intended failure and all independent safety checks were observed.

## Non-goals and evidence limits

Pure unit sensitivity only. No native/SDK runtime execution, SQL execution,
scoring, actor-resource cleanup proof, corpus access, model/network calls, spend,
profile activation, source repinning, production selectors or gate relaxation.
MockTransport requests are not model calls. NOT_STARTED owners do not establish
actor lifetime behavior. Research 4/5 remain PARTIAL and 6 BLOCKED.

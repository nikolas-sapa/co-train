# Owned SQL SCORER sensitivity controls

Status: verified in the provisioned interpreter on 2026-10-31. Two one-hit
intended failures and two fresh restored positives accepted.
Production, PROGRAM controls, source pins and gates are unchanged.

## Test plan and expected results

Two cases, each with a fresh `-I -B` negative child followed by a fresh restored
child: exactly four children. Each child has a 20s direct-child outer timeout.
Scenario observation is limited to 5s; pending-task cancellation gets 250ms.
Exceeding either observation/drain limit refuses acceptance, not cleanup proof.

| Case | Negative acceptance | Restored acceptance |
| --- | --- | --- |
| `retained-close` | 1 bypass hit; 0 adapter-triggered public owner closes; exact AssertionError `SCORER_RETAINED_CLOSE_OMITTED`; actual infrastructure error and no result. | 0 hits; 1 public owner close; retained close task and identical real ACK; actual infrastructure error and no result. |
| `abort-to-zero` | 1 bypass hit; original exact infrastructure error; deliberate manufactured zero result; exact AssertionError `SCORER_INFRASTRUCTURE_BECAME_ZERO_RESULT`; 1 public owner close. | 0 hits; actual infrastructure error and no result; 1 public owner close with retained close task and identical real ACK. |

All four children require exactly one real owner/completion, two delegated fresh
admissions (explicit admission and scoring), one explicit adapter shutdown, one
independent original-public owner drain, zero forbidden attempts, no pending
tasks and restored patches. SHA256 must remain unchanged for:

- `ptc/sql_owned_score.py`
- `ptc/sql_isolation.py`
- `ptc/harness.py`
- `ptc/sql_owned_program.py`

Each child's before/after source hashes must also equal the launcher's hashes.
Negative exit 0 means the exact named failure and all other expected observations
were established, not that the broken operation succeeded correctly.

## Real path and deliberate faults

Uses `test_sql_owned_score._fixture(root)` for a fresh profile, opaque non-SQLite
DB, private SqlTask, InstrumentSettings and concrete PilotExecutor. The actual
`build_owned_sql_scorer` builder is used, followed by mandatory explicit `admit`.
No TaskData, SDK client, harness launch, policy or model is needed.

The `owned_score` wrapper delegates the actual canonical factory, immediately
retains the actual owner and requests `runner_closed` cancellation before
dispatch. Observational public execute/close wrappers delegate the original
methods. Actual owner close must run in `job.close_task`.

The owner itself issues the real NOT_STARTED cancelled completion and private-
authority ACK. No public completion or ACK is fabricated, copied or substituted.

Mutants exist only in this driver:

1. `_join_close(job)` removes that job from the scorer's `_jobs` once and returns
   None without calling public owner close. Operation-finally reaches this
   before explicit shutdown. Shutdown's all-starts loop sees no job and cannot
   rescue the omitted close. Constructor, `_ensure_close_task`, admission and
   source/settings metadata are not changed.
2. `score_sql` awaits the original method, catches only ScoreInfrastructureError,
   records whether its exact type/message is
   `ScoreInfrastructureError("owned SQL scorer did not complete")`, then returns
   the declared negative-only
   `ExResult(0.0, "pred_error", True, "CONTROL abort-to-zero", 0, 0)`.
   This manufactured RESULT is the intentional fault, never a positive result,
   cleanup capability, native outcome or reward record.

After capturing result/error and explicitly closing the adapter, retained-close
first asserts actual public close count is 1. Abort-to-zero first asserts result
is None, before checking the expected exception. No pytest.raises can hide the
intended assertion. Arbitrary exceptions, wrong type/message, wrong counters or
safety failures cannot qualify as sensitivity evidence.

## Safety and receipts

Before every fixture/body, including restored children, DENY guards cover:
core staging, secure directories, staged activation, native/boundary/guardian
paths, legacy score/program methods, PROGRAM ownership, creator construction,
Popen, Thread.start, SQLite, socket connect/bind/DNS and PID/group signals.
The event loop's anonymous self-pipe is created before socket guards.
Importing test helpers does not execute their autouse fixture; this driver
installs its own guards and real predispatch cancellation.

Every actual owner is independently drained with ORIGINAL public `aclose`,
under the same guards, even after assertion failure. API observations are frozen
before these drains and never upgraded. Checks require the owner already had
its real terminal cancelled completion, matching authority/ACK/completion/job
identities, NOT_STARTED/released flags and zero children, controller threads,
resources, endpoints or host/seal descriptors. No actor is created.

Only the launcher creates subprocesses: four directly owned finite interpreter
children, fixed argv, no shell, no process-group operations. Standard subprocess
timeout handling kills/waits only its direct child. Child stdout is bounded
sanitized JSON; incidental output is discarded. No gold, prediction, task values,
credentials, exception text or raw logs are written to receipts.

Artifacts are create-only JSON: four case receipts plus `controls.json`.
Existing names refuse overwrite. Source hashes, named assertions, counters and
flags are the only evidence retained. Fixture scratch uses temporary directories,
not the artifact directory.

## Entry command

Use the already qualified repository interpreter. No installation:

```text
<qualified-python> -I -B /Users/nikolassapalidis/Developer/co-train/spec/spikes/reference/ptc-owned-sql-scorer/control.py --artifacts-dir /absolute/fresh/receipt-directory
```

Observed: exit 0, four accepted case receipts and accepted `controls.json`.
Negatives reached their exact named assertions with one hit; restored children
hit zero. All forbidden-operation, pending-task, independent-drain and
unchanged-source checks passed.

## Non-goals and proof limits

Pure-unit NOT_STARTED sensitivity only. No native/SQL execution, actor-resource
lifetime proof, SDK scoring, prediction extraction, reward persistence, corpus,
model/network calls, spend, profile activation, repinning or gate changes.
The existing 15 actor cases belong to a separate regime and are not run or
qualified here. Research 4/5 remain PARTIAL, 6 BLOCKED.

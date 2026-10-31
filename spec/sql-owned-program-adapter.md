# Owned SQL PROGRAM adapter

2026-10-31. Base `b46c82591868be2b8ab35ce590218bae76148c6e`.
Source engineering with canonical first-party fake-boundary actors only.

## Test plan, before implementation

| Gate | Numeric acceptance |
| --- | --- |
| Inert construction | Valid builder: zero file opens/staging/native/SQL/model calls; create canonical `sql_catalog` once. |
| Binding | Exact original TaskData identity/name/fingerprint, original config fingerprint, exact base/compiled catalog membership and every captured callback identity. Independently alter each: zero policy requests/invocations. Mutation after policy request 1 refuses before next program allocation. |
| Host-data encoding | Strict finite sorted compact UTF-8 JSON from JSON-mode Pydantic serialization; 131,072 bytes accepted, 131,073 refused. Plaintext TaskData subclasses supported; image inputs refused. Retain digest, not serialized data. Nested mutation detected. This host-data bound is not a DB cap. |
| Timeout | Only non-bool numeric `5`/`5.0`. Unsupported values refuse before policy. Valid constructed runners close once on preflight failure; invalid initial launch values retain existing zero-factory behavior. |
| Fresh profile admission | Share the current invocation source-closure check. Missing/extra PROGRAM or SCORER member, missing controller module, changed source/observer pin: public preflight and execution both refuse with zero dispatches. Never replace expected pins. |
| Database identity | Non-staging streaming SHA256; reject parent/final symlink, hardlink, wrong UID, FIFO, each of three sidecars, digest mismatch, pathname replacement and in-place change. Zero SQLite/staging writes. FIFO refusal within 1s fixture cap; descriptors return to baseline. No new DB byte cap. |
| Pre-program freshness | Initial validation seals DB identity. Every program checks the same identity and live task/config/catalog/executor guards before allocation. Existing execution-time source/staging admission remains. |
| Dispatch/feedback | Two programs create two distinct actual invocation owners, retained before first await; two dispatches, one runner. Forward ordinary and rejected/error observations byte-for-byte, without doubled prefixes. Native-invalid empty/oversized input is infrastructure-fatal, zero invocations, not invented feedback. |
| Close | Each actual invocation `aclose` called once through one retained task; runner close once after all jobs. Returned close ACK must match retained owner identity/digests and identical completion ACK when available. No reconstructed capability. |
| Fatal infrastructure | Real canonical protocol abort and malformed/unexpected branches are fatal: one model request/program/allocation, no subsequent policy or scorer call. Cleanup still joins. |
| Cancellation | Three actual launch Task cancellations, two during held canonical cleanup; first intent/deadline unchanged, exactly two physical 40B endpoint writes, one dispatch/owner close. Original first cancellation escapes only after real ACK and runner close. Also test first cancellation during otherwise-normal close and an earlier body cancellation followed by two during runner close. |
| Unknown proof | Withhold one canonical proof. At real first-intent deadline +30ms: launch pending, no completion/ACK, owner/admission barrier retained. Independent physical teardown cannot upgrade API outcome. No completed runner-close claim while launch remains inside execute. |
| Sensitivity | Retained-close, fatal-abort and DB-preflight bypasses each hit once and fail one named intended assertion; safety teardown and restored positives pass. No production bypass selectors. |

Ownership gates must use public `OwnedSqlInvocation` with actual creator-owned
fake-boundary subprocesses, canonical finalization and real waits/joins.
Unit-only malformed-response tests do not establish resource cleanup.

Five canonical fixture nodes: ordinary→rejected and ordinary→error (two
programs each), execution cancellation, real protocol failure, missing proof.
Use actual ordinary PTCHarness with its supported MockTransport seam, not a
replacement loop or public fake completion. No actual SDK/native/SQL execution
claim from these fixtures.

## Selected API

New `ptc/sql_owned_program.py`:

```python
def build_owned_sql_program_harness(
    config: PTCHarnessConfig, *, data: TaskData, task: SqlTask,
    executor: PilotExecutor, db_sha256: str, max_rows: int,
) -> PTCHarness: ...
```

Return an ordinary PTCHarness using the existing public constructor. A private
launch-local owner implements `validate_program_timeout`, `run_program`,
`aclose`. Do not make a new configured SDK adapter or alter QA.

New explicit, non-native core API:

```python
PilotExecutor.admit_program(
    *, db_path: str, db_sha256: str,
) -> ProgramDatabaseIdentity
```

Frozen identity fields: `path`, `sha256`, `st_dev`, `st_ino`, `st_size`,
`st_mtime_ns`, `st_ctime_ns`, `st_uid`, `st_mode`, `st_nlink`.
Path is absolute and lexically normalized, not resolved by inert construction.
Row cap/digest/code scalar rules inherit ProgramRequest; no new native limits.

## Binding and trust

The caller explicitly associates original public TaskData with private SqlTask.
Require matching nonempty names, exact SqlTask/concrete PilotExecutor and
ordinary PTCHarnessConfig. This is NOT independent draw or semantic task
provenance verification. Do not claim the host object graph is gold-free.

Keep live data/config/base and compiled catalog references in a private guard,
plus sealed scalar execution inputs and fingerprints. Do not retain SqlTask
or copy its gold into the runner, PROGRAM wire, descriptions or errors.
Canonical base catalog is built once; capture actual callback references
including SQL primitives, not names/signatures or introspected closures.
Compiled catalog must equal that set plus exactly one callable harness print.
Freeze its print reference after factory binding and recheck before each run.
Retain executor identity, profile fingerprint and state directory; reject drift.
Errors are stable host infrastructure messages, not values/snapshots/private SQL.

TaskData runtime representation was checked in the qualified interpreter:
actual Pydantic ModelMetaclass, subclassable TaskData class with JSON-mode dump.
No policy/native/SQLite call was made in that representation check.

## Non-native admission

Extract existing `_start` source/binding closure checks into one private helper;
use it in both `_start` and public admission, preserving refusal behavior.
Public admission must not stage, execute observer, contact daemon, create native
resources or invoke SQLite.

Walk DB parents without symlinks, check `-wal`, `-shm`, `-journal`, open with
`O_RDONLY | O_NOFOLLOW | O_NONBLOCK`, require same-UID regular file with one link,
stream digest, compare before/after complete identity and current pathname
identity, recheck sidecars, close all descriptors on every exit. Seal returned
identity on initial validation; require it unchanged before each program.
This is a freshness check, not protection against arbitrary same-UID writers.
Existing source and staged DB revalidation at actual execution stay mandatory.

## Ownership and result handling

Private runner retains `_jobs`; every job exposes its actual `invocation`,
retained `close_task`, eventual `ack` and optional `completion` for observational
test inspection. Register the job synchronously before first await.

Await public execute directly, without outer wait_for/default executor/replay.
Create each invocation close task once, retain it before awaiting, shield/join
through repeated cancellation. Runner shutdown joins those same tasks, never
calls public close again. Check owner identity/request/profile digest and exact
ACK identity; do not construct a replacement record.

Forward usable ProgramOutcome.observation verbatim, including native rejection
or error text. Invocation/nested abort, malformed completion, bad ACK or
unexpected failure is ProgramInfrastructureError, not ProgramRejected feedback.
Preserve original CancelledError after acknowledged cleanup. Failed cleanup
remains infrastructure-fatal. Unknown proof remains retained/pending.

Narrowly fix the existing harness-finally cancellation gap if the named
regression proves it: later cancellation during retained runner close must not
replace an earlier body cancellation. Keep cleanup failure precedence.

## Fixture safety

Reuse existing guest source, 19.5s outer safety deadline, independent pre-Base
creator ledger, lifetime keepers and mandatory nested SAFE proof on every exit.
Extend teardown to every retained owner, including partial allocations. Route
events/releases/evidence by invocation/slot, not `slots[0]`. Preserve all old
phase behavior and zero forbidden native/network/SQLite/group-signal attempts.
Missing-proof intent must start early enough for real 12s +30ms observation
before existing independent teardown; never extend budgets to make it pass.
Static fake-role responses prove forwarding only, not native SQL/runtime parity.
Fence actual owner startup under the creation lock before constructor
publication. A stopped inert owner must not start; an admitted start must publish
its controller before teardown can snapshot it. Two pure extracted-function
regressions must fail before this fence and pass after it.
Security/Python source review precedes new actor execution.

## Non-goals

No scorer adapter, configured BIRD registration, SDK modification/activation,
VM-progress/EX1/JSONL qualification, real corpus/draw/baseline/training,
policy/runtime/model/spend selection, source/profile repinning or gate relaxation.
Research 4/5 remain PARTIAL and 6 BLOCKED. Native/profile activation stays closed.

## Implementation order

1. Independent adapter/admission tests and canonical fixture gates, intended RED.
2. Shared admission and streaming non-staging DB identity.
3. Inert builder, private mutation guard and retained owned runner.
4. Prove/fix first-cancellation propagation through complete harness cleanup.
5. Canonical positives/unknown proof, sensitivity/restoration, affected regression
   checks and Python/security review; publish only verified source scope.

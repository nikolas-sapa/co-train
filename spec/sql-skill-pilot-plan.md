# SQL skill pilot: frozen implementation plan

PLAN FROZEN / SOURCE IMPLEMENTED / PRODUCTION ACCEPTANCE PENDING.
NO MODEL/PILOT RESULTS.
Live inference is FINANCIALLY BLOCKED. This document authorizes no calls, probes,
downloads or production-acceptance claim. [Protocol](sql-skill-pilot.md) governs
the 20-case ROWCOUNT experiment. Paths/APIs below are frozen contracts; existing
source and offline checks do not imply production acceptance.

## 1. Test plan: before implementation

Collect RED inside test bodies, not through import/collection failure. Default
tests require zero daemon/provider/key/cache accesses. Real acceptance uses the
two explicit nondefault files below; missing infrastructure FAILS, never skips.

| Named check | Numeric acceptance |
|---|---|
| T01 legacy/data-only | Preserve every historical 2,446 node ID, union the 106 committed budget cases once, then add new cases. Only existing optional Torch skip/two tokenizer deselections remain. V1 canonical bytes identical; decode/construct/rejected consent cause 0 daemon operations. |
| T02 strict records | Every duplicate/unknown/missing/version/type/UTF-8/nonfinite/bool-as-int/path-traversal negative rejects. Exact/+1: program 65,536 bytes, artifact/input/HTTP-body 8 MiB, extraction-work 64 MiB, PROGRAM stdout 1 MiB, other streams 64 KiB, messages+tools 131,072 bytes, tmp 16 MiB/shm 1 MiB. No truncated success. |
| T03 protected parity | Correct/wrong/invalid-gold fixtures preserve all 6 existing ExResult fields; actual native catalog/quoted-table ROWCOUNT succeeds in both roles under full caps. |
| T04 OS/resources | Both roles deny real AST-bypassing host-read/write/socket/fork attempts. Touched 288 MiB OOMs at 256 MiB; touched 96 MiB fails at 64/succeeds at 128. Verify swap=0/pids=1/nofile=64 and subsequent benign success. Never uncap VM. |
| T05 scorer confinement | Giant cell, wide result, recursive SQL and Counter/comparison allocation hit bounds inside SCORER, including proven comparison entry. No host hostile SQL/materialization. |
| T06 deadlines/reexec | PROGRAM 10s/whole-grade 30s external deadlines, owned cleanup ≤12s after trigger; next benign succeeds. Allowed same-PID exec retains strict 14 non-ENV/7 status/6 namespace fields. Initial ENV7 exact; post-ENV is mutable, not an exemption for kernel state. |
| T07 lifecycle | Guardian journal/ACK precedes CREATE; single-fault/lost-create/start/inherited-FD controls clean owned resources. Actual SIGKILL409 transition plus 9 strict negatives: 0 STARTs for unknown/stale/retired/foreign states. Join ACK precedes REMOVE. On the CLOSED path the guardian reap wait is hygiene only: a guardian that exits slowly past the wait bound still returns the completed typed outcome, never a raw exception. |
| T08 binding/admission | Wrong image/config/platform/source/profile each yields 0 START. Missing/stale/>4s/lower-headroom samples refuse. Sample age is measured from each sample's finished timestamp; a slow-but-successful sample near its own budget never forces UNRESOLVED. Cross-process/profiles/run-directories overlap=0; unresolved history prevents next admission. |
| T09 DB/wire | Original mutation or any WAL/SHM/journal sidecar rejects without deletion. Hostile prefix/frame/digest/role/request/bootstrap/UTF-8/overflow inputs fail closed. Whole output envelope, READY and bootstrap count toward caps. |
| T10 isolated records | V2 host-score calls=0; rescore PROGRAM launches=0. Every accepted receipt matches its dispatched canonical request hash; foreign PROGRAM hashes cause 0 subsequent SCORER calls, and foreign SCORER successes cause 0 successful captures/promotions. Native rejection containing FINAL_SQL preserves its flag/text/receipt and causes 0 SCORER calls; it cannot originate, qualify or rescore. Typed abort keeps unscored evidence; exact v1 defaults/bytes unchanged. Four actual qualification successes; fresh-process reuse on 2 fresh DBs after historical DB removal. |
| T11 controller/leakage | Manifest 20 distinct cases: 8/4/8, 0 cross-partition IDs/fingerprints/DB hashes. All 8 pairs retained. Payload gold/credential/qualification/held-out canaries=0 where prohibited; raw ExResult.detail absent from proposal. |
| T12 action/request | Both arms expose exactly 1 identical submit schema/all 4 required fields. Direct bytes never count as approved reuse; unknown selection has 0 fallback/retry. Native rejection is MODEL failure within denominator 8, not infrastructure INCOMPLETE. Malformed outer provider JSON/envelope means protocol STOP and 0 subsequent model requests, not an ordinary invalid-action failure. Exactly 2 messages/request; maximum 25 requests, output request 2,048 tokens. |
| T13 money/transport | Missing/incomplete profile or approval: 0 HTTP/0 credential reads. One durable claim/one attempt, 0 retries; ambiguous delivery/usage holds full reservation across restart. Credential collision/echo fixtures, including escaped and JSON-in-JSON strings/keys, leave 0 credential-bearing artifacts; request collision causes 0 HTTP. Receipt-field/hash/currency/charge mismatches never settle. Committed ledger remains unchanged. |
| T14 sensitivity | Bypass each binding/confinement/routing/rescore/qualification/approval/budget/sanitization guard separately: ≥1 intended assertion RED per bypass, never stale-binding/import/infrastructure failure. |
| T15 manifest DB admission | Replace a DB after HTTP admission for direct/reuse: 0 PROGRAM/SCORER dispatches and no COMPLETE report. Construction/restore races never adopt replacement hashes; source/evaluation/all four qualifications/reuse propagate the exact saved hash. Post-PROGRAM mutation causes unscored SCORER rejection. Normal/rejected/exception-carried captures must match asset hash/IDs/fingerprint. Conflicting expectations reject; None preserves v1 defaults/bytes. |
| T16 development graph | Coherently rehash response/capture/checkpoint/approval inconsistencies, including one comment/newline: 0 endpoint claims/API/executor constructions/credential reads/HTTP calls. Valid responses require matching captures; invalid actions require MODEL_ACTION_INVALID with null score/route and no capture. Fabricated prior classifications reject; disable action comparison and require an intended assertion RED. |

Offline transport/receipt fixtures prove only local protocol behavior, never
current Vyce prices, authoritative settlement or a provider ceiling.

## 2. Frozen shared records and API

Owner module: planned `ptc/sql_isolation.py`. Records are frozen, closed-field,
strictly typed; booleans are not integers. Digests are lowercase 64-hex strings.
SourcePin paths are bundle-relative, unique and traversal-free. Execution-source
pins resolve beneath the installed source root, never symlink/bundle escapes.

```text
SourcePin(path, sha256)
Limits(memory_bytes, swap_bytes, pids, tmp_bytes, shm_bytes, nofile,
       deadline_ms, stdout_bytes, stderr_bytes, input_bytes)
RoleBinding(role: program|scorer, image_manifest_sha256, image_config_sha256,
            platform: linux/arm64, sources: tuple[SourcePin],
            security_profile_sha256, limits: Limits)
ExecutionBinding(schema_version=1, program: RoleBinding, scorer: RoleBinding,
                 controller_sources: tuple[SourcePin], policy_sha256,
                 instrument_runtime_scope='host')
AbortInfo(stage: program|scorer,
          reason: admission|binding|start|deadline|memory|output|protocol|cleanup|transport)
RuntimeReceipt(role, request_sha256, python_version, sqlite_version,
               bootstrap_sha256, journal_sha256)
ProgramOutcome(observation: str|None, abort: AbortInfo|None,
               receipt: RuntimeReceipt|None, *, rejected: bool=False)
ScoreOutcome(result: ExResult|None, abort: AbortInfo|None,
             receipt: RuntimeReceipt|None)
MemoryObserver(kind='colima_default_meminfo_v1', binary, binary_sha256,
               profile='default', timeout_ms=2000)
ExecutionProfile(schema_version=1, daemon_socket, shared_state_dir,
                 observer: MemoryObserver, admission_bytes=469762048,
                 reserve_bytes=201326592, max_sample_age_ms=4000,
                 api_timeout_ms=3000, environment: tuple[7 pairs],
                 policy: SecurityPolicy, binding: ExecutionBinding)
```

Outcomes have exactly one completed/abort branch. A completed PROGRAM outcome
requires observation and program receipt, including native rejection with
`rejected=True`; preserve both fields from ProgramResponse, never infer rejection
from observation text. Infrastructure/resource abort requires observation=None
and rejected=False. Reject integer flags. The new outcome codec requires exactly
four keys, including rejected; the existing two-field wire response is unchanged.
Round-trip rejected FINAL_SQL text without losing flag, text or receipt.
Observation means the exact returned native PtcResult.observation, not an
additional capture of internal print buffers. Forward native rejection unchanged.
The native runner discards earlier prints on failure; do not recover, combine or
invent those unavailable prints. A real print-then-fail test must retain its
returned native error and rejection with zero scoring. SQL-looking rejected
observations are also tested directly at the wire/outcome/record boundary.
SecurityPolicy is the closed,
typed final effective HostConfig/hostname/mount-slot/environment-rule
representation, not an arbitrary dictionary or callback.

```python
load_execution_profile(path: Path, *, source_root: Path) -> ExecutionProfile
build_execution_binding(profile, *, source_root) -> ExecutionBinding
shared_state_dir_for(daemon_socket: Path) -> Path
PilotExecutor(profile: ExecutionProfile, *, state_dir: Path)
PilotExecutor.run_program(program: str, *, db_path: str,
                          db_sha256: str, max_rows: int) -> ProgramOutcome
PilotExecutor.score_sql(predicted_sql: str, task: SqlTask, *,
                        db_sha256: str, instrument: InstrumentSettings) -> ScoreOutcome
```

PilotExecutor is the concrete typed aggregate with immutable configuration,
owning both engines. Controller derives
source_root from its installed module checkout, never user-selected source.
Construction/codecs perform zero daemon operations; local metadata/source checks
are allowed. Legacy InstrumentSettings versions describe HOST inventory,
not guest versions; bootstrap/RuntimeReceipt records actual guest Python/SQLite.

shared_state_dir_for returns pwuid-home/
`scratch/co-train-isolation-shared/<uid>-<sha256(canonical-daemon-socket-path)>`.
Profile.shared_state_dir must equal it. ONE stable lock and unresolved registry
span every instance/profile/run-state directory for that daemon. state_dir holds
per-run journals only. Lock remains held through cleanup. Use an explicit local
UNIX socket, never DOCKER_HOST or global Docker CLI configuration.

## 3. Frozen boundary and wire

Only approved image, linux/arm64:
manifest `c3729439afc4ec3f3e159e0c86aeabfadac8030ef46838a0256383d0511c5f5e`,
config `81c0aac584c3e136c75a8da272f5d08e45e1f2ae00701fbce768f490dd22164b`.
It was pulled once, compressed content 44,927,391 bytes. Never pull implicitly.

Both roles: memory=268435456, additional swap=0, pids=1, nofile=64,
UID/GID65534, root read-only, cap-drop ALL, NNP, private PID/IPC/cgroup namespaces,
network none/default-deny seccomp; six read-only paths (five defaults plus
/dev/mqueue), twelve masks, fixed hostname co-train-isolation/exact initial ENV7.
tmp=16777216, shm=1048576: at least 17 ordinary MiB, not exclusive writable state.
PROGRAM deadline=10000ms/stdout=1048576; SCORER deadline=30000ms/stdout=65536.
Both stderr=65536/input=8388608; program UTF-8≤65536. Execve remains allowed.

Bind image/config/platform/effective policy before START. Require fresh
min(VM MemAvailable, VM total minus summed RAW container charges)≥469762048,
age≤4000ms, live controller and healthy observer before START. Sample age is
measured from the sample's finished timestamp (the data's true as-of time),
never its start: a sample that succeeds within its own budget is fresh on
completion and must not force UNRESOLVED. Start original
deadline before START, never reset. One compartment across pilot processes.
Watchdog sampling below reserve=201326592 or missing/stale observations kills
only owned compartment. Sampling is mitigation, not continuous capacity proof.

For BOTH roles: saved-capture/admitted DB SHA → source hash → owned copy →
staged hash → second sidecar check → read-only `/db.sqlite` mount.
Check sidecars before copy and again after staging; reject present
-wal/-shm/-journal without deletion. Never replace expected
SHA with a newly observed digest. Immutable owned read-only source staging binds
all actual controller/guardian/stager/decoder/worker/native closures/profile.

PROGRAM mounts only selected DB/minimal five existing ptc modules:
__init__, runtime, sql_arms, sql_runtime, sqlite_safety; native catalog and stdlib/
SQLite, no TaskView/gold/repository/keys. SCORER uses normal package initialization
and complete eleven-source existing closure, plus pinned new bootstrap/worker
sources. It runs unchanged protected EX including gold/prediction, fetch,
normalization/comparison, never PROGRAM Python/state. Gold stays controller/
SCORER only. No host broker or scoring fallback.

Wire order: exact 13-byte `PILOT_READY!\n`, one bootstrap frame, wait for
controller approval, one request, one result. Canonical UTF-8 JSON+LF envelope:

```text
{format:'sql_pilot_wire', schema_version:1, role,
 kind:'bootstrap'|'request'|'result', request_sha256, payload, sha256}
bootstrap payload: {python_version, sqlite_version, sources, db_sha256}
PROGRAM request: {program, max_rows, db_sha256}
SCORER request: {task, predicted_sql, timeout_s, max_rows, compare, db_sha256}
PROGRAM result: {observation, rejected}
SCORER result: {score, status, valid, detail, n_pred_rows, n_gold_rows}
```

Bootstrap request_sha256 is null. Subsequent request SHA includes DB hash.
Task uses existing SqlTask fields only, translating DB mount path. Bootstrap/
source/DB checks precede request delivery. sha256 hashes canonical payload;
integrity, not authentication. Reject all extra/duplicate keys and unsolicited
frames. READY/bootstrap/protocol bytes count inside stdout limits. Never drain
the opposite stream after abort.

Durable fsynced journal/guardian ACK precede CREATE. Controller watches guardian; pipe EOF,
not PID liveness, detects controller loss. Unknown inspect/kill/remove/transport
state retains UNRESOLVED and blocks admission. SIGKILL409 is accepted only after
fresh same-CID/config/owner proof: Running=false, Paused=false, Restarting=false,
Pid integer 0, never body/regex inference or generic-error swallowing.
Retire observer/CLI and join ACK before REMOVE; retired samples
are never reused. Fresh absence permits authorized CLOSED history append, never
deletion of original block. Cleanup assumes one supervisor survives and daemon
responds; simultaneous death/outage/reboot/power loss are outside guarantees.
Failure discovered while joining an in-flight observer sample must propagate:
zero successful outcomes, zero CLOSED transitions, and the next admission blocked.
A replacement guardian must reconcile durable observer/CLI ownership and spawn
intent, including interrupted registration. observer=None is not join evidence.
Without positive actor absence, retain UNRESOLVED; emit zero synthetic join ACKs
and perform no removal dependent on that ACK. Never signal an unproven actor.
Perform final controller-liveness, observer/headroom/freshness and original-
deadline checks after all pre-START durable writes, immediately before START.
Delayed-write controls for stale samples, expired deadlines, lost controller or
failed observer each require zero STARTs. Bound START by the remaining deadline.
Set one absolute cleanup deadline at the cleanup trigger; every transport and
observer/CLI join consumes that same remaining twelve-second budget. Deadline
exhaustion retains UNRESOLVED, not retrospective success after twelve seconds.
Add an intended guard-disabled assertion RED for each of these four paths.
Once the guardian has durably written its outcome and the journal is CLOSED,
reaping the guardian process is hygiene: a bounded reap wait that expires must
be tolerated (kill+wait or continue), never discarding the completed typed
outcome with a raw subprocess exception.
The isolated guardian must import SCORER records/packages only from its verified
staged closure, not an installed or original-checkout copy. Test successful
SCORER decoding in the actual isolated interpreter without the checkout on its
import path. An attempted CREATE with unknown CID and unknown completion stays
UNRESOLVED even when reconciliation temporarily lists zero matches; never retry
CREATE or infer completion from an empty list. Include delayed-registration proof
that a later CREATE cannot release the block or enable another START.
Per-socket inactivity timeouts are insufficient: bound whole progressing HTTP
transactions and delayed START by absolute operation/original deadlines, while
external supervision remains effective during blocking calls.
Observe actual allocation exceptions out-of-band within each isolated native
call, including MemoryError swallowed by native handlers. Such cases must exit
through the memory-abort path, with no EX result or native-rejection label.
Do not classify observation strings or change protected native grading logic.
Inject MemoryError beneath each native catch boundary; ordinary ZeroDivisionError
still produces unchanged native rejection. Never run hostile allocations/SQL on
the host to test this. Add separate intended assertion mutants for these guards.

## 4. Existing capture/promotion integration

Add keyword-only executor=None to start_capture/rescore_capture/
evaluate_candidate/promote_candidate/reuse_promoted. Propagate through
_instrument/_bind/_current_binding/_admit_origin/_execute/session.
V2 step calls PROGRAM only; finish calls SCORER only; rescore calls SCORER with
zero PROGRAM replay. V1 None retains exact trusted-host behavior.

Frozen database admission adds only these optional public arguments:

```python
start_capture(task, *, ids, allow_execution=False, executor=None,
              expected_db_sha256: str | None = None)
SkillCase(role, task, ids, *, expected_db_sha256: str | None = None)
```

Validate non-None expectations with existing strict digest validation.
SkillCase remains a frozen host-only record with its three positional arguments;
the new field is keyword-only. No persistent artifact/producer API changes.
After literal execution consent, a supplied expectation becomes the admitted
capture db_sha256. Verify actual bytes against it; never substitute a fresh hash.
Construct with that hash, explicitly verify constructed capture equality and
recheck database binding before returning the session. None retains the existing
fresh-snapshot path. Step/finish/rescore/executor staging keep using the immutable
capture hash, not a newly read replacement hash.

Resolve the existing private _execute expected_db_sha256 against the case field;
conflicting supplied values reject. Pass the resolved value to start_capture
and check all returned and exception-carried captures against it. Qualification
admission uses supplied case hashes for byte checks/disjointness and retains
them for execution. Reuse does not unconditionally adopt _db_digest(case.task).
Origin admission requires source-case expectation equal source_capture.db_sha256
before source rescoring. No callback/wrapper/task-path relocation or new rescore
argument. Cover construction/restore races and disable propagation separately
for intended assertion REDs. This prevents replacement rebinding, not a claim
of hostile-host filesystem snapshot isolation.

Before accepting any returned receipt, reconstruct the dispatched request using
the existing public ProgramRequest/ScoreRequest and request_sha256 helpers.
PROGRAM binds exact code, action_max_rows and the captured DB digest. SCORER
binds the existing task with only db_path translated to /db.sqlite, exact SQL,
scorer_timeout_s, scorer_max_rows, compare and the captured DB digest.
A mismatched receipt becomes AbortInfo(stage, "protocol"), without accepting its
observation/result/rejection or appending the foreign receipt as matching evidence.
Apply this check to completed and aborted outcomes that carry receipts. Fixtures
must calculate actual request hashes, not reuse placeholder hashes. Separately
disable each adapter's hash check and require an intended test-body RED.

SqlCapture adds execution_binding=None, runtime_receipts=(),
execution_abort=None. V1 encoding omits these keys and requires empty defaults.
V2 requires its closed fieldset/version-aware size admission.
execution_aborted has result=None/typed AbortInfo, retaining final/extracted SQL
when available. finish returns capture; failed step/rescore raises
CaptureExecutionAborted carrying frozen unscored capture. Resource/infra aborts
are not fabricated EX0/invalid-gold outcomes; endpoint abort means INCOMPLETE.
If a later qualification raises CaptureExecutionAborted, the promotion aggregator
returns no promotion and the ordered prefix including that abort capture.
Two completed qualifications followed by a PROGRAM abort retain exactly three
captures; the fourth qualification and held-out execution have zero launches.
The controller persists all retained qualification captures before stopping.

Native rejection is separate. V2 step appends the unchanged ActionObservation
and receipt, then seals terminal_label="program_rejected", result=None and
execution_abort=None. Preserve existing final_answer/extracted_sql, normally None;
do not extract or score rejected SQL-looking observation text. Raise new
CaptureProgramRejected(CaptureError), carrying frozen .capture. Introduce
CaptureError(RuntimeError) as base for the two new v2 exceptions, without
changing legacy exceptions. V2 program_rejected requires at least one step,
a completed PROGRAM receipt, no result and no execution abort; v1 rejects it.
_execute catches this exception and returns its capture. The controller records
MODEL failure and continues endpoint cases; rejection is not an origin EX0 or
qualification success. rescore_capture rejects before any scorer launch.
A guard mutant dropping rejected must cause an intended assertion failure.

SkillBinding adds execution_binding=None. V2 promotion requires both engines.
Candidate remains v1, SourceRef.instrument/InstrumentSettings/ActionObservation
unchanged; whole-v2-capture SHA supplies transitive engine binding.
Promotion binds candidate SHA/composite binding/four actual capture SHAs.
Wrong current engine/source/profile/pins reject before dispatch. Historical v1
data-only approval never authorizes v2. Preserve 8-MiB artifact/64-MiB extraction
work limits and existing four actual qualification EX1/source valid-EX0 rules.

## 5. Future-only financial gate

Committed [ledger](sql-pilot-budget.md) remains unchanged. Current Vyce has no
provider hard cap/complete charge proof/approved USD receipt collection.
Missing approved billing profile means ZERO network and credential reads.
Metadata GET is not asserted free. No current local model backend is assumed.

Billing profile canonical envelope is exactly
{format,schema_version,payload,sha256}, schema_version=1; payload:

```text
provider, endpoint='https://vyceai.com/v1/chat/completions', model,
valid_from, valid_until, authority_ref, evidence: tuple[SourcePin], charges,
settlement_mode='authoritative_receipt_only', authorization, receipt_directory
charge: {name, unit, rate_numerator_micros, rate_denominator,
         max_units_per_request}
authorization: {run_id, manifest_sha256, execution_profile_sha256,
                budget_directory, limit_usd_micros:50000000, request_limit:25}
```

Validity uses integer UTC seconds. Charges use bounded integers/positive
denominators; reserve SUM of per-class upward-rounded maxima. Complete external
authoritative evidence must cover fees/taxes/hidden reasoning/every billable
class and server caps. Self-digest/authority_ref is not certification.
External approval SHA binds the WHOLE canonical envelope.

Bind all CLI paths/manifest/execution-profile/run/ledger configuration exactly;
canonical absolute budget/receipt directories. Different directory/manifest
cannot clone another $50 authorization. init-budget creates only explicitly
approved local path; run opens existing ledger only, never creates/resets/replaces.

Receipt file: receipt_directory/sha256(request_id UTF-8).json, canonical version-1 envelope
payload exactly:

```text
run_id, request_id, model_request_sha256, model_response_sha256, currency='USD',
actual_charge_usd_micros, authority_ref, evidence
```

Charge is exact nonnegative int64, never float/decimal string/conversion.
Only externally reviewed authoritative receipts settle. Missing receipt retains
full reservation and STOPs; never call reservation maximum an actual charge.
This is a closed future workflow, not a claimed supported Vyce adapter/collector.
Trusted-storage deletion/rollback is outside ledger guarantees.

Order: validate current complete approval/profile/bounds/ledger → reserve →
durable claim → memory-only credential → one HTTPX attempt. TLS verification,
trust_env=False, no redirects/retries, response body≤8 MiB, deadline120s.
After claim, inspect actual request strings for credential collisions before
persisting request bytes or dispatching. Inspect bounded response JSON string
keys/values, including serialized nested JSON, without repr-based comparisons
before persistence. Retain raw-byte checks. Decode/work-limit uncertainty fails
closed without saving unsafe raw bytes. Malformed outer provider JSON/envelopes
stop the protocol, not an ordinary model-action failure; unsafe/undecodable raw
bodies need only hash-only rejection evidence, never credential-bearing artifacts.
Persist no auth header/raw key. Ambiguous delivery never replays. Unknown
charge/usage remains reserved. Implement no extra financial adapters or ledger
changes; unsupported current billing continues to fail closed.

## 6. Assets, controller and CLI

Planned `train/sql_pilot_assets.py` freezes:

```text
PilotAsset(case_id, partition:development|qualification|heldout, seed:int,
           task:SqlTask, ids:EpisodeIds, task_fingerprint, db_sha256)
PilotManifest(schema_version=1, run_id, assets:tuple[20], pair_first:tuple[8])
prepare_manifest(target:Path, *, output_dir:Path, run_id:str) -> PilotManifest
load_manifest(path) -> PilotManifest
validate_manifest(manifest) -> None
```

Independent random.Random(seed) construction creates each DB from scratch.
20 cases partition 8/4/8; unique IDs/fingerprints/DB SHAs, common validated scope/
provenance. Manifest fixes all questions/seeds/splits/hashes before requests;
pair-first B,L,L,B,B,L,L,B. Outputs/DBs/manifest live outside checkout.
prepare --manifest target must not exist; check/run only read existing manifest.

Supply each asset.db_sha256 to direct start_capture and to source,
qualification and approved-reuse SkillCase construction. Verify every normal,
rejected and exception-carried capture against the asset hash/fingerprint/IDs
before accepting it. Mismatch is admission/infrastructure failure, not a model
failure: preserve existing evidence, mark INCOMPLETE and never let the final
endpoint produce COMPLETE against replacement bytes.

CLI prepare/check/run require --manifest --execution-profile --output-dir.
init-budget adds approved financial arguments/paths. run additionally requires
--allow-execution AND --allow-model-requests, --billing-profile,
--billing-approval-sha256, --budget-dir. check is data-only, 0 daemon/provider/key
operations; runtime/provider status UNPROBED.

One identical submit tool across stages/arms; all fields required/no extras:
{kind,program,skill_id,promotion_sha256}. Program: nonempty program/other fields '';
approved_skill: program ''/exact frozen ID/external promotion pin.
Development/proposal postvalidation forces program with empty library.
Baseline library=[]; treatment one entry with exact
skill_id,promotion_sha256,scope,description,program. Fixed description:
"ROWCOUNT candidate qualified on four distinct databases; use only within its advertised scope."
Scope is validated routing, not universal correctness.
Approved selection routes actual reuse_promoted; unknown reference fails without
fallback/retry. Byte-identical direct programs stay direct; adaptations are not
approved reuse. Native run_program(code) is unchanged.

Exactly two messages: fixed system plus canonical user payload, no history.
temperature=0/top_p=1/n=1/max_tokens=2048/stream=False/
parallel_tool_calls=False/forced submit. Unsupported behavior is protocol STOP,
zero retry. Messages+tools≤131072 UTF-8 bytes, no truncation; not a billing bound.
Canonical native capture prompt is not actual API prompt: retain exact sent
request bytes/hash separately. Model alias is opaque/cache protocol unknown
until supported/frozen; do not invent cache economics.

≤8 development requests/one submission each; first independently rescored valid
EX0 source or legitimate STOP. Exactly one proposal receives only question/
schema/attempt/observation/sanitized valid-zero flag, never raw ExResult.detail/
gold/qualification/heldout. Freeze exact program, zero repairs. Four actual
distinct qualification EX1 or STOP. Endpoint 8 pairs, one request/submission/
arm, maximum25 total, zero retries, all failures retained/denominator8.
Report tokens/latency/invocation/accuracy; setup/ongoing overhead separately.
Dollars require actual receipts; amortization100/1000/10000/break-even only with
defensible positive net savings.

### 6.1 External promotion approval and one-shot continuation

Test this amendment before implementing it:

1. Missing/malformed/mismatched external approval or checkpoint permits zero
   endpoint requests, credential reads, HTTP calls, executions or approved reuse
   during continuation admission. Qualification alone permits zero held-out work.
2. Valid continuation repeats zero development requests, proposals, source
   grading or qualification executions.
3. Any changed artifact/IDs/manifest/execution profile/billing approval/run path/
   budget directory/ledger snapshot rejects before endpoint activity.
4. The checkpoint has exactly 2–9 settled requests, the actual development prefix
   plus one proposal; require 16 remaining request slots and enough remaining
   budget for sixteen maximum-charge reservations, with total requests at most 25.
5. Eight concurrent continuation processes obtain at most one durable endpoint
   claim. Repeated invocation or claimant death never permits another claimant.
6. Kill after endpoint claim or financial dispatch claim: restart replays zero
   requests, never resets the ledger, and retains unresolved reservations.
7. Keep all eight pairs and B,L,L,B,B,L,L,B order, including explicit UNRUN/
   INCOMPLETE outcomes after crashes. Verify real whole-file pins, not constants.

Split only at the qualification boundary, not a generalized resume facility.
`run` retains unused-ledger admission and exclusive `pilot-<run_id>` creation.
After four successful actual qualifications it persists source/candidate/
promotion/captures/request evidence and an AWAITING_PROMOTION_APPROVAL report,
with all endpoint pairs UNRUN. It must not author a promotion approval or
advertise a library. Fsync the report first; publish the checkpoint last.

Checkpoint envelope: format=sql_pilot_qualification_checkpoint, schema_version=1,
closed payload exactly:

```text
run_id, run_directory, manifest_sha256, execution_profile_sha256,
billing_approval_sha256, budget_directory, ledger_snapshot_sha256,
request_count, source_case_id, source_capture_sha256, candidate_sha256,
promotion_sha256, promotion_ids, artifacts
```

`artifacts` is sorted/unique `{path,sha256}` entries for planned/report files,
candidate/promotion, development/qualification captures and request/response/
telemetry evidence. Paths are run-relative regular files without traversal or
symlinks. Snapshot hash is SHA256 of existing canonical_bytes(asdict(snapshot)),
not a new ledger representation. Require active status, all requests settled and
exact expected history. Revalidate the source/candidate/promotion/four-qualified-
capture graph and current binding by data inspection, not execution.

Before endpoint claim, parse EVERY historical development response with existing
parse_response(..., library=[], program_only=True). A valid action requires its
corresponding capture with exactly one step and exact UTF-8 program equality to
capture.steps[0].action. Validate asset/runtime identity and receipt request
hashes. Require report failure_type/score/route equal
capture_result(actual, route="DIRECT"), and report telemetry equal persisted
request telemetry. Use terminal-aware validation: graded, program_rejected and
no-final aborted outcomes differ; infrastructure-aborted development cannot lead
to an eligible qualification checkpoint. ModelActionError requires
MODEL_ACTION_INVALID, null score/route and no capture file; ProtocolStop rejects
the checkpoint. Preserve the selected source's valid-zero/proposal checks and
proposal-to-candidate checks. This reconstructs semantic provenance with zero
execution/rescoring, not a new pin mechanism or external attestation claim.

Keep external sql_pilot_host_approval payload exactly
`{promotion_sha256,candidate_sha256,ids}`. Add required approval_sha256 to
ApprovedSkill and verify the externally supplied WHOLE-envelope hash before
existing checks. Approval file is outside the controller-owned run directory;
the controller reads it, never authors/overwrites it. Caller also supplies the
whole-checkpoint SHA. This is trusted-host approval, not PKI or pricing proof.

```text
continue_pilot(manifest, execution_profile, *, output_dir,
  checkpoint_path, checkpoint_sha256, promotion_approval_path,
  promotion_approval_sha256, billing_profile_path, approval_sha256,
  budget_dir, allow_execution=False, allow_model_requests=False)
```

CLI continue-endpoint requires existing run arguments/both consent flags, plus
--checkpoint, --checkpoint-sha256, --promotion-approval and
--promotion-approval-sha256. Derive the same existing run directory from the
original output parent; checkpoint must be its expected file. Create no new run.

Before API/executor construction: validate external pins/closed graph, same
current financial approval/canonical budget directory, exact checkpoint ledger
snapshot/capacity, and current execution sources. Then exclusively create/fsync
endpoint-claim.json, closed payload exactly
`{checkpoint_sha256,promotion_approval_sha256,ledger_snapshot_sha256,request_ids}`.
request_ids contains all sixteen deterministic endpoint IDs in frozen order.
Never delete/reset this claim; partial files block too. Crash consumes the one
continuation opportunity, not permission to resume uncertain endpoint work.
Use one exclusive endpoint/ directory and endpoint-report.json, preserving
phase-one evidence. Persist progress atomically after each outcome; original
planned pairs remain authoritative if a crash interrupts a progress write.
No ledger changes, approval callbacks, extra providers or extra model requests.

## 7. Implementation order and ownership

1. Persist this plan, then collected RED for shared pure records/codecs/signatures.
   Implement/freeze section2 contract before parallel tracks. No daemon access
   in this phase. All callers use these exact types, not alternate executors.
2. Three disjoint tracks, tests first:
   - Boundary: NEW ptc/sql_isolation.py, ptc/sql_worker.py,
     bench/sql_score_worker.py, ptc/test_sql_isolation.py and worker unit tests;
     NEW nondefault ptc/sql_isolation_acceptance.py.
   - Records: existing train/sql_capture.py, train/sql_skills.py,
     train/sql_skill_eval.py, train/test_sql_capture.py, train/test_sql_skills.py,
     train/test_sql_skill_eval.py; NEW nondefault
     train/sql_skill_isolation_acceptance.py. No legacy grader semantics changes.
   - Controller: NEW train/sql_skill_pilot.py, train/sql_pilot_api.py,
     train/sql_pilot_assets.py, train/test_sql_skill_pilot.py,
     train/test_sql_pilot_api.py, train/test_sql_pilot_assets.py. Ledger untouched.
3. Integrate concrete source closures/record bindings; no scratch imports/import
   substitutes. Narrow checks, then fresh real nondefault acceptance; recompute
   all actual production policy/source/binding hashes. Reference pins never
   authorize new production bytes.
4. Full offline regression/fault sensitivity, Python/general/security reviews,
   fix loop, then parent-owned reviewed local commit. No push.

## 8. Verification, provenance and non-goals

Run from `/Users/nikolassapalidis/Developer/co-train`, existing reviewed offline
harness/reference Python -B, observer/IP denial/cold caches:

```text
python -m pytest -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider ptc/sql_isolation_acceptance.py train/sql_skill_isolation_acceptance.py
```

These are future validation selections, not permission to run bare pytest now.
Explicit acceptance: zero skips/no automatic privileged probes. Audit source
fingerprints, owned PIDs, cache/network receipts; review actual outputs.

Reference root:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/kill409-spike-le2xr2tn`.
Final result SHA `02d0bffeebf3818db0a2a2417b5fe3359ef1af5163ceb1834107ec63e5e2f0d8`;
source readback `ab074d404406dd81b419d47c5086408bd2ae23d4c4aa4b74079b24c0e8814b26`.
Policy `297da200de06f3dd7b5294cc3b224716c7fd0da0ebfec0ae2195d134c27a6176`
is reference provenance, NOT new canonical production policy SHA.
[Frozen kill409.py](spikes/reference/sql-isolation/kill409.py) SHA
`83c44dea17cbcbeb2d759d288866014b6082cdf78c6c9dce9e8d4a81a8c4ee78`;
it binds the 65,627-byte [frozen README](spikes/reference/sql-isolation/README.md).
Never edit/append/slim/repin reference files. Preserve historical partial failures.
Security/Python spike reviews do not approve future production.

Non-goals: new probes/root commands, live inference, weights/dependencies/image
pulls, VM changes/unrelated jobs, training/BIRD-wide claims, native/default-arm/
scientific changes, global configuration, new financial adapters, ledger edits,
Git push/PR/deploy. The implementation passed focused source reviews and
independent offline regression, not production confinement acceptance. The
attempted nondefault native-pair check failed at fixture setup because the approved Docker socket
was absent, with no container created. No runtime/kernel or model result follows.

### 8.1 Independent offline verification, 2026-10-25

The default configured selection, with no trailing `.` or marker override,
passed **3,108 tests**, with **one existing optional Torch skip**, **two deliberate
tokenizer-integration deselections**, and **10 warnings**, in **1,055.54 seconds**.
All **2,447 historical node IDs** (2,446 passes plus the optional skip) were
retained; 662 nodes were added. The 106 committed budget cases appear once.
Runtime (133), records (684), and controller (233) are subsets, not additional
totals. No production Python source or pytest configuration changed during the
run. The protected scorer and committed budget implementation/tests/spec stayed
byte-identical.

Focused Python/general/security reviews closed the final saved-database and
development-response provenance findings with no new findings. These were source
reviews; they did not execute the kernel acceptance or authorize inference.

The independent launcher used OS-level external IPv4/IPv6 denial, inherited by
children, plus cold-cache/tokenizer/network audit guards. UNIX access was admitted
only for exact `fixture.sock` paths in the first-party test's registered,
same-UID-owned temporary roots. The run recorded zero external-network attempts,
zero cache accesses, zero tokenizer loads, 18 loopback events, and 20 owned UNIX
events. The fixture counted 12 accepted UNIX connections including its child.
All 133 runtime cases retained zero FD delta and zero new live threads; 47
recorded actor PIDs were independently absent afterward. The native process
observer recorded 188 observations with zero observer errors. This is owned
fixture evidence, not a general proof of child behavior or container confinement.

Seven negative launcher controls each failed for the intended denial, with a
positive owned-loopback control. A separate deliberate assertion failed inside
its test body, proving the launcher preserves a failing pytest exit. A focused
runtime/real-HTTPX-loopback selection passed 137 tests before the full run.
Earlier canary attempts that failed because of Darwin UNIX path length or
pytest traversing denied cold-cache metadata were retained and excluded from
valid sensitivity evidence.

The 10 warnings are CPython `DeprecationWarning`s from three controller process
tests using `os.fork()` after the pytest process became multithreaded. All three
tests passed with matched before/after FD identities and reaped actors, but this
does not eliminate the inherited-lock/deadlock risk. No warning was suppressed.

Evidence directory:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/production-independent-final-z8xbqjvl`.
`independent-validation.json` SHA256:
`084f7b8fac6330c4678305418d5c80dfcc02d5d91a65460b7f8c670e181140da`.
The receipt binds 132 Python/configuration files and retains node, audit,
resource, process, and proof-limit results; `full.log` and `full.xml` retain
the actual pytest outcome. Historical spike reference files remain unchanged.

At completion of this offline verification, production acceptance was blocked.
The approved `/Users/nikolassapalidis/.colima/default/docker.sock` was absent;
no real-container acceptance or restoration had yet been attempted. The later
bounded restoration and real checks are recorded in §8.2. Complete authoritative pricing/fees/billable maxima and supported
USD settlement receipts remain unavailable; no provider hard ceiling is
established. Zero live pilot/model inference requests were made. Offline success
does not establish fresh-task skill benefit, native weight training, kernel
confinement, or an external spending guarantee.

### 8.2 Approved real checks and current blockers, 2026-10-25

**PRODUCTION ACCEPTANCE PENDING / NO MODEL RESULTS.** The existing stopped default
Colima VM was started under host external-network denial, with context activation,
configuration saving and SSH-config generation disabled. Its saved configuration
hash and 2-CPU/2-GiB/disk allocation were unchanged. No restart, resize, new VM,
image pull, sudo or unrelated-container operation was requested.

Read-only preflight verified the existing pinned image, Docker 29.5.2/cgroup v2,
and ten unrelated containers (nine running, one exited). The first real run
exposed Docker normalizing requested `MemorySwappiness=0` to explicit `null`.
The source now permits only that present-null normalization with requested exact
integer zero and matching positive integer memory/total-swap caps. Missing,
invalid, unlimited or changed caps/configuration still reject; CREATE and all
resource limits remain unchanged. Test-first RED and four guard-mutant REDs were
retained. The 133 original runtime nodes plus 132 normalization nodes passed.

On that normalization-only source, the runtime/records/controller selection
passed **1,182 tests** in **865.98 seconds**, with three existing
`record_property`/JUnit-xunit2 compatibility warnings, zero external-network,
cache or tokenizer attempts, 12 loopback events and 20 registered fixture UNIX
events. This is an intermediate-source result, not a full-suite result for later
diagnostic additions. The §8.1 full regression remains bound to its original
source receipt.

The earlier diagnostic-stage source
`4d9a1dbca3efc880467957470bbacaebdaa2ea775edf293eb1083f6074b0c129`
passed **280 runtime tests** independently in **9.75 seconds**: all 265 prior
nodes plus 15 diagnostic cases, zero external/cache/tokenizer attempts, 67
registered UNIX events, and zero FD/new-live-thread deltas. Focused Python and
security reviews found no outstanding P1/P2 issue. Cause and field-shape
diagnostics are bounded and allowlisted; they exclude messages, locals, arbitrary
filenames, raw bodies, environment values and metadata values. Diagnostic I/O
does not replace the original failure. No observer guard or deadline was relaxed.

On that diagnostic source, the real native pair passed **2 tests in 3.26 seconds**: quoted
catalog/ROWCOUNT with all six native scorer fields, and actual print-then-native
rejection with zero scoring. The frozen acceptance-profile whole-file SHA256 is
`31ffde906f49c59d39c15c3f99616725284e9ce4f0e817eaf59c7ffcaddbcf84`.
These two checks do not establish all T04–T09 resource/adversarial gates.

The real isolated skill lifecycle **FAILED** before fresh-process reuse. An
in-flight stats response for the exact owned container contained a dictionary
`memory_stats` without `usage`. It was consumed after positive STOPPED proof;
the original stats-RPC completion timestamp was not captured, so this does not
prove the response was produced after STOPPED. Healthy CLI completion was
recorded. The strict observer correctly retained UNRESOLVED instead of using a
zero charge or returning a successful capture. No completed qualification,
promotion, fresh-process reuse or model-generated skill benefit is claimed.
No missing charge is replaced with zero or a fixed OWN reservation. The narrow
conditional terminal-discard test plan in §8.3 does not authorize a discard unless
all of its proof predicates pass.

All **14 created owned containers** were independently absent afterward;
**63 recorded actor PIDs** were absent. Ten ordinary jobs closed within their
original cleanup budgets. Four separately authorized late recoveries used fresh
complete ownership/stopped/actor checks and exact non-force deletion. Every
original failed journal, event, outcome, profile and request remained byte-identical,
with original deadlines and UNRESOLVED blocks retained. Linked closure records
release only the proven recovered reservations. Late recovery is explicitly
**not** retrospective production acceptance. The ten unrelated containers
remained unchanged.

Evidence root:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/production-real-acceptance-flx9gm02`.
`real-evidence-validation.json` SHA256:
`61b60bcc6fd8672281dddcab2f4ecad34b8b96ae0199b68ffbaf2184b251c1b7`.
Failed runs, one-shot claims, recovery receipts, native XML/logs and current
diagnostic validation are retained there. Separate normalization and diagnostic
RED/GREEN/mutant evidence remains under `normalization-fix-kz03jw2s` and
`diagnostic-fix-7lkczul7` in the same completion root.

Public-only research retrieved [official Vyce terms](https://vyceai.com/terms)
on 2026-10-25. Section 6 describes prepaid per-token billing at dashboard rates;
section 2 permits upstream routing changes. Neither establishes complete rates,
all billable maxima, a pending-inclusive $50 hard ceiling, or request-specific
settled USD receipts. Failure to locate public documentation is not proof that
documentation does not exist. `public-billing-evidence.json` records the findings
and limits. The approved pilot model remains `deepseek-v4-flash`, distinct from
the agent model. No account access, provider API probes, purchases or live pilot
inference occurred. The financial gate remains closed.

### 8.3 Strict conditional terminal observation: test-first addendum

This is a narrowly conditional observation rule, not a claim that the captured
failure satisfies it. Actual stats-RPC completion must be timestamped inside the
stats worker, immediately after the bounded daemon call returns; the later
consumer/rejection timestamp is insufficient. The original four-second complete
sample and twelve-second cleanup budgets remain unchanged.

**Test plan before implementation:**

| Named check | Numeric acceptance |
|---|---|
| Terminal OWN positive | Both roles: exactly one absent-usage observation discarded; zero new memory samples, tokens or replacement charges; JOIN_ACK before DELETE. |
| Shape and identity | Explicit null/bool/string/negative usage, absent/non-dict memory_stats, malformed/HTTP/JSON responses, foreign CID/job/nonce/config/guardian/token, changed caps and live/paused/restarting/nonzero-PID states: zero discards, JOIN_ACKs or successful outcomes. |
| Time and order | Last-valid age exactly 4.000s at STOPPED may qualify; 4.001s refuses. Proof age 4.001s and stats-RPC completion before STOPPED proof refuse. |
| Genuine failure priority | Any other failed stats future, VM/info error, timeout or earlier latched failure wins in both container-order permutations: zero discards/JOIN_ACK/DELETE/CLOSED. |
| Diagnostics and join | Failed diagnostic/discard writes, outstanding thread/future/CLI/HTTP aliases or expired original budget: zero successful discards/JOIN_ACK/DELETE/CLOSED. |
| Rejection timing evidence | Both roles, RPC completion before and after STOPPED: four cases retain worker-side completion and sample-start times in the bounded rejection event, including refusals. No response values or exception text. |
| Admission and sensitivity | Retired/pending-discard state permits zero STARTs. Bypassing CID, freshness, failure-priority or join predicates produces at least one intended assertion RED per gate. Retain all 280 prior runtime nodes and the real in-flight-error regression. |

**Selected private implementation:** distinguish only an actual dictionary
memory_stats with absent usage using a typed observation exception containing the
validated requested CID, sample bounds, stats-RPC completion and original cause.
Any supplied contradictory response identity rejects. Validate every other
stats result, VM/info consistency and known charges before raising the candidate;
any genuine error takes priority. Never emit a valid MEMORY_SAMPLE or calculate
replacement headroom from that candidate.

The existing final verified owned inspect in cleanup may mint an immutable
private proof bound to full CID, job, nonce, config digest, guardian and observer
token, with a monotonic STOPPED timestamp. It adds no daemon call. Only the
concrete observer retirement call receives this proof. Under its existing lock,
retirement captures the last eligible valid frame, installs proof/time and
invalidates every token. A missing-usage candidate can become pending only if
proof/retirement were already installed when handled; otherwise it remains a
failure. A genuine failure is first-failure-latched, never overwritten.

After all existing joins and durable actor proof, discard only if identities all
match, candidate spans retirement, stats RPC completed at/after STOPPED proof,
last eligible valid sample had reserve headroom and was at most four seconds old
at STOPPED, proof is at most four seconds old now, all aliases are absent and the
original cleanup deadline remains unexpired. Emit one bounded
MEMORY_TERMINAL_DISCARDED before existing JOIN_ACK. Diagnostic failure or any
predicate failure retains the original UNRESOLVED path. Existing guardian
failure/uncertain outcomes are never cleared. Retired/pending state cannot
authorize execution or admission.

**Non-goals:** zero/fixed-cap charge substitution, relaxed RAW accounting,
general observer-error suppression, retries/recovery API, extra daemon calls,
new resource limits or runtime changes. No quantitative upper bound on OWN RAW
charge overshoot has been established; a fixed cap/reserve substitution is not
accepted as conservative. This conditional rule may still refuse the captured
case if the actual response completed before STOPPED. A real acceptance claim
requires fresh passing native and record-lifecycle evidence on the new source.

### 8.4 Terminal-proof verification

The §8.3 implementation received focused Python and security reviews with no
actionable findings. Both were static reviews, not runtime acceptance.
Current source SHA-256 pins:

- `ptc/sql_isolation.py`: `4f382b45d2c96ccd540329bbcbd6a82b1336982136ee6d588c3956e40187d602`
- `ptc/test_sql_isolation.py`: `5949730ff26ce1c55bc5c6ea8326f16bb50677b609e21b34c370c233e32aa4bc`

Main independently ran all 428 runtime cases: 428 passed, with zero FD/thread
deltas, external-network attempts, cold-cache accesses or tokenizer loads.
All 424 worker-delivered nodes remain; four added cases first failed for absent
timing evidence, then passed. Rejection events now preserve sample start and
worker-side RPC completion even when terminal discard is refused; unsuccessful
RPCs record no completion time. The closed-field diagnostic assertion was
extended, not relaxed to arbitrary fields or response values.

Independent gate mutants produced intended assertion failures: CID 2,
freshness 4, genuine-failure priority 4, join 6, RPC-before-STOPPED 2. Seven
offline guard canaries refused their forbidden operation; owned loopback passed.
The full offline regression passed **3,403 tests**, including the 428 runtime
cases, with one unchanged optional Torch skip and two deliberate tokenizer
deselections. All 2,447 historical nodes and all 3,109 prior implementation
nodes remain selected without duplicates. The fresh 132-file source snapshot
remained unchanged. Its harness is byte-identical to the reviewed earlier
harness, with current-source pins and fresh output paths.

Independent result validation found zero errors: all 428 runtime FD/thread
deltas were zero; 47 recorded actors were absent; 188 native process
observations had zero errors. External-network, cache and tokenizer audit
counts were zero (18 loopback and 1,175 owned-UNIX events allowed). Protected
budget/scorer hashes remain unchanged. Ten existing multithreaded-fork
DeprecationWarnings remain; inherited-lock risk has not been eliminated.
The 60-second faulthandler diagnostic during a long nested mutation-baseline
test was retained; that test subsequently passed. Full pytest time was
1,203.49 seconds, not an acceptance or cleanup deadline measurement.

Evidence:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/terminal-independent-FiZOcW0x/`
contains `runtime-independent-validation.json`, runtime XML/logs, the timing
test-first RED, mutation/guard results and completed full-run artifacts.
`independent-validation.json` SHA-256:
`694a885b151c6f606ecf3f831b73bcb8a35273e27f22cdb4621206a5c2db9be3`.
The worker's separate 424-case stage remains under `terminal-proof-snf57oy_`.

At completion of this offline verification, no real daemon trial had run on
these source pins. The earlier final one-shot claim was consumed, not replayed.
Section 8.5 records a subsequently authorized trial with fresh bindings.
The captured historical RPC completion remains unknown; this conditional rule
may correctly refuse it. Full kernel acceptance, fresh-process skill reuse and
live model benefit remain unproven. The financial gate remains closed.

### 8.5 Newly authorized terminal-proof trial, 2026-10-25

The user explicitly authorized one new native-pair plus record-lifecycle trial,
at most 19 owned jobs, using only the existing pinned image and running Colima.
No retries, inference, downloads, VM or unrelated-container changes were allowed;
late recovery required separate approval. Fresh read-only preflight verified
the ten-container baseline, no active reservation/unclosed block, local pinned
image and two healthy memory samples (0.138/0.106 seconds). Saved Colima
configuration and runtime source pins were unchanged.

The exclusive claim binds runtime commit
`37a519501e1c1d7f8dc0f4928135b97c75d78c1b` and fresh execution-profile whole SHA-256
`17c1fd25226768f73339d57036c272b6d3c05f83b6d62701a7c10e2bb803425e`.
The native pair **passed two tests in 4.49 seconds**, with three ordinary CLOSED
jobs. Independent checks verified matching shared-history closure hashes,
original cleanup deadlines, typed container absence and unchanged baseline.
A validation-only assumption was corrected: CLOSED is a shared-history record,
not a job event, and the start-intent event is START_ATTEMPT. No acceptance
test was rerun.

The single real record-lifecycle attempt **failed in 0.86 seconds**, on its first
PROGRAM, before source scoring, qualification, promotion or fresh-process reuse.
Its exact owned missing-usage response completed at `36442.182172`, before
positive STOPPED proof at `36442.186967916`, a **4.795916-ms** gap. Rejection was
consumed later, at `36442.257090583`. These are monotonic clock values.
Unlike the earlier diagnostic-only case, worker-side timing is now recorded.
The §8.3 discard correctly refused this pre-STOPPED response; it did not repair
this observed cleanup race. No replacement charge, success receipt, JOIN_ACK,
DELETE or retrospective acceptance was fabricated.

Four owned jobs were created, not 19: three closed normally; the record PROGRAM
retained its original UNRESOLVED failure. After separate explicit user approval,
one exact stopped-owned non-force late removal completed with fresh ownership,
strict exited/PID-zero and actor proof, a new exclusive twelve-second claim,
typed absence and matching reservation release. The scoped recovery procedure
received a focused security review with no findings; 12 negative/two positive
controls passed and stopped-state/proof-target mutants failed as intended.
Proof writes used a recovery-root copy of the actor manifest.

Independent final verification: **all four owned CIDs absent, all 18 recorded
actors absent, ten unrelated containers unchanged**, no active reservation or
unclosed block. All five original failed-job artifacts, original deadline and
UNRESOLVED journal/block remained unchanged. Only a separate linked late-closure
record released the matching reservation. Recovery used one exact non-force
DELETE, zero START/KILL, and is not production acceptance.

Evidence root:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/terminal-real-acceptance-hmpp3s96/`.
`trial-final-validation.json` SHA-256:
`4d32f539a0e49a01eab48669cb31276de7cb8fdd7a40287c05ba6b1d5b621abc`.
The separate late-recovery receipt SHA-256:
`c1ffd170dc8e93657a8ddab90df78e7f3d29111f16258309c9ed62bcd9c10aa6`.
Claims, preflight, native XML/logs, record failure, captured timing and original
artifact pins remain retained. Parent record-audit counters do not cover the
fresh child interpreter; OS external-IP denial was inherited by children.

The newly authorized trial and exact late cleanup are consumed. No retry or
further trial is authorized. Production record reuse, full kernel acceptance
and model-generated benefit remain unproven; live inference remains financially
blocked, with zero provider/model requests.

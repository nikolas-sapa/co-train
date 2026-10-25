# SQL skill pilot: frozen implementation plan

PLAN FROZEN / IMPLEMENTATION PENDING / NO MODEL/PILOT RESULTS.
Live inference is FINANCIALLY BLOCKED. This document authorizes no calls, probes,
downloads or production-acceptance claim. [Protocol](sql-skill-pilot.md) governs
the 20-case ROWCOUNT experiment. All new paths/APIs below are planned, not exports.

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
| T07 lifecycle | Guardian journal/ACK precedes CREATE; single-fault/lost-create/start/inherited-FD controls clean owned resources. Actual SIGKILL409 transition plus 9 strict negatives: 0 STARTs for unknown/stale/retired/foreign states. Join ACK precedes REMOVE. |
| T08 binding/admission | Wrong image/config/platform/source/profile each yields 0 START. Missing/stale/>4s/lower-headroom samples refuse. Cross-process/profiles/run-directories overlap=0; unresolved history prevents next admission. |
| T09 DB/wire | Original mutation or any WAL/SHM/journal sidecar rejects without deletion. Hostile prefix/frame/digest/role/request/bootstrap/UTF-8/overflow inputs fail closed. Whole output envelope, READY and bootstrap count toward caps. |
| T10 isolated records | V2 host-score calls=0; rescore PROGRAM launches=0. Typed abort keeps unscored evidence; exact v1 defaults/bytes unchanged. Four actual qualification successes; fresh-process reuse on 2 fresh DBs after historical DB removal. |
| T11 controller/leakage | Manifest 20 distinct cases: 8/4/8, 0 cross-partition IDs/fingerprints/DB hashes. All 8 pairs retained. Payload gold/credential/qualification/held-out canaries=0 where prohibited; raw ExResult.detail absent from proposal. |
| T12 action/request | Both arms expose exactly 1 identical submit schema/all 4 required fields. Direct bytes never count as approved reuse; unknown selection has 0 fallback/retry. Exactly 2 messages/request; maximum 25 requests, output request 2,048 tokens. |
| T13 money/transport | Missing/incomplete profile or approval: 0 HTTP/0 credential reads. One durable claim/one attempt, 0 retries; ambiguous delivery/usage holds full reservation across restart. Receipt-field/hash/currency/charge mismatches never settle. Committed ledger remains unchanged. |
| T14 sensitivity | Bypass each binding/confinement/routing/rescore/qualification/approval/budget/sanitization guard separately: ≥1 intended assertion RED per bypass, never stale-binding/import/infrastructure failure. |

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
               receipt: RuntimeReceipt|None)
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

Outcomes have exactly one success/abort branch. SecurityPolicy is the closed,
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
age≤4000ms, live controller and healthy observer before START. Start original
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

## 4. Existing capture/promotion integration

Add keyword-only executor=None to start_capture/rescore_capture/
evaluate_candidate/promote_candidate/reuse_promoted. Propagate through
_instrument/_bind/_current_binding/_admit_origin/_execute/session.
V2 step calls PROGRAM only; finish calls SCORER only; rescore calls SCORER with
zero PROGRAM replay. V1 None retains exact trusted-host behavior.

SqlCapture adds execution_binding=None, runtime_receipts=(),
execution_abort=None. V1 encoding omits these keys and requires empty defaults.
V2 requires its closed fieldset/version-aware size admission.
execution_aborted has result=None/typed AbortInfo, retaining final/extracted SQL
when available. finish returns capture; failed step/rescore raises
CaptureExecutionAborted carrying frozen unscored capture. Resource/infra aborts
are not fabricated EX0/invalid-gold outcomes; endpoint abort means INCOMPLETE.

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
Git push/PR/deploy. No production implementation or new runtime validation was run here.

# Disposable SQL isolation spike

**256-MiB feasibility PASS, not production implementation or pilot evidence.**
2026-10-24, repository source `feebc447085525743f0088f5182f1e148ba5a074`.
Owner-amended draft read before resuming:
`7d8cb5e79ff6707eb1d81064ee2940c66358ee5a335a37542d849ed12ed4adff`.
Original 1-GiB proposal was blocked before execution. **No 1-GiB stress proved.**

## PROVES: measured execution

Actual `run_ptc_program` / `sql_catalog` in PROGRAM, native SQLite, no mocks,
provider imports, TaskView construction, host SQL broker, or model inference.
Catalog names: `execute_sql`, `join`. A program discovers the sole user table,
quotes each identifier double quote, queries it, and prints:

```text
3
FINAL_SQL:SELECT COUNT(*) AS n FROM "odd ""quoted table"
```

SCORER is a different fresh container. Normal package imports are preserved,
including `bench/__init__.py`; no namespace replacement or explicit-file bypass.
Unchanged `bench.score.execution_accuracy` executes gold/prediction, fetches,
normalizes and compares. Only its complete six-field `ExResult` JSON is returned,
no rows. Three tiny trusted host references exactly match:

| Fixture | Existing result |
|---|---|
| Correct count | `score=1.0, status=match, valid=true`, 1/1 result rows |
| Wrong prediction (`SELECT 4`) | `0.0, mismatch, true`, 1/1 result rows |
| Missing gold table | `0.0, gold_error, false`, 0/0 result rows |

Only these fixed benign fixtures were scored on host. Hostile SQL ran only inside
SCORER. Default 500,000-row ceiling and 30-second cooperative query limit unchanged.

## Image and effective policy

Official `docker.io/library/python`, native `linux/arm64`:

```text
manifest sha256:c3729439afc4ec3f3e159e0c86aeabfadac8030ef46838a0256383d0511c5f5e
config   sha256:81c0aac584c3e136c75a8da272f5d08e45e1f2ae00701fbce768f490dd22164b
seccomp  7db0790356ebe3372b8032958d9f77cba5599dd70929ff836f107085982ddb55
```

Compressed layers 44,921,692 + config 5,699 = **44,927,391 bytes**, checked before
the single digest-only pull. This is content size, not measured network overhead.
Installed manifest/platform and exported local config bytes/hash verified.
Docker 29 containerd image ID equals manifest digest, not config digest.
Official Dockerfile has no entrypoint/OnBuild, CMD `python3`; entrypoint overridden
to absolute Python. Docker-library maintainers Tianon Gravi/Joseph Ferguson;
Dockerfile MIT, Python PSF and Debian component licenses separate, not a full
license audit. Sources: [official image catalog](https://github.com/docker-library/official-images/blob/master/library/python),
[Dockerfile](https://github.com/docker-library/python/blob/2a3b794c223ab067d122719541cdd54a068732a5/3.12/slim-bookworm/Dockerfile),
[licenses](https://github.com/docker-library/docs/blob/master/python/README.md#license).

Fixed local UNIX endpoint `/Users/nikolassapalidis/.colima/default/docker.sock`;
Docker 29.5.2, runc 1.3.5, kernel 6.8.0-117-generic, cgroup v2.
Create/start API never implicitly pulls. No Docker CLI/global credentials used.

Both base compartments: UID/GID 65534, PID 1, private PID/IPC/cgroup namespaces,
network none, readonly root, capabilities dropped ALL, no-new-privileges,
default-DENY arm64 seccomp allowlist, pids=1, memory.max=268435456,
memory.swap.max=0. Actual effective capabilities zero/NoNewPrivs=1/Seccomp=2
observed. `/tmp` 16 MiB, noexec/nosuid/nodev; log driver none; incrementally
bounded pipes. PROGRAM stdout 1 MiB, stderr 64 KiB, UTF-8 program 65,536 bytes.
SCORER stdout/stderr 64 KiB each. PROGRAM mounts only staged runtime + selected
DB, both RO (synthetic canary mounts appear only in explicit security controls).
No repo, gold, credentials, captures, or Docker socket in PROGRAM.

Each launch takes a shared host `flock`, retained by its independent session
watchdog through cleanup. Admission freshly requires
`min(MemAvailable, VM total − sum(raw container charges)) >= 469762048`.
Missing/older-than-4-second observations refuse. Colima default-profile SSH reads
only `/proc/meminfo`, parsing numeric MemAvailable, through sanitized subprocess
environment. Watchdog samples the same metric, fails closed on observation
failure/staleness, kills only its ID after exact UUID-label verification below
192 MiB reserve. Minimum admission observed **579,645,440**; minimum monitored
headroom **437,882,880**; maximum monitor sample time **0.340s**.

## Numeric receipts and sensitivity

| Actual probe | Outcome |
|---|---|
| AST-bypassing host-canary read | ENOENT; explicitly mounted synthetic read control succeeds |
| Root write / RO canary write | EROFS; synthetic RW control succeeds, writes identical original bytes |
| Socket / fork / subprocess | EPERM; socket-only allow control succeeds, network remains none |
| Fork control | Child succeeds only with clone/wait4 **and** pids=2, immediately reaped |
| SQLite ATTACH / DELETE | Real authorizer/read-only rejection; original DB/canary hashes unchanged |
| Touched allocation targeting 288 MiB | cgroup OOMKilled, exit 137; 1.575s actual process, 1.936s controller elapsed |
| 96-MiB allocation at 64/128-MiB caps | OOM at 64; fully touched 96 succeeds at 128, never uncapped |
| Program / stdout / stderr exact +1 | 65,536/1,048,576/65,536 accepted; +1 rejected, not accepted truncated SQL |
| Blocking C-level sleep | Actual process 9.977s, cleanup/controller 10.135s, within 12s |
| Reserve watchdog control | Fresh real metric below deliberately raised 3-GiB threshold kills only owned sleeper in 0.317s; no VM pressure induced |
| Live-ready controller SIGINT/SIGKILL | Cleanup 0.164s/0.128s after signal; controller/watchdog absent; subsequent benign success |
| SCORER giant 300-MiB cell / 256-column result | Actual OOM, 1.107s / 0.952s controller elapsed |
| SCORER 500k-row comparison | OOM **after real `rows_match` entry**, 2.773s; not merely fetch failure |
| Infinite recursive SQL | Whole-score watchdog abort, actual process 29.946s, controller/cleanup 30.196s |
| SCORER envelope / scratch | 65,536 accepted, +1 rejected; 16-MiB tmpfs ENOSPC |

OOM requests use real touched pages; kernel kills before the requested over-limit
allocation can complete. All OOM/deadline/overflow outcomes are experimental
resource ABORTs, never fabricated EX=0. Recovery runs return correct results.
Two concurrent controller processes were serialized; audited launch intervals
have zero overlap. 44 initial owned cases cleaned, including failed bootstrap;
10 unrelated container IDs/states unchanged. Reference replay adds two owned cases
(PROGRAM 0.413s, SCORER 0.361s); final audit: **46 owned IDs/watchdogs absent**.

## Actual source closure

Full per-file SHA-256 receipts: `source-hashes.json` in scratch.
Canonical sorted compact manifest SHA-256:
`296135e2c7cb7eabd82e00766713aad1f3d27f66cea480a2bf4f74ec08184d80`.
Every staged byte rechecked against current repository source.

- PROGRAM: `ptc/{__init__,runtime,sql_arms,sql_runtime,sqlite_safety}.py`.
- SCORER: `bench/{__init__,task,score,loader,shapes,suite}.py` and
  `ptc/{__init__,runtime,sqlite_safety,paired,metrics}.py`.
- Real import diagnostics confirmed these five/eleven project modules;
  remaining imports are image stdlib/native SQLite.
- Protected scorer SHA-256:
  `e55a4e6027cce31208881965d222a5e10636dda69a94b0a3c43c0768b2de703c`.

## SHORTCUT / MISSING: not production-ready

Preserved prototypes/receipts:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/isolation-spike-256-nqg8aj6a/`.
`spike.py` replays using hash-pinned `lab.py`/`core.py` there; deliberately
nonportable. Source bundles, DBs, logs and binary outputs remain outside repo.
Main evidence: `audit.json`, `parity.json`, `scorer-stress.json`, `interrupts.json`,
`source-hashes.json`, `pull.jsonl`, and each `cases/*/` admission/create/inspection/
watchdog/result receipt.

First failures retained: old config-ID assumption after pull; first bootstrap
failed binding its namespace before Python. Source-reviewed runc pathrs support
added only openat2/statfs/fstatfs; next bootstrap succeeded. Exact missing syscall
was not individually isolated. No permissive seccomp fallback. First reference
driver import typo also retained in `reference-first-error.log`; corrected
`record` import to its real `core` module, then replay passed.

**execve remains allowed for OCI bootstrap**, image contains shell binaries.
Re-exec is not prohibited; fork/clone/subprocess creation is. This requires
security review, not a broader “no executable can run” claim. PTC's internal
print accumulator is not streaming; container memory still bounds it.
No durable crash-safe pre-create/watchdog-registration transaction; only
already-running interruption coverage. No hostile/malformed codec, wrong-pin/
source mutation, watchdog-death, inherited-FD, PID-reuse, or exhaustive syscall
escape coverage. Strict six-field actual output is proved, not a production
hostile-input decoder. Reserve test exercises a real observer with a raised
threshold, not genuine VM exhaustion; concurrent unrelated allocations can still
race sampling. No production executor/capture schema/API, full suite, pilot,
inference, billing validation, API-key read, or Vyce call. Architect/security
review and a new spec/implementation plan remain mandatory.

## Lifecycle/surface/re-exec extension: test plan (before prototype)

One bounded follow-up, not a production executor. Preserve all prior receipts,
helpers and `spike.py`. No new image/dependency/provider calls or repeated OOM/
scorer-stress campaign. New scratch uses `lifecycle-spike-*`.

1. **Guardian-first ownership:** durable nonce/name/labels/deadline reservation
   before create, independent guardian ACK before any Docker create/start.
   Guardian alone creates, records full CID and starts; 0 duplicate creates/starts.
2. **Single-fault lifecycle:** controlled readiness events gate controller death
   before create, real create with response withheld, after create/before start,
   real start with ACK withheld, and during run. Guardian SIGKILL while controller
   lives must trigger controller reconciliation. Each daemon-available case:
   0 owned running/stopped objects and guardian processes within 12s, 0 overlaps,
   unrelated IDs/states unchanged, then a benign PROGRAM and SCORER succeed.
3. **Unresolved reservation:** inject owned-only inspect/delete failures, never
   global daemon failure. Durable unresolved state must deny 1 next admission;
   only explicit positive owned absence reconciliation releases it. Do not claim
   cleanup guaranteed when daemon access is unavailable or both supervisors die.
4. **Liveness identity/FDs:** EOF on dedicated inherited controller pipe, not PID
   existence. Keep a separate unrelated live canary process after controller
   death; it must not mask EOF. A real bounded host CLI child must also remain
   alive while guardian observes EOF and cleans within 12s. Enumerate both-role
   guest descriptors/environment: 0 host-file/env canaries/control sockets or
   controller liveness descriptors. Explicitly reap the owned host child.
5. **Writable surfaces:** retain `/tmp=16777216`, explicitly set
   `/dev/shm=1048576`. Probe UID-65534 access and effective mount properties for
   root, source, DB, `/tmp`, `/dev`, `/dev/shm`, `/dev/mqueue`, `/proc`, `/sys`,
   generated `/etc` files and descriptors. Fill tmp/shm separately using <=16-KiB
   writes: ENOSPC at <=16 MiB/1 MiB. Report >=17 MiB ordinary scratch, not 16 MiB
   total. Stop on a newly discovered unbounded writable kernel interface.
6. **Confined re-exec:** AST-bypassing `/bin/sh` -> exec Python preserves PID 1,
   UID/GID 65534, memory.max=268435456, swap=0, pids=1, caps=0, NNP/seccomp,
   private namespaces/network-none/root-RO. Socket/fork remain EPERM. Real
   external 10s deadline/1-MiB +1 overflow still abort. Re-exec is allowed, not
   shell-free. All source/DB/canary hashes unchanged.

Every launch retains fresh >=469762048-byte admission, one-compartment
reservation, <=4s sample freshness and continuous 192-MiB reserve monitoring.
All ordinary faults use real owned daemon objects; a private UNIX test transport
may withhold actual responses. Missing/low memory stops, never changes other jobs.

## Extension results: PARTIAL, BLOCKED on `/dev/mqueue`

Prototype evidence:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/lifecycle-spike-24d8d7b6/`.
`lifecycle.py` validates pinned source/receipts only, launches nothing.
Prior `spike.py`, helpers, bundles and first errors remain unchanged.

**PROVES: guardian-first single-fault lifecycle, not production durability.**
Serialized `flock` plus fsynced nonce/name/config/labels/deadline journal and
durable active reservation precede guardian launch. Independent session guardian
ACK precedes Docker create; guardian alone submits create/start once, records
full CID, and reconciles by exact name + nonce/labels/config. Dedicated pipe EOF
replaces PID-existence liveness. Controller watches its actual guardian `Popen`;
guardian SIGKILL triggers controller-owned reconciliation, no replacement.

| Actual event-gated fault | Cleanup after trigger |
|---|---:|
| Controller killed before any create | 0.079s |
| Actual created object, response withheld from caller | 0.135s |
| Created/CID journaled, before start | 0.174s |
| Actual start succeeded, ACK withheld | 0.224s |
| Running payload emitted readiness, controller killed | 0.096s |
| Running guardian SIGKILL, controller survives | 0.580s |
| Unrelated live process cannot mask controller EOF | 0.106s |
| Real `/bin/sleep` CLI child stays alive across controller death | 0.100s |

Lost-response controls consume real daemon responses in an owned test transport,
then withhold them from the operation caller; actual object/state independently
inspected before controller kill. Not a globally broken daemon or a fake create.
Each fault recovered, then fresh PROGRAM + SCORER succeeded. Injected owned-only
inspect/remove failures each preserved **UNRESOLVED** state and denied a next
launch before explicit emergency reconciliation established absence (0.182s/
0.145s total control timings). These are intentional infra aborts, not automatic
cleanup successes. No daemon/VM outage was induced.

Liveness test retains an unrelated live direct-child canary, demonstrating that
its live PID cannot satisfy the pipe identity. This is **not actual kernel PID
reuse**. A controller-spawned `/bin/sleep` remained alive after EOF cleanup, then
was explicitly terminated and disappeared. `close_fds=True`/restricted pass-fds
prevent retaining the controller write end. No mass forking.

**BLOCKED: effective writable/kernel surface is not fully bounded.**
Real PROGRAM UID 65534 inventory found:

- `/tmp` ENOSPC at exactly 16,777,216 bytes; explicit 1,048,576-byte `/dev/shm`
  ENOSPC, using 16-KiB writes. At least **17 MiB**, not “16 MiB total scratch.”
- `/dev` remains root-owned 0755 on Docker's 64-MiB tmpfs; UID cannot create
  ordinary files there. Device nodes/PTY and several `/proc/self` controls are
  write-openable, not ordinary scratch; no process-control contents were mutated.
- Root/source/DB/sys/cgroup/generated `/etc` file writes denied; mount properties
  and actual open/create errno receipts retained.
- **`/dev/mqueue` permits `openat(O_CREAT)` entry creation** (probe removed its
  own entry), while libc `mq_open` gets EPERM. Denying `mq_open` does not cover
  that alternate path. Queue count/byte/kernel-accounting bounds were not
  verified or bound in this profile. Stopped rather than assert a safe total
  writable budget or silently remount/mask the path.

PROGRAM descriptors were only 0=`/dev/null`, 1/2=pipes: no host canary FD,
controller pipe, Docker/control socket. Synthetic host-env canary absent.
First exact environment assertion failed: Docker adds `HOME`/`HOSTNAME` to the
five public image/config variables. Kept the assertion and first-failure receipt,
did not widen it until green. SCORER descriptor/surface inventory and confined
re-exec tests **NOT RUN** after the blocker. Re-exec remains allowed by policy;
this extension supplies no execution proof of its retained bounds.

**Follow-up proposal, not applied:** owner/architect select an explicit read-only
or masked `/dev/mqueue` policy (and review write-openable pseudo/dev controls);
explicitly bind Docker-generated environment or set deterministic approved
values. Then authorize only remaining surface/FD and re-exec probes.

Final audit: 33 jobs, **32 actual owned CIDs absent**, all 66 controller/guardian
PIDs absent, 10 unrelated IDs/states unchanged, 0 overlapping reservations,
active reservation absent. Minimum fresh admission 658,944,000 bytes; monitored
headroom minimum 658,554,880. All source/DB/canary hashes unchanged. No pulls,
registry/network/provider calls, inference, spending or production edits.

New concrete policy receipt SHA-256:
`70daca97ff5306ac0dbf512a4461e412ed3df32e7fdb8cb48673e5466c97fac9`.
Underlying seccomp and project source manifest unchanged. `lifecycle.py` pins
new guardian/controller/lifecycle/driver/test/decoder source hashes explicitly.
Full per-job create configs, admission, streams, fsynced journals, transport proof
and events are in `jobs/*`; aggregate `audit.json`, `fault-receipts.json`,
`surface-first-failure.json`, `surface-blocker.json` preserve partial outcomes.

**MISSING:** real daemon-unavailability cleanup is not guaranteed. Durable
unresolved reservation prevents further admission until positive reconciliation;
simultaneous loss of both trusted supervisors is outside this single-fault
spike. No production restart/reboot/crash-consistency, hostile codec, or complete
v2 binding acceptance. Do not freeze production from this partial result.

## Approved confinement continuation: tests before new prototype

Preserve every prior prototype/receipt and both old reference scripts. New copies
only in `confinement-spike-*`. One installed digest, no pulls or new dependencies.

1. **Effective policy:** preserve reviewed Docker default ReadonlyPaths/MaskedPaths,
   union `/dev/mqueue` into ReadonlyPaths. Both roles must show every visible
   mqueue mount RO and actual entry creation EROFS/EACCES. Exactly seven approved
   public environment keys/values: pinned image five (fixed PATH/LANG overrides),
   HOME=/nonexistent, HOSTNAME=co-train-isolation; Config.Hostname matches.
   Both-role descriptors contain only approved stdio, zero host/control/canary FDs.
   Both roles: 16-MiB tmp + 1-MiB shm ENOSPC with <=16-KiB writes; retain “at least
   17 MiB ordinary scratch,” not an exclusive total kernel-memory claim.
2. **Sensitivity:** one owned negative-control container removes ONLY the new
   mqueue readonly path. Guest creates/unlinks exactly one entry; the intended
   DENIAL assertion must fail after actual execution. No queue filling.
3. **Before-start gate:** after all create/inspect/attach work, check controller
   pipe, original unreset deadline, reserve observer, and a new qualifying memory
   sample (age <=4s) immediately before START. Actual create-response withholding
   >4s must yield remeasurement before start; controller EOF and original deadline
   expiry must each produce exactly zero starts and positive owned absence.
4. **Critical lifecycle regression:** event-gated controller EOF/create-response
   loss/guardian SIGKILL under stricter config: owned cleanup <=12s, no duplicate
   create/start, subsequent normal PROGRAM + unchanged full SCORER succeed.
5. **Allowed confined re-exec:** actual Python -> `/bin/sh` -> exec Python keeps
   PID 1, UID/GID 65534, caps=0, NNP/seccomp, private namespace identities,
   root RO, memory.max=268435456, swap=0, pids=1. Socket/fork EPERM. After re-exec,
   PROGRAM external deadline <=10s (cleanup <=12s); PROGRAM stdout 1 MiB +1,
   SCORER stdout 64 KiB +1, stderr 64 KiB +1 each reject. Next benign role pair
   succeeds. No shell-free claim, no inference or hostile host execution.
6. **Final audit:** all owned objects/supervisors absent, unrelated ten IDs/states
   unchanged, 0 overlaps, unknown cleanup retains durable reservation. Every launch
   has fresh >=469762048 admission and 192-MiB reserve monitoring. Single-fault/
   daemon-available claims only, no continuous-headroom or reboot guarantees.

Continuation observer correction, before its code: keep first errors. The initial
dual-snapshot path rejected one real stale sample; a following initial-admission
request timed out (0 creates, 0 starts). Single observer supplies post-attach
measurements. Overlap only independent VM meminfo/info/container-list reads,
then unchanged per-container RAW stats. No retry or larger timeout; a complete
measurement still must finish and qualify within 4 seconds. One diagnostic
snapshot must qualify before further launches, otherwise stop as infrastructure
BLOCKED. Preserve both failed job directories. Resolve mqueue mount visibility
using kernel fdinfo mount ID, retaining hidden lower `rw` and resolved top `ro`
records; actual create denial is separately required.

### Continuation outcome: BLOCKED_MEMORY_METADATA_TRANSPORT

Scratch: `/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/confinement-spike-8gaeoa1e/`.
`confinement.py` verifies the preserved partial evidence offline, deliberately exits
2 (BLOCKED), and performs no launch. **Do not freeze architecture from this run.**

- **PASS:** effective Env/Hostname and ownership binding verified in actual
  PROGRAM and SCORER inspections. Exactly seven public variables; five baseline
  readonly paths + `/dev/mqueue`, all twelve baseline masks retained.
- **PASS, PROGRAM only:** UID/GID 65534, PID 1, three stdio FDs, synthetic host
  environment/FD absent. Resolved mqueue mount 757 is RO; lower mount 875 is
  hidden, not discarded from receipt. Create returns EROFS (30). `/dev`
  mode 0755 rejects creation EACCES (13). Tmp/shm hit ENOSPC (28) at exactly
  16,777,216 / 1,048,576 bytes using 16,384-byte writes. At least 17 MiB ordinary
  scratch, not a total-memory or shell-free claim. SCORER inventory **BLOCKED**.
- **PASS:** negative control differs only by removal of mqueue readonly path
  (plus nonce/config binding). Exactly one actual owned entry created/unlinked;
  intended denial assertion red after execution, strict-profile assertion green.
- **PASS:** next actual PTC output 59 bytes, unchanged whole SCORER output
  88 bytes, exact complete six-field ExResult match. Not a post-reexec proof.
- **BLOCKED:** delayed-create freshness/EOF/original-deadline harness never run.
  Six earlier starts had qualifying post-attach sample ages <=0.882168s, but
  this does not prove delayed-start races. One stale prestart sample rejected
  after one create and zero starts; next initial timeout had zero creates/starts.
  Single-observer revision then failed its sole diagnostic while waiting for
  Docker GET `/containers/json` response status (unchanged 3s API timeout).
  No subsequent launches. Freshness ceiling remains 4s, no automatic retry.
- **BLOCKED:** critical fault regressions, new-config unresolved-reservation
  injection, reexec and post-reexec deadlines/output caps not executed. Final
  observer code is syntax-checked, **not live-launch validated**.
- **PASS cleanup:** 8 jobs, all 7 CIDs / 16 supervisor PIDs absent; 10 unrelated
  IDs/states unchanged; 0 overlaps; no active reservation; shared lock available.
  Minimum admitted headroom 678,862,848 bytes, monitored 650,850,304 bytes.
  Bundle/canary hashes unchanged. Prior originals/receipts retained.

Pins (SHA-256):
- `artifact-manifest.json` (107 files): `5707b2554569560f8e4bf2f612602da34ffa1c748fd1454caa2a281f1747fdc3`
- `audit.json`: `773bb92c037bffb0e412f90ce7ace6aa7d241d9391716c4f93415c64597ca61d`
- `policy.json`: `146495851c27c79a046151a5c775022392ad7cfbdda571dbed72e370f937f7fa`

Required follow-up is only the remaining already-approved probes after fresh
metadata becomes available, not new isolation research. Current continuation
stopped at its explicit diagnostic gate. Non-goals unchanged: no production,
new image, VM change, provider/inference/spend, or outage/reboot guarantee.

## Controlled connection-cleanup follow-up: test plan before code

Exactly two sequential direct Unix requests already completed once: `/_ping`
200 in 0.112949291s; `/v1.52/containers/json` 200 in 0.258622750s. Fresh clients,
3s socket timeout, 256-KiB body bound, finally-close. These prove only endpoint
health. Prior timeout root cause remains UNKNOWN, not FD exhaustion.

New unique scratch root only; preserve every frozen helper, reference and receipt.
1. Check new per-request finally-close on success and request/status/read/JSON/
   overflow/HTTP-error exits (7 cases per active API entry point). Verify actual
   sampler, life/guard, cleanup and core aliases reach the new owned transport,
   never frozen old API function. No pool/proxy/reuse introduced.
2. Exactly one live full sampler must qualify: complete sample <=4s and
   min(VMavailable, VMtotal-sum RAW memory) >=469762048. Failure stops launches;
   futures may outlive individual 3s operations, no whole-sample retry.
3. SCORER-only surface probe: exact 7 public env vars, fixed hostname, only
   3 stdio FDs, all resolved mqueue mounts RO and create errno13/30; tmp16MiB/
   shm1MiB ENOSPC with <=16-KiB writes. Keep PROGRAM/one-entry prior proofs.
4. Actual create-response and attach withholding past initial sample age4.2s:
   post-attach measurement must start after hold, qualify <=4s before START.
   Controller EOF and original 10s expiry each yield exactly 0 starts and owned
   absence <=12s. Immediately preSTART recheck live pipe/original deadline/
   healthy reserve observer/new qualifying sample, never reset deadline.
5. Only critical new-profile faults: controller EOF, lost create/start response,
   guardian death and retained unresolved-reservation denial as needed; one
   create/start maximum, cleanup <=12s, next actual native PTC/full SCORER pair.
6. Both role policies: same-PID Python -> /bin/sh -> exec Python, UID/GID65534,
   caps0, NNP/seccomp, private namespaces/net, memory268435456/swap0/pids1/rootRO,
   socket/fork EPERM. Reexec stdout exactly cap+1 (1MiB/64KiB), stderr64KiB+1,
   absolute PROGRAM10s/SCORER30s deadlines; next benign actual role pair succeeds.
7. Final positive CID/PID absence, unchanged 10 unrelated IDs/states, 0 overlaps,
   source/policy/receipt pins. Any first unexpected failure stops this follow-up.

Non-goals: no timeout/reserve/freshness relaxation, automatic retry, image pull,
dependencies, VM/global changes, keys/providers/models/inference, agents, Git
writes, production integration, outage/reboot guarantee, or new research gate.

### Controlled follow-up outcome: BLOCKED_REEXEC_IDENTITY_ASSERTION

New scratch:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/confinement-spike-cleanup-l901euc3/`.
`connection_cleanup.py` checks 306 preserved artifact hashes offline and deliberately
exits 2. Its scope is proven partial results, not a green architecture reference.
The manifest includes a complete absolute file list. Older roots/references untouched.

- **PASS transport:** new `owned_http.py` has request ownership via
  `try: request/getresponse/read/check/decode; finally: c.close()`.
  Actual sampler, life/guard/cleanup and core aliases verified reachable to this
  implementation, not frozen old API aliases. 16 close-path cases (including
  serialization) passed. No pool/proxy/reuse added, timeouts unchanged.
  Prior timeout cause remains **UNKNOWN**, no FD-exhaustion/cure claim.
- **PASS live observer:** exactly one initial full sampler qualified in
  1.338949500s with 687,104,000 bytes headroom and ten RAW memory readings.
  Subsequent owned starts all required post-attach fresh admission, live original
  controller pipe/deadline and healthy reserve observer; 22 starts, maximum
  prestart sample age 0.218337708s. Whole samples >4s still reject without dispatch.
- **PASS SCORER surfaces:** exact seven public env values/fixed hostname, only
  three stdio FDs; resolved mqueue RO/create EROFS, preserved six readonly paths/
  twelve masks. Tmp16MiB/shm1MiB exact ENOSPC using 16-KiB writes. Existing PROGRAM
  surface and exactly-one-entry negative-control evidence retained, not rerun.
- **PASS freshness:** actual create-response and actual attach holds aged the
  original sample 4.204913s/4.227743s. Both remeasured after hold before START.
  EOF and original 10s expiry each caused zero starts; positive absence at
  4.296996s/10.091860s from original reservation, deadline never reset.
- **PASS critical lifecycle:** create-lost/start-lost/controller EOF/guardian
  SIGKILL/scoped remove-failure. Cleanup after trigger 0.054795–0.717275s,
  at most one create/start. Durable unresolved reservation rejected next admission,
  then explicitly reconciled. Seven actual native PTC + unchanged full SCORER
  recovery pairs succeeded across surface/freshness/fault checks.
- **BLOCKED reexec:** first PROGRAM identity probe emitted `SHELL_PID:1`, then
  exec'd Python failed guest line34 `assert before==after`, exit1, no OOM.
  Post-state was not emitted, so differing field is UNKNOWN (assertion compares
  mutable env as well as security state). This is not proof of policy escape.
  No rerun or further probes. Both-role postexec identity completion, socket/fork
  checks, stdout/stderr cap+1, 10/30s postexec deadlines and next benign pair unrun.
- **PASS final cleanup:** 25 jobs/CIDs and 50 supervisor PIDs absent; ten unrelated
  IDs/states unchanged; zero overlaps; no active reservation; lock available.
  Minimum admission 647,172,096 bytes, monitored headroom 647,241,728 bytes.
  Source bundles/canaries unchanged. First failures and old blocker history retained.

SHA-256 pins:
- Manifest: `bad9b9a86843d8fe3601b8712b22f9dc953f7534b6a42475e093e02214236891`
- `owned_http.py`: `ab087ef2675c20f12dc5dd1595001b12be4b893ec69da733a8a6513aade42287`
- `policy.json`: `0fdefcc0c58167e9f5c6ebfe1a3ec28324e9f56f04bbe5391f0a6c53b8007483`
- `audit.json`: `587f0dac3a5e8deede0cdae2d0f149543c28baa673e51d9db5ed8f8ad13594ff`

Authorized HEAD is `eb902c543b2a5b085128a002f6bc14022bb145ff`, not the previous
parent commit. No Git writes or production changes. Required reexec tests remain
incomplete: **no architecture freeze**. Parent review, not an automatic retry.

## Final re-exec continuation: corrected tests before code

Security a9 conditional approval is now activated by the actual diagnostic:
only ENV gained PWD; every non-ENV field matched. ENV is mutable process data,
not a kernel invariant. Initial exact seven-key/value whitelist remains mandatory.
No other field, including current pids, hostname, interfaces or cgroup, is exempt.

1. Pure-data comparator: ENV-only add/remove/change PASS; same-type mutation of
   each of all 14 non-ENV fields FAIL. Each nested status (7) and namespace (6)
   field mutation FAIL. Missing/unknown top-level or nested fields FAIL on either
   side; type changes FAIL. Do not execute external resources for these tests.
2. New `final-reexec-spike-*` root only. Preserve failed sources/receipts. Before
   exec, both roles assert all initial kernel values plus exact launch ENV7.
   Compare the unchanged full non-ENV fieldset/types strictly. New published probe
   receipts expose ENV keynames only, never values. Working config needed for
   unresolved reconciliation is retained; resolved configs are redacted afterward.
3. Resume only BOTH-role identity, socket/fork EPERM, exact stdout cap+1
   (PROGRAM1048577 / SCORER65537), stderr65537, original external deadlines10/30s
   without reset, and subsequent actual PTC/full unchanged SCORER benign pair.
   Check same PID through shell/exec, UID/GID65534, five caps0, NNP1/seccomp2,
   all six namespace identities, memory268435456/swap0/pids1/current1/rootRO/
   nofile64. Do not repeat surfaces, mqueue control or lifecycle faults.
4. Keep real per-operation tracing. Exactly one initial sample must qualify;
   every launch and immediate preSTART require fresh >=469762048 and age<=4s,
   original deadline/live pipe/healthy reserve monitor. Reserve192MiB remains.
   Any metadata failure stops remaining guest gates with exact slot/stage/trace.
5. Review fixes, offline: add reviewed actual ROOT/watchdog.py hash BEFORE imports;
   baseline pure pin check PASS, mutated bytes at that exact target FAIL before
   helper import/create. All four reference scripts reject python -O before
   scratch IO/import or daemon access (four negative controls).
6. Clarify lifecycle evidence: helper sources and policy are hash-pinned;
   audit/fault/journal/surface receipts are UNPINNED semantic checks, not hash-bound
   immutable originals or authentication. No new receipt framework for that fix.
7. Final owned CID/supervisor/CLI absence, ten unrelated states unchanged,
   zero overlap, reservation state, source/policy/result hash readback.

Non-goals unchanged: production integration/security acceptance, new dependencies,
images/pulls, global/VM changes, model/provider calls or financial enforcement.
Safety assumptions: daemon available and at least one trusted supervisor survives.
Re-exec is allowed, not shell-free. $50 authorization is not billing-hardcap proof.

Output-observer correction before remaining-only code: the first SCORER stdout
case actually rejected 65,537 bytes and retained 65,536. Its extra opposite-stream
marker assertion failed because overflow abort need not drain another stream.
Preserve that runner/result unchanged; do not rerun the case. The required bound
predicate remains rejection reason + exact target cap+1 + retained target cap.
Pure-data mutations of each predicate must fail. No kernel comparator or actual
guard change. Continue only unrun SCORER stderr/deadline and benign role pair,
with normal fresh per-launch/preSTART admission (no cached sample permission).

After all eight required guest gates passed, an additional cross-job assertion
observed identical namespace inode numbers in sequential, already-destroyed
containers. Those numbers are not permanent unique IDs. This extra assertion was
not a requested gate and does not test simultaneous separation. Preserve both
failed runners/results; do not rerun guest gates. All six within-job namespace
identities must still compare strictly across reexec. Run only the remaining
actual benign PTC/full SCORER pair through the existing unchanged controller.

## Final reexec evidence: PARTIAL, benign pair BLOCKED

Reference: `reexec.py` (offline, expected exit 2 for the preserved overall BLOCK).
Scratch:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/final-reexec-spike-c4ogmely`.
Earlier four reference stages and all failing sources/results remain preserved.
Within this final root no guest case was repeated. Two auxiliary runner failures are retained:
opposite-stream marker not drained after stdout overflow; namespace inode numbers
identical across destroyed sequential containers. Neither changed the strict
within-job kernel comparator, guard, policy or any requested acceptance bound.

| Gate | Actual outcome |
| --- | --- |
| Comparator sensitivity | PASS, 138 pure-data cases, 14 non-ENV fields + 7 status/6 namespace nested fields, 0 external-resource calls. ENV-only add/remove/change accepted; all required mutations/type/fieldset negatives rejected. |
| Both-role reexec identity | PASS, Python PID1 -> shell PID1 -> Python PID1; exact initial ENV7 checked. Afterwards dict -> dict, only PWD added, no removed/changed keys. Every non-ENV field strictly unchanged, no additional exemption. |
| Kernel posture | PASS both roles: UID/GID65534, five caps0, NNP1/seccomp2, six namespace identities unchanged, memory268435456/swap0/pids1/current1/rootRO/nofile64, fixed hostname, loopback-only interface, cgroup0::/. |
| Postexec denials | PASS both roles, socket/fork EPERM (errno1). Trusted raw probe bypasses frontend AST; not an AST exploit or shell-free claim. |
| Stdout bound | PASS PROGRAM1048577 / SCORER65537 bytes observed, retained1048576/65536, overflow reject. Three pure-data boundary predicate mutations rejected. |
| Stderr bound | PASS both roles65537 observed, retained65536, overflow reject. |
| Original absolute deadline | PASS PROGRAM10s / SCORER30s, never reset at exec. Actual running9.284930s/29.229189s; guard deadline lag0.009890s/0.011064s; positive absence after deadline0.096714s/0.072431s. |
| Post-fault benign role pair | BLOCKED. Actual PROGRAM produced exact59bytes, exit0/no OOM. Independent observer then reported raw-stat HTTP404, slot stats[0], sample40003:4, body stage. SCORER benign case NOT RUN. No further create/START after error, no retry. |
| Review findings | PASS: actual ROOT/watchdog.py hash checked before imports, baseline passes and altered bytes fail before helper import/daemon call; all four -O controls fail before scratch/helper/daemon access. Lifecycle source/policy pins and UNPINNED semantic receipt checks now correctly distinguished. |
| Cleanup | PASS, 9 owned CIDs/18 supervisors/117 CLI children absent; ten unrelated IDs/states unchanged; zero overlap; reservation absent. |

Fresh initial full sample0.384599s, headroom696389632. Minimum admitted646193152,
monitored645165056 bytes. Maximum immediate preSTART sample age0.267374s.
Unchanged required fresh headroom469762048, sample age<=4s, live pipe/original
deadline/healthy independent observer; reserve201326592. This is sampled mitigation,
not a continuous availability guarantee. Memory256MiB; ordinary scratch at least
17MiB (/tmp16MiB + /dev/shm1MiB), not an exclusive-total claim.

Trace has10626 events. Exact failure: raw stats GET, HTTP404/body, process40003,
sample40003:4/slot stats[0], owned_http.api line19 via observer.stat line18.
This does NOT establish the cause of the earlier intermittent timeout.
Resolved Env/Cmd/duplicate Args values are redacted, with keynames/original hashes;
no unresolved operational config was discarded.

SHA256 readback:
- policy.json: `8ba231eaddaea9f9bf70353db8913f190d0fe09d9ac4d2c1268bb7e635b0dd81`
- acceptance.json: `79568c455e69ff9a5de48123e49ef1684c2c5cef014eb98eebb33029fdfd5501`
- operations.jsonl: `2b04f57cdb1dc8798d53a99ad1b6271f5d838e96d3d38f20192e48d19026934d`
- offline-readback.json: `5c6686f242cf4825c4aab7ee74bf4c0b5d41bd8a1167ae4c2d5a53b6af4603ef`

Superseding four reference SHA256 values (review fixes):
- spike.py: `6485adc658b48e7ca400cec6ae6ca2ad02555702bbd15c18bed288e259603903`
- lifecycle.py: `0aaaa8d4d47bfa7d5d4e9d76e708584f4c311e8d87cf9c7605df852234d6fe6d`
- confinement.py: `8f285eedc75b06dcf63d9e4276a18097cd27820bf71c0af4be74de9cf23c5f2b`
- connection_cleanup.py: `356eebde5d9bbcf78f2ffdd8a7ca79fc7ce39b147bc5b2b7be153b4cab4edc70`

HEAD remains eb902c543b2a5b085128a002f6bc14022bb145ff; index empty.
Budget three files equal HEAD blobs; draft SHA256 remains
d359bcbb4aab44bf9c8a2d868d1bba79d6c2e68c91ee93667017c7fd6463a009.
External native worktree HEAD remains da011d7a7a4d95d37aee1142b1ae549c3c6dfddd;
its code was not inspected. No commits/push, production/native/budget/draft edits,
model/provider requests or spend. $50 permission is not billing-hardcap evidence.
Boundary feasibility only, not production security acceptance. Any further live
attempt needs separate authorization; investigate the observed metadata 404 first.

## Authorized observer-retirement correction: test plan BEFORE code

One bounded sequence in one new `observer-retirement-spike-*` scratch root.
Old lifecycle/confinement/final-reexec roots and the six existing references stay
unchanged. No repeat of the eight accepted reexec/deadline gates.

1. **One unchanged-order identity control, maximum one actual attempt.** Keep the
   old guardian/observer/decoder order. A private transport gate captures exactly
   one actual OWN raw-stat request, records sample/slot/matches-owned/phase (never
   raw Docker IDs or bodies), and sends an event ACK. That ACK triggers the existing
   controller ABORT path, not a timing sleep. Positive validated OWN STOPPED and
   actual DELETE204 ACK release the captured request to obtain one real OWN404.
   Require captured/STOPPED/REMOVE/request/error/observer-join ACKs, all tracked
   clients closed and CLI children joined. Gate wait<=2s; join<=1s after the old
   cleanup returns; PROGRAM original10s and positive absence<=12s from reservation.
   FOREIGN/UNKNOWN404, another metadata error, missing ACK or nonreproduction:
   STOP, no retry and no ordering correction.
2. **Only after OWN predicate is demonstrated**, new prototype ordering:
   trusted positive OWN STOPPED -> prohibit new snapshots -> bounded observer JOIN
   and retirement ACK (<=1s) -> REMOVE -> positive absence -> reservation release.
   Every retired sample is permanently admission-ineligible (including cross-job
   cached reuse), never a zero-charge or partial measurement. All real foreign/
   unknown/other metadata errors remain fatal, with a durable future-admission
   block. If bounded join fails, cancel only owned pending readonly work and join
   within the remaining <=2s cleanup budget; record failure/UNRESOLVED, not PASS.
   No generic phase/time-cutoff error exclusion. Pure/scope controls must reject
   foreign404 and unknown404 after STOPPED, OWN404 while alive, pre-STOPPED errors,
   reuse of a retired sample and subsequent admission/START (zero starts).
3. **Trusted stable VM-host namespace baseline.** One existing fixed Colima SSH
   readonly metadata command reads six `/proc/self/ns/*` links and corresponding
   PID1 namespace links to establish VM-host context (trusted Colima VM route,
   self==VM PID1 for all six). No sudo, userfiles, config, source or cache reads.
   If context/equality cannot be established, STOP BASELINE_UNKNOWN. Repeat this
   baseline once after the two fast role identity probes; require all six stable.
   Both roles retain all six guest namespace fields, strict within-job equality
   across exec, effective private configuration and inequality to trusted host.
   Pure controls reject host-mode config, any guest==host field and any within-job
   namespace change. One compartment at a time, no temporal cross-job uniqueness
   assumption, no concurrent-container proof.
4. **Exactly four corrected target-stream boundary cases.** Marker is first bytes
   IN target stream and included in its cap+1 total. PROGRAM stdout1048577,
   SCORER stdout65537, both stderr65537. Require observed target prefix, exact
   target cap+1, retained target cap, overflow rejection, positive cleanup.
   No opposite-stream observation claim, drain, sleep, or marker-byte exclusion.
   Pure literal mutations must reject wrong prefix/count/retained length/reason.
   Do not repeat the already valid10/30s deadline cases.
5. **One actual fresh native PROGRAM + complete unchanged SCORER benign pair**
   after corrected ordering/boundary cases, exact59/88-byte results and exit0/no
   OOM, fresh per-launch/preSTART admission. All samples unchanged numeric policy:
   min(VM available, total-sum RAW running charge)>=469762048, age<=4s,
   independent reserve201326592, live controller and original10/30s deadlines.
6. Final all owned CIDs, observer workers, CLI children and supervisors absent;
   ten unrelated IDs/states unchanged, zero overlap, reservation state explicit.
   Pin/read back actual active guardian/controller/observer/stager/decoder/config/
   transport/role helpers and policy/results. New small offline reference only
   after actual new-scope PASS or clearly marked PARTIAL/BLOCKED.

Non-goals: production freeze/security acceptance, billing acceptance, provider/
model calls, installs/pulls/downloads, Git writes, old-root modifications,
foreign-container mutation, VM/global changes or repeating accepted deadlines.
Available-daemon/one-trusted-survivor assumptions remain, no outage guarantee.

### Observer-retirement actual result: BLOCKED_BASELINE_UNKNOWN

Scratch:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/observer-retirement-spike-qrh4ikjq`.
New `observer_retirement.py` is OFFLINE partial evidence, expected exit2.
No corrected retirement implementation or production freeze was produced.

| Gate | Actual result |
| --- | --- |
| One unchanged-order identity control | PASS for selected predicate only. Captured sample88602:4/stats[0], actual target_matches_owned=true while OWN Running. Event ACK triggered existing ABORT, not a timing sleep. Validated STOPPED exit137/no OOM, DELETE204, then the captured real request returned OWN404/body. Historical sample40003:4 target remains UNKNOWN. |
| Control ordering/ACKs | Capture507618.132286625 -> trusted STOPPED507618.170161875 -> DELETE204507618.186145958 -> OWN404507618.188049291 -> old observer joined in0.021814s. This is post-REMOVE teardown, NOT corrected pre-REMOVE retirement. |
| Trusted VM-host baseline | BLOCKED_UNKNOWN. Fixed authorized readonly Colima SSH namespace command returned6/12 links, exit1, stderr nonempty,0.578233s. The six self-to-VM-PID1 equalities could not be established. No sudo, fallback or retry. No claim which missing link failed or why. |
| Corrected ordering/permanent sample ineligibility | NOT IMPLEMENTED/NOT RUN after baseline stop. Control ACK's boolean ineligibility annotation is not a proof of future admission protection. No zero-charge/partial/cached snapshot substitute was used. |
| Foreign/unknown retirement + blocked-admission controls | NOT RUN; no invented PASS and no foreign container mutation. |
| Two-role host/private namespace checks | NOT RUN; no sequential cross-job namespace-ID uniqueness claim, no guest field removed. |
| Four corrected target-marker boundary cases | NOT RUN. Historical opposite-stream marker remains unobserved where it was unobserved. |
| Fresh corrected native PROGRAM/full SCORER pair | NOT RUN. Earlier eight accepted reexec/deadline gates were not repeated. |
| Cleanup | PASS:1 owned CID/2 supervisors/5 CLI children absent (4 observer +1 host-baseline);53 observer future workers ended, observer joined, HTTP clients finally closed including2 final-audit requests. Ten unrelated IDs/states unchanged, zero overlap, reservation absent. |

Control positive absence1.294066s from reservation, original PROGRAM deadline10s
(within12s total). Minimum admitted691613696, monitored691408896 bytes; immediate
preSTART sample age0.147809s. Bounds/policy unchanged: memory268435456,
MemorySwap==Memory (guest swap0), pids1/FD64, single compartment, readonly6/masks12,
tmp16MiB+shm1MiB, fixed ENV7/hostname, private PID/IPC/cgroup and networknone,
exact previously approved installed image, no pull. Fresh minimum469762048,
reserve201326592, age<=4s/live controller/original PROGRAM10/whole SCORER30 remain
requirements; corrected new runtime acceptance remains incomplete.

Resolved working copies redact ENV/embedded commands and Docker IDs, retaining
pre/post-redaction hashes. No unresolved operational config was discarded.
The old five reference Python files are unchanged; earlier README content is an
identical prefix, and the old final-root pinned files read back unchanged.

SHA256:
- identity-control-result.json: `9c2113f75c1424cf5dc876e82f1521362e95c837ab9fc63ba160b8bc9186ea72`
- correction-result.json: `703795eb9df5f949461a124d2f12ed3f2216e5aec8791292690ce8aa4cb25922`
- policy.json: `3c8ba99e70f6166cf42643bfd840f6acc325bd0c4db4ca9bc3cb43eb3248e4f8`
- operations.jsonl: `881a5aeeb5f7f04eacceaf55b394ab2c6f22e954854f9765dc4047cdcd7eccd9`
- source-readback.json: `71dbac7d16de05dffaa514cc096af668163f908b6fdf3254a967eb190db34ea5`

The readback includes the complete37-entry absolute created/modified file inventory.

Active control source pins are in source-readback.json: guardian/decoder/config
life.py214a7de6..., controller9f85a009..., observer8cc5c476...,
transportab087ef2..., tracer96390b47..., entry/stager/actual control guest helper
stage.py36ca4ffe..., host metadata helper519b5bcf.... Old native/lifecycle sources
were not modified. HEAD eb902c543b2a5b085128a002f6bc14022bb145ff, index empty;
budget three and existing dirty draft hashes unchanged. Zero model/provider calls.
Further live work requires a separately established trusted VM-host context and
authorization; no security/billing/full-production acceptance is claimed.

## Final authorized retirement sequence: numeric test plan BEFORE code

New `observer-retirement-final-*` root only; preserve every older proof/source.
Carry forward the demonstrated selected OWN404 predicate, but historical40003:4
target remains UNKNOWN. User explicitly approved ONLY two fixed noninteractive
VM-root namespace commands, not billing or other root actions.

1. Before any new guest, fixed BASELINE1 argv: existing Colima default SSH,
   `sudo -n -- readlink`, twelve literal `/proc/self/ns/{pid,mnt,net,ipc,uts,cgroup}`
   then `/proc/1/ns/...` paths, stdin DEVNULL, timeout2s, bounded stdout/stderr.
   Require exit0, exactly12 formatted namespace links and all six self==VM PID1.
   Denial/unknown/timeout: STOP, no retry, escalation or password fallback.
2. New prototype only: positive fully ownership-validated OWN STOPPED -> prohibit
   new observer samples -> observer JOIN/retirement ACK<=1s -> REMOVE ->
   positive absence -> release. Retire all sample tokens permanently; no cached,
   partial or zero-charge admission. A foreign/unknown/other real metadata error
   remains fatal, including during retirement; persist a block on later admission.
   Ambiguous cleanup retains reservation. No generic time/phase error cutoff.
   Preserve original10/30s deadlines and PROGRAM positive absence<=12s.
   If retirement join fails, bounded cancellation is failure cleanup, NOT PASS.
3. Pure/scoped negatives: reject OWN404 alive, foreign404 and unknown404 after
   STOPPED, pre-stopped error, retired/cross-owner sample reuse and ambiguous
   cleanup. Every such branch denies next START (zero starts); no foreign runtime
   mutation. Namespace controls reject host-mode effective config, guest==host
   for each of six fields and within-job namespace drift.
4. Exactly two fast identity probes, one per role. Exact initial ENV7; mutable
   postexec ENV reported as keynames only. All14 non-ENV fields/types, seven
   status fields and six namespaces strictly unchanged. Effective private
   PID/IPC/net/UTS/mnt/cgroup, guest!=trusted host for all six. Retain UID/GID65534,
   caps0, NNP1/seccomp2, memory268435456/swap0/pids1/current1/rootRO/nofile64,
   hostname/loopback/cgroup fields. One compartment, no temporal uniqueness test.
5. Exactly four target-stream cases: marker is prefix INSIDE total cap+1,
   PROGRAM stdout1048577, SCORER stdout65537, both stderr65537. Require prefix,
   exact observed cap+1, retained cap, overflow rejection and complete cleanup.
   Literal negative controls mutate prefix/count/retained/reason. No opposite
   stream drain or marker-byte exclusion. Carry both accepted10/30s deadlines
   forward unchanged, DO NOT replay them.
6. One fresh actual native PROGRAM PTC/catalog and complete unchanged SCORER pair
   AFTER fault cases: exact59/88 bytes, complete six-field scorer result, exit0,
   no OOM, retired observers/CLI children absent. Every job requires its own
   fresh precreate and immediate preSTART sample, minimum469762048,
   age<=4s/live controller/original deadline, independent reserve201326592.
7. BASELINE2 is the identical second and last authorized root command, after the
   checks; require twelve valid links, host-context equality and equality to
   BASELINE1. Instability blocks namespace acceptance. No third root command.
8. Final all owned CIDs/supervisors/observer workers/CLI children absent, ten
   unrelated IDs/states unchanged, zero overlap, reservation explicit. Pin and
   reread actual active sources/config/policy/receipts. New small reference has
   pre-IO -O guard and is PASS only if ALL new gates complete.

Non-goals: production/security/billing acceptance, model/provider/keys/inference,
downloads/images/packages, Git writes, foreign mutations, global/VM changes,
root commands outside the two literal namespace probes, old-root modifications.
Available-daemon/one-trusted-survivor assumptions and all existing resource,
readonly6/masks12/tmp16+shm1MiB/ENV7/image/network policies remain unchanged.

### Final authorized attempt: BLOCKED_OWN_KILL409_INCOMPLETE_RETIREMENT

Root:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/observer-retirement-final-1sl59eoj`.
New offline `observer_retirement_final.py` deliberately exits2. Old six Python
references, historical README prefix and every older artifact root are preserved.

| Gate | Actual outcome |
| --- | --- |
| Authorized fixed ROOT BASELINE1 | PASS: exact twelve readlink paths, stdinDEVNULL, sudo-n--readlink only; exit0, stderr empty,12 valid links, all six self==VM PID1,0.394914s. One of two permitted root commands used, no other root command. |
| Pure/scoped controls | PASS31: foreign/unknown retirement404, OWN404 alive/retired, early error preservation, retired/cross-owner cache, ambiguous cleanup, host-mode/host-equality/namespace-drift and boundary literal mutations. Observed START callbacks0, actual foreign mutations0. |
| Two identities | PASS relative to BASELINE1 only: PID1 through shell/exec, exact initial ENV7, postenv only PWD added, all14 non-ENV fields/seven status/six namespace fields strictly unchanged. Effective private configs, all six guest namespaces differ from trusted before-baseline. UID/GID65534/caps0/NNP1/seccomp2/memory256MiB/swap0/pids1/current1/rootRO/nofile64 retained. Final namespace stability NOT PROVED without BASELINE2. |
| Managed retirement ordering | Three accepted jobs: positive OWN STOPPED -> prohibit samples/retire tokens -> observer/CLI JOIN ACK -> REMOVE -> positive absence/release. Max join0.110178s. No generic phase/time error exclusion, partial sample, charge0 or cached admission. |
| PROGRAM stdout target marker | PASS: marker first13bytes INSIDE1048577 total, retained1048576, overflow rejection/cleanup. |
| SCORER stdout target marker | Payload observed65537, retained65536, target prefix present. Overall case BLOCKED: owned KILL409/body (daemon: not running) after inspect had reported Running. Cleanup exited before managed observer retirement. Original journal remains UNRESOLVED. |
| Failed teardown evidence | worker-final recorded observer_dead=false/http_clients_remaining1. Preserve this failure; no managed JOIN claim for this job. Stop remaining jobs, no kill retry or protocol patch. |
| Both stderr cases / native recovery pair | NOT RUN after stop. No deadline replay; earlier accepted10/30s and13-byte readiness proofs carried forward unchanged. |
| ROOT BASELINE2 | NOT RUN after failure stop; no stable-host/full namespace acceptance claim. |
| Emergency cleanup only | Positive fully ownership-validated OWN STOPPED exit0/no OOM, all supervisors/observer CLI already absent, separate process-death retirement ACK, first DELETE204 (force=false/v=false), positive absence. Not a runtime retry or corrected-protocol PASS. Reservation released only after proof; durable future admission block retained. |
| Final cleanup | Four owned CIDs/eight supervisors/16 CLI children absent (15 observer +1 root baseline), all observer processes gone, logged HTTP clients finally closed. Ten unrelated IDs/states unchanged, zero overlap, reservation absent. |

Failure exact endpoint POST /containers/{owned}/kill, status409/body,
target_matches_owned=true, phaseALIVE, time526274.402047708,
elapsed0.032747416s. Selected OWN404 witness remains valid; historical40003:4
target/cause remains UNKNOWN. No new missing-metric or foreign-error exception.
Minimum admission676552704, monitored676573184 bytes; max preSTART age0.428954s.
All original resource/admission/observer/deadline/image/ENV policies remain.
The failed cleanup/retirement path prevents acceptance despite successful payload
counts. Correcting that path and completing the unrun gates requires separate work.

Source pins include actual guardian/decoder/config life.py6f973717..., controller
d5129b2f..., observera2e91cb1..., retirementaf17c5f1..., HTTPab087ef2...,
trace36198018..., entry/stager7e4c58d6..., actual role helper530b9ba3... and frozen
native lab/core imports. All106 absolute created/modified paths, source hashes
and byte-bound receipts are recorded in source-readback.json; hashes are local
integrity evidence, not authentication or production acceptance.

- policy.json: `c90b28af33dbb0ce4f8a43bdb17f58d929b809c8393243c9da30f4d96b3b81a7`
- final-result.json: `ac3afd1d32c58c5d41d53636980220bf47089110fffac30e942006a6881ea7a6`
- operations.jsonl: `36765b60dd48c9fccc9f47a6544b04c79f25c2a8ca4b18664b52d86c8d4536e8`
- source-readback.json: `9490a9a015f3e7e7e6c88b18427fefd2832608c15d85de8ad3db754e2bc708ab`

Resolved/emergency-absent copies redact ENV/command/Docker-ID data with original
hashes; the failed original status is not relabeled successful. HEAD remains
eb902c543b2a5b085128a002f6bc14022bb145ff, index empty; budget three and dirty draft
hashes unchanged. External native branch untouched/uninspected, no Git writes.
Zero model/provider calls. Production security, rate and billing proofs absent;
$50 authorization remains financially blocked.

## Authorized minimal KILL409 transition: numeric test plan BEFORE code

One new `kill409-spike-*` root. Preserve all prior source/receipt bytes and failed
statuses. Only append the explicitly authorized operator CLOSED history receipt.
No new before-baseline/root command, no accepted-gate replay.

1. Before any START, hold the existing single-compartment lock and freshly prove
   absence of all four prior owned identities: four name inspections404 plus a
   complete daemon list containing no matching full-CID hash, nonce or name.
   Freshly prove all eight supervisors/fifteen observer CLI PIDs absent (their
   processes own the observer clients), no reservation and unrelated ten states
   unchanged. Append fsynced operator-reconciliation/CLOSED history, retain the
   old block/journal files and their original hashes. Any uncertainty: STOP.
2. Reuse the byte-pinned, successful twelve-link HOST BASELINE1 from the last
   root. Root privilege remains ONLY the second previously approved fixed sudo
   namespace command at the END, stdinDEVNULL/timeout2s/no fallback or retry.
3. Minimal typed transition: one cleanup SIGKILL attempt. Only actual HTTP
   APIError.status409 permits one fresh inspection addressed to the previously
   recorded full CID, with full ownership/config revalidation. Require explicit
   RunningFALSE/PausedFALSE/RestartingFALSE/Pid0. Never infer STOPPED from error
   body, old inspection or404. Preserve exit/OOM/original failure and observer
   health. Then normal STOPPED -> prohibit sampling/retire tokens -> observer/CLI
   JOIN ACK<=1s -> REMOVE -> absence/release. Keep monitor active if OWN may run;
   error paths with trusted STOPPED also retire, but remain failures. No second
   cleanup KILL, no raw metadata exception or cache/zero-charge fallback.
4. Exactly one genuine private OWN TOCTOU control: install a guest TERM handler
   before readiness ACK; existing ABORT enters cleanup with actual RunningTRUE.
   Private test transport releases that guest via TERM (normal handler exit0),
   waits for actual exit ACK, then submits the original cleanup SIGKILL once and
   obtains real409. This is event-driven, no timing sleep to chance the race.
   Require fresh full-CID stopped inspection and managed ACK BEFORE DELETE.
   PROGRAM original10s, positive absence<=12s; observer retirement<=1s.
5. Pure/scoped negatives:409 still-running/paused/restarting/nonzero PID,
   foreign/unknown/missing inspection, and status500 all reject and block next
   START (zero callbacks). Missing/raw metadata remains fail-closed. No real
   unrelated mutation, no generic reset or exception swallowing.
6. Only remaining cases: SCORER stdout65537 retained65536; PROGRAM and SCORER
   stderr65537 retained65536. First13 bytes are target marker INSIDE cap+1,
   prefix/count/retained/rejection/managed-cleanup all required. No opposite
   stream drain, no extra sleep. PROGRAM stdout/identities/deadlines carried
   forward; do NOT replay them.
7. After faults, one real native PROGRAM PTC/catalog result59bytes and complete
   unchanged SCORER result88bytes/six fields, exit0/no OOM, fresh separate jobs.
   Each admission min(VM available,total-sum RAW charge)>=469762048; age<=4s,
   reserve201326592, live controller/healthy observer, original10/30s deadlines.
8. At end only ROOT COMMAND2: identical approved twelve-path sudo-n-readlink,
   exit0/twelve valid links/self==VM PID1/all six stable vs pinned baseline1.
   Total privileged commands across both roots must be exactly two, no third.
9. Final all owned CIDs/supervisors/observer workers/CLI children absent, ten
   unrelated IDs/states unchanged, zero overlap, reservation clear. Pin actual
   active guardian/HTTP/observer/decoder/config/stager/role sources and receipts;
   new commented reference -O guard before IO, overall PASS only if all complete.

Non-goals unchanged: production/security/billing/rate acceptance, provider/model/
keys/private config/cache/downloads/packages/image pulls, Git writes, other jobs,
VM/global changes. Exact approved image and256MiB/zeroSWAP/pids1/FD64/readonly6/
masks12/tmp16+shm1MiB/ENV7/hostname/private namespaces/networknone unchanged.

### Actual minimal409 result: PASS_REMAINING_GATES, not production acceptance

Root `/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/kill409-spike-le2xr2tn`.
Fresh prior absence succeeded under the compartment lock: four names404, all
four full-CID hashes/nonces absent from the complete daemon list, eight
supervisors/fifteen observer CLI children absent and unrelated ten unchanged.
An fsynced `metadata-block-reconciliation.jsonl` CLOSED history was appended
ONLY to the specifically authorized old root. Original block bytes, journals,
failed UNRESOLVED status, all old sources and receipts remain unchanged.

Six new jobs accepted, no identity/PROGRAM-stdout/deadline replays. Genuine
control proved actual ownership-checked RunningTRUE -> private event TERM
handler normal exit0 ACK -> actual HTTP helper SIGKILL409/body -> fresh
previous-full-CID ownership/config-checked RunningFALSE/PausedFALSE/
RestartingFALSE/Pid0 -> managed retirement ACK -> REMOVE -> positive absence.
Exactly one cleanup SIGKILL, no regex/body inference or retry. Control join
0.011992s, total1.483519s. Nine strict transition negatives rejected with zero
START callbacks/real mutations; unknown/live state leaves healthy sampling
active while admission is durably blocked. Original exit137/OOMtrue synthetic
control remained unchanged. Prior31 negatives remain preserved/accepted.

SCORER stdout65537/retained65536; PROGRAM stderr65537/retained65536; SCORER
stderr65537/retained65536. Each target prefix13bytes INCLUDED inside total,
correct overflow reason/rejection and complete managed cleanup. Subsequent
real native PROGRAM59bytes and whole unchanged SCORER88bytes/six exact fields,
exit0/no OOM, passed. Every new job STOPPED -> retirement ACK before DELETE,
max join0.062045s. No other-stream drain or extra boundary sleeps.

Only remaining approved root invocation2 ran at END: twelve valid links,
self==VM PID1 for six namespaces, exactly equal pinned BASELINE1, exit0,
stdinDEVNULL, no stderr, CLI absent,0.241039s. Actual cumulative root commands
EXACTLY2, new before/third commands0. New helper rejects invocation1/3 and retry.
Latest prior both-role ENV7/kernel/status/namespace/exec/socket/fork proofs
carry forward; stable host baselines now bracket their namespace context.

Fresh final audit: new6 CIDs absent by full-CID inspections; old4 CID hashes
still absent from complete list. Combined20 supervisors, new20+old15 observer
CLI children absent; both root children reaped. All six observers joined,
clients finally closed, recorded59 prior/current actors absent plus finalizer
exit. Ten unrelated IDs/states unchanged, zero interval overlap, reservations
absent. Old original block retained with CLOSED history, new block absent.
Minimum admitted657874944, preSTART/monitored654647296 bytes; maximum preSTART
age0.193275s, complete sample0.374617s. Admission469762048/reserve201326592
and4s bound unchanged; memory sampling remains mitigation, not continuous
capacity guarantee. Tmp16+shm1MiB is at least17MiB ordinary scratch, not an
exclusive total. All approved resource/image/ENV/deadline values unchanged.

`active-source-pins.json` binds the actual16 active local helpers (including
real guardian entry `final_stage.py --guardian`, life decoder/config, observer,
typed HTTP helper, transition and test transport), not the rewritten nominal
guardian filename. Frozen lab/core import bytes remain explicitly pinned.
`source-readback.json` binds policy, active sources, runtime/root/closure
receipts and absolute created/modified inventory; `kill409.py` is offline only.
Local hashes establish integrity, not authentication or TOCTOU immunity.

HEAD/index/budget/draft/old seven Python references preserved; external native
physical worktree untouched/uninspected. No Git writes, model/provider requests
or spend. Spend not independently verified; $50 remains financially BLOCKED.
Full production codecs/CV2/wrong-pin, security, billing/rate proofs NOT PROVED.
Historical metadata-timeout root causes remain UNKNOWN. No further probes.

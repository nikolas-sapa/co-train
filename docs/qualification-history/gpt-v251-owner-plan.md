# V251 A completion plan, SOURCEONLY UNRUN

## Tests first

Parent executes, author performs file reads/writes only. Repair the existing
suite against V226 public signatures and V237/V250 private bridge, not the
previous candidate's public admission/evidence constructors. Maximum 200
collected cases, unique names, zero skips/xfails. Consolidation preserves the
old arithmetic, bootstrap, anchored-file, registry, permit, framing, evidence,
writer, metadata, admission, pin, staging, lifecycle and release test intents.

Named gates and numeric criteria:

1. `test_frozen_surface`: seven public entry/method signatures, no fictitious
   DTO exports, private construction/copy/deepcopy/pickle refusal for all
   authority objects. `ExportEntry` has exactly key/kind/size.
2. `test_metadata_refusals`: invalid request/spec/resources/recipe/pins/setup/
   uploads/paths/timing make 0 claims, 0 content opens, 0 SDK calls, 0 children.
   Original authorization four-tuples bind supplied five-field upload items.
   Planning ceiling >$25 or integer CPU tuples refuse with the same 0 effects.
3. `test_admission_*`: original claim/consume/bind exactly once, same common
   latch max 1, replays refuse, failed reservation close retains owner/latch.
4. `test_writer_*`: foreign root/key/path/size/hash refused before 1st source
   open; zero bytes accepted; streams <=65536 bytes; private mode 0600;
   request.json only; readonly child snapshots; outcome O_RDWR. Full hashes,
   4096+1 rows, 2 GiB/member, 8 GiB aggregate and 8 MiB manifest unchanged.
5. `test_launch_*`: exact deployed repository, train entry paths, fixed complete
   first-party closure/helper, module-name SDK binding versus path source pins,
   one descriptor/seal, copied DTO does not grant authority. Newly owned
   interpreter/source/SDK fixtures only, never installed interpreter reads.
6. `test_registration_*` and `test_lease_*`: register once after seal; 0 births
   without registration; actual owner/registration/request/prepared/root/
   generation/proof identities; foreign/copy/replay refusal; clean worker wait0
   precedes any read and first normal STOP; all 3 joins precede publication.
7. `test_reader_*`: acquire then immediately register before post-open checks;
   <=65536/read; yield each entry/chunk; exact inventory and full hashes;
   final sweep includes earlier closed files; closed/recycled FD never fstat;
   intermediate anchors/iterators have observed closes by C; top anchors held.
   Failed close is attempted once and retains actual handle plus both errors.
   Socket wrapper failure retains the pre-registered inherited FD, and a
   wrapper that clears its slot on failed close cannot erase that FD number.
8. `test_mocked_*`: explicitly fake spawning, valid 64-hex sessions and canonical
   framed messages, worker/controller/gate success; partial births (0/1/2/3);
   lost OPEN/ARM/CREATE ACK sends each capability at most once; original stage
   once at the launcher boundary, arm never given a surrogate App.
9. `test_worker_*`: one fixed C call, actual App retained before entry await,
   Sandbox retained before ACK, OUTCOME then FINISH and clean exit without
   normal STOP; concurrent STOP/EOF cancels the running body on the SDK loop.
10. `test_shutdown_*`: exact eight fixed cutoffs; at least 3 repeated
    cancellations at App/ARM/body/validation cannot escape joins/independent
    closes; no renewed expired
    waits; controller containment by O+3, gate preserved until its late kill
    stage; EARLY_STOP once and unconditional SHUT_WR; partial control framing
    cannot starve trigger EOF; initial alarm exactly L+4+T+.5, only advances.
    `test_independent_loss_*`: blocked worker receive detects stopper exit/EOF
    in <0.5 seconds without a detached task or renewed absolute cutoff.
    External ECHILD produces 0 clean observations, 0 PID-reuse signals and
    exactly 1 failed wait attempt. Actual waitpid(WNOHANG) status, not Popen's
    possible ECHILD-to-zero fallback, establishes the retained Popen's reap.
    `test_gate_exec_*`: command pin, environment, stdin and cwd ready BEFORE
    ARMED; 0 explicit closes after ARMED, inherited control/journal CLOEXEC,
    one same-PID exec call and unchanged original argv/environment on trigger.
11. `test_publication_*`: fixed C type and exact links only; reader closes by C,
    data sealed by P, STOP by L; final wrapper has 0 FS/hash/new-lease operations;
    unknown reap/close retains latch/resources and never publishes success.

Injected process observations are not actual OS reaps. Fixture SDKs/native
serializer substitutions do not prove provider/native lifecycle or science.
Existing C104 acceptance and pure scheduling acceptance remain separate evidence.

## Implementation

Replace broken A candidate internals, retaining original stage/arm and common
host latch behavior. Order: private metadata admission and generation registry;
anchored streaming preparation and launch custody; fixed verified-buffer child
bootstrap and worker-only raw SDK bridge; three direct-child lifecycle;
owner-held fixed C validation lease; immutable-origin cancellation-resistant
shutdown; observed-close release and one-use publication. No new shared APIs.

Reserve each generation before acquisition. Retain every actual returned handle
before validation/exposure/await. Close each generation at most once; unknown
close/reap keeps actual owner/resources, primary and cleanup exceptions and latch.
Use actual nonblocking waitpid status for each retained Popen, no executor wait
or detached cleanup. Finish gate's fallible file/pipe/cwd preparation before
ARMED, transfer remaining control/journal close responsibility to kernel exec.

## Non-goals and authority

No DTO/helper/RPC/C/engineering host/native/image/watchdog/launcher edits. No
execution, compile, imports, tests, Git, network, SDK-source/assets/config reads,
delegation, provider/GPU/build/upload/install/native/science actions. No settings
changes, commits or paid launch. G7 real interpreter authority remains 0 reads.
C public pre-admission refusal stays. Parent alone reviews, executes, integrates.
$30 gross maximum ($25 plan+$5 reserve); separately bounded preparation; one
attempt <=1800 seconds including cleanup, no retry. Native/science 0/7;
Alliance/Orca unverified. No universal OS/billing bound or same-UID atomicity claim.

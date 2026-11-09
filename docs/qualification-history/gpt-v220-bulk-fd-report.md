# V220 bulk-FD repair report

**SOURCEONLY UNRUN. Arithmetic-blocked, not approval.**
Sole new GPT author. Parent owns execution/review/integration.

## Exact new files

- `spec/spikes/gpt-v220-bulk-fd.py`
- `docs/gpt-v220-bulk-fd-plan.md`
- `docs/gpt-v220-bulk-fd-report.md`

Plan, independent arithmetic and minimal parent-owned guard-loss/exact-restore
controls were written before source. Existing Core, V213 and first-party sources
remain read-only. No extra control copies, scripts or test files created.

## Blocking arithmetic finding

The brief's **5870001** maximum excludes the required digest value. Its 74-byte
template contains `"sha256":""`, which is not a valid 64-character digest.
Adding the digest gives 138 fixed bytes. At both legal 256-character key limits:

`1 + 10000*(138 + 256 + 256 + 1) = 6510001`.

The missing contribution is exactly **640000 bytes**. Original
`_asset_path` allows those ASCII names, and original digest validation requires
64 lowercase hex characters. The 10-digit maximum size is 2147483648. No padding
fields or relaxed hashes are needed for this counterexample.

Exact 8MiB is still infeasible, but the correct shortfall is **1878607**.
The source cross-checks real canonical serialization against both independently
counted 74-byte empty and 138-byte valid templates.

C2 generates the genuine full-width **6510001-byte** witness. The brief's
**5870001-byte expected gate remains unchanged**, after actual worker/reap/
snapshot/cleanup observations. Thus an otherwise successful run must report
NONPASS at C2 and stop. There is no bypass flag. A seven-fixture PASS is
impossible until parent adjudicates the conflicting maximum. This is not a
runtime observation or a substituted passing expectation.

## Source repairs authored

- Seven fixed case definitions, one parent Popen site, at most seven fresh
  new-session workers, no retries or worker spawn/exec/session API calls.
  C1 is exactly 8193 bytes. C3 is exactly 8388609 bytes with 12886 members;
  C4 has 10001 members in 1630164 bytes. C5-C7 each have 4105 bytes.
- Genuine QualificationRequest, SqlTask, FilePin and AttemptBounds objects.
  The request FD carries `v220-local-request-projection`, **not original
  serialization**. The unsafe original serializer, full request validation,
  original model inventory and fixture database validation are never called.
- Both inherited payload FDs receive actual F_GETFL readonly, regular/single-link,
  expected UID/private0600, expected identity, bounded read/hash and final
  post-parse/record-validation identity checks, repeated before the marker
  permit is consumed. No payload-path fallback.
- C3's byte refusal precedes manifest reads/parsing/count/permit; C4's count
  refusal follows parsing. C5 changes only the expected digest on the real FD;
  C6 independently hashes a same-size byte-identical different inode, preserving
  the original expected identity; C7 changes actual open access mode.
- Strict fixed-schema/session/sequence/nonbool/duplicate/nonfinite framed
  control, <=2048-byte bodies and <=8192 aggregate wire bytes. Bulk bytes never
  enter control. Positives alone can receive a fresh one-use permit and create
  the exclusive private marker.
- Actual completed sends/receives, permit sends, worker operations, real reaps,
  filesystem markers, journal rows and FD closes are counted. Case gates use
  final observations **after cleanup**, never stale pre-close counts or None.
- Parent registers actual Path/FD/socket/Popen owners at creation and retains
  ledger entries, unresolved handles and primary/cleanup exceptions.
  Passed copies close after spawn; owning FDs, snapshots and root release wait
  for actual reap. Cleanup attempts remain independent. Failure contains only
  the verified unreaped Popen group and raises an actual owner-bearing Failure;
  diagnostic JSON is not a substitute for retaining that exception.
- Journal is exclusively parent-precreated0600; every later append lacks
  O_CREAT. Worker logs final inherited-FD close/operation counts. Parent appends
  and reads back the journal and marker only after actual child wait/reap.
- Clock precedes stdlib/project imports; case clock precedes generation.
  Immutable run+8/case<=2.5, .25s case/base teardown reserves, spawn cutoff,
  operation<=2/challenge<=.5/kill+reap<=1 all clamp to enclosing bounds.
  Worker alarm is armed before bootstrap file I/O, without renewal.
  No TERM probe, epsilon wait floor or unbounded wait. Accepted cleanup must
  have zero forced cleanup, lease exits, errors or retained resources.

## PROVES planned, not observed

After arithmetic adjudication and parent measurements only: genuine fresh-worker
request projection and record-valid canonical bulk delivery over readonly FDs,
small actual control, exact refusal stages/exits, one marker per positive,
and complete measured local reap/FD/root/journal cleanup.

Currently C3-C7 are authored but would not be reached after the expected C2
arithmetic failure in the unmodified harness. No results from those cases exist.

## SHORTCUT / MISSING

- Manifest member sizes/digests are synthetic declarations. No manifest member
  files or bytes exist. No snapshot-member content or aggregate asset admission
  is proved.
- Only eight newly created tiny synthetic request-pin files exist per case.
  They are not SQLite fixtures, a native-approved source bundle or valid model
  inventory. Worker reconstructs pin values; it does not reopen their files.
- Base fixtures do not adversarially exercise UID, permissions, hardlinks,
  malformed/replayed input or mid-read/post-parse mutation. Planned guard-loss
  controls are UNRUN and parent-owned.
- External10 containment and complete outer launch/output wall measurement
  belong to the parent. Kernel/syscall latency is not assumed bounded by Python
  timeouts; overruns or unknown custody cannot produce PASS.

**Executed checks: none.** No import, compile, test, command, Git, network,
SDK/provider, delegation, binary/hash or original asset operation was performed.
Only permitted file-tool source inspection and edits. No runtime timing, memory,
FD-close, journal, worker or marker evidence exists. Production owner/API,
staged stop executable, native/science/GPU work and schema freeze remain out of
scope. Original interpreter-binary hashing was neither run nor bypassed.

VERIFY_REAL: SOURCEONLY UNRUN. Arithmetic unresolved; no approval.

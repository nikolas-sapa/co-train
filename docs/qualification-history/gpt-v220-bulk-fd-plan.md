# V220 compact bulk-FD plan, before source

SOURCEONLY UNRUN. Sole GPT author. Parent owns execution/review/integration.
Only the three new V220 files are writable. No original serializer, assets,
SDK, interpreter-binary hashing, subprocess or imports executed while authoring.

## Independent arithmetic, blocking inconsistency

The brief's 5870001 maximum omits the required 64-character digest value.
Hand-count the sorted closed record, with size 2147483648:

| Piece | Bytes |
| --- | ---: |
| Braces and four commas | 6 |
| `"key":""` | 8 |
| `"root":"source"` | 15 |
| `"sha256":""` | 11 |
| `"size":2147483648` | 17 |
| `"snapshot_key":""` | 17 |
| Empty-string template total | 74 |
| Required lowercase hex digest value | 64 |
| Fixed cost of a valid member, excluding key/snapshot contents | 138 |

Original `_asset_path` permits 256 ASCII characters in each key; the snapshot
rule uses the same validator. `source` is the longest legal root. Thus a full
width valid record is 138+256+256=650 bytes. For n nonempty records, canonical
array bytes are `1 + 139*n + sum(key lengths) + sum(snapshot lengths)`.
The true maximum is `1 + 651*10000 = 6510001`, not 5870001.
The discrepancy is exactly `64*10000 = 640000`. Exact 8MiB remains infeasible,
with shortfall `8388608-6510001 = 1878607`. No padding fields or weakened hashes.

Preserve the brief's expected 5870001 as an explicit C2 gate, NOT silently
replace it with the derived value. Generate the genuine full-width C2 witness,
then gate observed counters and length after actual reap/snapshots/cleanup.
C2 must therefore report NONPASS under this brief even if transport succeeds.
Stop on that failure. All seven fixtures will be authored, but C3-C7 cannot be
claimed reached in the unmodified harness after C2. Parent must adjudicate this
arithmetic before a seven-fixture PASS is possible. No bypass switch.

## Seven fixed fixtures and independent expectations

All sizes below include a 64-character synthetic digest and 10-digit size.
Fitting uses actual canonical JSON with exactly root/key/size/sha256/snapshot_key.
Names have unique fixed-width prefixes; records sort strictly by (root,key).

| Fixture | Members | Key/snapshot length sums | Serialized bytes | Worker stage/exit | Permits/markers |
| --- | ---: | --- | ---: | --- | --- |
| C1 | 40 | 1632 / 1000 | 8193 | accepted / 0 | 1 / 1 |
| C2 | 10000 | 2560000 / 2560000 | 6510001 observed witness, brief expects 5870001 | accepted / 0, parent arithmetic NONPASS | 1 / 1 |
| C3 | 12886 | 3298638 / 3298816 | 8388609 | manifest_bytes / 8 | 0 / 0 |
| C4 | 10001 | 100010 / 140014 | 1630164 | member_count / 11 | 0 / 0 |
| C5 | 24 | 336 / 432 | 4105 | manifest_hash / 9 | 0 / 0 |
| C6 | 24 | 336 / 432 | 4105 | manifest_identity / 7 | 0 / 0 |
| C7 | 24 | 336 / 432 | 4105 | manifest_mode / 6 | 0 / 0 |

C1: 32 keys of length 41 and 8 of length 40, snapshots length 25.
C3: `651*12885=8388135 < 8388608 <= 8388786=651*12886`;
12708 keys of length 256 and 178 of length 255, snapshots length 256.
Byte refusal precedes manifest read/hash/parse/count/permit. C4 count refusal
follows parsing but precedes record validation/READY/permit. C5 preserves the
actual same-FD signature and changes only the expected digest. C6 supplies a
separate byte-identical, same-size inode, independently hashed from actual FDs,
while expected identity remains the original. C7 changes only access mode.

## Required observations, not declared counters

- Up to seven fresh Popen workers, exactly seven for any accepted run, one per
  fixed case, start_new_session, no retry/replacement or child spawn/exec/setsid.
  Record actual Popen/PGID/SID, fresh session/challenge/permit and frame sequence.
- Both payloads use inherited FD numbers only. F_GETFL readonly, regular,
  single-link, expected UID, exact 0600 and complete FD signature before read,
  throughout <=65536-byte reads/hash, after read and after complete parsing/
  record validation, before READY/permit. No payload-path reopen.
- Reconstruct the real QualificationRequest/SqlTask/FilePin/AttemptBounds.
  The wire is a disclosed local projection. Never call the unsafe original
  serializer or `_validate_request`, model inventory or fixture database checks.
  Only eight newly created tiny synthetic pin files exist per case.
- Strict duplicate/nonfinite/nonbool/exact-schema/session/sequence control;
  aggregate real control bytes <=8192. No bulk payload on control.
- Parent exclusively precreates a regular single-link 0600 journal. Every
  append opens O_APPEND without O_CREAT. Worker records final operation/close
  counts; parent appends and snapshots only after actual child wait/reap.
  Gate actual journal entries, actual exclusive markers and actual sent permits.
- Register Path/FD/socket/Popen owners immediately, retain unresolved entries,
  primary and independent cleanup exceptions in an actual failure object.
  Close passed dup copies after spawn, keep owning FDs until actual reap.
  No marker/journal snapshots or root release while a child is unreaped.
  Gate all FD-close counters only after closure, not from pre-cleanup copies.

## Immutable numeric bounds

Clock before stdlib/project imports; case clock before request/manifest generation.
One module-entry+8s run expiry. Each case <=2.5s through generation, FD work,
worker, marker/journal snapshots and complete teardown. Reserve .25s teardown
inside case/run bounds and refuse Popen once that work cutoff expires.
Operations <=2s, challenge <=.5s, stop/reap <=1s, all clamped to case/run/work
bounds. No TERM probe, no epsilon floor, renewed stop allowance or unbounded wait.
Worker gets the same immutable absolute bounds and one bootstrap alarm.
Failure containment uses only the original still-unreaped Popen group.
Expired waits get zero; unknown custody retains real owners and prevents release.

Accepted run: all 7 actual reaps/FD closures/root removals, no forced cleanup,
lease exits, retained owners or cleanup errors; base/journal teardown included
in total <8. Parent independently enforces external10 and measures launch/output
tails. Syscall latency is not assumed bounded by Python timeouts.

## Minimal parent-owned guard-loss controls, exact restoration

No generated control copies or extra fixture modes:

| Gate removed by parent | Existing witness and changed result | Exact restore |
| --- | --- | --- |
| Manifest byte cap only | C3 proceeds to member_count/11, manifest parses once rather than zero | manifest_bytes/8; zero manifest reads/parses/permits |
| Member count only | C4 reaches READY (parent still refuses to authorize a negative fixture) | member_count/11, zero permits/markers |
| Digest equality only | C5 reaches READY with wrong expected digest | manifest_hash/9 |
| All expected-signature equality sites only | C6 reaches READY; same-FD stability and byte/hash checks still pass | manifest_identity/7 before manifest read |
| F_GETFL comparison only | C7 reaches READY on same inode | manifest_mode/6 before manifest read |
| Final post-parse identity sites | Parent wraps final validation once with private-FD fchmod 0400 then 0600, verifies changed ctime but restored mode/content, and expects final identity rejection; removal exposes READY | restore exact sites and expect rejection again |
| Post-cleanup close gate | Parent injects one failed close and preserves its real FD entry; no PASS or root release | restore close and zero cleanup errors/retention |

The base fixtures do not attack UID, permissions, hardlinks, malformed records,
mid-read mutation or replay. Those guards are authored, not runtime-proven.
Do not weaken the arithmetic gate to obtain a green measurement.

## Non-goals and limitations

No production owner/API or frozen schema, SDK/provider/GPU/native/science,
original caller assets, stager/stop executable, binary hashing, installs,
Git/commit/push/deploy. Manifest sizes/digests are synthetic declarations:
there are NO manifest member files or bytes, snapshot-member verification,
aggregate asset admission or model approval. Synthetic request pins are not
SQLite fixtures or a valid model inventory. All tests/controls/timings UNRUN.

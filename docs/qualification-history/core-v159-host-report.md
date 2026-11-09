> Sanitized public reference. Historical acceptance applies to the private original, not these derivative bytes.

# V159 host source correction report, revision 4

Provenance: **Core Qwen original implementation, backend corrections**.
Not Core GPT authorship. SOURCE-ONLY, ALL REVISED TESTS UNRUN.
No commands, Python/import execution, tests, Git, SDK/network/provider calls,
processes, credentials/env/locks, binary/assets/installations or other-worktree
reads performed by this worker. Parent owns review, execution and integration.
This source correction grants no paid/cloud approval.

## Exactly six existing assigned paths modified

- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-qwen-engineering-host/train/qualification_engineering_host.py`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-qwen-engineering-host/train/qualification_modal_host.py`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-qwen-engineering-host/train/test_qualification_engineering_host.py`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-qwen-engineering-host/train/test_qualification_modal_host.py`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-qwen-engineering-host/docs/core-v159-host-plan.md`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-qwen-engineering-host/docs/core-v159-host-report.md`

No files created. Original strict/native/default source, stop binding/test,
existing watchdog/launcher, SDK and B RPC untouched.

## Corrections to the six supplied findings

1. **Complete policy identity.** AttemptReservation now retains and exposes
   read-only `policy_pin` (original exact FilePin, path/size/SHA256) in addition
   to existing `request_binding`; `policy_sha256` remains as a compatibility
   property. ModalOwnedHost compares all three FilePin fields plus request
   binding before `_require_sdk`, image construction, binding or allocation.
   Marker derivation and reserved JSON bytes remain unchanged. No approval
   enters from a bool, worker JSON or receipt.
2. **Finite FIFO refusal and identity checks.** Policy read, marker append and
   exclusive marker creation opens include O_NONBLOCK|O_NOFOLLOW. Opened policy
   must be regular/single-link before read, with matching nofollow path/handle
   state before and after hashing actual bytes. Appends validate opened and
   named inode/device, regular/single-link status, euid and exact private mode
   before writing, then check them again after file fsync. Real FIFO witnesses
   assert the NONBLOCK flag before allowing the actual syscall, so a regressed
   flag cannot hang the test. Write-only FIFO open may itself refuse ENXIO,
   without reaching fstat or writing, which is also fail-closed.
3. **Directory durability ordering.** Claim writes reserved line, fsyncs the
   file, validates its identity/size, then fsyncs the retained parent directory
   before any usable AttemptReservation is returned. A directory-fsync failure
   propagates its original error, preserves the exclusive marker and releases
   descriptors instead of returning authority.
4. **Close failure is terminal and releases custody.** close(event) uses
   finally to mark the reservation closed, clear its retained descriptor and
   attempt directory release even when the final append fails. The append
   descriptor also closes in finally. Primary append/fsync/replacement errors
   survive secondary close errors. Repeated close writes nothing; consume and
   record_identity refuse. Existing stop_owned caching therefore need not
   retry a failed close to release the reservation. No deletion/recovery added.
5. **Private owner/mode rechecked every append.** Both opened handle and
   nofollow record name must be owned by euid and have
   `stat.S_IMODE(mode) == 0o600`, including rejection of special mode bits.
   Same-inode chmod 0666 or foreign-owner observation refuses before any write.
6. **Colliding test approvals separated, expectations preserved.**
   test_reservation_required_and_unused now uses distinct consumed/closed
   policy bytes. test_reservation_bound_to_claiming_authorization uses distinct
   A/B policy bytes. Each now derives distinct markers and can reach its
   intended assertions. The genuine identical-byte substitution case is a
   separate witness with different 0700 directories, the same request, A's
   already-consumed marker and B's unused reservation.

## Preserved behavior and scope

- GPU suffix counts still bind to exactly one charged GPU, including rejection
  of A100:8; fallback/list escapes remain closed.
- Sealed base-only image factory unchanged, no caller image/layers/installs.
- ArmError.controller custody and ambiguity/no-rearm/no-create behavior unchanged.
- Raw async class chain remains intentional: plain coroutine awaits, no `.aio`.
  No SDK compatibility assertion follows from fake structural class labels.
- Sandbox create kwargs unchanged. Host does not create/assert an uncreated
  workdir; it inherits the image workdir (host workdir None).
- Original stop binding, watchdog and launcher unchanged. Stop ACK is not billing
  proof; remote termination and charged end stay UNKNOWN.
- Deterministic exclusive marker path, marker wire schema, original strict and
  native/default gates unchanged. No retries, replacements or cloud actions.

## Corrected test inventory and concrete witnesses

Two edited files now define **38 engineering + 33 lifecycle = 71** ordinary
finite pytest tests (12 additions to the prior 59 in these files). The parent's
supplied unchanged 19 stop-binding cases yield **90 total A cases**, all UNRUN.
The unchanged stop test file was not reopened/count-verified by this worker.
No parametrization, plugins, process/signal/thread timeouts or real SDK calls
were introduced. Tests use the existing pytest fixtures and real filesystem
I/O, with local fault-injection wrappers.

Revision-4 named additions, planned before their implementation:

| Test | Observable criterion / proposed guard-removal witness |
| --- | --- |
| `test_identical_policy_bytes_different_paths_refuse_substitution` | Identical bytes/size/hash and same request, different private paths; reject before SDK validation, 0 SDK calls, no bind/consume/marker writes. Also rejects size-only pin mismatch; legitimate same-pin construction succeeds afterward. |
| `test_policy_fifo_open_requires_nonblocking` | Real FIFO, flag checked before real open, nonregular failure, no policy read or marker. |
| `test_append_fifo_open_requires_nonblocking` | Real FIFO replacing marker name; flag checked before syscall, 0 writes, old marker preserved, all tracked FDs released. |
| `test_policy_replacement_during_read_refuses_claim` | Real read then rename/replacement with identical bytes but different inode; no claim marker, both files preserved, 0 live tracked FDs. |
| `test_claim_fsync_file_then_directory_before_return` | Ordered actual descriptor types: file, directory, returned; only then consume. |
| `test_claim_directory_fsync_failure` | Exact injected primary object propagated, marker retained, file-then-directory calls, 0 live tracked FDs. |
| `test_close_short_write_releases_directory` | Real partial append, failure, preserved original prefix, balanced FD counts, terminal state, repeated close 0 writes. |
| `test_close_fsync_failure_releases_directory` | Primary fsync object preserved even when both real-closing wrappers then raise secondary errors; balanced FD counts and no reuse/write. |
| `test_close_replacement_releases_directory` | Renamed owned marker plus unknown replacement; 0 writes, both preserved, balanced FD counts, no reuse/write. |
| `test_append_mode_drift_refuses_before_write` | Exact 0600 positive append then same-inode chmod 0666; 0 writes, unchanged record, balanced FD counts. |
| `test_append_owner_drift_refuses_before_write` | fstat-injected foreign uid (no privileged chown); 0 writes, unchanged record, balanced FD counts. |
| `test_stop_owned_close_failure_does_not_leak_cached_reservation` | Failed close fsync yields reservation_close_failed, UNKNOWN ends, 0 live tracked FDs; cached second outcome adds 0 writes/fsyncs. |

These are written candidate witnesses, not executed red/green results.

## Remaining risks / parent follow-ups

- All 90 A tests, Python compilation, guard-removal controls and platform checks
  remain UNRUN. Parent must execute and review the revised source.
- No real SDK constructor compatibility has been proved. Class-label fakes
  exercise structural guards only. Parent's separate SDK-loop/transport bridge
  repair and sterile compatibility checks remain separate work.
- fsync success expresses the operating system's durability contract, not an
  observed crash/power-loss experiment. Unsupported directory fsync refuses
  instead of silently granting a reservation.
- FD witnesses track explicit Python os.open/os.close calls. A wrapper raising
  after a real close proves primary-error preservation, not that a kernel close
  failure necessarily released its descriptor. Close errors are ambiguous,
  terminal, never blindly retried against a potentially reused integer.
- Private owner-controlled directories remain required. Named/handle checks
  detect observed mutations, not atomic filesystem snapshots. Full same-uid
  control can rename/recreate the entire policy directory and its marker; this
  residual needs the parent's filesystem ownership/isolation control.
- Caller must eventually close live reservations. A failed identity append
  still raises to its caller; terminal close is the release boundary.
  A partial/unsynced marker stays on any failed claim/close, intentionally
  preventing silent recovery or retry.
- Existing ambiguous pre-watchdog App entry or pre-arm staging can leave remote
  state UNKNOWN; retained-handle cleanup is attempted, not independent proof of
  termination or billing end. This correction changes no cloud lifecycle lane.

VERIFY_REAL: Six assigned files written/read with file tools; revised tests,
runtime, SDK compatibility and mutation controls UNRUN. No PASS claim.

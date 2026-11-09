# V189 Report: Fixed-Child Local Capability Spike (SOURCEONLY, UNRUN)

Status: SOURCEONLY, UNRUN, NOT VALIDATED, NOT PRODUCTION. Nothing here is
approval or evidence of a working system.

## Exact scope

Files created (3, all NEW, all inside the V189 writable list):

| Path | Lines | Status |
|---|---|---|
| `spec/spikes/local-capability-candidate.py` | 2088 | written, UNRUN |
| `docs/core-v189-local-capability-plan.md` | written | complete |
| `docs/core-v189-local-capability-report.md` | this file | written |

Files touched outside that list: NONE. All original V159 Track A paths
(`train/qualification_engineering_host.py`, `train/qualification_modal_host.py`,
`train/qualification_owned_stop.py`, the three `train/test_qualification_*.py`
files, `docs/core-v159-host-plan.md`, `docs/core-v159-host-report.md`) were left
byte-identical. Read for reference only:
`../parent-v189-core-local-capability-brief.md` and
`../parent-v187-local-isolation-safety-plan.md`.

No other first-party module was read. No SDK source was read. Nothing outside
this repository and those two parent documents was read.

## Sourceonly discipline

No command was executed. No file was imported. No test was run. No Git
operation. No network, provider, credential, installation, lock, binary, model,
dataset, wheel, global setting, provider, model or asset change. No subprocess,
thread or async task was started by this session. No delegation. The only tools
used were read, list, search and write.

Consequence: every counter, gate and timing number below is a prediction from
the source paths, not an observation. The candidate has never been parsed by an
interpreter, let alone run.

## What was written

One standalone Python file with exactly three fixed modes and no other entry
points:

1. Harness (no argument): registers the run-wide nonce ledger, runs the seven
   named numeric cases in order, prints one `CASE` line per case plus `TOTAL`
   and `RESULT`, and returns 0 or 1.
2. `--spike-child <fd>`: the fixed child. One inherited descriptor, one leased
   absolute deadline, the fixed READY -> ack_ready -> request_open ->
   grant_open -> request_create -> grant_create -> ONE op -> ack_create flow.
3. `--spike-sentinel <fd>`: the fixed arm witness. Waits for one `arm` frame,
   replies `armed`, exits 0.

`main` returns `EXIT_INTERNAL` (2) for any other argument shape, so there is no
undocumented fourth mode.

## Case inventory: exact names, budgets and gate counts

Every case appends the same two cleanup gates (`cleanup_errors_0`,
`retained_roots_0`) in its `finally` block, after the primary gates.

| # | Case name | Budget | Primary gates | + cleanup |
|---|---|---|---|---|
| 1 | `case1_absent_endpoint_or_replay_zero_ops` | 1.00 s | 11 | 13 |
| 2 | `case2_wrong_session_zero_ops` | 0.50 s | 9 | 11 |
| 3 | `case3_create_before_armed_or_dead_sentinel_zero_ops` | 1.25 s | 10 | 12 |
| 4 | `case4_valid_ready_open_armed_create_one_op` | 2.00 s | 14 | 16 |
| 5 | `case5_duplicate_reordered_seq_zero_additional_ops` | 0.50 s | 7 | 9 |
| 6 | `case6_second_admission_rearm_extended_deadline_zero_additional_ops` | 0.75 s | 15 | 17 |
| 7 | `case7_disconnect_after_consumed_permit_at_most_one_op` | 1.75 s | 12 | 14 |
| | | **7.75 s** | **78** | **92** |

Total gate: `elapsed < 8.00 s`. Harness exit 0 on PASS, 1 on FAIL, 2 if the
harness itself broke.

## Exact expected counters

Predicted by tracing the source paths. Not observed.

C1 (`ops exit_absent exit_replay grants_open_src grants_open_b grants_open_c
refusals_c reason_c retries reissues lease_exits`):
`ops=0 exit_absent=3 exit_replay=6 grants_open_src=1 grants_open_b=0
grants_open_c=0 refusals_c=1 reason_c=session_mismatch retries=0 reissues=0
lease_exits=0`

C2 (`ops refusals_a reasons_a last_seq_a exit_b grants_open grants_create
retries lease_exits`):
`ops=0 refusals_a=2 reasons_a=session_mismatch|session_mismatch last_seq_a=1
exit_b=6 grants_open=0 grants_create=0 retries=0 lease_exits=0`

C3 (`ops grants_open grants_create armed_acks arm_failures refusals_total
reasons retries lease_exits`):
`ops=0 grants_create=0 armed_acks=0 arm_failures=2 refusals_total=5
reasons=not_armed|sentinel_dead|not_armed|sentinel_absent|not_armed retries=0
lease_exits=0`

C4 (`ops marker_mode marker_lines worker_exit sentinel_exit grants_open
grants_create armed_acks refusals acks_create retries reissues lease_exits
elapsed_s`):
`ops=1 marker_mode=0o600 marker_lines=1 worker_exit=0 sentinel_exit=0
grants_open=1 grants_create=1 armed_acks=1 refusals=0 acks_create=1 retries=0
reissues=0 lease_exits=0 elapsed_s<=2.000`

C5 (`ops grants_open grants_create refusals reasons last_seq retries`):
`ops=0 grants_open=1 grants_create=0 refusals=7 last_seq=2 retries=0`
`reasons=seq_not_monotonic|seq_not_monotonic|metadata_oversize|duplicate_keys|nonfinite|seq_not_monotonic|extra_fields`

C6 (`ops admissions grants_open grants_create armed_acks arm_failures refusals
reasons nonce_replay_refusals sentinel_exit retries`):
`ops=0 admissions=1 grants_open=1 grants_create=0 armed_acks=1 arm_failures=1
refusals=3 nonce_replay_refusals=1 sentinel_exit=0 retries=0`
`reasons=deadline_extension|second_admission|rearm_refused`

C7 (`ops_a lines_a ops_b exit_a sentinel_exit_a state_a state_b ambiguous_b
grants_create_total second_grants retries reissues lease_exits`):
`ops_a<=1 lines_a=1 when ops_a=1 else -1 ops_b=0 exit_a in (0,4)
sentinel_exit_a=0 state_a=consumed state_b=consumed ambiguous_b=1
grants_create_total=2 second_grants=0 retries=0 reissues=0 lease_exits=0`

Every case: `cleanup_errors=0 retained_roots=0`.
Harness: `TOTAL elapsed_s<8.000 gate_s=8.00 PASS`, `RESULT PASS`, exit 0.

## Remaining gaps, named

MISSING (no code, by design):

- M1. No production owner, no billing/reservation owner, no watchdog change, no
  `train/` or `spec/` production amendment.
- M2. No SDK interaction of any kind. No image build, no filesystem
  provisioning, no secret or entitlement use.
- M3. No `os.fork`, no `preexec_fn`, no pickling, no `multiprocessing`.
- M4. No retry, reissue, reconnect or rearm code path exists anywhere. The
  `retries` and `reissues` counters are structurally always 0; they are
  declared to prove absence, not to count occurrences. A reviewer who expects
  them to be able to go non-zero will find they cannot.
- M5. No fourth child mode, no `shell=True`, no `os.system`, no `eval`, no
  `exec`, no `__import__`.
- M6. No signal-by-PID. Signals travel only through the retained `Popen`
  handle, poll-checked first, never after reap.
- M7. No global setting, trust, provider or model change.

SHORTCUT (declared substitutions, each marked in the source):

- S1. `ScriptedPeer` is a parent-owned writer on the child end of a
  socketpair. It emits byte-identical frames but is not a real child, and it
  cannot perform the witnessed operation at all. Used in C2a, C3a/3b/3c, C5,
  C6, C7b. Every one of those cases keeps at least one REAL `subprocess.Popen`
  fixed child or sentinel for the exit-code claim (C1a, C1b, C2b, C3b, C4,
  C6, C7a).
- S2. C5's seven protocol violations are harness-authored frames. The strict
  decoder they hit is the same `decode_and_validate` the real child uses.
- S3. `_new_controlled_sentinel_link` pre-scripts the `armed` reply on a
  harness-held channel end. Used only in C7b, where the sentinel is not the
  subject of the assertion. C4 and C6 arm a REAL fixed sentinel process.
- S4. The witness root is `tempfile.mkdtemp(prefix="v189-cN-")` under the
  inherited `TMPDIR`. Private (0700) and owner-owned, but not a purpose-built
  isolation boundary.
- S5. The "tiny synthetic operation" is one
  `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` open of `spike-op.marker`, an explicit
  `fchmod(0o600)`, exactly one appended line and one `fsync`. It proves the
  dispatch chain, not any real workload.
- S6. The child safety lease is a daemon `threading.Timer` firing
  `os._exit(97)` at 8 s monotonic, started by the child itself. Independent of
  the parent, but not a kernel-level guarantee.
- S7. The 10 s external parent timeout is declared in the plan only. This file
  cannot enforce a timeout on its own invoker; the parent owns that.
- S8. Socket buffers are widened best-effort to 262144 bytes per end so the one
  oversize-metadata injection in C5 cannot deadlock the harness against a
  same-thread reader. `ScriptedPeer` also falls back to a daemon writer thread
  when a payload exceeds the achieved send buffer minus 64 bytes. If
  `setsockopt` is refused on the target platform, the threaded path carries it;
  either way C5 must still produce exactly 7 refusals.

UNVERIFIED ASSUMPTIONS (the first real run settles these):

- U1. `socket.socket(AF_UNIX, SOCK_STREAM, 0, fd)` plus `getsockname()` raises
  `OSError` for an absent descriptor, so C1a's `exit_absent=3` is structural
  rather than timing-dependent.
- U2. `subprocess.Popen(..., env={"PATH": "/usr/bin:/bin"})` starts
  `sys.executable` successfully with no inherited environment. If the host
  interpreter needs a variable this file does not set, every real-child case
  fails at spawn and is reported as NONPASS, not as a silent pass.
- U3. Two interpreter cold starts plus the full C4 flow fit inside 2.00 s, and
  all seven cases fit inside 8.00 s, on the target machine. Estimated actual
  total is around 2.5 s, dominated by C7b's 0.50 s scripted-silence wait.
- U4. `tempfile.mkdtemp` returns a path for which `os.path.normpath(p) == p`,
  so `_validate_root` accepts the parent's own root. macOS resolves the
  `/var` -> `/private/var` symlink inside `mkdtemp` before returning, but this
  has not been observed here.

## V187 constraint compliance

- Immediate descriptor protection: every socketpair end is tracked in
  `Resources` at creation; every `Popen` at spawn; every root at `mkdtemp`.
  `_spawn_worker` and `_spawn_sentinel` close the parent's copy of the child
  end immediately after `Popen` returns, before any wait.
- Independent cleanup: `Resources.cleanup` runs three loops, each item in its
  own `try/except`. One failure never skips another item and never masks the
  primary error.
- Snapshot only after reap: every case snapshots the witness root after the
  worker's `_reap` returns, never before.
- Containment errors are NONPASS: any exception escaping a case body becomes
  `internal_error` plus a `("internal_error", False)` gate in the harness, so
  it cannot pass. Cleanup failures append `cleanup_errors_0` and
  `retained_roots_0` in the `finally` block, after the primary gates, so they
  cannot be skipped.
- Failed cleanup keeps ownership: `reap_failed` retains every root instead of
  releasing it, which fails `retained_roots_0`.

## Two theses, and what would falsify each

Thesis 1 (copied JSON alone performs zero operations): falsified if any case
other than C4 and C7a reports `ops > 0`, if C4 reports `ops != 1`, or if any
`grants_create` counter is non-zero in C1, C2, C3, C5 or C6.

Thesis 2 (one live parent session cannot be replayed, replaced or rearmed):
falsified if C1 `exit_replay != 6` or `grants_open_b != 0`, if C2
`refusals_a != 2` or `exit_b != 6` or `last_seq_a != 1`, if C3
`armed_acks != 0` or `arm_failures != 2` or `refusals_total != 5`, if C5
`refusals != 7` or the ordered reason string differs or `last_seq != 2`, if C6
`admissions != 1` or `second_admit_sent_no_frame != 0` or
`nonce_replay_refusals != 1`, or if C7 `second_grants != 0` or `state_a` /
`state_b` is not `consumed`.

## Execution contract

Parent-owned. To run: `python spec/spikes/local-capability-candidate.py` with
no arguments, under a 10 s external timeout. Exit 0 means PASS, 1 means FAIL, 2
means the harness itself broke (NONPASS). Nothing in this report should be
treated as a result until the parent has run it and recorded the seven `CASE`
lines verbatim.

## Handoff

Nothing here changes Track A. The V159 host interface names consumed by Track C
are untouched. This spike owns no production surface and amends no billing,
watchdog or reservation owner.

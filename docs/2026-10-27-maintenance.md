# Repository maintenance, 2026-10-27

This work follows the repository/Obsidian organization pass. It does not
complete the product, prove model improvement or submit an application.
Validation continued on 2026-10-28.

## Changes

- Register `--controller-mutant` in `train/conftest.py`, where pytest loads
  command-line options before collection. Previously the hook lived inside a
  test module and ordinary invocation rejected the flag.
- Correct the mutation example in `ptc/README.md` to use `ptc/harness.py`.
- Add a coordinated SQL result/exit protocol. Workers hold their provisional
  result while the host closes the sampler scheduling gate and drains any
  reserved sample. A single exit grant binds the request and exact result
  bytes. STOPPED still precedes retirement, joins, deletion and absence proof.
- Preserve failure cleanup when journal writes fail. If durable cleanup intent
  cannot be saved, absence remains unproven and the reservation stays blocked.
- Preserve the original success deadlines through cleanup and prevent the
  controller from accepting a provisional outcome.
- Add an immutable pending marker before reservation removal, a bound terminal
  acknowledgement after successful release fsync, and a controller-authored
  commit. Missing acknowledgement or uncertain finalization must block success
  and future admission, even if the active-reservation file is already absent.

The protocol amendment and its test criteria are in
[the implementation plan](../spec/sql-skill-pilot-plan.md) and
[pilot contract](../spec/sql-skill-pilot.md). Live wire schema is now 2;
old profiles must not silently authorize changed source or wire behavior.
Record/profile schema versions are unchanged.

## Executed checks

| Check | Result |
|---|---|
| Original mutation-option invocation | Reproduced pytest exit 4 before the fix. |
| Fixed controller suite | 136 passed. |
| Database-pin bypass control | Two intended assertion failures, exit 1; not collection errors. |
| Corrected mutation target | Resolves to the existing `ptc/harness.py`. |
| Final SQL runtime suite | 678 passed in 38.63 seconds; all 568 prior node IDs retained, including the 428 original IDs. |
| Finalization sensitivity controls | Pending-admission, required-ACK and outcome-digest bypasses each caused their intended assertion failure. |
| Full default offline suite | 3,653 passed in 339.95 seconds; one optional Torch skip, two tokenizer deselections, ten existing fork warnings. |
| Protected accounting/scoring files | All four byte-identical to the pre-change commit. |

The first SQL invocation denied even owned UNIX sockets and therefore failed
fixture setup. A verified UNIX-only network policy allowed those fixtures
while denying TCP. Under that policy the first implementation had two failing
sensitivity controls; both were repaired before the 568-pass run.
Those failed logs are retained, not counted as acceptance.

Review then found a post-unlink fsync failure could leave provisional success
artifacts without a durable admission barrier. The pending/ACK/commit
transaction replaces that absence-based decision. Its first test execution
recorded 574 passes and 104 failures, exposing an incorrect request-digest
context and two superseded unresolved-fixture expectations. Passing the actual
request digest and asserting the nonce-bound unresolved block fixed those
failures. Python, general and security reviewers independently identified the
digest regression; the final suite exercises both roles and clean typed aborts.
The Python reviewer reread and approved the final digest and fixture corrections.

The full run used the existing Python environment, denied external networking
and allowed only owned UNIX sockets and loopback fixtures. Final Python source
hashes were unchanged across execution. Python, general and security static
reviews found no other actionable issue in the revised protocol. These checks
do not replace live lifecycle acceptance.

An initial full-suite run recorded 3,506 passes and 37 failures because macOS
`sandbox-exec` forbids the setuid system `ps` used by existing liveness fixtures.
The existing offline-harness specification describes this host limitation.
A fresh validation-only SDK `libproc` observer was checked against real live,
unreaped and reaped children, with system `ps` comparison outside the sandbox.
Injected observer failure was rejected by the actual liveness guard.
With that observer on the validation process's PATH, all 135 process-watchdog
and SQL-sweep tests passed under unchanged external-network denial, with zero
errors in 129 recorded native observations. No repository test or production
liveness rule was changed to accommodate the sandbox.
The final full-suite run added 188 native observations, bringing the combined
ledger to 317, with zero observer errors.

## Separate RSS diagnosis

All seven MLX evidence manifests and 568 listed entries matched before
diagnosis and again after the fixes. Only fresh scratch copies were instrumented:

`~/scratch/co-train-rss-diagnosis-2026-10-27/cpu-_4p5fd36/`

- Unmodified supervisor/channel tests: 45 passed.
- Instrumented tests: 54 passed, including 300-ms parent/helper/partial-reply
  delays and a stale-sequence failure control.
- Unmodified 303.032-second CPU control: 5,948 accepted samples, no probe error.
- Instrumented 303.050-second CPU control: 5,900 accepted samples, no probe error.
- Both workers/helpers reaped, no cleanup error. Separate Python and security
  static reviews found no actionable issues in the diagnostic changes.

The scratch `RESULTS.md` and reports preserve commands, source hash, timing and
limitations. This is low-memory CPU evidence, not MLX/Metal contention.
Instrumentation improves future failure attribution; the historical seed7002
timeout remains unexplained and is not claimed fixed.

## Remaining boundaries

- No new Docker/native lifecycle trial, model call, training, holdout, install,
  download, paid service, push or submission ran.
- The financial gate remains closed. Existing one-shot trial permissions are
  consumed; new real acceptance requires explicit approval and fresh bindings.
- Actual guardian crash/restart at grant boundaries, grant-token corruption and
  real owned CLI/UNIX-HTTP unwind through drain remain unverified.
- Offline tests cannot establish kernel confinement, actual container limits,
  Docker stats reliability or production cleanup timing.
- The failed SQL lifecycle receipt and sealed MLX evidence remain historical
  evidence. Neither is replaced by passing offline checks.

# Bounded direct-evaluator native acceptance, 2026-10-29

Completed authorized native evidence, separate from the
[final offline qualification/timing acceptance](2026-10-29-sql-qualification-evidence.md).
This is direct-evaluator lifecycle coverage, not native file-SDK acceptance.

## Result and cleanup

Three tests passed with 19 native jobs (10 PROGRAM, 9 SCORER), zero retries and
zero model calls. Source and independent rescore were valid EX=0; all four
qualifications and two separate fresh-process reuses were valid EX=1.
The wrong promotion pin dispatched nothing.

Five historical source/qualification DB files were moved out of their recorded
paths and preserved, not deleted. Both fresh reuse processes operated while
those paths were unavailable.

All 19 jobs CLOSED, each with matching pending/committed finalization evidence.
All 75 recorded owned actors and fresh children were absent afterward; active
reservations and unclosed blocks were zero. Ten unrelated containers retained
the same IDs/state. Normal owned-container DELETE cleanup occurred.
This is not a claim of no deletions or global host clearance.

Maximum observed cleanup was 0.241047542s against a 12-second bound.
There were 56 memory samples, maximum observed interval 0.291s, minimum observed
headroom 703,954,944 bytes; post-run headroom 729,161,728 bytes.
Observed FD/thread deltas were zero. All 145 native-trial frozen source files
and three configuration files remained unchanged.

## Environment and incidents

The existing VM profile was booted with activate/save-config/SSH-config changes
disabled; all three configuration hashes matched. Boot logs show emulator
registration and Docker provisioning. No download was observed; this does not
mean no provisioning occurred.

A stale VM PID marker was reversibly quarantined, without signaling a reused
system PID. The VM remained running to preserve unrelated workloads.
Two scratch-parser mistakes were corrected without another native trial.
They are evidence-processing incidents, not retries or product fixes.

## Receipt and acceptance boundary

Local receipt:
`~/scratch/co-train-2026-10-29/native-readiness/authorized-native-w4nahdg7/trial-final-receipt.json`.
SHA256:
`4bbeea95b03b76a5fd0f39b0c27f6622746fad117633c491741e85ea739f4677`.
Its sibling `artifact-manifest.json` inventories 1,137 local files, all verified
present. Original logs/receipts remain local scratch; a clone does not contain
this native environment or its evidence.

The later complete offline suite passed 3,793 tests, one optional Torch skip,
two configured tokenizer deselections, ten warnings and 28 subtests, exit 0 in
725.24s, followed by 28 independent probes and three intended RED/restored GREEN
controls. It retained an earlier interruption, then 3,792-pass/one-failure
bench-package regression, repaired by moving an unchanged SDK test to train.
These counts overlap; the offline result is not another native campaign.
The correction changed no production timing/evaluator/SDK bytes or native
closure. Final offline verification confirms 16 native-closure files and four
protected files match HEAD; it does not extend native coverage.

Native SDK, full adversarial OOM/timeout/guardian-fault coverage, provider/model
latency, billed economics and team benefit remain unproved. This bounded pass
does not retroactively turn the earlier failed trial into success or establish
its root cause. The earlier
[trial failure](../spec/sql-skill-pilot-handoff.md#latest-real-trial-failed-safely-closed)
remains historical evidence.

This receipt itself grants no additional native trials, paid/model calls,
workload shutdown or deployment permissions. Separate standing Git instructions,
consumed one-shot permissions and financial gates remain unchanged.

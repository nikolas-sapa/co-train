# Local stop-command gate reference

PROVES: a parent-owned gate can OS-exec a fixed command in the same PID/group/
session, preserving the original Popen handle. Three fresh local cases passed:
normal trigger, genuine controller EOF before trigger, and controller death
after a resistant command starts. The command remains separately containable
after worker/controller death.

Accepted source: 28,389 bytes, SHA256
`e063bcbb4324cec8882ae141e22464020ec386ae83c66f57adc64188e7cae08a`.
The source is byte-exact from parent V208. Its preserved SOURCEONLY UNRUN
header describes author-time status; parent execution receipts below supersede
that status for this exact version only.

## Observed evidence

- Default baseline: 3 PASS, 9 actual children reaped, 3 exec/command/marker
  witnesses, 11 fresh challenges. Total0.26022016699789674s after base removal;
  worst TERM/challenge/KILL/reap0.0015814170001249295s. Zero cleanup errors,
  retained objects or leftover managed directories.
- Eight causal/fault profiles: 33 additional actual children reaped, no unknown
  actual reaps, lease exits or open owned socket FDs. Premature post-fire
  controller exit, missing reap observation, expired spawn, expired wait guard
  loss/restore, teardown timing, and journal prerequisite loss/restore all
  produced their required stage-specific witnesses.
- Timing fault included both injected tails: C1 elapsed2.6243916249986796s
  and whole run4.815130082999531s. It correctly failed original timing gates.
- Original C1 failed before this repair. A diagnostic captured ENOENT when
  gate and controller both initially created the journal. Parent now creates
  the empty0600 journal before spawning; child appends omit O_CREAT. No retry
  or relaxed expected result was added. Missing parent creation fails
  deterministically; restoring it makes C1 pass.

Parent evidence lives in the continuation workspace:
`parent-v208-stop-gate-execution.json`,
`parent-v209-stop-gate-baseline-verification.json`,
`parent-v209-stop-gate-controls-plan.md`,
`parent-v209-stop-gate-controls-{preparation,execution}.json`,
and `parent-v210-stop-gate-reference-acceptance.json`.
Individual control receipts are `parent-v209-control-*-execution.json`.
Failed V205 and diagnostic V206/V207 source/receipts remain preserved.

## Limits

SHORTCUT: trusted same-user local processes, harmless marker command, Python
timer leases and responsive local OS/filesystem. The original 2.5s case,
8s total, 10s external, .5s challenge, 1s stop and 2s operation limits were
not increased.

SHORTCUT: reap-observation fault throws after a real OS reap. It checks
bookkeeping refusal and actual-object retention, not an unresponsive kernel
or an actually unreapable live child. Negative controls deliberately retain
inert private roots. No old roots were removed.

MISSING: real SDK stop executable, production delegated watchdog/isolated
owner/worker integration, remote completion, provider billing/charged-end
proof, native execution and scientific qualification. This is a mechanism
reference, not a production foundation or authority to launch paid work.

# Mutation subprocess lifetime

## Tests before implementation

Six real-process checks failed against `91b90bd` in 5.71 seconds: Step2/train
exceeded the independent 2.5-second supervisor deadline; PTC left a TERM-ignoring
descendant alive after its leader exited. All three left a descendant alive
after a successful leader exit with closed output pipes.

Acceptance:

- All three runners clean their original POSIX process group on completion,
  a 0.15-second suite deadline, KeyboardInterrupt and SystemExit(7).
- A leader's early exit must not prevent KILL of a TERM-ignoring descendant.
  Total fixture execution stays below three seconds.
- Direct children are reaped. Captured stdout/stderr remain exact and appear
  once. Completed statuses 0, 7 and 124 remain unchanged.
- Inherited output pipes have a separate bounded drain, even when a deliberately
  escaped fixture retains one. The independent supervisor cleans that escape.
- An interruption during the TERM-grace wait, or a signaling failure, still
  closes both captured streams and attempts a bounded reap. Preserve the first
  exception; annotate any later escalation, closure or reap failures.
- All three runner adapters retain incomplete-drain warnings. The PTC CLI
  prints them even when its timeout policy counts the mutant as killed.
- Invalid/nonfinite/nonpositive timing bounds cause zero launches.
- Real isolated baselines, existing status classification and all 52 registered
  mutation anchors remain valid.

Fixture loops expire after five seconds; the readiness handshake has a separate
one-second cap. They run under an independent 2.5-second supervisor. Finally
cleanup targets only recorded fixture PIDs/groups. Tests distinguish zombies
from running descendants.

## Implementation

Add stdlib-only `process_watchdog.run_bounded`, returning CompletedProcess on
completion and raising TimeoutExpired after cleanup on deadline. Preserve an
interruption after cleanup. Save the group ID as the session-owning child's PID;
never rediscover it through an exited leader.
Preserve all nested cleanup notes on the original interruption. Snapshot notes
before adding them when the same exception instance is raised twice.

TERM, bounded wait, then KILL the original group regardless of leader exit.
Bound final pipe drainage and direct-child reap separately. Close captured
streams, and report an incomplete drain without waiting indefinitely.

Each runner uses its existing command/environment with a 300-second suite
deadline, bootstraps the helper import for direct-script execution, and copies
the flat helper into fresh sandboxes. PTC keeps timeout as killed(timeout);
Step2/train keep it INVALID. Every nonzero baseline remains invalid.

## Review regressions

Python review found an escalation-error path that bypassed stream closure/reap,
and adapters that discarded escaped-pipe exception notes. The parent reproduced
10 failures with three passing controls before the fixes. The updated group
passed 151 checks, excluding only the three expensive real isolated baselines
then reserved for the final default suite. No production thresholds changed.
Security re-review then exposed lost secondary diagnostics at the public API.
Two regressions failed before repair; a guarded shared-exception case failed
before the note snapshot. The final targeted group passed 154 checks.

Both specialists re-approved the final code. The final offline warm-cache
default suite passed 1277 tests, with one optional torch skip, in 147.57 seconds.
It includes all 79 lifecycle and 78 mutation-harness cases and the three real
isolated baselines. These groups overlap; do not add them to the default total.

## Non-goals

No Windows support, OS sandbox, escaped-process containment, output-volume
limit, bench daemon cancellation, scientific contract changes, model/training
execution, paid services or push/deploy.

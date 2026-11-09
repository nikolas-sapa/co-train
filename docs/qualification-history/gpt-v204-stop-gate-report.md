# V204 stop-gate repair report, SOURCEONLY UNRUN

Delivered only three new assigned files:

- `docs/gpt-v204-stop-gate-plan.md`, numeric plan written first.
- `spec/spikes/gpt-v204-stop-gate.py`, standalone stdlib candidate.
- `docs/gpt-v204-stop-gate-report.md`, this handoff.

Source is about 660 lines versus frozen V202's reported 1602. It modestly
exceeds the approximate 400-600-line aim to retain explicit reap/ownership,
filesystem-operation timing and failure-reporting guards. No production
framework or API was added.

All old files, including V194 and V202, were left read-only. No Git/checksum
comparison was performed. Reads were limited to own AGENTS, the V204 brief,
frozen V202 source/plan/report, and the new authored artifacts.

## Five frozen blockers addressed in source, NOT verified

| Blocker | Candidate change | Required parent evidence |
|---|---|---|
| Controller returned immediately after trigger | Controller increments its one-use fire latch before dispatch, sends the trigger and fired reply, then continues serving fresh challenges. Only explicit parent quit returns 0. | C1 challenges after fire before quit/reap 0. C3 challenges AFTER command started, observes the retained controller currently live, then actually kills/reaps it -9. |
| Failed reap became None and permitted snapshots | `join` returns an observed integer or raises. `record_exit` checks the actual Popen returncode. Snapshot requires all three retained roles and all three observed reaps, then rechecks actual codes. | No journal/marker read or root removal on incomplete/unobserved reaps; NONPASS with retained owner. |
| Expired waits renewed; fresh TERM/cleanup budgets; unchecked spawn | All waits take minima of fixed run/case/operation bounds, with no epsilon. Every Popen has an immediate deadline check. TERM resistance uses a challenge inside the same <=1 s stop bound. Cleanup reaps share one deadline clamped to the original case end; expired cleanup uses wait(0) only. | Original <=0.5 s challenge, <=1 s stop, <=2 s operation, <=2.5 s fixture and <8 s total gates; expiration controls must refuse spawn/renewal. |
| Failed owners lost when loop variable changed | `Run.owners` retains every Fixture. Module-level `RETAINED` keeps actual failed Fixture/Run objects with their Popen, socket and root references. FD/process cleanup attempts are independent; primary and cleanup failures remain separate. | First-fixture failure remains owned while later fixtures run. Failed containment keeps paths and handles, never only root strings. |
| Timing rounded/captured before final cleanup | Case elapsed is unrounded and captured after process/FD cleanup, witness snapshot and root disposal. Total is captured after base disposal. Filesystem operations have explicit measured local caps too. No timing is rounded in the output. | Delayed fixture/base cleanup must affect its gate and produce NONPASS. Parent measures fresh-process wall time separately. |

These are source changes, not passing test results or review approval.

## Exact three cases and planned counters, all UNRUN

Every fixture expects:

- Actual `popen_attempts=3`, `popen_successes=3`, three distinct retained PIDs.
- `arm_acks=1`, `started_replies=1`, `trigger_parent_copies=0`.
- Command started PID/PGID/SID and marker PID equal the original gate Popen PID.
  `original_gate_handle=true` comes from actual object identity.
- Post-reap journal counts `exec=1`, `command=1`, `marker=1`.
  Marker files 1, lines 1, mode 0600; journal also mode 0600.
- All three actual reaps, empty cleanup errors, root released, no lease exit.
- Fixture elapsed <=2.50 s AFTER teardown. Every challenge <=0.50 s,
  every planned kill/join or TERM/challenge/KILL/join <=1.00 s,
  every other local operation <=2.00 s. All bounds use unrounded values.
  Combined containment/FD cleanup shares one measured <=1.00 s bound and
  never receives time beyond the original case end.

| Case | Expected observations, not results |
|---|---|
| `C1_normal_original_handle` | Worker TERM/challenge/KILL/reap -9; controller and gate fresh responses after worker death; one fire dispatch and one fired reply carrying actual `fires=1`; started via trigger; original gate handle reaps normal command 0. Controller still responds after fire, then explicit quit/reap 0. Four fresh challenge responses. Fire journal count 1. |
| `C2_controller_eof_original_handle` | Controller and gate fresh responses before controller KILL/reap -9; fire dispatches 0 and no fire journal event; clean sole-writer EOF causes started via eof and original gate handle reap 0. Worker independently TERM/challenge/KILL/reaps -9. Three fresh challenge responses. |
| `C3_controller_dies_during_resistant_command` | Fire/started via trigger first. Actual command pulse thread is alive with ticks >0 and actual SIGTERM-ignore disposition. Fresh controller response and live-handle check precede controller KILL/reap -9. Worker independently TERM/challenge/KILL/reaps -9. Command answers after both other-group deaths, then TERM/fresh-challenge/KILL/reaps -9 through the original gate group. Four fresh challenge responses. Fire journal count 1. |

Nominal run inventory, derived from source only: 3 fresh fixture roots,
9 Popen attempts/successes, 3 gate exec events, 3 command events, 3 markers,
2 controller trigger events, 11 fresh challenge responses. No command spawn,
no replacement Popen. Every event count is read from the actual journal or
instrumented call boundary, not a declared constant success counter.

Runtime JSON records contain actual owned PIDs, challenges and echoed tickets,
signal target/role events, observed reaps, byte/record counters, operation
timings, journal counts and marker data. Expected zeros are compared against
observations; no fabricated retry/reissue counters.

Run-level acceptance requires all three cases, actual Popen counts 9/9,
no retained objects/errors, base released and total elapsed <8.00 s.
Exit 0 means runtime gates passed; 1 means NONPASS. Invalid fixed-mode
invocations/internal child errors return 2. Timer exit 97 is never accepted.
The external 10.00 s cap belongs to the parent.

## FD and exec custody

Four socketpairs per fixture:

| Channel | Parent retains | Passed endpoints and immediate closure |
|---|---|---|
| Parent-worker | Worker parent end | Only worker inherits peer; parent closes that peer immediately. |
| Parent-controller | Controller parent end | Controller inherits peer plus trigger writer; parent closes both immediately. |
| Parent-gate | Gate parent end | Gate inherits peer plus trigger reader; parent closes both immediately. |
| Controller-gate | Neither endpoint | Only controller holds writer and only gate holds reader. Other children inherit neither. Actual parent socket-object FD states must count zero open copies. |

All parent spawns use current Python with `-I -S -B`, close_fds, explicit
pass_fds, new session, DEVNULL stdio and minimal PATH/private TMPDIR.
Gate closes its trigger endpoint before exec and explicitly makes only the
parent-channel application FD inheritable. Standard DEVNULL descriptors remain.
Its sole exec call targets current Python, the same source and fixed command
mode. Sequence state, original case I/O bound and unchanged run expiry travel
in trusted argv. Command never spawns, execs or creates a new session.

The gate function is gone after exec and command owns no trigger endpoint.
Later controller EOF therefore cannot launch another command; the post-reap
journal must still contain exactly one exec and one command entry.

## PROVES, planned only until parent execution/review

- Original parent Popen custody and same PID/group/session survive fixed exec.
- Genuine controller EOF before trigger causes exactly one fixed exec with
  no hidden writer copy and no replacement process.
- Controller death during a real resistant, thread-active command does not
  remove parent stop/reap custody or kill another group.

No such process, signal, exec, challenge, counter or timing was observed by
this author.

## SHORTCUT / MISSING

- Synthetic marker command, trusted same-user fixed code, one fixture at a time.
  Gate ARMED means its trigger channel is installed, not production authority.
- `exec` journal records intent before the actual exec; actual replacement
  additionally requires command-start journal, started frame, same PID facts
  and original-handle reap. A marker alone cannot establish the topology.
- Heartbeat ticks come from an actual daemon pulse thread; `pulse_alive`
  inspects that thread and `term_ignored` inspects the current signal handler.
  TERM survival uses a fresh post-signal response, not a timeout-only claim.
- Python timer fallback cannot bound interpreter startup, wedged runtimes,
  unresponsive OS/filesystem syscalls or signal delivery. Every mode, including
  exec target, arms the same harness-start +8 s lease before channel I/O.
  No lease is restarted at now+8.
- Fresh-process/default-entry timing, syntax/lint, Python/security review,
  all three cases and all five parent red controls are UNRUN. No numeric limit
  was relaxed. Source inspection does not establish measured headroom.
  The controller red control is marked after the valid fired reply so earlier
  protocol stages stay valid and cannot mask the liveness check.
- Existing checks run: NONE. Newly written checks: the three named cases and
  shared deadline/reap/FD/journal guards. Newly written checks run: NONE.
- Production API/schema/defaults, sealed authorization, SDK lifecycle, real
  provider stop, watchdog delegation, budgets, paid/native/tensor/science
  proof remain MISSING. Earlier capability and OS isolation evidence is
  separate; it was not rerun or extended here.

VERIFY_REAL: SOURCEONLY UNRUN. Parent executes and reviews; no approval.

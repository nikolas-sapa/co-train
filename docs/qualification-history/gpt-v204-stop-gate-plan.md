# V204 stop-gate numeric plan, SOURCEONLY UNRUN

Written before implementation. Parent executes, measures and reviews. Frozen
V202 and working V194 remain read-only. No result below is observed.

## Numeric test plan FIRST

Exactly three fresh fixtures. Each creates exactly three parent-owned Popen
children, worker/controller/gate, in separate sessions/groups. Command replaces
gate by fixed OS exec, never another spawn. Every fixture uses a fresh nonce
and private root inside a private base selected through the parent's TMPDIR.

| Named test | Required observations, not results |
|---|---|
| C1 `normal_original_handle` | Popen attempts/successes 3/3; gate ARMED 1. Worker has a live heartbeat thread and actual SIGTERM-ignore disposition. Parent sends TERM to its retained worker group, obtains a fresh resistant/thread-active challenge response, then KILLs/reaps worker -9 within 1.00 s total. Controller and gate each answer fresh challenges within 0.50 s after worker death. Fire dispatch 1, controller fired reply 1 with observed trigger count 1, gate-to-command started reply 1. Command PID/PGID/SID equal the original gate handle's PID, journal exec/command/marker counts each 1, exclusive 0600 marker count 1 containing actual command PID and nonce. Original gate handle reaps command 0. Controller still answers after fire, remains alive until explicit quit, then exits/reaps 0. |
| C2 `controller_eof_original_handle` | Popen attempts/successes 3/3; controller and gate challenged before controller death; both parent copies of the controller-gate channel are actually closed. Controller group KILL/reap -9 within 1.00 s, before any fire. Gate observes clean EOF at record boundary, journal exec/command/marker counts each 1, trigger/fire journal count 0, started via `eof`, PID equals original gate Popen PID, normal command exits/reaps 0 through that handle. Worker separately TERM/challenge/KILL/reaps -9 within 1.00 s. |
| C3 `controller_dies_during_resistant_command` | Popen attempts/successes 3/3; genuine fire then started via `trigger` first. Actual command PID equals retained gate PID; its heartbeat thread is active and SIGTERM disposition is ignore. AFTER started, controller must answer a fresh independent challenge and be observed currently live BEFORE KILL/reap -9. Worker separately TERM/challenge/KILL/reaps -9. Command survives both other-group deaths and answers a fresh challenge within 0.50 s. Parent then TERM/challenge/KILL/reaps its original unreaped gate group -9 within 1.00 s. Exec/command/marker journal counts each 1 despite later controller EOF; fire count 1; no additional Popen. |

Every fresh challenge includes a new random ticket, exact echo, strict sequence,
actual PID/group/session, actual heartbeat/thread state and actual signal
disposition. Reported PID is a comparison witness only, never a signal target.
TERM survival is checked with a fresh response under the SAME stop deadline,
not a fresh fixed-duration wait.

Each fixture must observe all THREE actual reaps before ANY marker/journal
snapshot or root removal. Incomplete construction cannot silently become an
empty successful fixture. A join returns an actual observed code or raises.
Unknown exits, lease exit 97, forced cleanup, missed bounds, nonempty cleanup
errors, or retained ownership are NONPASS. Preserve primary and cleanup errors.

Numeric gates, all original limits unchanged:

- Each fixture <=2.50 s, unrounded, measured AFTER independent process/FD
  cleanup, witness snapshot and root removal.
- Each local operation <=2.00 s; each fresh challenge <=0.50 s; every kill/join
  or TERM/challenge/KILL/join <=1.00 s, including all its phases.
  Root creation, combined witness snapshot/root release, and base creation/
  removal also have measured <=2.00 s gates, not just channel operations.
  Combined containment/FD cleanup has one measured <=1.00 s bound shared by
  all its reaps, additionally clamped to the original case end.
- Total <8.00 s, unrounded, measured AFTER all fixture cleanup AND base removal.
  Expected real Popen attempts/successes 9/9, exec journal events 3, command
  events 3, markers 3, retained objects 0, cleanup errors 0.
- External parent cap 10.00 s, owned by the invoker, not this program.
- One immutable harness-start +8.00 s monotonic lease goes to all modes and
  through exec. Every child arms it before I/O. Command immediately re-arms
  the SAME expiry because exec destroys gate's timer.
- Case deadline is min(shared expiry, case start +2.50 s). Reserve 0.25 s for
  teardown. All operation/read/write/reap bounds are minima of their already
  fixed enclosing bounds. Expired waits raise, never get an epsilon or renewal.
  Cleanup may signal an owned unreaped group and observe wait(0), never add time.

### Parent-owned red controls, UNRUN

Use disposable source copies and fresh externally capped invocations:

1. At `CONTROLLER_STAYS_ALIVE`, add return 0 AFTER the valid fired reply,
   preserving trigger/journal/reply. C1/C3 post-fire controller challenges must
   fail causally, rather than failing at a missing earlier reply or accepting
   kill of an already-exited child.
2. Force one reap to remain unobserved: no snapshot/root release, NONPASS,
   actual Fixture/Popen/FD/root references retained in the harness registry.
3. Expire the enclosing deadline before spawn/wait: no new Popen or renewed
   wait budget. Preserve containment failure if nonblocking observation fails.
4. Fail containment in the first fixture, then enter another: original failed
   owner must remain in the registry with its actual handles, not just paths.
5. Delay final fixture/base removal beyond its relevant limit: measured timing
   must include that delay and fail without rounded-threshold acceptance.

## Minimal implementation plan

One standalone stdlib file, aiming roughly 400-600 lines if safety permits.
Exactly five fixed modes: default harness, worker, controller, gate, command.
No generic command runner. Only harness calls Popen. Gate's only exec target:
current Python, `-I -S -B`, same source, fixed command mode, minimal environment.
No child creates a process/session.

Each Popen uses new session, close_fds, explicit pass_fds, DEVNULL stdio and
minimal PATH/private TMPDIR. Check the shared operation deadline immediately
before every spawn. Parent owns the handle and FD objects immediately.

Four socketpairs: parent-worker, parent-controller, parent-gate, controller-gate.
Parent closes each passed child endpoint immediately after its spawn.
Controller alone retains the trigger writer; gate alone retains its peer.
Other children inherit neither. Parent retains zero trigger-channel copies.
Before exec gate closes its trigger endpoint, makes only its parent channel
FD inheritable among application FDs, and passes sequence state in trusted argv.
Command does not inherit the trigger channel, so later EOF cannot retrigger.

Nonblocking framed JSON, <=4096 B, exact field sets, duplicate/nonfinite/bool-as-
integer rejection, direction/stage restrictions and consecutive per-direction
sequences. Gate accepts only a valid trigger or clean empty EOF, never a
truncated trigger. Sequence state and both fixed deadlines survive exec.

Controller latches one fire before dispatch, reports its actual trigger count,
then keeps answering until parent quit or kill. Gate/command append actual
exec/command/marker events to a private journal. One exclusive 0600 marker is
independent of event counts; it cannot hide duplicate command attempts.

One exclusive parent reaper. Signals use only PID/PGID from retained NEW
unreaped Popen handles, never protocol facts and never after observed reap.
Independent cleanup attempts every process and FD even after another fails.
Module-level RETAINED owns actual failed Fixture/Run objects across iterations;
no path disposal when containment is unproved.

## Non-goals / SHORTCUT / MISSING

Synthetic local marker command only. No production API/schema, sealed
authorization, SDK/provider/Modal stop, watchdog delegation, budget, paid,
native, tensor or science work. No changes to defaults or old artifacts.
No shell, Python exec/eval, fork/preexec/pickle/multiprocessing, TCP/service,
caller commands, installed-distribution enumeration or assets.

Trusted same-user fixed code, not hostile-code containment. Python timer
leases are fallback only. Interpreter startup, OS unresponsiveness, filesystem
syscalls and signal latency remain explicit SHORTCUT limits until measured.
Already-proven same-host monotonic sharing and OS isolation are not rerun.

All checks are newly written inside this probe. Existing checks run: NONE.
New checks run: NONE. Syntax, review, red/green controls and timings: UNRUN.
PROVES is planned only until the parent executes and reviews.

# V202 Core stop-gate topology spike: named numeric plan (SOURCEONLY, UNRUN)

Status: SOURCEONLY, UNRUN. This plan was written BEFORE the candidate source.
Nothing here is measured. The parent owns execution, review and integration.

## Technical unknown under test

A deadline controller that launches a new-session stop grandchild cannot
guarantee parent custody if the controller dies: the grandchild is reparented,
its handle is not the parent's, and the parent can neither reap nor stop it.

Probe: a **parent-owned prestarted gate** that, on trigger or on genuine
controller EOF, `os.execve()`s a FIXED harmless command **in the SAME PID**.
Because exec replaces the image of an already-parent-owned `Popen` child, the
parent's original handle keeps working across the transition: same PID, same
reap, same stop authority, no new process boundary.

This is a topology probe only. No SDK, no App, no Sandbox, no GPU, no actual
stop executable, no remote stop, no Modal watchdog change.

## Theses

T1. A prestarted gate child that `os.execve()`s a fixed command keeps the
parent's original `Popen` handle valid: the command's actual PID equals the
retained gate `Popen.pid`, and the parent reaps it through that same handle.

T2. Genuine controller EOF (every writer copy of the controller-to-gate channel
closed, including the parent's) reaches the gate and causes exactly one exec,
with no replacement controller, gate or command and no additional `Popen`.

T3. Controller death after the exec changes nothing about custody: the command
survives, answers a fresh challenge, and is stopped and reaped by the parent
through the retained handle, with exactly one marker.

## Non-goals (mandatory)

- No production owner API, no authorization serialization, no common latch.
- No delegated-watchdog code, no `train/` change, no default/native change.
- No SDK, no billing, no paid-readiness change, no provider or GPU path.
- No shell, no caller-supplied command, no `eval`, no `exec()` of Python source,
  no `os.fork`, no `preexec_fn`, no pickling, no `multiprocessing`, no TCP, no
  bind/listen, no service.
- No signal derived from a protocol-reported PID or process group. Signals only
  through retained unreaped `Popen` handles, poll-checked, never after reap.
- No retry, no reissue, no cap increase, no replacement spawn.
- No writer threads. All channel I/O is nonblocking and bounded.

## Architecture: one standalone stdlib-only file, five fixed modes

`spec/spikes/core-v202-stop-gate.py`, dispatched on `sys.argv[1]`. Any other
argument shape returns exit 2. There is no sixth mode.

| mode | argv count | role |
|---|---|---|
| (none) | 1 | harness: runs C1..C3, prints one numeric line per case, `TOTAL`, `RESULT` |
| `--spike-worker` | 6 | tiny worker. Ignores SIGTERM, retains an active thread, answers challenges. Never exits on its own inside a case budget |
| `--spike-controller` | 7 | independent controller. Answers challenges; on one `fire` frame sends exactly one `trigger` to the gate, then exits 0 |
| `--spike-gate` | 9 | prestarted gate. Answers challenges; on `trigger` OR genuine EOF on the controller channel, execs the fixed command in the same PID |
| `--spike-command` | 11 | the FIXED harmless command that replaced the gate. Writes exactly one exclusive 0600 marker holding its own actual PID and the case nonce, reports `started`, then exits 0 (normal) or resists SIGTERM and keeps answering (resistant) |

Fixed exit codes: `0` OK, `1` harness gate fail, `2` internal, `3` no/invalid
channel, `4` protocol violation, `5` gate saw an invalid trigger frame and
refused to exec, `6` shared expiry reached, `97` lease.

## Spawn and exec contract

Initial spawns (harness only, exactly three per fixture):

```
[sys.executable, "-I", "-S", "-B", abspath(__file__), <mode>, ...]
stdin/stdout/stderr = DEVNULL, close_fds=True, pass_fds=<explicit tuple>,
start_new_session=True, env={"PATH": "/usr/bin:/bin", "TMPDIR": <private base>}
```

The gate's one and only process replacement:

```
os.execve(sys.executable,
          [sys.executable, "-I", "-S", "-B", SCRIPT, "--spike-command",
           parent_fd, expiry_mono, expiry_wall, root, nonce, resistant,
           via, out_seq, in_seq],
          {"PATH": "/usr/bin:/bin", "TMPDIR": <inherited private base>})
```

Immediately before that one call the gate closes its `t_gate` end so the command
never holds the trigger channel, then `detach()`es the parent end (returning the
descriptor WITHOUT closing it) and calls `os.set_inheritable(parent_fd, True)`.
That last step is load-bearing: `execve` closes every descriptor marked
`FD_CLOEXEC`, so inheritability is set explicitly rather than left to whatever
`socket.socket(fileno=...)` happens to do. A failure there is the fixed
no-channel exit 3, never a half-exec'd state.

`argv[0..4]` are compile-time constants. The gate cannot exec anything else:
the file contains exactly one `os.execve` call site and exactly one
`subprocess.Popen` call site, the latter reachable only from harness-side
fixture construction. The command mode contains no `Popen`, no fork, no
`setsid`, no `execve`. This is trusted OS process replacement of a fixed
same-source image, not arbitrary code execution.

Resistance (`resistant` = `0` or `1`) is chosen by the PARENT at gate spawn
time and travels in argv. The controller cannot select it.

### Design note the parent should weigh

`execve` preserves the PID, the process group, the session and every
non-CLOEXEC descriptor. It does NOT preserve interpreter state. The gate
therefore hands its outbound and inbound protocol sequence counters to the
command in argv (`out_seq`, `in_seq`). Without that hand-off the command's
first frame would reuse seq 1 and the parent's strict monotonic check would
reject it, or the check would have to be weakened across the exec boundary.
Neither is acceptable, so the counters are explicit exec arguments.

## FD ownership map (EOF must be genuine, never masked)

Four `socket.socketpair(AF_UNIX, SOCK_STREAM)` channels per fixture. Every copy
is accounted for; the parent closes each child end immediately after the spawn
that inherited it, before any wait.

| channel | ends created | parent retains | child inherits | parent closes |
|---|---|---|---|---|
| W parent-worker | `w_parent`, `w_child` | `w_parent` | worker: `w_child` | `w_child` right after worker spawn |
| C parent-controller | `c_parent`, `c_child` | `c_parent` | controller: `c_child` | `c_child` right after controller spawn |
| G parent-gate-command | `g_parent`, `g_child` | `g_parent` | gate, then command across exec: `g_child` | `g_child` right after gate spawn |
| T controller-gate | `t_ctrl`, `t_gate` | NOTHING | controller: `t_ctrl`; gate: `t_gate` | both, right after their own spawns |

Spawn order is fixed: create T, then W and the worker, then C and the
controller (closing `c_child` and `t_ctrl`), then G and the gate (closing
`g_child` and `t_gate`).

Post-state: `t_ctrl` exists only in the controller, `t_gate` only in the gate.
The parent holds zero copies of T, so when the controller is SIGKILLed the
kernel closes the sole writer and the gate's `recv` returns `b""`: genuine EOF,
not a masked one.

Across exec: the gate closes `t_gate` (closing its descriptor), calls
`socket.detach()` on the parent end (which returns the descriptor WITHOUT
closing it), then calls `os.set_inheritable(parent_fd, True)` explicitly before
`execve`. The explicit `set_inheritable` is deliberate: it removes any
dependence on whether wrapping a descriptor in a `socket.socket(fileno=...)`
object changed its inheritability. The command re-wraps the same descriptor.

## Wire protocol

4-byte big-endian length prefix plus UTF-8 JSON, `MAX_FRAME_BYTES = 4096`.
Strict decode on both ends: duplicate object keys, `NaN`/`Infinity`, extra or
missing fields, wrong `v`, wrong nonce shape, non-`int` or non-increasing `seq`
all raise a fixed protocol error. Exact schemas:

| kind | direction | fields |
|---|---|---|
| `challenge` | parent to child | `v, kind, nonce, seq` |
| `fire` | parent to controller | `v, kind, nonce, seq` |
| `alive` | child to parent | `v, kind, nonce, seq, pid, stage` |
| `trigger` | controller to gate | `v, kind, nonce, seq` |
| `started` | command to parent | `v, kind, nonce, seq, pid, stage, via, marker` |

`stage` is one of `worker|controller|gate|command`; `via` is `trigger|eof`.
Per-direction `seq` is strictly increasing and survives exec via argv.

`pid` in any frame is a WITNESS ONLY. It is compared against the retained
`Popen.pid` for same-PID evidence and is never used as a signal target.

## Witness counters (all observed, none constant)

- `popen_calls`: incremented inside the single `Popen` wrapper on every real
  call. Gated at exactly 3 per fixture and 9 for the run.
- `exec_count`: 1 only when a `started` frame with `stage == "command"`
  arrives on the ORIGINAL gate channel.
- `markers`, `marker_mode`, `marker_pid`, `marker_nonce`, `marker_via`,
  `marker_lines`: read from the private root AFTER all three reaps.
- `same_pid`: `marker_pid == popen_gate.pid` AND `started_pid == popen_gate.pid`.
- `worker_rc`, `controller_rc`, `command_rc`: from the retained handles.
- `worker_stage`, `controller_stage`, `gate_pre_stage`, `started_stage`,
  `chal_command_stage`: the `stage` field witnessed in each frame. Recorded in
  every case and gated where the case thesis depends on it (C1 gates
  `worker_stage` and `controller_stage`; all three gate `gate_pre_stage`), so a
  mode answering on the wrong channel shows up on the `CASE` line rather than
  passing silently.
- `worker_term_ignored`, `command_term_ignored`: 1 when `wait()` after
  `terminate()` raised `TimeoutExpired`, proving SIGTERM resistance.
- `chal_*_ms`: per fresh challenge round trip, gated at 500 ms.
- `*_stop_ms`, `*_reap_ms`: gated at 1000 ms.
- `additional_popens`: `popen_calls` delta across a controller death, gated 0.
- `lease_exits`: reaped children with returncode 97, gated 0.
- `cleanup_errors`, `retained_roots`, `base_released`.

## Named numeric cases

Shared per-case absolute deadline = `min(harness expiry, case start + 2.50 s)`.
Every wait is clamped to that deadline minus a 0.25 s teardown reserve, floored
at 0.02 s. No sequential full timeouts, no retry.

### 1. `case1_normal_arm_worker_kill_exec_same_pid` (budget 2.50 s)

Flow: fresh fixture, `resistant=0`. Challenge the worker. Stop the worker with
`terminate()` then a 0.15 s resistance probe then `kill()`, reap. Challenge the
controller and the gate (both must still be responsive after an unrelated group
death). Send one `fire`. The controller sends one `trigger` and exits 0. The
gate execs; the command writes the marker and reports `started`. Reap the
controller, then reap the command through the ORIGINAL gate handle. Snapshot.

EXPECTED: `popen_calls=3`, `worker_rc=-9`, `worker_term_ignored=1`,
`worker_stop_ms<=1000`, `worker_stage=worker`, `chal_worker_ms<=500`,
`chal_controller_ms<=500`, `chal_gate_ms<=500`, `controller_stage=controller`,
`gate_pre_stage=gate`, `gate_pre_pid_match=1`,
`started_via=trigger`, `started_stage=command`, `started_pid_match=1`,
`exec_count=1`, `started_ms<=2000`, `controller_rc=0`,
`controller_reap_ms<=1000`, `command_rc=0`, `command_reap_ms<=1000`,
`markers=1`, `marker_mode=0o600`, `marker_lines=1`, `marker_pid==gate_pid`,
`marker_nonce==nonce`, `marker_via=trigger`, `same_pid=1`, `lease_exits=0`,
`cleanup_errors=0`, `retained_roots=0`, `elapsed_s<=2.50`.

### 2. `case2_controller_death_before_trigger_eof_exec_once` (budget 2.50 s)

Flow: fresh fixture, `resistant=0`. Challenge worker, controller and gate (the
gate is armed and blocked on `t_gate`). Record `popen_calls`. Kill and reap ONLY
the controller. The sole `t_ctrl` writer dies, so the gate must observe genuine
EOF and exec the fixed normal command exactly once, same retained PID. The
parent reads `started` and then reaps the command through the ORIGINAL gate
`Popen`. Stop and reap the worker independently. Snapshot.

EXPECTED: `popen_calls=3`, `chal_worker_ms<=500`, `chal_controller_ms<=500`,
`chal_gate_ms<=500`, `gate_pre_stage=gate`, `gate_pre_pid_match=1`,
`controller_rc=-9`,
`controller_stop_ms<=1000`, `additional_popens=0`, `started_via=eof`,
`started_stage=command`, `started_pid_match=1`, `exec_count=1`,
`eof_exec_ms<=2000`, `command_rc=0`, `command_reap_ms<=1000`, `worker_rc=-9`,
`worker_term_ignored=1`, `worker_stop_ms<=1000`, `markers=1`,
`marker_mode=0o600`, `marker_lines=1`, `marker_pid==gate_pid`,
`marker_nonce==nonce`, `marker_via=eof`, `same_pid=1`, `lease_exits=0`,
`cleanup_errors=0`, `retained_roots=0`, `elapsed_s<=2.50`.

### 3. `case3_controller_death_while_command_runs_custody_retained` (budget 2.50 s)

Flow: fresh fixture, `resistant=1`. Challenge worker, controller and gate.
Record `popen_calls`. Send `fire`; observe the genuine trigger and exec
(`started` with `via=trigger`). Kill and reap the controller, then stop and reap
the worker independently. The resistant command must survive both deaths and
answer a fresh challenge. Then the parent `terminate()`s, probes 0.15 s, and
`kill()`s its retained gate/command handle and reaps it. Snapshot.

EXPECTED: `popen_calls=3`, `chal_worker_ms<=500`, `chal_controller_ms<=500`,
`chal_gate_ms<=500`, `gate_pre_stage=gate`, `gate_pre_pid_match=1`,
`started_via=trigger`, `started_pid_match=1`,
`exec_count=1`, `started_ms<=2000`, `controller_rc=-9`,
`controller_stop_ms<=1000`,
`worker_rc=-9`, `worker_term_ignored=1`, `worker_stop_ms<=1000`,
`chal_command_after_death_ms<=500`, `chal_command_stage=command`,
`chal_command_pid_match=1`, `command_term_ignored=1`, `command_rc=-9`,
`command_stop_ms<=1000`, `additional_popens=0`, `markers=1`,
`marker_mode=0o600`, `marker_lines=1`, `marker_pid==gate_pid`,
`marker_nonce==nonce`, `marker_via=trigger`, `same_pid=1`, `lease_exits=0`,
`cleanup_errors=0`, `retained_roots=0`, `elapsed_s<=2.50`.

## Declared worst-case timing gates

| gate | value |
|---|---|
| per-case budget | 2.50 s each, 3 cases = 7.50 s |
| total baseline | harness `TOTAL` must stay < 8.00 s |
| per local operation | <= 2.00 s (marker write, exec observation, each reap) |
| fresh challenge | <= 0.50 s round trip, including after an unrelated group death |
| stop plus reap | <= 1.00 s, including a 0.15 s SIGTERM resistance probe |
| shared absolute expiry | harness start + 8.00 s, IMMUTABLE, passed to every mode including the exec target as both a monotonic and a wall-clock value |
| child safety lease | each mode arms a daemon `threading.Timer` firing `os._exit(97)` at that SAME absolute expiry, armed BEFORE any channel I/O |
| post-exec lease | exec destroys the gate's threads and timer, so the command immediately re-arms from the SAME absolute expiry. Never `now + 8` |
| lease exit | 97 from any child fails the case. Success never accepts a lease exit |
| external parent timeout | declared 10.0 s, enforced by the parent's runner, never by this harness |
| teardown reserve | 0.25 s under the common deadline; wait floor 0.02 s |
| cap changes | none. No budget may be increased, no wait retried, no permit reissued, no process replaced |

## Safety and cleanup rules

- Lease armed before channel I/O in every mode, including the post-exec
  command. If the remaining shared budget is already <= 0 the mode exits 97
  immediately rather than doing I/O.
- Independent cleanup: `Resources.cleanup` runs three loops (reap every
  `Popen`, close every socket, release every root), each item in its own
  `try/except`. One failure never skips another item and never masks the
  primary error, which is preserved by the case's own `finally`.
- Snapshot and release only after actual reap: every case snapshots its private
  root after all THREE of its children were actually reaped, and its roots are
  released only in the case `finally` after that snapshot.
- Failed cleanup keeps ownership: any reap failure sets `reap_failed`, which
  retains every root instead of releasing it, failing `retained_roots_0`.
- The private base TMPDIR is released by the harness only after all three cases
  report zero cleanup errors and zero retained roots; otherwise it is retained
  and `base_released=0` fails the run.
- No old marker, PID or resource is touched. Each case has a fresh
  `mkdtemp` root inside the parent-set private base and a fresh 16-hex nonce.
- Nonblocking bounded I/O only. Every channel end is `setblocking(False)`;
  reads and writes loop on `select` with a 0.10 s slice against an absolute
  deadline. No blocking send follows a `select`. No writer threads.
- Signals only through retained unreaped `Popen` handles, `poll()`-checked
  first, never after a successful reap, never from a protocol-reported PID or
  group. `start_new_session=True` makes each child its own session and group;
  because no child ever creates a child, the process is the whole group.

## PROVES / SHORTCUT / MISSING register (planned)

PROVES, planned only until the parent measures it:
- P1. The parent's original gate `Popen` handle stays valid across
  `os.execve`: the command's actual PID equals `popen_gate.pid`, the parent
  reaps it through that handle, and no second `Popen` exists.
- P2. Genuine controller EOF, with every writer copy accounted for and the
  parent holding none, reaches the gate and produces exactly one exec and
  exactly one marker, with no replacement controller, gate or command.
- P3. Custody survives controller death after the exec: the command answers a
  fresh challenge, ignores SIGTERM, and is terminated then killed and reaped by
  the parent through the retained handle.
- P4. Exec preserves the channel descriptor and the session, so one parent-held
  socket serves `stage=gate` before and `stage=command` after, with strictly
  monotonic sequence counters handed over explicitly.

SHORTCUT:
- S1. The "stop command" is a harmless marker writer, not a real Modal stop,
  App stop or Sandbox termination. Nothing remote happens.
- S2. The gate, controller, worker and command are fixed trusted first-party
  source in this one file. This is not hostile-same-user security and not
  arbitrary-code containment: the exec target is a compile-time constant.
- S3. Same-user `socketpair` channels are a local delegation concept between a
  parent and its own freshly exec'd children. No sealed authority, no
  authorization serialization, no billing, no owner API.
- S4. The 8 s shared lease plus the declared 10 s external parent timeout are
  experimental orphan protection, not production supervision.
- S5. The witness root is `tempfile.mkdtemp` inside a parent-created 0700 base,
  not a purpose-built isolation boundary.
- S6. One fixture at a time. No multi-fixture concurrency, no contention probe.

MISSING:
- M1. Everything is UNRUN. Every counter, exit code and latency above is
  planned, not observed.
- M2. Interpreter startup cost is not measured here. Three fixtures spawn nine
  interpreter starts plus three execs; if cold start is slow on the target
  machine the 2.50 s per-case budget or the 8.00 s total could be exceeded.
  That is a FAIL, not a silent pass.
- M3. Cross-process monotonic clock sharing is assumed. `time.monotonic()`
  (`CLOCK_MONOTONIC` on Linux, `mach_absolute_time` on macOS) is system-wide
  within one boot, so an absolute monotonic expiry can be passed in argv. Every
  mode also takes a wall-clock expiry and uses the MINIMUM of the two remaining
  budgets, so a monotonic reference mismatch or a wall-clock jump shortens the
  budget and can never lengthen it. Neither clock behaviour is verified here.
- M4. OS unresponsiveness, `execve` failure, descriptor exhaustion and
  `SIGKILL` latency under load are not modelled beyond the fixed gates. An
  `execve` failure returns exit 2 and the case fails; there is no fallback
  spawn, by design.
- M5. No coverage for a kill landing between `O_EXCL` and the append beyond the
  `markers<=1` gate; no coverage for clock skew; no coverage for a controller
  that sends a malformed trigger (the gate returns 5 and the case fails, which
  is the intended NONPASS, but no case exercises it).
- M6. No SDK, GPU, App, Sandbox, remote stop, science or provider evidence.
  Prior V194/V197/V200 local process and capability results do NOT cover this
  exec-gate topology and are not rerun here.

## Execution contract (parent-owned)

Run `python3 spec/spikes/core-v202-stop-gate.py` with no arguments, under a
10 s external timeout. Exit 0 means every gate passed. Exit 1 means a gate
failed. Exit 2 means the harness itself broke and is NONPASS. The parent should
record the three `CASE` lines, the `TOTAL` line and the `RESULT` line verbatim
before treating any claim in this plan as evidence.

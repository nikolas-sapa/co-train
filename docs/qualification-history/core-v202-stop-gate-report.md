# V202 stop-gate topology spike: delivery report

Author: Core Qwen. Assignment: `../parent-v202-core-stop-gate-spike-brief.md`.

**STATUS: SOURCEONLY UNRUN.** Nothing in this delivery was executed. No import
of the spike module, no run, no spawn, no `execve`, no signal, no socket, no
test, no command, no Git operation, no network or provider call. Every counter,
latency, exit code and PASS/FAIL below is *planned*, not measured. The parent
owns execution, review and integration. This report is not approval.

## Delivered paths (the only three writable paths)

| path | state |
|---|---|
| `docs/core-v202-stop-gate-plan.md` | written, matches source after this review pass |
| `spec/spikes/core-v202-stop-gate.py` | written, 1602 lines, standalone, stdlib only |
| `docs/core-v202-stop-gate-report.md` | this file |

No other file was created or modified. All oldA8/V189/V194 paths were left
untouched and READONLY. No production owner, billing, watchdog, SDK or
interface file was amended.

## What the spike probes

A deadline controller that launches a new-session stop **grandchild** cannot
guarantee parent custody if the controller dies: the grandchild is reparented,
the parent holds no handle for it, and it can neither reap nor stop it.

The probe replaces that shape with a **parent-owned prestarted gate** that
`os.execve()`s a FIXED harmless command **in the same PID**. Because exec
replaces the image of an already-parent-owned `Popen` child rather than creating
a new process, the parent's original handle keeps working across the
transition: same PID, same reap, same stop authority, no new process boundary.

Three theses, one per case:

* **T1** the parent's original gate `Popen` handle stays valid across
  `os.execve`.
* **T2** genuine controller EOF (parent holding no copy of that channel) causes
  exactly one exec, with no replacement process.
* **T3** custody survives controller death *after* the exec: the surviving
  command is still challengeable, still SIGTERM-resistant, and still stoppable
  and reapable by the parent through the retained handle.

## How the parent runs it

```
python3 spec/spikes/core-v202-stop-gate.py
```

No arguments selects harness mode. Recommended external guard: a 10 s parent
timeout, which is strictly outside the harness's own immutable 8.00 s expiry, so
an internal wedge shows as an external kill rather than a silent hang.

Output contract: one `CASE n <name> <key=value ...> PASS|FAIL` line per case,
one `TOTAL ...` line, one `RESULT PASS|FAIL` line. Exit `0` only when every gate
passes; `1` on any gate failure; `2` on internal error. A failing run retains
its private base under `$TMPDIR/v202-base-*` for inspection; the parent must
remove those directories.

## Fixed modes

| mode | `len(sys.argv)` | role |
|---|---|---|
| (none) | 1 | harness: C1..C3, `TOTAL`, `RESULT` |
| `--spike-worker` | 6 | ignores SIGTERM, retains an active thread, answers challenges |
| `--spike-controller` | 7 | answers challenges; on one `fire` sends exactly one `trigger`, exits 0 |
| `--spike-gate` | 9 | on `trigger` OR genuine EOF, one `os.execve` in the same PID |
| `--spike-command` | 11 | the FIXED command: one exclusive 0600 marker, `started`, then exit 0 or resist |

Any other argument shape returns exit 2. There is no sixth mode.

Fixed exit codes: `0` OK, `1` harness gate fail, `2` internal, `3` no/invalid
channel, `4` protocol violation, `5` gate saw an invalid trigger and refused to
exec, `6` shared expiry reached, `97` lease.

## Hard limits honoured in source

Exactly ONE `os.execve` call site (the gate) and exactly ONE
`subprocess.Popen` call site (the harness-side fixture wrapper). The command
mode contains neither, so the exec target cannot launch a subprocess or a
session. Spawn shape is fixed:
`[sys.executable, "-I", "-S", "-B", abspath(__file__), <mode>, ...]` with
`close_fds=True`, explicit `pass_fds`, `start_new_session=True`, `stdin`,
`stdout`, `stderr` all `DEVNULL`, and a minimal env of `PATH` plus a
parent-created private `TMPDIR`.

No SDK, App, Sandbox, GPU, network, provider, credential or
installed-distribution enumeration. No shell, no caller-supplied command, no
`eval`, no Python `exec()`, no `os.fork`, no `preexec_fn`, no pickling, no
`multiprocessing`, no TCP, no bind/listen, no service, no writer threads. All
channel I/O is nonblocking and bounded by a shared absolute deadline.

No frame-reported `pid` is ever a signal target. The protocol carries no
process-group field. Signals travel only through retained unreaped `Popen`
handles, poll-checked first, never after a successful reap.

## FD ownership map (why EOF is genuine)

Four `socket.socketpair(AF_UNIX, SOCK_STREAM)` channels per fixture; every copy
is accounted for.

| channel | parent retains | child inherits | parent closes |
|---|---|---|---|
| W parent-worker | `w_parent` | worker: `w_child` | `w_child` immediately after the worker spawn |
| C parent-controller | `c_parent` | controller: `c_child` | `c_child` immediately after the controller spawn |
| G parent-gate-command | `g_parent` | gate, then command across exec: `g_child` | `g_child` immediately after the gate spawn |
| T controller-gate | **NOTHING** | controller: `t_ctrl`; gate: `t_gate` | both, immediately after their own spawns |

The parent holds zero copies of T, and closes `t_ctrl` right after the
controller spawn, so the controller is the sole writer. When it dies, the gate
observes real EOF rather than an EOF masked by a parent duplicate.

## Shared expiry and lease

The harness computes one immutable expiry at start (`start + 8.00 s`) and passes
it to every mode as BOTH a monotonic and a wall-clock value, including across
the exec boundary in argv. Each mode arms a daemon `threading.Timer` firing
`os._exit(97)` at that same absolute expiry, armed before any channel I/O. Each
mode's working budget is `min(monotonic remaining, wall remaining)`, so a
monotonic reference mismatch or a wall-clock jump can only shorten a budget,
never lengthen it.

`execve` destroys the gate's threads and its timer, so the command re-arms
immediately from the SAME handed-over expiry. Never `now + 8`.

`execve` also destroys interpreter state, so the gate hands its outbound and
inbound protocol sequence counters to the command in argv. Without that
hand-off the command's first frame would reuse seq 1 and the parent's strict
monotonic check would reject it. The check was not weakened instead.

## Named numeric cases and exact expected counters

Per-case deadline = `min(harness expiry, case start + 2.50 s)`. Every wait is
clamped to that deadline minus a 0.25 s teardown reserve, floored at 0.02 s. No
sequential full timeouts, no retry.

### C1 `case1_normal_arm_worker_kill_exec_same_pid`

`resistant=0`. Challenge the worker, stop it (`terminate()`, 0.15 s resistance
probe, `kill()`, reap). Challenge the controller and the gate, both still
responsive after an unrelated group death. One `fire`; the controller sends one
`trigger` and exits 0; the gate execs; the command writes the marker and reports
`started`. Reap the controller, then reap the command through the ORIGINAL gate
handle. Snapshot after all reaps.

Expected: `popen_calls=3`, `worker_rc=-9`, `worker_term_ignored=1`,
`worker_stop_ms<=1000`, `worker_stage=worker`, `chal_worker_ms<=500`,
`chal_controller_ms<=500`, `chal_gate_ms<=500`, `controller_stage=controller`,
`gate_pre_stage=gate`, `gate_pre_pid_match=1`, `started_via=trigger`,
`started_stage=command`, `started_pid_match=1`, `exec_count=1`,
`started_ms<=2000`, `controller_rc=0`, `controller_reap_ms<=1000`,
`command_rc=0`, `command_reap_ms<=1000`, `markers=1`, `marker_mode=0o600`,
`marker_lines=1`, `marker_pid==gate_pid`, `marker_nonce==nonce`,
`marker_via=trigger`, `same_pid=1`, `elapsed_s<=2.50`, plus the four cleanup
gates.

### C2 `case2_controller_death_before_trigger_eof_exec_once`

`resistant=0`. Challenge worker, controller and gate. Record `popen_calls`. Kill
and reap ONLY the controller. The sole `t_ctrl` writer dies, so the gate must
observe genuine EOF and exec exactly once, same retained PID. Read `started`,
reap the command through the ORIGINAL gate `Popen`, then stop and reap the
worker independently. Snapshot.

Expected: `popen_calls=3`, `chal_worker_ms<=500`, `chal_controller_ms<=500`,
`chal_gate_ms<=500`, `gate_pre_stage=gate`, `gate_pre_pid_match=1`,
`controller_rc=-9`, `controller_stop_ms<=1000`, `additional_popens=0`,
`started_via=eof`, `started_stage=command`, `started_pid_match=1`,
`exec_count=1`, `eof_exec_ms<=2000`, `command_rc=0`, `command_reap_ms<=1000`,
`worker_rc=-9`, `worker_term_ignored=1`, `worker_stop_ms<=1000`, `markers=1`,
`marker_mode=0o600`, `marker_lines=1`, `marker_pid==gate_pid`,
`marker_nonce==nonce`, `marker_via=eof`, `same_pid=1`, `elapsed_s<=2.50`, plus
the four cleanup gates.

### C3 `case3_controller_death_while_command_runs_custody_retained`

`resistant=1`. Challenge worker, controller and gate. One `fire`; observe the
genuine trigger and exec. Kill and reap the controller, then stop and reap the
worker independently. The resistant command must survive both deaths and answer
a fresh challenge. Then the parent `terminate()`s, probes 0.15 s, `kill()`s its
retained handle and reaps it. Snapshot.

Expected: `popen_calls=3`, `chal_worker_ms<=500`, `chal_controller_ms<=500`,
`chal_gate_ms<=500`, `gate_pre_stage=gate`, `gate_pre_pid_match=1`,
`started_via=trigger`, `started_pid_match=1`, `exec_count=1`,
`started_ms<=2000`, `controller_rc=-9`, `controller_stop_ms<=1000`,
`worker_rc=-9`, `worker_term_ignored=1`, `worker_stop_ms<=1000`,
`chal_command_after_death_ms<=500`, `chal_command_stage=command`,
`chal_command_pid_match=1`, `command_term_ignored=1`, `command_rc=-9`,
`command_stop_ms<=1000`, `additional_popens=0`, `markers=1`,
`marker_mode=0o600`, `marker_lines=1`, `marker_pid==gate_pid`,
`marker_nonce==nonce`, `marker_via=trigger`, `same_pid=1`, `elapsed_s<=2.50`,
plus the four cleanup gates.

### Cleanup gates appended to every case

`popen_calls_3`, `lease_exits_0`, `cleanup_errors_0`, `retained_roots_0`.
Cleanup attempts every resource independently, each in its own `try`; one
failure never skips another and never masks the primary error. Roots are
released only after every tracked child was actually reaped; a reap failure
keeps ownership and retains the root.

### Run-level gates

`TOTAL` must satisfy six conditions: `elapsed_s < 8.00`, `cleanup_errors=0`,
`retained_roots=0`, `lease_exits=0`, `base_released=1`, `popen_total=9`.

**Gate count: 31 (C1) + 30 (C2) + 33 (C3) = 94 per-case gates, plus 6 run-level
conditions = 100 numeric gates.** Every gate is a hard equality or an explicit
upper bound. There is no warning tier and no tolerated miss.

## Review pass: defects found in source and fixed before delivery

This spike was reviewed by trace, not by execution. Seven defects were found and
fixed in source. Four of them would have produced a wrong or vacuous result on
the parent's first run, so they are listed in full.

1. **`trigger` was not sendable (would have broken C1 and C3).** The send
   allowlist was `PARENT_TO_CHILD_KINDS | CHILD_TO_PARENT_KINDS` =
   `{challenge, fire, alive, started}`. The controller-to-gate `trigger` is
   child-to-child and belongs to neither set, so `clink.send("trigger", ...)`
   raised `ProtocolError` and the controller exited 4 without ever firing. The
   gate would then have seen EOF instead, and C1/C3 would have failed
   `started_via_trigger` and `marker_via_trigger`. Fixed by adding
   `CHILD_TO_CHILD_KINDS = {"trigger"}` and `SENDABLE_KINDS` as the union of all
   three directed sets. The directed sets remain load-bearing for inbound
   validation.
2. **Stale loop locals in gate expressions (would have broken C3 outright).**
   Gate lists were built from locals (`frame`, `ms`, `rc`) that later statements
   rebind. In C3, `("started_via_trigger", frame["via"] == "trigger")` was
   evaluated after a post-death challenge had rebound `frame` to an `alive`
   frame, which has no `via` key: a guaranteed `KeyError`, caught by the harness
   as a NONPASS `internal_error`. C1 had the same class of bug on `ms` (the
   worker-latency gate was silently reading the gate's latency), and C2 was
   correct only by accident of statement order. All three gate lists now read
   exclusively from the `observed` mapping, so no gate can depend on evaluation
   order.
3. **`Resources.cleanup()` was not idempotent.** The case `finally` owns
   cleanup, and the harness calls it again on a containment error. The second
   pass re-ran `shutil.rmtree` over already-removed roots, which would have
   manufactured `root:FileNotFoundError`, appended a retained root, and turned a
   clean single-cause failure into an additional hygiene failure with a
   misleading reason. Cleanup is now guarded by `self.cleaned` and is a no-op on
   a second call.
4. **The declared teardown reserve was dead code.** `_remaining()` and
   `TEARDOWN_RESERVE_SECONDS` (0.25 s) were defined but never called; the three
   stop/reap primitives computed their own clamp without the reserve the plan
   declares. All three (`_reap`, `_kill_and_reap`, `_stop_resistant`) now clamp
   through `_remaining(deadline)`, so the plan's stated wait discipline is what
   the source actually does.
5. **Plan/source gate drift.** The source asserted stage and latency gates that
   the plan's EXPECTED lists omitted (C1 `worker_stage`, `controller_stage`; C2
   `gate_pre_stage`; C3 `chal_worker_ms`, `chal_controller_ms`, `chal_gate_ms`,
   `gate_pre_stage`, `gate_pre_pid_match`, `started_ms`). Resolved by
   strengthening the plan lists and adding the two missing C3 challenge-latency
   gates, so every measured counter is gated and the two documents now agree
   exactly. The source was never weakened to match the plan.
6. **Counter-name drift.** The plan's witness list named `marker_count`; the
   observed key is `markers`. Corrected in the plan, and the stage witnesses
   (`worker_stage`, `controller_stage`, `gate_pre_stage`, `started_stage`,
   `chal_command_stage`) are now named there too.
7. **Dead code removed.** A no-op `if not result_ok and base_released == 0: pass`
   block in the harness was replaced by a comment stating the retention
   behaviour; the module docstring's `markers<=1` reference was corrected to the
   actual `markers==1` gate.

## SHORTCUT register (probe-only, NOT production)

* The "stop command" is a harmless marker writer. No real Modal stop, App stop
  or Sandbox termination happens. Nothing remote happens at all.
* Worker, controller, gate and command are fixed trusted first-party source in
  this one file. This is NOT hostile-same-user security and NOT arbitrary-code
  containment: the exec target's `argv[0..4]` are constants and the parent
  chooses `resistant`, not the controller.
* Same-user socketpair channels are a local delegation concept between a parent
  and its own freshly exec'd children. No sealed authority, no authorization
  serialization, no billing, no owner API.
* The 8 s shared lease plus the declared 10 s external parent timeout are
  experimental orphan protection, not production supervision. The lease is a
  daemon `threading.Timer` calling `os._exit(97)`: if the interpreter is wedged
  such that the timer thread never runs, the lease does not fire.
* The witness root is `tempfile.mkdtemp` inside a parent-created 0700 base, not
  a purpose-built isolation boundary.
* One fixture at a time. No multi-fixture concurrency or contention probe.

## MISSING: gaps the parent must weigh before freezing production interfaces

* **Everything is UNRUN.** Every counter, exit code, latency and PASS above is
  planned. No thesis in this report has any empirical support yet.
* **Interpreter startup cost is unmeasured.** Nine spawns plus three execs must
  fit the 2.50 s per-case and 8.00 s total budgets. Exceeding them is a FAIL by
  design, never a silent pass, but the parent should expect startup to be the
  first thing that breaks on a loaded machine.
* **Cross-process monotonic clock sharing is ASSUMED.** Mitigated by carrying a
  wall-clock expiry alongside it and taking the minimum of both remaining
  budgets, so a mismatch can only shorten a budget. Neither clock behaviour is
  verified here.
* **`pass_fds` descriptor-number preservation is ASSUMED.** The child modes
  trust that the inherited descriptor keeps the number the parent passed in
  argv. `_open_end` calls `getsockname()` so an absent or wrong endpoint is
  always the fixed no-channel exit 3 rather than a later ambiguous failure, but
  the preservation itself is unverified.
* **Descriptor inheritability across `execve` is set explicitly, not verified.**
  The gate calls `os.set_inheritable(parent_fd, True)` after `detach()` because
  exec closes CLOEXEC descriptors. If that call is insufficient on the parent's
  platform, C1/C2/C3 all fail at `started` with the command exiting 3.
* **No case exercises a malformed trigger.** The gate's refusal path (exit 5,
  no exec) is reasoned in source only.
* **No coverage for a kill between `O_EXCL` and the write** beyond the
  `markers==1` gate. `O_EXCL` makes a second marker by one command structurally
  impossible, but a kill inside that window is untested.
* **Not modelled:** OS unresponsiveness, `execve` failure under load, descriptor
  exhaustion, SIGKILL latency, clock skew, concurrency contention. An `execve`
  failure returns exit 2 and the case fails; there is deliberately no fallback
  spawn.
* **No SDK, GPU, App, Sandbox, remote stop, science or provider evidence.** This
  spike says nothing about whether a real Modal stop is idempotent, billed
  correctly, or safe to issue from an exec'd child.

## Recommended parent execution order

1. Read the plan, then the source, then this report.
2. Run once under a 10 s external timeout on an otherwise idle machine.
3. If `RESULT FAIL`, read `failed_gates=` on each `CASE` line first. Latency
   gates (`*_ms`, `elapsed_s`) failing together indicate startup cost, not a
   topology defect; a `started_via` or `marker_via` mismatch indicates a real
   topology finding.
4. If any case reports `internal_error`, the containment path already ran
   cleanup; the retained base under `$TMPDIR/v202-base-*` holds the marker state.
5. Remove retained `v202-base-*` directories after inspection.

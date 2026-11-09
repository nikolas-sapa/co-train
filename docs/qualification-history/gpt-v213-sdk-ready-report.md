# V213 fresh SDK-worker READY spike report

**SOURCEONLY UNRUN. PROVES is planned, not observed. Production policy provisional.**
Sole GPT author, no delegation. Parent owns execution, review and integration.

## Delivered source

Only three new assigned files:

- `spec/spikes/gpt-v213-sdk-ready.py`
- `docs/gpt-v213-sdk-ready-plan.md`
- `docs/gpt-v213-sdk-ready-report.md`

The numeric plan preceded source creation. All prior C files and accepted parent
probes remain unchanged. The accepted V181 source and V183 receipts supply the
real local constructor/bridge pattern; their earlier result is not V213 evidence.
No SDK sources or distributions were inspected.

The fixed experiment has three sequential fixtures, `fresh_1`, `fresh_2`,
`fresh_3`, and one Popen site, no retries/nested processes. Only the child imports
Modal. Each command uses the specified SDK interpreter with `-I -S -B`,
start_new_session, a private minimal environment and one inherited Unix socket.
Parent creates the private directories, empty config and escape fixture before
spawn. The reviewed source-pinning bootstrap gains a child alarm before its
explicit file I/O; it never reads/hashes the interpreter binary.

Audit denial is installed before SDK imports. A temporary read-only client-call
profile guard also covers imports, then accepted `_Client.from_env`/`__init__`
denial covers constructors and the SDK thread. The exact accepted read whitelist,
public OS plist exception, empty config/environment checks and sticky metadata
denial remain. No fake SDK packages or sys.modules substitutes.

Both sides use partial nonblocking framed I/O. READY/FINISH/DONE have strict
keys, types, duplicate/nonfinite checks, case/nonce and sequences 0/1/2.
Individual JSON bodies are capped at 2048 bytes; aggregate wire is <=8192.
Actual loop IDs, raw reader type/fd, real counters and denial witnesses form
READY facts. The origin hash hashes the resolved SDK **path**, not SDK contents.

Parent records actual Popen object identity, observed PGID/SID, nonce, sequences,
READY/I/O/reap/full-fixture times, real wait status and cleanup witnesses.
It retains both parent socket objects until actual zero reap, checks final EOF,
removes the known fixture entries and closes directory FDs, then removes base.
There are no control writer threads or detached cleanup tasks.

Failure raises `Failure` with actual owner state, Popen/socket/Path/FD objects,
primary exception and separate cleanup exceptions. Only a verified still-owned,
unreaped Popen group can receive failure containment; no protocol PID or
post-reap signal. Incomplete cleanup retains the actual objects and emits no
success receipt. An embedding parent must retain this exception; the CLI's
NONPASS JSON is diagnostic, not persistent custody or a production exception.

## Numeric gates, all unmeasured

| Gate | Required for acceptance |
| --- | --- |
| Fresh workers | Exactly 3; each actual zero exit and reap |
| Ordinary-loop controls | 3 actual AssertionErrors |
| SDK-loop constructors | 3 real `_StreamReader`, text=True, fd 1, actual synchronizer loop identity |
| Constructor client/network calls | 0/0 in each worker |
| Intentional guard controls | Client 3, network 3, private metadata 3, writes 6 |
| Unexpected denials | 0 |
| Popen dispatch to validated READY | <=2 s in every worker, including first cold call |
| Control I/O | <=0.5 s, fixed absolute deadlines |
| Stop/reap | <=1 s, clamped to the same case/run expiry |
| Entire fixture, setup through teardown | <=2.5 s each |
| One immutable harness expiry | start+8 s, total <8 through base removal/FD closure |
| External ceiling | 10 s, supplied by parent, includes launch/output tails |
| Accepted cleanup errors / forced cleanup / lease exits / retained ownership | 0 / 0 / 0 / 0 |

A READY miss is NONPASS. No caps are raised. Case, I/O and stop deadlines all
clamp to the same immutable run/case bounds. Expired wait receives zero, never
a renewed positive budget. A failed fixture stops further dispatch.

## PROVES planned

Only if parent runs and independently accepts every gate: three genuinely fresh
SDK interpreters can refuse ordinary-loop construction, construct the real local
raw reader on the actual SDK loop, demonstrate live guards, send READY within
the measured bound and terminate/reap with complete local fixture cleanup.

## SHORTCUT

The accepted `client=object()` placeholder is local-constructor scope only.
No stream iteration, RPC, authentication, provider connection, build, upload,
App/Sandbox/image creation or provider stop. SDK daemon threads die with the
worker process; this is not remote cleanup, billing-end, native or science proof.

## MISSING and checks

Executed imports, workers, tests, static compilation, lint/type checks and timing
measurements: **0**. Only file-tool source inspection occurred. No measured READY,
reap, control or teardown result exists. No temporary iteration helpers created.
No new pytest files; the spike contains the planned finite assertions and live
negative controls, not a passing test report.

Parent must provide external-10 containment and measure launch/output tails.
Popen, filesystem operations and final output cannot be assumed preemptible by
Python timeouts. Internal timestamps include source preparation, all stdlib
imports after the initial clock, private setup, process teardown and base removal;
outer interpreter/bootstrap launch and final output tails need the parent's
independent wall measurement. Any overrun or retained ownership is NONPASS.
The pre-import guard's startup cost is included and remains unmeasured.

No production owner/delegation interface, protocol or READY policy is frozen.
The original staged-stop executable remains blocked by both original stager and
adapter interpreter-binary rereads. Neither was run, bypassed or changed.

VERIFY_REAL: SOURCEONLY UNRUN. No execution, timing guarantee or approval.

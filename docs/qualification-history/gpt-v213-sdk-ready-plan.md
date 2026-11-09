# V213 fresh SDK-worker READY spike, numeric plan first

SOURCEONLY UNRUN. Sole author: genuine GPT. Parent owns every execution,
review and integration. No production policy or previous C file changes.

## Fixed experiment and acceptance gates

Exactly three identical fresh workers, named `fresh_1`, `fresh_2`, `fresh_3`,
in sequence, with no retry or nested process. Coordinator imports stdlib only.
Each worker uses the exact existing absolute SDK interpreter with `-I -S -B`,
a new session, one inherited Unix control socket, and primitive fixed arguments.
No inherited SDK objects, forked SDK parent, credentials or ambient environment.

1. `fresh_sdk_import`: each child imports real Modal 1.6.3 from the specified
   SITE, after installing audit and client-call denial. Use the accepted
   V181/V183 constructor and bridge pattern, not SDK substitutes.
2. `ordinary_loop_refuses`: each child actually catches exactly 1 AssertionError
   constructing the real server `_StreamReader(text=True)` on an ordinary
   asyncio loop. Retain the actual ordinary loop object for identity comparison.
3. `sdk_loop_constructs`: each child uses no_io_translation plus
   synchronize_api(...).aio once. Require actual running-loop identity equal
   to the actual synchronizer loop, unequal to the retained ordinary loop;
   actual reader type `_StreamReader`, fd 1, exactly 1 SDK-loop construction.
   Placeholder `client=object()` is local-constructor scope only. Iterate 0
   streams and perform 0 RPCs.
4. `guards_are_live`: constructor client/network deltas both 0, unexpected
   denials 0. Separately execute exactly 1 denied client call, 1 denied local
   AF_INET connect, 1 denied private-path metadata enumeration, and 2 denied
   writes (outside root and through the prepared escape symlink) per worker.
   Audit denies network before connect. Metadata denial is sticky even when
   FastPath.children swallows RuntimeError. Intentional totals across 3 workers:
   client 3, network 3, private metadata 3, writes 6. No extra mutation profiles.
5. `ready_latency`: measure immediately before Popen through full validated
   READY, including cold interpreter/bootstrap/SDK imports and guard controls.
   Require <=2 seconds in EACH case, not average. A miss is NONPASS, no cap raise.
6. `control_and_identity`: small strict JSON frames, total control wire <=8192
   bytes per case, duplicate/nonfinite/type/key/sequence/nonce rejection.
   Nonblocking partial I/O uses absolute deadlines. Require actual Popen pid,
   observed PGID and SID all equal, matching child comparison witnesses.
   READY seq 0, FINISH seq 1, DONE seq 2; ACKs never substitute for wait/reap.
7. `bounded_fixture`: case clock starts BEFORE private fixture creation;
   case expiry is min(case-start+2.5, immutable harness-start+8). READY expiry
   is min(dispatch+2, case/run expiry); one I/O expiry is min(READY+.5,
   case/run expiry); stop/reap expiry is min(READY+1, case/run expiry).
   Child independently arms an immutable alarm BEFORE bootstrap file I/O
   and SDK imports, clamped to the passed case/run expiry. No lease renewal,
   positive expired wait budget, control writer thread or detached cleanup.
8. `reap_and_remove`: actual worker returncode 0 and wait/reap before control
   FD/root release and receipt. All 3 reaps, closed parent socket/root FDs,
   removed case/home/tmp/config/escape and base directory, cleanup errors 0,
   forced cleanup 0, lease exits 0, retained live ownership 0.
   Each full fixture <=2.5 seconds; total <8 through base removal/FD closure.
   Parent supplies an independent external 10-second ceiling, including launch
   and output tails. Do not launch another monitor process inside this spike.

## Boundary and implementation after this plan

Port the accepted V181 audit/read whitelist, exact public OS plist exception,
private empty config, minimal environment and `_Client` denial. A temporary
pre-import call guard covers `_Client` calls while real SDK modules load;
the accepted class-method/constructor denial then covers the bridge thread.
No fake modules or sys.modules replacement. Parent precreates 0700 case/home/tmp,
0600 empty config and the fixed private escape fixture before Popen.

Use the accepted reviewed bootstrap's nofollow/single-link/source-size/hash/
identity checks, prefixed only with the immutable child alarm. Parent hashes
only this spike's source, never the SDK interpreter binary. Fixed worker command
only, no arbitrary executable/module/root/environment selection interface.

Keep actual owner objects (Popen, both sockets, root Path and directory FD),
primary exception and cleanup exceptions in a raised failure object. Failure
may boundedly kill only its verified, still-unreaped Popen group, never a
protocol PID or a reaped process. If containment/reap/removal cannot finish,
retain ownership, return no success receipt and do not launch replacements.
Stop the experiment on failure; fewer than 3 completed workers is NONPASS.
An embedding parent must retain that exception, not reduce it to a log string.

## PROVES planned, SHORTCUT and MISSING

PROVES is planned until parent measurements: three genuine cold-worker local
loop/constructor/guard/READY observations only.

SHORTCUT: the accepted placeholder client exercises no provider stream. SDK
daemon threads die with each real worker process; this is not remote cleanup.

MISSING: no execution, syntax check, timings, actual reap/cleanup observations
or independent external-10 enforcement yet. Popen/filesystem/output syscall
latency is measured, not assumed bounded by Python timeouts; an overrun is
NONPASS and may leave retained failure ownership for the parent.

## Non-goals

No production worker/protocol freeze, custody exception, bulk manifests,
original staged-stop executable or bypass of its interpreter-binary rereads,
native/science/GPU work, caller assets, installs, provider/auth/build/upload/
App/Sandbox/image/stop actions, SDK-source reads, global configuration,
commands/tests/Git/delegation while authoring, or changes outside the three
new assigned paths.

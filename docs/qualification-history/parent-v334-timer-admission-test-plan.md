# V334 pure timer arithmetic, tests before corrective implementation

V332 is frozen and rejected, not executed. Corrective pure model only; no timer,
signal, clock, role, SDK or native operation. Production remains unchanged.

Independent review requires exact inversion of s=floor(n*NS/F):
lo=ceil(s*F/NS), hi=ceil((s+1)*F/NS)-1. Reject unreachable OBSERVED buckets.
A future window endpoint is a bound, not an observation, and need not be reachable.
Window start is observed; window span is explicitly at most28s. Bound all possible
native ticks across the entire declared installation/query/sample/future window:
B=min(INT64_MAX,(UINT32_MAX-1)*F-1), hi(window_end)<=B.

Use original, unreduced Mach operands. Enforce CPython's witnessed startup check
numer*denom<=INT64_MAX, and check remainder-product, whole-product and sum over
the native tick window. Keep all seven frequency classes through safe uint32
representations. No Mach denominator<=4 confusion or silent fraction reduction.
Require BOTH retained pretransition H and actual requested deadline.

Twenty-two NEW pure cases:
1 all seven frequency representations/q;
2 timebase exact types/ranges/noninteger/out-of-domain F;
3 unreduced CPython startup overflow rejection;
4 exact inverse reachable/unreachable observed buckets;
5 signed native-tick worst window endpoint and +1 crossing at F=UINT32_MAX;
6 uptime worst endpoint and +1 crossing at F=3m;
7 explicit window types/order/range/28s cap;
8 original CPython intermediate bounds across window;
9 exact float ceiling0.1=100000001 and0.5=500000000;
10 invalid remainder types/envelope;
11 reachable setter/getter noncanonical positive fixture;
12 coarse-term loss causes strict absolute-expiry undercoverage;
13 absolute expiry domination across all seven frequencies;
14 equality at BOTH expiry bounds accepts;
15 retained-H guard load bearing;
16 actual-requested-deadline guard load bearing;
17 sample outside declared window or unreachable sample refuses;
18 certificate exact argument types/ranges;
19 injected query strictly before sample,100repeats,zero writes;
20 missing/periodic/invalid interval values refuse (builtin finite float zero only);
21 horizon ordering/all signed64 additions checked;
22 future endpoint need not be observable.

Expected positive expiry is checked INDEPENDENTLY against pinned C model:
upper_ns*Mach_denom >= expiry_ticks*Mach_numer. No -1ns slack or floor-duration
shortcut. Retain the reachable negative-usec fixture and distinct exact-ceiling
vs coarse-term controls. Model agreement is not native/platform proof.

External RED source changes ONLY the retained-H comparison to false, retaining
its argument/domain checks. Expected exactly case15 assertion failure,21pass,
zero errors/skips. Frozen identical tests under GREEN:22pass. Internal coarse
mutant is data used to demonstrate strict undercoverage, not a false PASS.

Parent reviews/AST/pins and H191 unchanged29/30 before execution. No old bodies
rerun. No assertions of kernel/binary equivalence, clock origin, signal delivery,
termination time, arbitrary post-setsid SIGSTOP containment or GPU readiness.
No authority from caller booleans/digests. No new OS/recovery/fullvolume/GPU
permission inferred. Earlier finite unsigned model reports stay historical.

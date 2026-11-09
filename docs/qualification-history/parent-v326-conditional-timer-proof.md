> Sanitized public reference. Internal workflow identifiers replaced; historical acceptance applies to the private original.

# Conditional timer arithmetic proof, SOURCE ONLY

Architect taskpublic-review-06 supplied this analysis but had
no write tool. Parent persisted it. Exact C witnesses: parent-v325-pinned-timer-
definition-witness.md. This is conditional mathematics, NOT Darwin27 applicability,
installed-binary proof, OS execution approval or a termination-time guarantee.

## Admission
M=UINT32_MAX. Let F=10^9*Mach_denom/Mach_numer be an exact integer,
3,000,000<=F<=M; q=floor(F/10^6)>=3. Pinned callback/clocks apply without
timebase changes; raw callback operands/types are representable. Every sampled
absolute uptime second a obeys a+2<=M. Installed one-shot V satisfies0<V<=1s,
repeat interval0, no replacement. Signed timer intermediates accommodate below
bounds. CPython3.12.13 conversion is IEEE binary64 round-to-nearest, and monotonic
uses the witnessed positive tick conversion with less-than1ns integer loss.
Implementation admission must additionally cover every sampled native tick
within0..INT64_MAX and all expression intermediates, not only destination types.
See parent-v326-clock-premise-supplement.md for the public CPython cast witness.
Earlier finite corner models do not establish this signed-tick admission.

## Callback and microtime
Raw frequency N/d has1<=d<=4. If N/d=F, casting the quotient to uint32 preserves F.
Reduced Mach numerator<=10^9 and denominator<=M, so their casts also preserve the
ratio. D=rtclock_sec_divisor=F and rtclock_usec_divisor=q.

For n=aF+r,0<=r<F:
    mu(n)=a+floor(r/q)/10^6
    -1us < mu(n)-n/F < 1/q seconds.
No uptime-accumulating drift under D=F. Since F=q*10^6+s,0<=s<10^6:
    floor((F-1)/q)=10^6+floor((s-1)/q)<=1,333,332.
Use conservative C=1,333,333 for microsecond component.

## Expiry, casts and overflow
Normalized interval(b,v) has b in{0,1},0<=v<=999999; b=1 implies v=0.
Adding to mu, before any carry, seconds<=a+1 and useconds<=2,333,332.
timevalfix preserves total. Enclosing bounds even without a carry:
    0<=P.tv_sec<=a+2<=M; 0<=P.tv_usec<=2,333,332.
Signed64 seconds/signed32 microseconds suffice. Both uint32 interval casts safe.

clock_interval computes floor(ns*F/10^9) by split whole/remainder arithmetic.
interval*scale fits uint64; fractional product<10^9*F<2^64; whole product fits.
Do not independently maximize components to bound the final addition. Jointly:
    P=mu(install)+V<a+2+1/q<=M+1/q<M+1.
Thus result+usresult<=P*F<(M+1)*M=2^64-2^32, no sum overflow.
Both conversions round down, never late. Integer-second conversion is exact,
so total deficit is actually<1tick (weaker<2ticks also true).

## Returned components, without assuming canonicality
At later query, a_query>=a_install. Before subtraction fix:
    seconds difference<=2;
    useconds difference in[-1,333,333,2,333,332].
Single borrow/carry yields useconds in[-333,333,1,333,332], seconds<=3.
Seconds differences stay within exact binary64 integer range under uptime bound.
For positive returned float, seconds<=-2 impossible because usec contribution<2.
Therefore -1<=returned seconds<=3 and abs(usec)<=1,333,332.
This establishes weaker convenient bounds abs(seconds)<=4,abs(usec)<=1,333,334.

## CPython's two rounding operations
Both component integers convert to double exactly.
abs(usec/10^6)<2 gives division absolute error<=2^-53 seconds.
Addition magnitude<5 gives addition absolute error<=2^-51 seconds.
Total error<=5*2^-53 seconds<1ns, including noncanonical cancellation.

R_ns=(seconds*10^6+usec)*1000 is integer. Compute
C_ns=ceil(exact integer-ratio value of returned_float*10^9), NOT a rounded float
multiplication and not an assumed final nextafter. Underestimation<1ns implies
C_ns>=R_ns. No reliance on canonical timeval components.

## Earlier-expiry certificate
Stored expiry P; query microclock mu; exact returned remainder=P-mu.
Kernel expiry<=P. Installation-time microclock error cancels.
Sample monotonic AFTER query and admit only
    sample_after_ns + U <= requested_deadline_ns
where
    U=C_ns+ceil(10^9/q)+1000+ceil(10^9/F)+1.
This is conservative. The1000ns/tick terms are spare under this conversion proof,
not substitutes for unknown implementation. No reset/renewal/logical-only advance.

## Remaining BLOCK
Running Darwin27 matching implementation, actual clock/build assumptions and
prebirth admission, guard/exec/default-signal behavior/timing feasibility remain
unproved. Kernel programmed expiry does not bound delivery/termination delays.
No role source edit or OS/GPU authorization. V323 TIMEOUT remains NONPASS.

VERIFY_REAL: Architect source reasoning only; no OS query/execution. Parent will
separately validate finite corner models and review proof; those are not native
or exhaustive implementation proofs.

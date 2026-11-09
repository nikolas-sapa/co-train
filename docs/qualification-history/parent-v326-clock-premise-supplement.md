# Additional pinned clock premises and signed-tick admission

Parent extracted from full FetchUrl200 responses, not installed source/binaries.

Applecommitf6217f891ac0bb64f3d375211650a4c1ff8ca1ea: bsd/kern/kern_time.c andosfmk/arm/rtclock.c (sameURLs asV325). CPythonv3.12.13 Modules/signalmodule.c andPython/pytime.c:
https://raw.githubusercontent.com/python/cpython/v3.12.13/Modules/signalmodule.c
https://raw.githubusercontent.com/python/cpython/v3.12.13/Python/pytime.c

Pinned pexpert/pexpert/pexpert.h defines timebase_num/timebase_den asunsignedlong. Validatedd<=4 times10^9 fits even32-bit unsignedlong, so multiplication expression (not just destination) is representable; rawN representability remainsadmitted.

## clock_get_system_microtime

```c
void
clock_get_system_microtime(clock_sec_t *  secs,
    clock_usec_t * microsecs)
{
	absolutetime_to_microtime(mach_absolute_time(), secs, microsecs);
}
```

## absolutetime_to_microtime

```c
void
absolutetime_to_microtime(uint64_t       abstime,
    clock_sec_t *  secs,
    clock_usec_t * microsecs)
{
	uint64_t t64;

	*secs = t64 = abstime / rtclock_sec_divisor;
	abstime -= (t64 * rtclock_sec_divisor);

	*microsecs = (uint32_t)(abstime / rtclock_usec_divisor);
}
```

## getter_real

```c
case ITIMER_REAL:
		/*
		 * If time for real time timer has passed return 0,
		 * else return difference between current time and
		 * time for the timer to go off.
		 */
		aitv = p->p_realtimer;
		if (timerisset(&p->p_rtime)) {
			struct timeval          now;

			microuptime(&now);
			if (timercmp(&p->p_rtime, &now, <)) {
				timerclear(&aitv.it_value);
			} else {
				aitv.it_value = p->p_rtime;
				timevalsub(&aitv.it_value, &now);
			}
		} else {
			timerclear(&aitv.it_value);
		}
		break;
```

## double_from_timeval

```c
Py_LOCAL_INLINE(double)
double_from_timeval(struct timeval *tv)
{
    return tv->tv_sec + (double)(tv->tv_usec / 1000000.0);
}
```

## cpython_muldiv

```c
_PyTime_t
_PyTime_MulDiv(_PyTime_t ticks, _PyTime_t mul, _PyTime_t div)
{
    /* Compute (ticks * mul / div) in two parts to reduce the risk of integer
       overflow: compute the integer part, and then the remaining part.

       (ticks * mul) / div == (ticks / div) * mul + (ticks % div) * mul / div
    */
    _PyTime_t intpart, remaining;
    intpart = ticks / div;
    ticks %= div;
    remaining = _PyTime_Mul(ticks, mul) / div;
    // intpart * mul + remaining
    return _PyTime_Add(_PyTime_Mul(intpart, mul), remaining);
}
```

## cpython_apple_monotonic

```c
    uint64_t uticks = mach_absolute_time();
    // unsigned => signed
    assert(uticks <= (uint64_t)_PyTime_MAX);
    _PyTime_t ticks = (_PyTime_t)uticks;

    _PyTime_t ns = _PyTime_MulDiv(ticks, timebase_numer, timebase_denom);
    *tp = pytime_from_nanoseconds(ns);

```

## Additional explicit admission

CPython casts nativeuint64ticks to signed_PyTime_t and assertsuticks<=_PyTime_MAX. The positive-tick conversion premise therefore needs explicit0<=all sampleduticks<=INT64_MAX, plus exact positive representable mul/div/add operations. WithF<=UINT32_MAX, uptimea+2<=UINT32_MAX, reducednumer<=10^9 anddenom<=UINT32_MAX, remainderproduct<4.295e18 andresultns<4.295e18 fit signed64. Guard/prebirthplan must admit adequate signed-tick headroom for its whole boundedwindow, not assume the Cassert is present in release. No query/execution approved here.

Earlier finite models exercise the algebraic unsigned conversion theorem and doNOTestablish this added CPython signed-cast admission. Cases beyondINT64_MAX are not valid CPython-admitted clocks. Runtime/build/kernel/libsyscall common-origin applicability stillUNPROVED; sharedMachAPI calls are source evidence, not runtime equivalence proof.

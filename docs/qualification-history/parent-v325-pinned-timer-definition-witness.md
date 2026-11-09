# Pinned kernel timer definitions located, source-only

Apple XNU commit f6217f891ac0bb64f3d375211650a4c1ff8ca1ea. Parent FetchUrl200 full raw sources, extracted directly from retained responses (no guessed bodies).

- https://raw.githubusercontent.com/apple-oss-distributions/xnu/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/kern_time.c
- https://raw.githubusercontent.com/apple-oss-distributions/xnu/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm/rtclock.c

Setter at the pinned revision uses microuptime, not microtime. Previous shorthand naming must not stand in for this actual body. tvtoabstime casts seconds to uint32 then converts seconds and usecs separately and sums. ARM conversion uses rtclock_sec_divisor with split whole/remainder arithmetic. Require verified integer F=rtclock_sec_divisor and overflow/domain admission before a full-ratio bound. timevalsub and timevalfix preserve mathematical total even if a component stays noncanonical; CPython two-rounding outward bound still needs review. Darwin27 applicability remains UNPROVED. No role/source implementation or OS execution cleared.

## timevalsub

```c
void
timevalsub(
	struct timeval *t1,
	struct timeval *t2)
{
	t1->tv_sec -= t2->tv_sec;
	t1->tv_usec -= t2->tv_usec;
	timevalfix(t1);
}
```

## timevalfix

```c
void
timevalfix(
	struct timeval *t1)
{
	if (t1->tv_usec < 0) {
		t1->tv_sec--;
		t1->tv_usec += 1000000;
	}
	if (t1->tv_usec >= 1000000) {
		t1->tv_sec++;
		t1->tv_usec -= 1000000;
	}
}
```

## tvtoabstime

```c
uint64_t
tvtoabstime(
	struct timeval  *tvp)
{
	uint64_t        result, usresult;

	clock_interval_to_absolutetime_interval(
		(uint32_t)tvp->tv_sec, NSEC_PER_SEC, &result);
	clock_interval_to_absolutetime_interval(
		tvp->tv_usec, NSEC_PER_USEC, &usresult);

	return result + usresult;
}
```

## microuptime

```c
void
microuptime(
	struct timeval  *tvp)
{
	clock_sec_t             tv_sec;
	clock_usec_t    tv_usec;

	clock_get_system_microtime(&tv_sec, &tv_usec);

	tvp->tv_sec = tv_sec;
	tvp->tv_usec = tv_usec;
}
```

## clock_interval

```c
void
clock_interval_to_absolutetime_interval(uint32_t   interval,
    uint32_t   scale_factor,
    uint64_t * result)
{
	uint64_t nanosecs = (uint64_t) interval * scale_factor;
	uint64_t t64;

	*result = (t64 = nanosecs / NSEC_PER_SEC) * rtclock_sec_divisor;
	nanosecs -= (t64 * NSEC_PER_SEC);
	*result += (nanosecs * rtclock_sec_divisor) / NSEC_PER_SEC;
}
```

## timebase_callback

```c
static void
timebase_callback(struct timebase_freq_t * freq)
{
	unsigned long numer, denom;
	uint64_t      t64_1, t64_2;
	uint32_t      divisor;

	if (freq->timebase_den < 1 || freq->timebase_den > 4 ||
	    freq->timebase_num < freq->timebase_den) {
		panic("rtclock timebase_callback: invalid constant %ld / %ld",
		    freq->timebase_num, freq->timebase_den);
	}

	denom = freq->timebase_num;
	numer = freq->timebase_den * NSEC_PER_SEC;
	// reduce by the greatest common denominator to minimize overflow
	if (numer > denom) {
		t64_1 = numer;
		t64_2 = denom;
	} else {
		t64_1 = denom;
		t64_2 = numer;
	}
	while (t64_2 != 0) {
		uint64_t temp = t64_2;
		t64_2 = t64_1 % t64_2;
		t64_1 = temp;
	}
	numer /= t64_1;
	denom /= t64_1;

	rtclock_timebase_const.numer = (uint32_t)numer;
	rtclock_timebase_const.denom = (uint32_t)denom;
	divisor = (uint32_t)(freq->timebase_num / freq->timebase_den);

	rtclock_sec_divisor = divisor;
	rtclock_usec_divisor = divisor / USEC_PER_SEC;
}
```

Extraction correction: first helper extraction matched a forward declaration and the following early-init body. Corrected to the actual callback definition before review; raw tool log retains that parent extraction mistake. No implementation or approval relied on it.

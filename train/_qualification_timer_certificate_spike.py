"""Pure conditional timer arithmetic, not native admission or authority.

All timestamps/clock correspondence and coverage of the supplied window remain
external premises. No signal, timer, clock, process or network operation occurs.
"""
UINT32_MAX = 4_294_967_295
INT64_MAX = 9_223_372_036_854_775_807
NS = 1_000_000_000
MAX_WINDOW_NS = 28 * NS


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(label)
    return value


def _ceil(numerator, denominator):
    return -(-numerator // denominator)


def _frequency(value):
    return _integer(value, 3_000_000, UINT32_MAX, "frequency range")


def admit_timebase(numer, denom):
    """Check actual operands without silently reducing them."""
    _integer(numer, 1, UINT32_MAX, "Mach numerator")
    _integer(denom, 1, UINT32_MAX, "Mach denominator")
    # CPython py_mach_timebase_info checks this before clock conversion.
    if numer * denom > INT64_MAX:
        raise ValueError("CPython timebase product")
    product = NS * denom
    if product % numer:
        raise ValueError("noninteger frequency")
    frequency = _frequency(product // numer)
    return frequency, frequency // 1_000_000


def tick_bounds(sample_ns, frequency):
    """Inverse image of floor(native_ticks * NS / frequency)."""
    _integer(sample_ns, 0, INT64_MAX, "sample range")
    _frequency(frequency)
    return (_ceil(sample_ns * frequency, NS),
            _ceil((sample_ns + 1) * frequency, NS) - 1)


def observed_ticks(sample_ns, frequency):
    lower, upper = tick_bounds(sample_ns, frequency)
    if lower > upper:
        raise ValueError("unreachable observed clock bucket")
    return lower, upper


def admit_window(start_ns, end_ns, numer, denom):
    """Check every possible tick in a declared <=28s window.

    Start is an observation. End is a bound, not necessarily observable.
    This calculation does not prove that real execution stays in that window.
    """
    frequency, _ = admit_timebase(numer, denom)
    _integer(start_ns, 0, INT64_MAX, "window start")
    _integer(end_ns, start_ns, INT64_MAX, "window end")
    if end_ns - start_ns > MAX_WINDOW_NS:
        raise ValueError("window exceeds 28 seconds")
    lower, _ = observed_ticks(start_ns, frequency)
    _, upper = tick_bounds(end_ns, frequency)
    limit = min(INT64_MAX, (UINT32_MAX - 1) * frequency - 1)
    if upper > limit:
        raise ValueError("native signed-tick or uptime window limit")
    remainder_max = (upper % denom if lower // denom == upper // denom
                     else denom - 1)
    if (remainder_max * numer > INT64_MAX
            or (upper // denom) * numer > INT64_MAX
            or (upper * numer) // denom > INT64_MAX):
        raise ValueError("CPython conversion intermediate")
    return lower, upper


def remainder_ceiling_ns(value):
    if (type(value) is not float
            or not 0.0 < value < 5.5):
        raise ValueError("positive finite bounded float remainder")
    numerator, denominator = value.as_integer_ratio()
    return _ceil(numerator * NS, denominator)


def uncertainty_ns(frequency):
    frequency = _frequency(frequency)
    return (_ceil(NS, frequency // 1_000_000)
            + 1000 + _ceil(NS, frequency) + 1)


def check_certificate(value, interval, sample_ns, *, start_ns, end_ns,
                      pretransition_h_ns, requested_deadline_ns, numer, denom):
    """Pure model check against BOTH bounds; never grants live authority."""
    frequency, _ = admit_timebase(numer, denom)
    admit_window(start_ns, end_ns, numer, denom)
    _integer(sample_ns, start_ns, end_ns, "sample outside declared window")
    observed_ticks(sample_ns, frequency)
    _integer(pretransition_h_ns, 1, INT64_MAX, "pretransition H")
    _integer(requested_deadline_ns, 1, INT64_MAX, "requested deadline")
    if not start_ns <= pretransition_h_ns <= end_ns:
        raise ValueError("H outside declared window")
    if type(interval) is not float or interval != 0.0:
        raise ValueError("builtin float zero one-shot interval")
    upper = sample_ns + remainder_ceiling_ns(value) + uncertainty_ns(frequency)
    if upper > pretransition_h_ns:
        raise ValueError("expiry after retained pretransition H")
    if upper > requested_deadline_ns:
        raise ValueError("expiry after requested deadline")
    return upper


def certify_existing(getitimer, monotonic_ns, **facts):
    """Injected callables for ordering tests, not a native guard."""
    value, interval = getitimer()
    sample_ns = monotonic_ns()
    return check_certificate(value, interval, sample_ns, **facts)


def guard_horizon_ns(guard_ns, case_start_ns, invocation_start_ns):
    for value in (guard_ns, case_start_ns, invocation_start_ns):
        _integer(value, 0, INT64_MAX, "horizon input")
    if not invocation_start_ns <= case_start_ns <= guard_ns:
        raise ValueError("horizon time order")
    horizons = (guard_ns + 1_500_000_000, case_start_ns + 12 * NS,
                invocation_start_ns + MAX_WINDOW_NS)
    for value in horizons:
        _integer(value, 1, INT64_MAX, "horizon addition overflow")
    return min(horizons)

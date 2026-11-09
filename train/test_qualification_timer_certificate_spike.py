"""Pinned-C algebraic fixtures only, never running-kernel or containment proof."""
import unittest

from train import _qualification_timer_certificate_spike as g

N, M, I = 1_000_000_000, 4_294_967_295, 9_223_372_036_854_775_807
FREQUENCIES = (
    (1000, 3, 3_000_000, 3),
    (N, 3_000_001, 3_000_001, 3),
    (N, 3_999_999, 3_999_999, 3),
    (250, 1, 4_000_000, 4),
    (125, 3, 24_000_000, 24),
    (1, 1, N, 1000),
    (N, M, M, 4294),
)


def microtime(ticks, frequency):
    seconds = ticks // frequency
    return seconds, (ticks - seconds * frequency) // (frequency // 1_000_000)


def fix(seconds, useconds):
    if useconds < 0:
        seconds, useconds = seconds - 1, useconds + 1_000_000
    if useconds >= 1_000_000:
        seconds, useconds = seconds + 1, useconds - 1_000_000
    return seconds, useconds


def setter(ticks, interval, frequency):
    seconds, useconds = microtime(ticks, frequency)
    return fix(seconds + interval[0], useconds + interval[1])


def getter(expiry, ticks, frequency):
    now = microtime(ticks, frequency)
    if expiry < now:
        return 0, 0, 0.0
    seconds, useconds = fix(expiry[0] - now[0], expiry[1] - now[1])
    return seconds, useconds, seconds + useconds / 1_000_000.0


def expiry_ticks(expiry, frequency):
    seconds, useconds = expiry
    # Pinned split conversion, without treating sec/usec as canonical.
    nanos = useconds * 1000
    return (seconds * frequency + (nanos // N) * frequency
            + ((nanos % N) * frequency) // N)


def clock_ns(ticks, numer, denom):
    # The witnessed CPython split multiplication, not float conversion.
    return (ticks // denom) * numer + ((ticks % denom) * numer) // denom


def facts(**overrides):
    result = dict(start_ns=0, end_ns=28 * N, pretransition_h_ns=2 * N,
                  requested_deadline_ns=28 * N, numer=1, denom=1)
    result.update(overrides)
    return result


def noncanonical_fixture():
    frequency, numer, denom = 3_906_250, 512, 2
    expiry = setter(7 * frequency + 3_000_000, (1, 0), frequency)
    query = 7 * frequency + 3_300_000
    sample = clock_ns(query + 1000, numer, denom)
    components = getter(expiry, query, frequency)
    return frequency, numer, denom, expiry, sample, components


class TimerCertificateTests(unittest.TestCase):
    def test_01_all_frequencies(self):
        for numer, denom, frequency, q in FREQUENCIES:
            self.assertEqual(g.admit_timebase(numer, denom), (frequency, q))

    def test_02_timebase_types_ranges_ratio(self):
        for args in ((True, 1), (1, False), (0, 1), (1, 0), (M + 1, 1),
                     (1, M + 1), (1.0, 1), (1, float("nan")), (7, 3),
                     (2048, 4), (1, 5)):
            self.assertRaises(ValueError, g.admit_timebase, *args)

    def test_03_unreduced_cpython_product(self):
        self.assertGreater(M * M, I)
        self.assertRaises(ValueError, g.admit_timebase, M, M)
        # No silent reduction of (M,M) to (1,1).
        self.assertEqual(g.admit_timebase(1, 1), (N, 1000))

    def test_04_exact_inverse(self):
        self.assertEqual(g.observed_ticks(0, M), (0, 4))
        self.assertEqual(g.tick_bounds(1, 3_000_000), (1, 0))
        self.assertRaises(ValueError, g.observed_ticks, 1, 3_000_000)
        self.assertEqual(g.observed_ticks(1000, 3_000_000), (3, 3))
        for value in (-1, I + 1, True, 0.0):
            self.assertRaises(ValueError, g.tick_bounds, value, N)

    def test_05_signed_tick_window_edge(self):
        frequency, numer, denom = M, N, M
        limit_ns = ((I + 1) * N) // frequency - 1
        start_ns = clock_ns(I - 2 * frequency, numer, denom)
        self.assertGreater(clock_ns(I + 1, numer, denom), limit_ns)
        self.assertLessEqual(g.admit_window(start_ns, limit_ns, numer, denom)[1], I)
        self.assertRaises(ValueError, g.admit_window, start_ns, limit_ns + 1,
                          numer, denom)

    def test_06_uptime_window_edge(self):
        frequency, numer, denom = 3_000_000, 1000, 3
        limit_tick = (M - 1) * frequency - 1
        limit_ns = (M - 1) * N - 1
        start_ns = clock_ns(limit_tick - 2 * frequency, numer, denom)
        self.assertEqual((limit_tick + 1) // frequency + 2, M + 1)
        self.assertGreater(clock_ns(limit_tick + 1, numer, denom), limit_ns)
        self.assertLessEqual(g.admit_window(start_ns, limit_ns, numer, denom)[1],
                             limit_tick)
        self.assertRaises(ValueError, g.admit_window, start_ns, limit_ns + 1,
                          numer, denom)

    def test_07_window_bounds(self):
        for start, end in ((-1, 0), (0, -1), (1, 0), (0, 28 * N + 1),
                           (0, I + 1), (True, 1), (0, False), (0.0, N)):
            self.assertRaises(ValueError, g.admit_window, start, end, 1, 1)
        g.admit_window(0, 28 * N, 1, 1)
        g.admit_window(0, 0, 1, 1)

    def test_08_native_conversion_intermediates(self):
        for numer, denom, frequency, _ in FREQUENCIES:
            lower, upper = g.admit_window(0, 28 * N, numer, denom)
            remainder = (upper % denom if lower // denom == upper // denom
                         else denom - 1)
            self.assertLessEqual(remainder * numer, I)
            self.assertLessEqual((upper // denom) * numer, I)
            self.assertLessEqual(clock_ns(upper, numer, denom), I)
            self.assertLessEqual(upper // frequency + 2, M)

    def test_09_exact_ceiling(self):
        self.assertEqual(g.remainder_ceiling_ns(0.1), 100_000_001)
        self.assertEqual(g.remainder_ceiling_ns(0.5), 500_000_000)
        self.assertNotEqual(int(0.1 * N), g.remainder_ceiling_ns(0.1))

    def test_10_remainder_envelope(self):
        for value in (0.0, -0.1, 5.5, float("inf"), float("-inf"),
                      float("nan"), 1, True, "0.1", 0j):
            self.assertRaises(ValueError, g.remainder_ceiling_ns, value)

    def test_11_reachable_noncanonical(self):
        frequency, numer, denom, expiry, sample, components = noncanonical_fixture()
        self.assertEqual(expiry, (9, 0))
        self.assertEqual(components[:2], (1, -100_000))
        upper = g.check_certificate(
            components[2], 0.0, sample,
            **facts(numer=numer, denom=denom, pretransition_h_ns=10 * N))
        self.assertGreaterEqual(upper * denom, expiry_ticks(expiry, frequency) * numer)

    def test_12_coarse_term_load_bearing(self):
        frequency, numer, denom, expiry, sample, components = noncanonical_fixture()
        upper = g.check_certificate(
            components[2], 0.0, sample,
            **facts(numer=numer, denom=denom, pretransition_h_ns=10 * N))
        coarse = (N + frequency // 1_000_000 - 1) // (frequency // 1_000_000)
        mutant = upper - coarse
        self.assertLess(mutant * denom, expiry_ticks(expiry, frequency) * numer)
        self.assertGreaterEqual(upper * denom, expiry_ticks(expiry, frequency) * numer)

    def test_13_absolute_expiry_sweep(self):
        for numer, denom, frequency, _ in FREQUENCIES:
            checked = 0
            for interval in ((0, 500_000), (1, 0)):
                for install in (0, frequency // 7):
                    expiry = setter(install, interval, frequency)
                    end_tick = expiry_ticks(expiry, frequency)
                    for query in (install, install + frequency // 3, end_tick - 1):
                        if not install <= query < end_tick:
                            continue
                        sample_tick = query + min(frequency // 8, end_tick - 1 - query)
                        value = getter(expiry, query, frequency)[2]
                        if value <= 0.0:
                            continue
                        upper = g.check_certificate(
                            value, 0.0, clock_ns(sample_tick, numer, denom),
                            **facts(numer=numer, denom=denom))
                        self.assertGreaterEqual(upper * denom, end_tick * numer)
                        checked += 1
            self.assertGreaterEqual(checked, 2)

    def test_14_both_bounds_equality(self):
        upper = N + g.remainder_ceiling_ns(0.4) + g.uncertainty_ns(N)
        self.assertEqual(g.check_certificate(
            0.4, 0.0, N, **facts(pretransition_h_ns=upper,
                                 requested_deadline_ns=upper)), upper)

    def test_15_retained_h_load_bearing(self):
        upper = N + g.remainder_ceiling_ns(0.4) + g.uncertainty_ns(N)
        with self.assertRaisesRegex(ValueError, "retained pretransition H"):
            g.check_certificate(0.4, 0.0, N,
                                **facts(pretransition_h_ns=upper - 1))

    def test_16_requested_deadline_load_bearing(self):
        upper = N + g.remainder_ceiling_ns(0.4) + g.uncertainty_ns(N)
        with self.assertRaisesRegex(ValueError, "requested deadline"):
            g.check_certificate(0.4, 0.0, N,
                                **facts(requested_deadline_ns=upper - 1))

    def test_17_sample_window(self):
        for sample in (-1, 28 * N + 1, True, float(N)):
            self.assertRaises(ValueError, g.check_certificate, 0.4, 0.0,
                              sample, **facts())
        self.assertRaises(ValueError, g.check_certificate, 0.4, 0.0, 1,
                          **facts(numer=1000, denom=3))

    def test_18_certificate_argument_types(self):
        for key in ("pretransition_h_ns", "requested_deadline_ns"):
            for value in (-1, 0, I + 1, True, 2.0, float("inf"), float("nan")):
                self.assertRaises(ValueError, g.check_certificate, 0.4, 0.0, N,
                                  **facts(**{key: value}))
        for h in (28 * N + 1,):
            self.assertRaises(ValueError, g.check_certificate, 0.4, 0.0, N,
                              **facts(pretransition_h_ns=h))

    def test_19_order_and_zero_writes(self):
        calls = []
        def timer():
            calls.append("query")
            return 0.4, 0.0
        def clock():
            self.assertEqual(calls, ["query"])
            calls.append("sample")
            return N
        for _ in range(100):
            calls.clear()
            g.certify_existing(timer, clock, **facts())
            self.assertEqual(calls, ["query", "sample"])

    def test_20_interval_missing_periodic(self):
        for interval in (True, 0, 0j, "0", 0.1, float("inf"), float("nan")):
            self.assertRaises(ValueError, g.check_certificate, 0.4, interval, N,
                              **facts())
        for value in (0.0, -0.1, 5.5):
            self.assertRaises(ValueError, g.check_certificate, value, 0.0, N,
                              **facts())
        g.check_certificate(0.4, -0.0, N, **facts())

    def test_21_horizon_bounds(self):
        self.assertEqual(g.guard_horizon_ns(3 * N, 2 * N, N), 4_500_000_000)
        for args in ((0, 1, 0), (1, 0, 1), (-1, 0, 0), (True, 0, 0),
                     (1.0, 0, 0), (I, I, I)):
            self.assertRaises(ValueError, g.guard_horizon_ns, *args)

    def test_22_future_end_not_observed(self):
        self.assertRaises(ValueError, g.observed_ticks, 1, 3_000_000)
        self.assertEqual(g.admit_window(0, 1, 1000, 3), (0, 0))

"""Outer timing contracts. Real fixtures are local semantics, not a performance trial."""
import json
import os
import unittest
from fractions import Fraction

from bench.sql_reuse_timing import Arm, Pair, Span, Timer, analyze, render_summary


class Clock:
    def __init__(self, *ticks):
        self.ticks = iter(ticks)

    def __call__(self):
        return next(self.ticks)


class TimingTests(unittest.TestCase):
    def test_all_lifecycle_success_identity_exact_ns(self):
        for kind in ("candidate_prepare", "qualification", "reuse", "baseline_full"):
            with self.subTest(kind=kind):
                timer = Timer(clock=Clock(100, 350))
                value = object()
                self.assertIs(timer.run(kind, lambda: value, allow_execution=True), value)
                self.assertEqual(timer.observations, (Span(kind, 250, True, True),))

    def test_all_lifecycle_exception_identity_cause_exact_ns(self):
        for kind in ("candidate_prepare", "qualification", "reuse", "baseline_full"):
            for error in (RuntimeError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
                with self.subTest(kind=kind, error=type(error)):
                    timer = Timer(clock=Clock(100, 350))
                    cause = ValueError("SECRET")
                    error.__cause__ = cause

                    def fail():
                        raise error

                    try:
                        timer.run(kind, fail, allow_execution=True)
                    except BaseException as got:
                        self.assertIs(got, error)
                        self.assertIs(got.__cause__, cause)
                    else:
                        self.fail("must rethrow original")
                    self.assertEqual(timer.observations, (Span(kind, 250, False, True),))

    def test_opt_in_is_exact_and_has_no_callbacks(self):
        for flag in (False, None, 1, "yes"):
            timer = Timer(clock=Clock())
            with self.assertRaises(ValueError):
                timer.run("reuse", lambda: self.fail("invoked"), allow_execution=flag)
            self.assertEqual(timer.observations, ())

    def test_unknown_kind_never_invokes(self):
        timer = Timer(clock=Clock())
        with self.assertRaises(ValueError):
            timer.run("not-a-kind", lambda: self.fail("invoked"), allow_execution=True)

    def test_invalid_start_prevents_invocation(self):
        for start in (-1, True, 0.5):
            timer = Timer(clock=Clock(start))
            with self.assertRaises(ValueError):
                timer.run("reuse", lambda: self.fail("invoked"), allow_execution=True)
            self.assertEqual(timer.observations, ())

    def test_invalid_end_is_unknown_not_zero(self):
        for end in (-1, 99, True, 350.0):
            timer = Timer(clock=Clock(100, end))
            with self.assertRaises(ValueError):
                timer.run("reuse", lambda: None, allow_execution=True)
            self.assertEqual(timer.observations, (Span("reuse", None, True, False),))

    def test_invalid_end_preserves_operation_error(self):
        for error in (RuntimeError(), KeyboardInterrupt()):
            timer = Timer(clock=Clock(100, 99))

            def fail():
                raise error

            try:
                timer.run("qualification", fail, allow_execution=True)
            except BaseException as got:
                self.assertIs(got, error)
            else:
                self.fail("missing error")
            self.assertEqual(timer.observations, (Span("qualification", None, False, False),))

    def test_final_clock_exception_preserves_operation_error(self):
        original = SystemExit(3)
        timer = Timer(clock=Clock(100))

        def fail():
            raise original

        try:
            timer.run("reuse", fail, allow_execution=True)
        except BaseException as got:
            self.assertIs(got, original)
        self.assertFalse(timer.observations[0].clock_valid)

    def test_output_write_fsync_included(self):
        now = [100]

        def operation():
            now[0] += 7  # compute
            now[0] += 31  # output write
            if os.environ.get("TIMING_CONTROL") != "skip-final-fsync":
                now[0] += 11  # fsync, last SDK output step
            return "path"

        timer = Timer(clock=lambda: now[0])
        self.assertEqual(timer.run("reuse", operation, allow_execution=True), "path")
        self.assertEqual(timer.observations[0].elapsed_ns, 49, "final write/fsync span omitted")


class ArithmeticTests(unittest.TestCase):
    def setup_spans(self):
        spans = (
            Span("candidate_prepare", 10, True, True),
            Span("qualification", 40, False, True),
            Span("qualification", 50, True, True),
        )
        if os.environ.get("TIMING_CONTROL") == "drop-failure-overhead":
            spans = tuple(span for span in spans if span.completed)
        return spans

    def pairs(self):
        return tuple(Pair(f"case-{n}", Arm(300, True), Arm(200, True), True)
                     for n in range(8))

    def result(self, pairs=None, spans=None, setup_complete=True, planned=None):
        pairs = self.pairs() if pairs is None else pairs
        return analyze(
            pairs,
            self.setup_spans() if spans is None else spans,
            planned_case_ids=tuple(p.case_id for p in pairs) if planned is None else planned,
            setup_complete=setup_complete,
        )

    def test_missing_entire_pairs_preserves_independent_denominator(self):
        planned = tuple(p.case_id for p in self.pairs())
        for observations in (self.pairs()[:-1], ()):
            result = self.result(pairs=observations, planned=planned)
            self.assertEqual(result.planned_pairs, 8)
            self.assertEqual(len(json.loads(render_summary(result))["rows"]), 8)
            self.assertIsNone(result.baseline_mean_ns)
            self.assertIsNone(result.gross_per_use_ns)
            self.assertEqual(result.scenarios, ())
            self.assertFalse(result.rows[-1].eligible)

    def test_exact_setup_failure_overhead_and_scenarios(self):
        result = self.result()
        self.assertEqual(result.setup_ns, 100, "failed qualification overhead discarded")
        self.assertEqual(result.baseline_mean_ns, 300)
        self.assertEqual(result.treatment_mean_ns, 200)
        self.assertEqual(result.gross_per_use_ns, 100)
        self.assertEqual(result.break_even_uses, 1)
        self.assertEqual(tuple(s.uses for s in result.scenarios), (100, 1000, 10000))
        for scenario in result.scenarios:
            self.assertEqual(scenario.net_per_use_ns, 100 - Fraction(100, scenario.uses))
            self.assertEqual(scenario.total_net_ns, 100 * scenario.uses - 100)

    def test_fractional_mean_no_rounding(self):
        pairs = (Pair("a", Arm(2, True), Arm(1, True), True),
                 Pair("b", Arm(3, True), Arm(1, True), True))
        result = self.result(pairs=pairs)
        self.assertEqual(result.gross_per_use_ns, Fraction(3, 2))
        self.assertEqual(result.break_even_uses, 67)
        self.assertEqual(result.scenarios[0].net_per_use_ns, Fraction(1, 2))

    def test_missing_arm_preserves_eight_rows_no_claims(self):
        pairs = list(self.pairs())
        pairs[3] = Pair("missing", Arm(300, True), None, True)
        result = self.result(pairs=tuple(pairs))
        self.assertEqual(result.planned_pairs, 8)
        self.assertEqual(len(result.rows), 8)
        self.assertIsNone(result.baseline_mean_ns)
        self.assertIsNone(result.gross_per_use_ns)
        self.assertEqual(result.scenarios, ())
        self.assertIsNone(result.break_even_uses)

    def test_abort_known_duration_preserved_not_solved(self):
        pairs = list(self.pairs())
        pairs[7] = Pair("abort", Arm(300, True), Arm(70, False), True)
        result = self.result(pairs=tuple(pairs))
        self.assertEqual(len(result.rows), 8)
        self.assertEqual(result.rows[-1].treatment_ns, 70)
        self.assertFalse(result.rows[-1].eligible)
        self.assertIsNone(result.gross_per_use_ns)

    def test_unknown_invalid_or_incomparable_suppresses_all_savings(self):
        for arm, comparable in ((Arm(None, True), True), (Arm(20, None), True),
                                (Arm(20, True), False)):
            pairs = list(self.pairs())
            pairs[0] = Pair("bad", Arm(300, True), arm, comparable)
            result = self.result(pairs=tuple(pairs))
            self.assertIsNone(result.gross_per_use_ns)
            self.assertEqual(result.scenarios, ())

    def test_unknown_setup_never_zero(self):
        for spans, complete in (((), True), (self.setup_spans(), False),
                                ((Span("qualification", None, False, False),), True)):
            result = self.result(spans=spans, setup_complete=complete)
            self.assertIsNone(result.setup_ns)
            self.assertIsNone(result.gross_per_use_ns)
            self.assertEqual(result.scenarios, ())

    def test_nonpositive_gross_no_finite_break_even(self):
        for baseline in (100, 200):
            pairs = (Pair("x", Arm(baseline, True), Arm(200, True), True),)
            result = self.result(pairs=pairs)
            self.assertIsNone(result.break_even_uses)
            self.assertEqual(len(result.scenarios), 3)
            self.assertLess(result.scenarios[0].net_per_use_ns, 0)

    def test_validation_rejects_bad_inputs(self):
        for call in (
            lambda: Arm(-1, True), lambda: Arm(True, True),
            lambda: Arm(1.0, True), lambda: Arm(1, 1),
            lambda: Span("reuse", -1, True, True),
            lambda: Span("reuse", 1, True, False),
            lambda: analyze((), (), planned_case_ids=(), setup_complete=True),
            lambda: self.result(pairs=(self.pairs()[0], self.pairs()[0])),
            lambda: self.result(planned=("case-0",)),
            lambda: self.result(planned=("",)),
            lambda: self.result(spans=(Span("reuse", 1, True, True),)),
            lambda: self.result(setup_complete=1),
        ):
            with self.subTest(call=call):
                with self.assertRaises((TypeError, ValueError)):
                    call()

    def test_summary_never_renders_identifier_or_sensitive_payload(self):
        secret = '<script>alert("SQL SELECT password FROM users /private/token SECRET")</script>\n'
        result = self.result(pairs=(Pair(secret, Arm(300, True), Arm(200, True), True),))
        rendered = render_summary(result)
        parsed = json.loads(rendered)
        self.assertNotIn(secret, rendered)
        for forbidden in ("<script", "password", "/private", "SECRET", "SELECT"):
            self.assertNotIn(forbidden, rendered)
        self.assertEqual(parsed["rows"][0]["case"], 1)
        self.assertIn("unavailable", rendered)
        self.assertEqual(parsed["scenarios"][0]["label"], "SCENARIO")


if __name__ == "__main__":
    unittest.main()

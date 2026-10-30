# SQL reuse outer timing, 2026-10-29

[External caller-operation harness](../bench/sql_reuse_timing.py),
[pure tests](../bench/test_sql_reuse_timing.py),
[real-SDK integration test](../train/test_sql_reuse_timing.py) and
[contract](../spec/sql-reuse-timing.md).
The [final offline receipt](2026-10-29-sql-qualification-evidence.md)
records completed full-suite, independent-probe and sensitivity acceptance.

## Implemented span

`Timer.run` requires literal `allow_execution=True` to invoke a trusted callback.
It selects no SDK runtime, grants no SDK consent and approves no reuse.
Operations are candidate preparation, qualification, reuse and full baseline.
The callback's return or original exception is preserved.

Timing covers the entire synchronous callback, including reads, writes, rename
and final fsync inside it. Preparation outside the callback and observation
append/finalization are excluded. Callback completeness and the declaration
that every setup attempt was supplied are caller trust, not independently
verified provenance. An SDK callback span is not provider/customer/team
end-to-end time. Concurrent spans cannot be summed as team hours.

All caller-planned rows remain, including pairs missing both arms. The eight-row
regression is an example, not an API count restriction. Incomplete, invalid,
unknown or incomparable evidence withholds aggregates. Every setup attempt
counts, including failed qualification; empty/unknown setup is unavailable,
not zero.

Exact Fraction nanoseconds describe gross differences and amortized scenarios
at 100/1,000/10,000 uses. These are scenarios, not adoption predictions.
Break-even is the first integer with nonnegative net savings: equality is zero,
not positive benefit. Nonpositive gross savings has no finite break-even.
Billing, tokens, human review, CPU, provider latency, retrieval and team wall time
remain unavailable. No elapsed-time-to-money conversion is made.

## Completed checks and limits

The production module matches the scratch Python and actual Devin CLI SWE-2 High
approved prototype:
`97b593fabc7196fb1726cf25e8e9467fb7fbbfb2f003910c304c66021202262c`.
Static Python/security reviews found no findings; static review is separate
from execution.

Final full suite: **3,793 passed**, zero failed, one optional missing-Torch skip,
two configured tokenizer deselections, ten warnings, 28 passing subtests,
exit 0 in **725.24s**. All 260 pre-documentation source bindings stayed unchanged.
Twenty timing unit cases comprise 19 pure bench tests plus one train SDK case;
their subtests and focused counts overlap the full total.

Independent probes passed 28/28, including real SQLite four qualifications and
one reuse, all valid EX=1, with final fsync inside callback boundaries.
Three separate sensitivity controls failed intended assertions:

- Omit final fsync: 38 versus required 49 simulated ns.
- Omit failed setup: 60 versus required 100 simulated ns.
- Swallow post-rename final fsync: expected `OSError` not raised.

Restored 19 timing checks and one storage check passed. Synthetic nanoseconds
test measurement boundaries, not product speedups. Earlier root-context
20-test/525-focused evidence did not establish package isolation; the later
unchanged SDK-test relocation repaired that test-ownership regression.
See the linked final receipt for the retained 3,792-pass/one-failure run,
193-case correction and scoped resource/network evidence.

## Local evidence and non-goals

`~/scratch/co-train-2026-10-29/final-corrected-validation-q6afw45z/validation-receipt.json`
is the canonical receipt; `full.log` line 122 records the full-suite result.
Its sibling `independent-probes-execution.json` and
`timing-restored-20-execution.json` record actual outcomes (the latter's
historical filename contains 20, but its corrected pure-bench count is 19).
Receipt/manifest hashes are in the linked qualification receipt.

Original evidence remains local scratch. Source/tests reproduce mechanics,
not the original environment. The full run tested source before these docs;
documentation links/whitespace were checked separately.
This proves timing mechanics, not lower latency, money saved, model benefit,
authenticated approval, native SDK acceptance or team hours.
See [research and proposed experiment](../research/2026-10-29-team-reuse-economics.md).
No new schema, provider, registry or authorization gate follows.

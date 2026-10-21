# `bench` — the BIRD-SQL taskset: the instrument's contract

**Status: built, tested offline, and SIGNED 2026-10-12.** This instrument is the fourth
change to this project's measuring apparatus and it required a pre-registration amendment
before any number produced with it is reportable. That amendment is signed at
`docs/pre-registration.md:376` (heading carries `signed`; `train/guards.py`'s
`_amendment_is_signed("A8")` returns True). The draft at
`docs/amendment-A8-bird-sql-draft.md` is kept as the record of what was put in front of the
owner, not as the operative instrument.

**CORRECTED 2026-10-19.** This paragraph read "NOT SIGNED … That amendment is drafted …
and is unsigned. **No measurement has been run on this instrument**, and none may be until
the owner signs." Both halves went stale on the same commit: A8 was signed 2026-10-12
(`docs/pre-registration.md:376`), and the probe has since run over this instrument's own
prompt file, `bench/probe_prompts_sql.jsonl` (800 BIRD dev questions), with `--reward ex`,
scoring through `bench.score.extract_sql` and execution accuracy. It aborted at step 0 on
four groups and produced **no solve rate** (`docs/probe-v9.md`). So: extraction and the EX
reward are exercised; no EX number exists, and none is claimed here.

---

## 1. Why the previous instrument is dead

Established elsewhere and not re-derived here; stated so the replacement's design targets
are legible.

`ledger`'s record schema `{id, kind, amount, owner, link}` admits exactly **9 cheap
shapes** — 3 field reads, 5 chain-walk statistics, 1 reverse-link. Replicates of a shape
are correlated, so effective n is bounded by `shapes / rho` regardless of corpus size.
Against the **61 effective paired tasks** the project's own power function requires, that
is a vertical asymptote at `rho = 9 / 61 = 0.1475`. Going from 40 records to 400
multiplies replicates and adds **zero shapes**.

Run 3d then scored an exact **23/23 tie on both arms**. That is the same fact arriving as
saturation rather than as arithmetic: a 0/1 reward needs tasks the policy *sometimes*
solves, and both saturation (`p → 1`) and uniform failure (`p → 0`) produce groups with no
variance and therefore no advantage to learn from.

So a replacement has to clear two bars that pull against each other: **many more shapes**,
and **a difficulty inside the band where a 0.6B policy is neither saturated nor uniformly
failing.**

`ledger/generate.py`'s header states the convention this instrument is measured by, and it
is the one the replacement must honour: **only a grammar raises shapes; a bigger file
raises replicates.**

---

## 2. The frontier-band argument, with its numbers

A 0/1 execution-accuracy reward is informative only where the policy's success rate sits
away from both ends. Call that the **frontier band, 20–80%**.

BIRD-SQL is the only candidate found with a *published sub-1B number* to site that band
against. From SLM-SQL:

| model size | published EX on BIRD dev |
|---|---|
| 0.5B | **56.87%** |
| 1.5B | 67.08% |
| reported average gain from their training | **+31.4 pt** |

**The inference, stated as an inference.** `56.87 − 31.4 ≈ 25.5%`, so an *untrained* 0.5B
model sits at roughly **25% EX** — inside the 20–80% band, near its lower half, which is
where a 0/1 reward has the most headroom to climb without being uniform failure.

This is **arithmetic on a published aggregate, not a published untrained number.** The
+31.4 pt figure is an average across their model sizes, not the 0.5B's own delta, so 25.5%
is an estimate with unquantified error. It is strong enough to site a band and far too weak
to predict a score. The amendment draft treats it accordingly.

Licences pass: **BIRD CC BY-SA 4.0**, **Spider Apache-2.0**.

---

## 3. The interface the harness lane consumes

The HARNESS lane owns `ptc/sql_arms.py` and builds the paired arms. This is the entire
surface it needs. Nothing in `bench/` imports `verifiers`, deliberately: the shape
inventory, the scorer and the power report all run in a bare interpreter, so none of them
need a model, a network or an environment to exercise. The `verifiers` wrapping belongs in
`ptc/sql_arms.py`.

### 3.1 The task

```python
# bench/task.py
TIERS = ("simple", "moderate", "challenging")

@dataclass(frozen=True)
class SqlTask:
    name: str           # "bird-0042" — the key ptc/paired.py pairs arms on
    question: str       # verbatim from the corpus
    evidence: str       # BIRD's external-knowledge hint; "" for Spider
    gold_sql: str       # verbatim reference query, never rewritten
    db_id: str
    db_path: str        # ABSOLUTE path to the task's sqlite file
    tier: str           # one of TIERS
    tier_source: str    # "annotated" (BIRD) | "derived" (Spider, structural)
    shape: str          # fine clause skeleton — the effective-n unit
    coarse_shape: str   # coarse structural family
    source: str         # "bird" | "spider" | "fixture"

    @property
    def tier_index(self) -> int:   # position in TIERS
```

### 3.2 Loading

```python
# bench/loader.py
def load_bird(root: str | Path, require_db: bool = True) -> list[SqlTask]
def load_spider(root: str | Path, require_db: bool = True) -> list[SqlTask]
class CorpusMissing(FileNotFoundError): ...
```

Both raise `CorpusMissing` — naming the exact path expected — rather than returning an
empty list. An empty taskset scores 0/0 on both arms and reads as a tie, which is the
shape of the failure that killed the last instrument.

### 3.3 Scoring

```python
# bench/score.py
INVALID_STATUSES = frozenset({"gold_error", "gold_timeout", "gold_truncated",
                              "db_missing"})

@dataclass(frozen=True)
class ExResult:
    score: float        # 1.0 match, 0.0 otherwise; meaningless when valid is False
    status: str         # match|mismatch|pred_error|pred_timeout|pred_truncated|
                        # pred_empty| or one of INVALID_STATUSES
    valid: bool         # False => the TASK is defective, not the prediction wrong
    detail: str = ""
    n_pred_rows: int = 0
    n_gold_rows: int = 0

def extract_sql(text: str) -> str

def execution_accuracy(predicted_sql: str, task: SqlTask, *,
                       timeout_s: float = 30.0,
                       max_rows: int = 100_000,
                       compare: str = "multiset") -> ExResult

def validate_golds(tasks: list[SqlTask], *, timeout_s: float = 30.0,
                   max_rows: int = 100_000) -> list[tuple[SqlTask, ExResult]]
```

### 3.4 Suite construction and the report

```python
# bench/suite.py
def select(tasks: list[SqlTask], per_tier: dict[str, int] | int, *,
           seed: int = 0, granularity: str = "fine") -> list[SqlTask]
def inventory(tasks: list[SqlTask], granularity: str = "fine") -> dict[str, dict]
def report(tasks: list[SqlTask], out=sys.stdout) -> None
def discordance_from_band(p: float) -> float
```

`select` is pure and touches no database, so a suite can be built — and signed — before the
corpus is present.

### 3.5 Three integration rules the harness must follow

1. **Call `extract_sql()` before `execution_accuracy()`.** The scorer does not unwrap
   fenced output, by design, so that extraction stays an explicit auditable step rather
   than a silent leniency inside the metric. Skipping it scores every ```` ```sql ````
   prediction as a syntax error, which understates the model and looks exactly like a
   frontier-band problem while not being one. A test pins both halves of this.

2. **Map `ExResult.valid is False` onto the rollout's `ok` field, not onto a score of 0.**
   A defective task scored 0 credits whichever arm also failed — the precise asymmetry
   `ptc/paired.py:refuse_voids` exists to refuse. Better still, run `validate_golds()`
   over the suite *before* spending model calls: a defective task found beforehand is
   dropped with disclosure, and found mid-run it voids the whole comparison.

3. **Set `min_calls = task.tier_index`** in the `vf.TaskData` subclass, so
   `ptc/paired.py:split_tiers` — which keys on `min_calls` and buckets `max` against
   everything else — places `challenging` in its `full-scan` bucket. See §6.1 for what
   that split loses.

---

## 4. What the shape inventory actually says

Measured on the real BIRD dev corpus (`dev.zip`, 346 MB, downloaded and extracted
2026-10-11). Reproduce with:

```
.venv-ptc/bin/python -m bench <path-to-extracted-bird-dev>
```

**1534 questions over 277 fine shapes and 25 coarse shapes.**

| tier | questions | fine shapes | coarse shapes | replicates / fine shape | shapes with 1 question |
|---|---|---|---|---|---|
| simple | 925 | 141 | 20 | 6.6 | 74 |
| moderate | 464 | 154 | 20 | 3.0 | 94 |
| challenging | 145 | 87 | 17 | 1.7 | 64 |
| **TOTAL** | **1534** | **277** | **25** | **5.5** | **232** |

**1534 is a question count and it is not this instrument's n.** It is the single quantity
most likely to be mistaken for one, which is why `report()` prints that sentence where it
prints the number. The replicate distribution is concentrated: **24 fine shapes hold 991 of
the 1534 questions**, while 145 shapes hold exactly one each.

### 4.1 The decisive number: `rho_max = shapes / n_required`

`n_required` comes from `ptc/paired.py:power_pairs` — this project's own power function,
imported rather than reimplemented. Discordance is derived from the frontier band as
`2p(1−p)`, the rate two *independent* arms at marginal `p` disagree.

At band centre (`p = 0.50`, discordance `0.500`):

| effect | n required | simple (141) | moderate (154) | challenging (87) |
|---|---|---|---|---|
| +5.0 pp | 1571 | rho < 0.090 | rho < 0.098 | rho < 0.055 |
| **+6.8 pp** (pre-reg §3 APEX target) | **859** | **rho < 0.164** | **rho < 0.179** | **rho < 0.101** |
| +10.0 pp | 398 | rho < 0.354 | rho < 0.387 | rho < 0.219 |
| **+25.0 pp** (A6/N1's prediction) | **59** | **any rho** | **any rho** | **any rho** |

At the band floor (`p = 0.20`, discordance `0.320`) the requirements fall — +6.8 pp needs
546 and +25 pp needs 36 — and the `rho` ceilings rise accordingly. Both are printed by
`report()`.

**Every n here is a FLOOR, not an estimate.** `2p(1−p)` assumes the arms are independent.
Real paired arms are positively correlated — both fail the genuinely hard tasks and both
pass the easy ones — which *lowers* discordance, and lower discordance needs *more* paired
tasks. The report prints a halved-discordance row for exactly this reason.

### 4.3 Gold-query validity, measured on the full corpus

`validate_golds()` was run over all 1534 BIRD dev golds (72 s wall clock). **1530 execute
cleanly. 4 do not, and they are two different things:**

| task | db | tier | outcome at 30 s / 100 000 rows | what it actually is |
|---|---|---|---|---|
| `bird-0384` | card_games | simple | `gold_truncated` | **not a defect** — the gold legitimately returns **228 765 rows** and executes in 1.0 s with a 2 M row cap |
| `bird-0406` | card_games | simple | `gold_truncated` | **not a defect** — legitimately returns **278 230 rows**, executes in 0.7 s with a 2 M row cap |
| `bird-0518` | card_games | moderate | `gold_timeout` | **genuinely slow** — still times out at **60 s** |
| `bird-0701` | codebase_community | challenging | `gold_timeout` | **genuinely slow** — still times out at **60 s** |

So the corpus defect rate is **2 / 1534 = 0.13%** (the two that do not terminate), and the
rejection rate at this instrument's default bounds is **4 / 1534 = 0.26%**.

**The two row-cap rejections are a bound choice, not a corpus fault, and the choice is the
owner's.** `max_rows = 100_000` excludes tasks whose correct answer is a quarter of a
million rows. The argument for excluding them is that such a task is not a sensible target
for a 0/1 execution-accuracy reward and that fetching the rows costs memory for no
information; the argument against is that the exclusion is this lane's judgement and not
BIRD's. Either way it must be **disclosed as a bound rather than reported as a defect**,
which is why the two categories are separated above.

### 4.2 What that means, plainly

- **For A6/N1's ≥ 25 pp effect, this instrument is adequate at any within-shape
  correlation.** 59 paired tasks at band centre against 87 challenging-tier shapes; the
  asymptote is not in play. This is the change from `ledger`, whose cheap tier died at
  `rho < 0.148` against a *smaller* required n.
- **For the pre-registration's +6.8 pp APEX target, it is still not adequate unless
  `rho < 0.164`**, and on the challenging tier not unless `rho < 0.101`. BIRD raises the
  shape count roughly 31-fold over `ledger`'s 9 and **still does not reach the project's
  own headline target.** Stated here rather than discovered later.
- **At coarse granularity the +6.8 pp target is unreachable at any plausible rho**: 25
  coarse shapes against 859 required. The true ceiling lies between the granularities, so
  the honest reading of the +6.8 pp row is "probably out of reach", not "reachable if rho
  is small".

---

## 5. Divergences and decisions that need the owner

Each of these changes a number or a claim, so none is chosen silently.

1. **Multiset vs set comparison — affects comparability with published BIRD numbers.**
   BIRD's published `evaluation.py` compares with `set(predicted) == set(ground_truth)`,
   which collapses duplicate rows: a de-duplicated answer scores correct. This module
   defaults to `compare="multiset"` — the stricter comparison, and the one this lane was
   specified to build. **The lane brief described multiset as "BIRD's convention"; it is
   not — official BIRD is set-based.** Both are implemented and a test pins the
   divergence. **An EX number from this module is not comparable to a BIRD leaderboard
   number unless produced with `compare="set"`.** Which default to measure on is the
   owner's call.

2. **Execution accuracy is not semantic equivalence.** EX is BIRD's published convention
   and that is the reason to use it, but a semantically correct query that returns the
   right rows with an extra column, or the columns in another order, scores wrong. This is
   a property of the published metric, inherited deliberately, and it bounds what a score
   on this instrument means.

3. **Spider was not downloaded.** `load_spider()` is written against Spider's *documented*
   layout (`dev.json` + `database/<db_id>/<db_id>.sqlite`, gold SQL under `query`) and is
   exercised by `fixture.materialize_spider()`, which proves the loader matches the
   documentation — **not** that the real archive matches it. BIRD was downloaded, extracted
   and loaded in full; Spider was not. Any Spider number requires that download first.

4. **Spider tiers are derived, not annotated.** Spider ships no difficulty field, so
   `_derive_tier()` assigns one from the clause skeleton. `report()` refuses to pool
   `annotated` with `derived` tiers and prints one block per source, because a row covering
   both would report a quantity nobody defined. Whether Spider is admitted at all is the
   owner's call.

5. **Shape granularity is a judgement call and the ceiling depends on it** (277 fine vs 25
   coarse). Both are reported; neither is declared the truth.

---

## 6. What this instrument still does not fix

### 6.1 The tier split loses a tier — a required `ptc/paired.py` change, not made

`ptc/paired.py:split_tiers` buckets `min_calls == max` as `full-scan` and **everything
else** as `cheap`. That is a two-bucket split. BIRD has **three** tiers, so with
`min_calls = tier_index` the instrument collapses to `challenging` against
`simple + moderate`, and the interaction A6 defines becomes
`challenging − (simple ∪ moderate)` rather than a three-tier trend.

**The required change, written here rather than made** (this lane must not modify `ptc/`):
`split_tiers()` would need to return one bucket per distinct `min_calls` value instead of
two, and `main()`'s `for tier in ("cheap", "full-scan")` loop and its single
`bootstrap_interaction(diffs_low=..., diffs_high=...)` call would need to iterate the
buckets it actually found. `bootstrap_interaction` itself needs no change — it takes two
tiers' diffs and is correct for any chosen pair — but *which* pair constitutes "the
interaction" becomes a pre-registration question rather than a code question, and so
belongs in the amendment rather than in a patch.

Until that change exists, the two-bucket collapse is the honest description of what a run
measures, and the amendment draft states it that way.

### 6.2 The tiers are not shape-disjoint

Per-tier shape counts sum to 382 against 277 globally distinct: **105 shape-tier
duplications.** 192 shapes appear in one tier, **65 in two, and 20 in all three** — for
example `t2 join:INNER pred:2` and `t1 pred:1 ord lim`.

Two consequences:

- **BIRD's difficulty label is not a structural property.** The same clause skeleton
  appears at all three difficulty levels, so the annotation is tracking something else —
  schema size, question ambiguity, how much the evidence hint is needed. A tier split is
  therefore *not* the "cheap vs full-scan" structural contrast `ledger` was built around,
  and the mechanism A6 asks about does not transfer to it unexamined.
- **The interaction's components are correlated through shared shapes.** `paired.py`
  resamples the two tiers independently, which is correct for *tasks* (every task sits in
  exactly one tier) but within-shape correlation crosses the tier boundary. The
  interaction's effective n is therefore lower than either tier's own ceiling implies, by
  an amount this lane has not quantified.

### 6.3 Contamination — a handicap `ledger` did not have

`ledger` was self-authored, which was a construct-validity handicap and is recorded as one.
It had one compensating virtue: **it could not have been in any model's pretraining data.**
BIRD dev has been public since 2023. A 0.6B model's pretraining corpus may contain the
questions, the gold SQL, or both, and this lane has run no contamination check. Trading a
self-authored construct for a public benchmark trades one validity threat for another; it
does not eliminate the category. The 25% frontier-band estimate is itself drawn from a
*trained* published number and inherits the same exposure.

**CORRECTED 2026-10-19.** The sentence above ("this lane has run no contamination check")
is no longer true. One has been run, on 2026-10-18, and its verdict is **INCONCLUSIVE**:
the question channel is clean (AUC 0.455 / 0.508 against positive controls the instrument
can see at 0.764 / 0.825), and the gold-SQL channel cannot be read because the fresh
control was not length-matched to BIRD's golds and length alone reproduced the whole
signal. The primary FAIL was withdrawn as a length artifact. Full record, including the
control defect: `docs/contamination.md`. The handicap stated above still stands as a
category; what changed is that one instance of it is now measured rather than assumed.

### 6.4 Unchanged from before

One model behind one unaudited relay, no run repeats, and a 0/1 reward. None of that is
touched by changing the taskset. A confirmed result on this instrument is a reason to build
a better instrument, not a result to publish.

### 6.5 `bench` is not in the default test path

`pytest.ini` sets `testpaths = tests ptc ledger train`. `bench` is **not** among them, so a
bare `pytest` collects **zero** of this instrument's 50 tests and reports success without
having run any of them. That is the exact fault `pytest.ini`'s own comment records being
fixed on 2026-10-10 for `ptc` and `ledger`, reintroduced for the new package. (Verified by
collection count, not by a total: another lane added `train` to `testpaths` at 15:20 on
2026-10-11, so the repo's overall test total is moving and is not a stable thing to assert
against. `bench`'s contribution to a bare `pytest` run is 0.)

**CORRECTED 2026-10-19. `bench` is in `testpaths` now, and the suite is no longer 50.** The
gap above was closed on 2026-10-12 by the commit that landed this package, `9d2bb06`
(`-testpaths = tests ptc ledger train` / `+testpaths = tests ptc ledger bench train`), so
the claim "collected zero" and the "required change, not made" paragraph that followed it
both stopped being true the same day. Measured 2026-10-19: `pytest bench -q` gives **126
passed, 1 skipped** (127 collected) in the repo venv, and the default suite collects 587
passed / 1 skipped. The count of 50 was already stale when written: §7 below records 67
passing in `bench` on 2026-10-13. Kept visible because a reader should see that the
"moving total" caveat in parentheses was right for a short time and then the totals were
pinned.

**The required change, not made** (this lane must not modify `pytest.ini`): add `bench` to
`testpaths`. Until then the suite must be run explicitly:

**Dated note, 2026-10-19:** this requirement was met on 2026-10-12 (`9d2bb06`); `bench` is
in `testpaths` and a bare `pytest` collects it. The explicit invocation below is still the
fast way to run just this package.

```
.venv-ptc/bin/python -m pytest bench -q
```

---

## 7. Mutation evidence — each test seen red before being trusted

A green test proves nothing until it has been seen red. **Five** mutations were applied,
each reverted, and every file verified byte-identical to its pre-mutation SHA-256 afterwards.
(This line said "Three … each" until 2026-10-19 while the table beneath it listed five; the
text and its own table had disagreed since `9d2bb06`, and rows 4 and 5 are the two that
cover the frontier manifest. Corrected as a description fault: the number of rows, not the
number of findings, changed.)

| # | mutation | result |
|---|---|---|
| 1 | corrupted one fixture gold query to reference a non-existent table | **RED** — `test_every_fixture_gold_executes` failed with `gold error: OperationalError: no such table: nonexistent_table`; restored → green |
| 2 | weakened the `multiset` branch of the EX comparison to `set` | **RED** — `test_multiset_and_set_comparison_differ_on_duplicates` failed `assert 1.0 == 0.0`; restored → green |
| 3 | made `inventory()` undercount shapes by one per tier | **RED** — `test_inventory_shape_counts_are_the_real_distinct_counts` failed `assert 1 == 2`; restored → green |
| 4 | disabled the frontier probe's empty-frontier guard so a manifest could be emitted with no trainable task | **RED** — `test_an_empty_frontier_refuses_to_emit_a_manifest` and `test_write_manifest_refuses_an_empty_frontier` both failed `DID NOT RAISE ValueError`; restored → green |
| 5 | made a void task (unrunnable gold) score a solve rate of 0 instead of being excluded | **RED** — `test_a_void_task_is_not_a_solve_rate_of_zero` failed; restored → green |

**Mutation 3 found two real defects in the tests themselves**, which is the reason the
exercise is not ceremonial:

- `test_report_prints_the_derived_ceiling_not_a_stored_one` **passed under the mutation**,
  because it recomputed its expected ceiling from `inventory()` — the function being
  mutated. A test whose expected value comes from the code under test cannot fail for the
  reason it exists. It now derives shape counts straight from the tasks.
- The same test matched numbers with `str in text`, and `"10"` is a substring of `"100"`.
  With the shape count mutated down by one, the expected `10` still matched a `100`
  elsewhere in the table. It now **parses** the ceiling table and compares row by row.

After both fixes, mutation 3 turns all three report tests red. Final state: **67 passed**
in `bench`, and the repo's own suite unaffected (276 passed when measured at 15:05; other
lanes have since added tests, so that total is theirs to report, not this lane's).

**Dated note, 2026-10-19.** `pytest bench -q` now gives **126 passed, 1 skipped** (127
collected) and the default suite **587 passed, 1 skipped**. The 67/276 figures are the
state at the mutation session and are kept as the record of that session, not as a current
count.

---

## 9. The frontier manifest (TRAIN lane's §344 gate)

The TRAIN lane's gate `train/guards.py:frontier_taskset_status` reads
`bench/frontier/manifest.json` and refuses to let the GRPO pipeline run until it conforms.
Path and key names are that lane's declared contract; **this lane accepts them unchanged.**

**The manifest is deliberately absent, and the gate is correctly shut.** Two of its five
fields — `solve_rate_min` and `solve_rate_max` — are measurements on the policy being
trained. This lane is barred from taking them (no GPU, no relay runs, no paid API calls, no
measurement whose result would need the unsigned amendment). Hand-writing a plausible band
would fabricate the exact measurement the gate exists to verify, and would open the gate so
the pipeline could spend money on numbers nobody took. `bench/frontier/probe.py` is the one
authorized command that changes that state, and a test
(`test_the_committed_manifest_is_absent`) asserts the file's absence so it cannot appear
without a measurement behind it.

### 9.1 A marginal accuracy cannot substitute for the band

The gate reads a **per-task** solve rate `p_i = successes_i / G`. §2's ~25% figure is a
**marginal** accuracy over a corpus. They come apart completely — same marginal, G=4:

| composition at marginal EX 0.25 | mean dead-group fraction | tasks clearing the 0.60 ceiling |
|---|---|---|
| every task `p = 0.25` | 0.320 | 200 / 200 |
| `p ∈ {0.10, 0.25, 0.40}` | 0.378 | 133 / 200 |
| 25% of tasks `p = 1.0`, 75% `p = 0.0` | **1.000** | **0 / 200** |

All three are indistinguishable as a marginal; only the first is trainable. **So the
published-number arithmetic in §2 cannot be written into the manifest in place of a probe**,
and a test pins this.

### 9.2 What the band fields have to mean

The raw min and max of per-task rates over any real suite are **0.0 and 1.0** — some task
is never solved, some always is — which the gate's strict `(0, 1)` bounds refuse outright.
So the manifest describes the **retained frontier subset**: tasks whose measured rate clears
the dead-group ceiling, with `n_tasks` as the count that survived.

**That makes the band conformant by construction, which is worth saying plainly: once
out-of-band tasks are discarded, `solve_rate_min`/`max` can no longer fail.** The numbers
that carry information are the retention figures, which `probe()` returns and
`write_manifest()` records under a `measurement` key the gate ignores: `n_candidates`
(pre-filter), `retention`, `mean_dead_fraction`, `n_void_tasks`, `g`, `dead_ceiling` and the
derived `trainable_band`.

**Suggested addition to the TRAIN lane's contract, their call:** a floor on retention — or a
required `n_candidates` — would give the gate real teeth. As specified, `n_tasks > 0` passes
on a suite where 197 of 198 drawn tasks were discarded as untrainable, which is a finding
that should stop a run rather than start one.

**CORRECTED 2026-10-19.** The floor exists. `train/guards.py` gained
`retention_floor(band)` (line 555) on 2026-10-12 in `d5f00bb`, and `_check_measurement`
(line 645) applies it by default — the width of the trainable band, 0.760 at G=4 — so a
suite that retains less than a difficulty-blind draw is refused. The "their call" framing
above is stale; the suggestion was taken. `n_candidates` is still reported rather than
gated, as that docstring states, because gating on both would double-count one constraint.

### 9.3 Derived, not restated

`trainable_band(ceiling, g)` bisects `p**G + (1-p)**G <= ceiling` rather than storing a
pair. At the defaults (G=4, ceiling 0.60) it returns **(0.119964, 0.880036)**, which
matches the TRAIN lane's stated `0.120 < min <= max < 0.880`; verified independently, and
`p = 0.05` reads 0.8145 and is refused. The band moves with G — a test asserts it widens at
G=8 — so a changed `num_generations` cannot leave a stale band behind.

### 9.4 The amendment id is A8, not A7

`pre_registration_amendment` must name a heading containing the word `signed` in
`docs/pre-registration.md`. **The TRAIN lane is right about the collision:** this
instrument's draft was written as A7 while that file ended at A6, and A7 was appended at
14:43 on 2026-10-11 for the cost-claim restatement. The draft is renumbered
`docs/amendment-A8-bird-sql-draft.md`.

**The gate will still refuse A8, and should.** That draft is unsigned, is not in
`docs/pre-registration.md`, and its heading deliberately does not contain the word
`signed`. Only the owner can change that, and neither lane should work around it.

**CORRECTED 2026-10-19.** The owner changed it. `docs/pre-registration.md:376` now carries
`### A8 — 2026-10-12, BEFORE any run on it: the instrument is replaced … — signed`, and
`train/guards.py:_amendment_is_signed("A8")` returns True (run 2026-10-19, not inferred
from the heading). The gate is still shut, but for a different reason: it also requires a
per-task solve-rate band, and `bench/frontier/manifest.json` is absent because the probe
that would measure it has not produced a rate (`docs/probe-v9.md`). The sentence above
conflated the two requirements and the second is the one still binding.


---

## 8. Reproducing

```bash
# the offline suite — no download, no network
.venv-ptc/bin/python -m pytest bench -q

# the power report on the committed fixture
.venv-ptc/bin/python -m bench

# the power report on the real corpus
.venv-ptc/bin/python -m bench /path/to/extracted/bird-dev
```

The corpus lives outside the repo, by instruction, at
`~/scratch/bird-sql/bird-dev-extracted/dev_20240627/`. The download is
`https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip` (346 MB), and the databases
arrive as a **nested** `dev_databases.zip` that must be extracted separately — the loader's
error message says so, because that is the state the archive leaves you in.

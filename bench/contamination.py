"""Contamination check: has `Qwen3-0.6B` seen BIRD dev?

**The question this module exists to answer, and the reason it is not optional.** `ledger`
could not have been in any pretraining corpus because it was self-authored. BIRD dev has
been public since 2023, and `docs/bench-taskset.md` §6.3 records that no check has been
run. A membership score with no non-member control is uninterpretable: *every* text gets
some log-likelihood, and a model that simply prefers BIRD's register would look exactly
like a model that memorised BIRD. So this module is built around three sets of texts and
one rule -- **no BIRD reading is reported until a method has separated a positive control
from fresh non-members**, in the run that produced the reading.

The three sets:

- **BIRD** -- a seeded, tier-stratified draw from the seven small BIRD dev databases.
- **Fresh non-members** -- question/gold-SQL pairs authored on 2026-10-18 over the SAME
  databases (`bench/contamination_fresh.json`), every gold executed so the pair is a real
  text-to-SQL task. These cannot be in any pretraining corpus, and they share BIRD's
  register, schema vocabulary and length band, which is what makes them a fair negative.
- **Positive control** -- texts so widely reproduced that a pretraining corpus almost
  certainly contains them. Needed because a *negative* separation on its own is also
  uninterpretable: a method that cannot detect known-public text cannot detect BIRD.

Two methods, because one is a claim and two agreeing methods are an argument:

**A. Min-K% / Min-K%++** (Shi et al. 2023; Zhang et al. 2024). Per-token NLL under the
model; score the tail -- the lowest-likelihood `k` fraction of tokens. Intuition: a
memorised passage is unlikely to contain tokens the model finds surprising. Min-K%++
z-scores each token's log-prob against the model's own distribution over the vocabulary at
that position, which removes most of the local-difficulty confound that plain Min-K%
inherits. Implemented here for question text and gold SQL *separately*, because the two
could be contaminated independently -- a question paraphrase is a plausible accident, an
exact gold query much less so.

**B. Gold-SQL continuation** (the "give a prefix, let the model write the rest" test used
against code benchmarks). Present the question plus the first `f` fraction of the gold
SQL's tokens, greedy-decode, and compare the completion to the held-out suffix. A model
that memorised the query reproduces it; a model that did not continues plausibly but
differently. This is sequence-level and so is not the same statistic as A.

**What this module deliberately does NOT do.** It does not smooth, tune or calibrate a
threshold after seeing BIRD. `decide_verdict` encodes the thresholds, and they are stated
in `docs/contamination.md` before the numbers. A method that fails its control is dropped
with disclosure rather than reported quietly.

**Import discipline.** Everything torch-dependent lives behind a function-local import,
so `import bench.contamination` never needs torch and the repo suite never needs torch.
The scoring and statistics half is pure Python and is tested by
`bench/test_contamination.py`; the model half is exercised only by `main()` in a venv that
has torch.
"""

from __future__ import annotations

import json
import math
import random
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRESH_PATH = REPO / "bench" / "contamination_fresh.json"

# The seven BIRD dev databases small enough to hold the fresh control over, and the
# seven the project's probe prompts already use (`bench/make_probe_prompts.py`).
SHIPPABLE_DB_IDS = frozenset({
    "superhero", "student_club", "toxicology", "thrombosis_prediction",
    "california_schools", "formula_1", "debit_card_specializing",
})

# Tail fraction for Min-K%. 20% is the paper's default and is not tuned here.
MIN_K_FRACTION = 0.20

# Thresholds, stated before any reading is taken. See docs/contamination.md.
#
# ACCEPT: the method works on this model at all -- the positive control separates from
# the fresh non-members. Below this, a BIRD reading from the method is not a reading.
CONTROL_AUC_FLOOR = 0.75
CONTROL_P_FLOOR = 0.01
# FAIL: BIRD looks more like a member than a non-member by an amount worth acting on.
CONTAMINATION_AUC_FLOOR = 0.65
# PASS: the 95% CI's upper end stays below this, i.e. a real contamination effect of the
# size we care about is excluded.
PASS_AUC_CEILING = 0.65

# The binary method's minimum rate gap, in proportion of items exactly reproduced.
BINARY_RATE_GAP = 0.10

N_PERMUTATIONS = 10_000
N_BOOTSTRAP = 10_000
SEED = 0


# ---------------------------------------------------------------------------
# Text sets
# ---------------------------------------------------------------------------

def load_fresh(path: str | Path = FRESH_PATH) -> list[dict]:
    """The fresh non-member pairs, validated to execute by `validate_fresh`."""
    data = json.loads(Path(path).expanduser().read_text())
    return list(data["pairs"])


def validate_fresh(pairs: list[dict], db_root: str | Path) -> list[tuple[str, str]]:
    """Execute every fresh gold. A pair that errors or returns nothing is a broken
    control, not a result: an unexecutable "gold" is not a text-to-SQL task, so its
    membership score would be measuring something else. Returns the failures."""
    root = Path(db_root).expanduser()
    bad: list[tuple[str, str]] = []
    for p in pairs:
        path = root / p["db_id"] / f"{p['db_id']}.sqlite"
        if not path.is_file():
            bad.append((p["name"], f"missing db {path}"))
            continue
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = con.execute(p["sql"]).fetchmany(1)
            if not rows:
                bad.append((p["name"], "gold returns zero rows"))
        except (sqlite3.Error, ValueError) as exc:
            bad.append((p["name"], f"{type(exc).__name__}: {exc}"))
        finally:
            con.close()
    return bad


def bird_sample(tasks: list, n: int = 300, *, seed: int = SEED,
                db_ids: frozenset[str] = SHIPPABLE_DB_IDS) -> list:
    """Seeded draw over the small databases, stratified by tier in BIRD's own proportions.

    Tier counts are proportional to the tier's share of the seven databases, because a
    sample that over-drew `challenging` would trade questions for length and the length
    covariate is exactly what the fresh set is matched on.
    """
    from bench.task import TIERS

    pool = [t for t in tasks if t.db_id in db_ids]
    by_tier: dict[str, list] = {tier: [] for tier in TIERS}
    for t in pool:
        by_tier[t.tier].append(t)
    total = sum(len(v) for v in by_tier.values())
    per_tier = {tier: round(n * len(v) / total) for tier, v in by_tier.items()}
    # Rounding drift: give the remainder to the largest tier.
    drift = n - sum(per_tier.values())
    per_tier[max(per_tier, key=per_tier.get)] += drift
    rng = random.Random(seed)
    drawn = []
    for tier in TIERS:
        bucket = sorted(by_tier[tier], key=lambda t: t.name)
        rng.shuffle(bucket)
        drawn.extend(bucket[:per_tier[tier]])
    return drawn


# Prose controls. Public-domain lines, famous enough that any web-crawl corpus contains
# them many times over. Truncated to roughly BIRD's question length (mean 84 chars) to
# keep the length covariate in band.
POSITIVE_PROSE = [
    "It is a truth universally acknowledged, that a single man in possession of a good "
    "fortune, must be in want of a wife.",
    "Call me Ishmael. Some years ago -- never mind how long precisely -- having little "
    "or no money in my purse, and nothing particular to interest me on shore.",
    "Four score and seven years ago our fathers brought forth on this continent, a new "
    "nation, conceived in Liberty, and dedicated to the proposition that all men are "
    "created equal.",
    "To be, or not to be, that is the question: Whether 'tis nobler in the mind to "
    "suffer the slings and arrows of outrageous fortune.",
    "It was the best of times, it was the worst of times, it was the age of wisdom, it "
    "was the age of foolishness.",
    "Alice was beginning to get very tired of sitting by her sister on the bank, and of "
    "having nothing to do.",
    "Once upon a midnight dreary, while I pondered, weak and weary, over many a quaint "
    "and curious volume of forgotten lore.",
    "We hold these truths to be self-evident, that all men are created equal, that they "
    "are endowed by their Creator with certain unalienable Rights.",
    "We the People of the United States, in Order to form a more perfect Union, "
    "establish Justice, insure domestic Tranquility.",
    "Two roads diverged in a yellow wood, and sorry I could not travel both and be one "
    "traveler, long I stood.",
    "All happy families are alike; each unhappy family is unhappy in its own way.",
    "In a hole in the ground there lived a hobbit. Not a nasty, dirty, wet hole, filled "
    "with the ends of worms.",
    "It was a bright cold day in April, and the clocks were striking thirteen.",
    "Many years later, as he faced the firing squad, Colonel Aureliano Buendia was to "
    "remember that distant afternoon.",
    "The sky above the port was the color of television, tuned to a dead channel.",
    "All children, except one, grow up. They soon know that they will grow up, and the "
    "way Wendy knew was this.",
    "In the beginning God created the heaven and the earth. And the earth was without "
    "form, and void; and darkness was upon the face of the deep.",
    "When in the Course of human events, it becomes necessary for one people to dissolve "
    "the political bands which have connected them with another.",
    "Shall I compare thee to a summer's day? Thou art more lovely and more temperate.",
    "So we beat on, boats against the current, borne back ceaselessly into the past.",
]

# Fresh prose, authored 2026-10-18 in the same register and length band. The auxiliary
# control: if these separate from the positive prose just as well as fresh SQL separates
# from BIRD SQL, the effect is domain/register, not membership, and that is visible.
FRESH_PROSE = [
    "A narrow lane behind the harbour still smells of tar and rope at low tide, and the "
    "gulls treat it as theirs.",
    "She carried the toolbox up three flights, set it down, and decided the hinge could "
    "wait until after lunch.",
    "The town's only bakery opens at five, which means the first bus of the day always "
    "smells faintly of rye.",
    "Every January the committee argues about the same budget line for forty minutes, "
    "then votes the way it did last year.",
    "He wrote the address on the back of a receipt, folded it twice, and put it in the "
    "pocket that zips.",
    "The river runs shallow here, so the old bridge stands on eleven stone piers and is "
    "closed whenever it floods.",
    "A grey cat sleeps on the warm hood of a parked tractor and ignores the swallows "
    "circling the silo.",
    "The recipe calls for cardamom, but the shop on the corner has been out of it since "
    "the shipment was delayed.",
    "Wind came through the valley overnight and stripped the pear tree before anyone "
    "thought to pick it.",
    "Their neighbour repairs clocks in a shed behind the house and never advertises, "
    "which is how he prefers it.",
    "The last train leaves at 23:40 and the station clock has been four minutes fast for "
    "as long as anyone recalls.",
    "In the archive's basement the shelves are labelled by decade, and the 1970s are "
    "still waiting for a proper inventory.",
]

# Public SQL, the shape a model meets in documentation and tutorials many times over:
# the W3Schools/Northwind-style canonical examples.
POSITIVE_SQL = [
    "SELECT * FROM Customers WHERE Country = 'Germany'",
    "SELECT COUNT(*) FROM Orders WHERE OrderDate > '1996-12-31'",
    "SELECT CustomerName, City FROM Customers ORDER BY City",
    "SELECT * FROM Products WHERE Price BETWEEN 10 AND 20",
    "SELECT SupplierName FROM Suppliers WHERE Country IN ('USA', 'UK')",
    "SELECT EmployeeID, LastName, FirstName FROM Employees WHERE City = 'London'",
    "SELECT Department, AVG(Salary) FROM Employees GROUP BY Department",
    "SELECT o.OrderID, c.CustomerName FROM Orders o JOIN Customers c ON o.CustomerID = c.CustomerID",
    "SELECT ProductName FROM Products WHERE UnitsInStock = 0",
    "SELECT DISTINCT Country FROM Customers",
    "SELECT COUNT(DISTINCT CustomerID) FROM Orders",
    "SELECT MAX(Price) FROM Products",
]


# ---------------------------------------------------------------------------
# Pure scoring logic (torch-free; tested offline)
# ---------------------------------------------------------------------------

def min_k_score(token_logprobs: list[float], frac: float = MIN_K_FRACTION) -> float:
    """Mean of the lowest `frac` fraction of per-token log-probabilities.

    Higher = more likely = more member-like. `ceil` on the count so a short text still
    contributes at least one token, and the caller's tokenisation boundary is not the
    statistic's business.
    """
    if not token_logprobs:
        raise ValueError("min_k_score needs at least one token")
    if not 0.0 < frac <= 1.0:
        raise ValueError(f"frac must be in (0, 1], got {frac}")
    k = max(1, math.ceil(frac * len(token_logprobs)))
    return sum(sorted(token_logprobs)[:k]) / k


def min_kpp_score(token_logprobs: list[float], vocab_means: list[float],
                  vocab_stds: list[float], frac: float = MIN_K_FRACTION) -> float:
    """Min-K%++: tail mean of per-token z-scores against the model's own distribution.

    `z_i = (log p(t_i) - mu_i) / sigma_i`, where `mu_i` and `sigma_i` are the mean and
    standard deviation of `log p(v)` over the vocabulary at position `i`. The point of
    the z-score is that a token the model finds locally unremarkable but globally
    unlikely -- common English after an unusual schema name, say -- stops reading as
    memorisation.
    """
    if not (len(token_logprobs) == len(vocab_means) == len(vocab_stds)):
        raise ValueError("one mean and one std required per token")
    zs = []
    for lp, mu, sd in zip(token_logprobs, vocab_means, vocab_stds):
        if sd <= 0 or not math.isfinite(sd):
            raise ValueError("degenerate vocab std")
        zs.append((lp - mu) / sd)
    return min_k_score(zs, frac)


def normalise_ws(text: str) -> str:
    """Whitespace-collapsed, trailing-semicolon-stripped comparison form for a
    continuation. Case is preserved: SQL keywords are commonly upper-case in BIRD golds
    and a case-insensitive match would credit a model that reproduced only the words."""
    return re.sub(r"\s+", " ", (text or "").strip().rstrip(";").strip()).strip()


def suffix_match(completion: str, suffix: str) -> bool:
    """Exact match after whitespace normalisation."""
    return normalise_ws(completion) == normalise_ws(suffix)


def auroc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney AUC with ties at 0.5. Probability a member scores above a non-member.

    1.0 = perfect separation; 0.5 = the score carries no information about the group.
    """
    if not pos or not neg:
        raise ValueError("auroc needs both groups non-empty")
    wins = 0.0
    for p in pos:
        for q in neg:
            if p > q:
                wins += 1.0
            elif p == q:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def cliffs_delta(pos: list[float], neg: list[float]) -> float:
    """`2 * AUC - 1`, the ordinal effect size on [-1, 1]. |d| < 0.147 is 'negligible'
    by Romano et al.'s convention; quoted so the report has a scale."""
    return 2.0 * auroc(pos, neg) - 1.0


def permutation_auc_p(pos: list[float], neg: list[float], *,
                      n_perm: int = N_PERMUTATIONS, seed: int = SEED) -> float:
    """One-sided permutation p for `AUC > 0.5`: the fraction of label shuffles that reach
    the observed AUC. `(1 + count) / (1 + n_perm)` so the p-value can never be 0."""
    observed = auroc(pos, neg)
    pooled = list(pos) + list(neg)
    n_pos = len(pos)
    rng = random.Random(seed)
    at_least = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        if auroc(pooled[:n_pos], pooled[n_pos:]) >= observed:
            at_least += 1
    return (1 + at_least) / (1 + n_perm)


def bootstrap_auc_ci(pos: list[float], neg: list[float], *,
                     n_boot: int = N_BOOTSTRAP, seed: int = SEED,
                     alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap over both groups, resampled independently."""
    if not pos or not neg:
        raise ValueError("bootstrap needs both groups non-empty")
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        ps = [pos[rng.randrange(len(pos))] for _ in range(len(pos))]
        ns = [neg[rng.randrange(len(neg))] for _ in range(len(neg))]
        stats.append(auroc(ps, ns))
    stats.sort()
    lo = stats[int(alpha / 2 * (len(stats) - 1))]
    hi = stats[int((1 - alpha / 2) * (len(stats) - 1))]
    return lo, hi


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Exact Fisher test on a 2x2 table, used where a method is binary (a continuation
    either reproduces the suffix or does not) rather than continuous."""
    n = a + b + c + d
    row1, col1 = a + b, a + c

    def hyp(x: int) -> float:
        return math.comb(row1, x) * math.comb(n - row1, col1 - x) / math.comb(n, col1)

    observed = hyp(a)
    return min(1.0, sum(hyp(x) for x in range(max(0, col1 - (n - row1)),
                                              min(row1, col1) + 1)
                        if hyp(x) <= observed + 1e-12))


@dataclass(frozen=True)
class Reading:
    """One (method, channel) result: the control check and the BIRD reading together.

    They travel together because a reading without its control is the thing this module
    exists to prevent. `verdict` is never inferred downstream -- it is stored.
    """

    method: str
    channel: str
    n_positive: int
    n_fresh: int
    n_bird: int
    control_auc: float
    control_p: float
    bird_auc: float
    bird_p: float
    bird_ci: tuple[float, float]
    verdict: str


def decide_verdict(*, control_auc: float, control_p: float,
                   bird_auc: float, bird_p: float,
                   bird_ci: tuple[float, float]) -> str:
    """PASS / FAIL / INCONCLUSIVE for one (method, channel), by the pre-stated rule.

    - The control gates everything. If the positive control did not separate from fresh
      non-members, the method cannot see membership on this model and no BIRD reading is
      interpretable: INCONCLUSIVE, whatever the BIRD number says. This is the branch that
      stops a weak instrument from reporting a clean bill of health.
    - PASS: the CI upper end excludes a real contamination effect. A PASS is evidence of
      absence at this power, not proof of it, and the docs say so.
    - FAIL: BIRD separable from fresh at the contamination floor, outside the CI's tie.
    - Otherwise INCONCLUSIVE.
    """
    if control_auc < CONTROL_AUC_FLOOR or control_p >= CONTROL_P_FLOOR:
        return "INCONCLUSIVE"
    if bird_ci[1] < PASS_AUC_CEILING:
        return "PASS"
    if bird_auc >= CONTAMINATION_AUC_FLOOR and bird_p < CONTROL_P_FLOOR \
            and bird_ci[0] > 0.5:
        return "FAIL"
    return "INCONCLUSIVE"


def decide_binary_verdict(*, control_rates: tuple[float, float], control_p: float,
                          bird_rates: tuple[float, float], bird_p: float) -> str:
    """PASS / FAIL / INCONCLUSIVE for the binary continuation method.

    The instrument works if the positive control reproduces its suffix more often than
    the fresh non-members by at least `BINARY_RATE_GAP` and the difference is significant.
    If BIRD does not clear the same bar against a *working* instrument, that is a PASS;
    if it does, FAIL. If the instrument cannot reach the bar, INCONCLUSIVE. A zero fresh
    rate is not a problem here -- reproductions are rare, which is the point -- but a
    zero positive rate is, and it lands in the same INCONCLUSIVE branch.
    """
    pos, fresh = control_rates[0], control_rates[1]
    bird, _ = bird_rates
    if pos - fresh < BINARY_RATE_GAP or control_p >= CONTROL_P_FLOOR:
        return "INCONCLUSIVE"
    if bird - fresh >= BINARY_RATE_GAP and bird_p < CONTROL_P_FLOOR:
        return "FAIL"
    return "PASS"


def summarise(method: str, channel: str, positive: list[float], fresh: list[float],
              bird: list[float], *, n_perm: int = N_PERMUTATIONS,
              n_boot: int = N_BOOTSTRAP, seed: int = SEED) -> Reading:
    """Compute one `Reading` from three score lists. Pure; the tests use it directly."""
    control_auc = auroc(positive, fresh)
    control_p = permutation_auc_p(positive, fresh, n_perm=n_perm, seed=seed)
    bird_auc = auroc(bird, fresh)
    bird_p = permutation_auc_p(bird, fresh, n_perm=n_perm, seed=seed)
    ci = bootstrap_auc_ci(bird, fresh, n_boot=n_boot, seed=seed)
    return Reading(
        method=method, channel=channel,
        n_positive=len(positive), n_fresh=len(fresh), n_bird=len(bird),
        control_auc=control_auc, control_p=control_p,
        bird_auc=bird_auc, bird_p=bird_p, bird_ci=ci,
        verdict=decide_verdict(control_auc=control_auc, control_p=control_p,
                               bird_auc=bird_auc, bird_p=bird_p, bird_ci=ci),
    )


def reading_to_dict(r: Reading) -> dict:
    """JSON form. Tuples become lists on the way through `json.dumps`."""
    d = asdict(r)
    d["bird_ci"] = list(d["bird_ci"])
    return d


class Cache:
    """Append-only JSONL of per-item results, so a run longer than a shell's patience
    resumes instead of restarting.

    Why this exists is an instrument fact rather than an optimisation: the first full run
    was killed by a 10-minute background wall clock after finishing method A (916 forward
    passes, ~4 min) and starting method B (370 greedy generations, ~45-60 min). A run that
    must complete in one uninterrupted process is a run whose result depends on the
    operator's patience. Keyed by (method, group, sha1 of the conditioned text), so a
    changed text, a changed prefix fraction or a changed prompt is a cache miss rather
    than silently reusing a score from a different input.

    The cache is NOT an input to the verdict beyond `hit` lookups: `run()` recomputes
    every statistic from the assembled lists, and the JSONL is deleted and regenerated
    for a fresh measurement.
    """

    def __init__(self, path: str | None):
        self.path = Path(path).expanduser() if path else None
        self._rows: dict[tuple[str, str, str], list] = {}
        if self.path and self.path.is_file():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                self._rows[(r["method"], r["group"], r["key"])] = r["value"]
        self._fh = None

    @staticmethod
    def _key(text: str) -> str:
        import hashlib
        return hashlib.sha1(text.encode()).hexdigest()[:16]

    def get(self, method: str, group: str, text: str) -> list | None:
        return self._rows.get((method, group, self._key(text)))

    def put(self, method: str, group: str, text: str, value: list) -> None:
        key = self._key(text)
        self._rows[(method, group, key)] = value
        if self.path is None:
            return
        if self._fh is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a")
        self._fh.write(json.dumps({"method": method, "group": group,
                                   "key": key, "value": value}) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


# ---------------------------------------------------------------------------
# Model-dependent half. Torch imported inside functions so `import bench.contamination`
# works in the torch-free repo venv and the default test suite never touches it.
# ---------------------------------------------------------------------------

def load_model(model_id: str, cache_dir: str | None = None, device: str | None = None):
    """Load the policy in bfloat16 on MPS (or CPU when MPS is unavailable).

    **Precision is a measured choice, not a default.** Float32 was tried first, on the
    argument that Min-K% compares per-token probabilities and bf16's coarser mantissa
    might blur them. Measured on this machine (Apple M-series, 16 GB), the argument lost
    to the clock: fp32 on MPS took 135 s to load and 15.8 s for a cold forward pass, bf16
    took 4.4 s and 2.7 s, and a 20-token greedy generation took 33 s against 7 s. The
    log-probabilities the statistic consumes are computed from float32 logits upcast from
    bf16 activations, so the comparison precision is float32 even when the forward pass is
    not. The precision is recorded in the results JSON, so a re-run on a different device
    can be checked against it.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if device is None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "mps" else torch.float32
    tok = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, cache_dir=cache_dir, dtype=dtype)
    model.to(device).eval()
    return model, tok, device


def token_logprobs(model, tok, text: str, device: str,
                   chunk: int = 64) -> tuple[list[float], list[float], list[float]]:
    """Per-token log-probabilities of `text` under the model, plus the mean and std of
    `log p(v)` over the vocabulary at each position (the Min-K%++ inputs).

    **The first token has no conditioning context and is dropped** from all three lists:
    its log-probability is the unigram prior and carries no information about this text.
    A text that tokenises to fewer than two tokens cannot be scored and raises.

    **The vocabulary moment is accumulated in position chunks.** A 300-token text against
    a 151 936-entry vocabulary is a 46 M-element float32 tensor if the log-softmax is
    materialised whole -- 180 MB per item, and the run scores hundreds of items. The
    statistics are identical either way because softmax is per-row, and the chunking is
    stated here because an unexplained loop over positions looks like an optimisation
    nobody measured.
    """
    import torch

    ids = tok(text, return_tensors="pt", add_special_tokens=False).input_ids.to(device)
    if ids.shape[1] < 2:
        raise ValueError(f"text tokenises to {ids.shape[1]} token(s): {text[:40]!r}")
    tok_lp: list[float] = []
    mu: list[float] = []
    sd: list[float] = []
    with torch.no_grad():
        logits = model(ids).logits[0].float()          # [seq, vocab], float32
        tgt = ids[0, 1:]
        # Exactly `seq - 1` positions: position i predicts token i+1. The chunk bound is
        # `min(seq - 1)` rather than `chunk`, which is the off-by-one this first shipped
        # with -- the final chunk ran one position past the targets, `gather` silently
        # returned a shorter tensor and the moment lists came back one longer than the
        # log-prob list. Silent because `gather` truncates instead of raising.
        n_pos = logits.shape[0] - 1
        for start in range(0, n_pos, chunk):
            stop = min(start + chunk, n_pos)
            block = logits[start:stop]
            logp = torch.log_softmax(block, dim=-1)
            picked = logp.gather(1, tgt[start:stop].unsqueeze(1))
            tok_lp.extend(picked.squeeze(1).cpu().tolist())
            m = logp.mean(dim=-1)
            mu.extend(m.cpu().tolist())
            v = (logp - m.unsqueeze(1)).pow(2).mean(dim=-1).clamp_min(0)
            sd.extend(v.sqrt().cpu().tolist())
    assert len(tok_lp) == len(mu) == len(sd) == n_pos, (
        len(tok_lp), len(mu), len(sd), n_pos)
    return tok_lp, mu, sd


def greedy_continuation(model, tok, prefix: str, max_new_tokens: int, device: str) -> str:
    """Greedy completion of `prefix`. Deterministic, so the run is reproducible."""
    import torch

    ids = tok(prefix, return_tensors="pt", add_special_tokens=False).input_ids.to(device)
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=max_new_tokens, do_sample=False,
                             num_beams=1, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)


def _pair_texts(tasks: list, fresh: list[dict]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Question and SQL text for each group, in group order."""
    bq = [t.question for t in tasks]
    bs = [t.gold_sql for t in tasks]
    fq = [p["question"] for p in fresh]
    fs = [p["sql"] for p in fresh]
    return bq, bs, fq, fs


def run(model_id: str, *, bird_root: str, cache_dir: str | None = None,
        n_bird: int = 300, seed: int = SEED, out: str | None = None,
        max_new_tokens: int = 48, prefix_frac: float = 0.5,
        cache_path: str | None = None) -> dict:
    """The whole check, end to end. Writes the results JSON and returns it.

    Order matters: the fresh control is validated before any model call (a broken gold
    would otherwise score as a non-member with whatever text it has), and the control
    separation is computed before the BIRD reading is reported.
    """
    from bench.loader import load_bird

    tasks = load_bird(bird_root)
    bird = bird_sample(tasks, n_bird, seed=seed)
    fresh = load_fresh()
    bad = validate_fresh(fresh, Path(bird_root).expanduser() / "dev_databases")
    if bad:
        raise SystemExit(f"fresh control has unexecutable golds: {bad}")

    model, tok, device = load_model(model_id, cache_dir)

    cache = Cache(cache_path)

    def scores(group: str, texts: list[str]) -> tuple[list[float], list[float]]:
        mk, mkpp = [], []
        for i, text in enumerate(texts):
            hit = cache.get("min-k", group, text)
            if hit is not None:
                mk.append(hit[0])
                mkpp.append(hit[1])
                continue
            lps, mus, sds = token_logprobs(model, tok, text, device)
            a, b = min_k_score(lps), min_kpp_score(lps, mus, sds)
            cache.put("min-k", group, text, [a, b])
            mk.append(a)
            mkpp.append(b)
            if (i + 1) % 25 == 0:
                print(f"  scored {i + 1}/{len(texts)}", flush=True)
        return mk, mkpp

    bq, bs, fq, fs = _pair_texts(bird, fresh)
    print(f"method A: {len(bq)} BIRD questions, {len(fq)} fresh questions", flush=True)
    bird_q_mk, bird_q_mkpp = scores("bird-question", bq)
    fresh_q_mk, fresh_q_mkpp = scores("fresh-question", fq)
    print(f"method A: {len(bs)} BIRD golds, {len(fs)} fresh golds", flush=True)
    bird_s_mk, bird_s_mkpp = scores("bird-sql", bs)
    fresh_s_mk, fresh_s_mkpp = scores("fresh-sql", fs)

    pos_mk, pos_mkpp = scores("positive-prose", POSITIVE_PROSE)
    frp_mk, frp_mkpp = scores("fresh-prose", FRESH_PROSE)
    possql_mk, possql_mkpp = scores("positive-sql", POSITIVE_SQL)

    readings = [
        summarise("min-k", "question", pos_mk, fresh_q_mk, bird_q_mk),
        summarise("min-k", "sql", possql_mk, fresh_s_mk, bird_s_mk),
        summarise("min-kpp", "question", pos_mkpp, fresh_q_mkpp, bird_q_mkpp),
        summarise("min-kpp", "sql", possql_mkpp, fresh_s_mkpp, bird_s_mkpp),
    ]

    # Auxiliary: prose-vs-prose, the in-register control. Establishes whether separation
    # tracks membership or register; reported, never used to adjudicate BIRD.
    aux = summarise("min-k", "prose-control", pos_mk, frp_mk, bird_q_mk)
    aux_kpp = summarise("min-kpp", "prose-control", pos_mkpp, frp_mkpp, bird_q_mkpp)

    # Method B: continuation. Questions are excluded -- a question is a paraphrase, a
    # continuation requires an exact suffix and so answers "was this query reproduced".
    print("method B: continuations", flush=True)
    matches = {"bird": 0, "fresh": 0, "positive": 0}
    for group, pairs in (("bird", [(t.question, t.gold_sql) for t in bird]),
                         ("fresh", [(p["question"], p["sql"]) for p in fresh])):
        for idx, (q, sql) in enumerate(pairs):
            ids = tok(sql, add_special_tokens=False).input_ids
            cut = max(1, int(len(ids) * prefix_frac))
            prefix_text = tok.decode(ids[:cut], skip_special_tokens=True)
            suffix_text = tok.decode(ids[cut:], skip_special_tokens=True)
            key = f"{group}:{idx}"
            hit = cache.get("continuation", key, prefix_text)
            if hit is None:
                completion = greedy_continuation(
                    model, tok, f"{q}\n{prefix_text}", len(ids) - cut, device)
                hit = [suffix_match(completion, suffix_text)]
                cache.put("continuation", key, prefix_text, hit)
            matches[group] += int(hit[0])
            if (idx + 1) % 25 == 0:
                print(f"  continued {idx + 1}/{len(pairs)} ({group})", flush=True)
    for idx, sql in enumerate(POSITIVE_SQL):
        ids = tok(sql, add_special_tokens=False).input_ids
        cut = max(1, int(len(ids) * prefix_frac))
        prefix_text = tok.decode(ids[:cut], skip_special_tokens=True)
        suffix_text = tok.decode(ids[cut:], skip_special_tokens=True)
        hit = cache.get("continuation", f"positive:{idx}", prefix_text)
        if hit is None:
            completion = greedy_continuation(model, tok, prefix_text, len(ids) - cut, device)
            hit = [suffix_match(completion, suffix_text)]
            cache.put("continuation", f"positive:{idx}", prefix_text, hit)
        matches["positive"] += int(hit[0])

    cont_p = fisher_two_sided(matches["bird"], len(bird) - matches["bird"],
                              matches["fresh"], len(fresh) - matches["fresh"])
    cont_control_p = fisher_two_sided(matches["positive"], len(POSITIVE_SQL) - matches["positive"],
                                      matches["fresh"], len(fresh) - matches["fresh"])
    # Binary contrast: the score is exact reproduction, so two independent groups can
    # only differ by 1.0 (rate order agrees with the member/non-member order), 0.5 (a
    # tie) or 0.0 (reversed). A CI is meaningless on three support points, so this row
    # reports the rates and the Fisher p instead, and `decide_binary_verdict` encodes
    # its own thresholds. Reusing the continuous rule here would have written the
    # CONTROL's AUC into the BIRD column, which is the exact conflation this module
    # exists to prevent.
    cont_control_auc = (1.0 if matches["positive"] > matches["fresh"]
                        else 0.5 if matches["positive"] == matches["fresh"] else 0.0)
    cont_bird_auc = (1.0 if matches["bird"] > matches["fresh"]
                     else 0.5 if matches["bird"] == matches["fresh"] else 0.0)
    cont_rates = {g: matches[g] / n for g, n in (
        ("positive", len(POSITIVE_SQL)), ("fresh", len(fresh)), ("bird", len(bird)))}
    continuation_verdict = decide_binary_verdict(
        control_rates=(cont_rates["positive"], cont_rates["fresh"]),
        control_p=cont_control_p,
        bird_rates=(cont_rates["bird"], cont_rates["fresh"]),
        bird_p=cont_p,
    )
    readings.append(Reading(
        method="continuation", channel="sql",
        n_positive=len(POSITIVE_SQL), n_fresh=len(fresh), n_bird=len(bird),
        control_auc=cont_control_auc, control_p=cont_control_p,
        bird_auc=cont_bird_auc, bird_p=cont_p,
        bird_ci=(cont_bird_auc, cont_bird_auc),
        verdict=continuation_verdict))

    verdicts = sorted({r.verdict for r in readings})
    payload = {
        "model_id": model_id,
        "device": device,
        "dtype": "bfloat16" if device == "mps" else "float32",
        "prefix_frac": prefix_frac,
        "seed": seed,
        "n_bird": len(bird),
        "n_fresh": len(fresh),
        "n_positive_prose": len(POSITIVE_PROSE),
        "n_positive_sql": len(POSITIVE_SQL),
        "n_fresh_prose": len(FRESH_PROSE),
        "bird": [{"name": t.name, "db_id": t.db_id, "tier": t.tier,
                  "question": t.question, "gold_sql": t.gold_sql} for t in bird],
        "readings": [reading_to_dict(r) for r in readings],
        "auxiliary_prose_control": [reading_to_dict(aux), reading_to_dict(aux_kpp)],
        "continuation_matches": matches,
        "continuation_counts": {"bird": len(bird), "fresh": len(fresh),
                                "positive": len(POSITIVE_SQL)},
        "raw_scores": {
            "bird_question_min_k": bird_q_mk, "fresh_question_min_k": fresh_q_mk,
            "bird_sql_min_k": bird_s_mk, "fresh_sql_min_k": fresh_s_mk,
            "positive_prose_min_k": pos_mk, "fresh_prose_min_k": frp_mk,
            "positive_sql_min_k": possql_mk,
            "bird_question_min_kpp": bird_q_mkpp, "fresh_question_min_kpp": fresh_q_mkpp,
            "bird_sql_min_kpp": bird_s_mkpp, "fresh_sql_min_kpp": fresh_s_mkpp,
            "positive_prose_min_kpp": pos_mkpp, "fresh_prose_min_kpp": frp_mkpp,
            "positive_sql_min_kpp": possql_mkpp,
        },
        "verdict": "FAIL" if "FAIL" in verdicts else (
            "PASS" if "PASS" in verdicts and "INCONCLUSIVE" not in verdicts
            else "INCONCLUSIVE"),
        "thresholds": {
            "control_auc_floor": CONTROL_AUC_FLOOR,
            "control_p_floor": CONTROL_P_FLOOR,
            "contamination_auc_floor": CONTAMINATION_AUC_FLOOR,
            "pass_auc_ceiling": PASS_AUC_CEILING,
            "min_k_fraction": MIN_K_FRACTION,
            "n_permutations": N_PERMUTATIONS,
            "n_bootstrap": N_BOOTSTRAP,
        },
    }
    if out:
        Path(out).expanduser().write_text(json.dumps(payload, indent=2))
    return payload


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Min-K%/Min-K%++ and continuation "
                                            "contamination check of Qwen3-0.6B on BIRD dev")
    p.add_argument("--model", default="unsloth/Qwen3-0.6B")
    p.add_argument("--bird", required=True, help="extracted BIRD dev root")
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--n-bird", type=int, default=300)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", default=str(REPO / "bench" / "contamination_results.json"))
    p.add_argument("--cache", default=None, help="JSONL of per-item results; enables "
                                                 "resume across interrupted runs")
    a = p.parse_args(argv)
    payload = run(a.model, bird_root=a.bird, cache_dir=a.cache_dir,
                  n_bird=a.n_bird, seed=a.seed, out=a.out, cache_path=a.cache)
    print(json.dumps([{k: r[k] for k in ("method", "channel", "control_auc",
                                        "control_p", "bird_auc", "bird_p",
                                        "bird_ci", "verdict")}
                      for r in payload["readings"]], indent=2))
    print("verdict:", payload["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

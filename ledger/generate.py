"""`ledger/generate.py` — a SHAPE GRAMMAR for `ledger` tasks. Prototype, not wired in.

Why this file exists rather than more hand-written tasks in `taskset.py`:

`docs/pre-registration.md` §8/A5 had to disclose that the 15 hard tasks were authored
after seeing which shape bash failed on. Hand-authoring more tasks repeats that fault
exactly. This module instead declares a GRAMMAR and a set of ADMISSION RULES, and
enumerates every task the grammar can produce. Nothing is chosen; the cross product is
taken and the rules filter it. That is the only form of taskset extension that can be
signed before the data exists, because the generator is the object being signed.

The second reason is statistical, and it is the one that decides whether generation is
worth anything at all. `taskset.py`'s 29 tasks are 19 distinct SHAPES: `total-invoice`,
`total-memo` and `total-receipt` are one shape instantiated three times, and bash failed
two of those three in run 2h while passing everything structurally unlike them.
Replicates of a shape are correlated, so 500 tasks over 19 shapes do not carry 500
paired tasks of information -- the effective n is bounded by the SHAPE count divided by
the within-shape correlation, no matter how large the corpus gets. Scaling the record
file raises replicates. Only a grammar raises shapes.

Every task therefore carries `shape`, so the analysis can cluster on it and report an
effective n rather than a nominal one.

## Admission rules, declared here and applied mechanically

R1. The answer is computed from `RECORDS`. Never typed, never a second implementation.
R2. Reject a task whose answer is not uniquely determined (a tie in an argmax, an empty
    filter). An ambiguous answer is a task that grades a correct agent wrong.
R3. Reject a task whose answer string appears in its own prompt.
R4. Reject a task whose answer is a corpus constant the prompt discloses (the record
    count, the kind count, the owner count) -- it is answerable with zero tool calls.
R5. Reject a task whose answer collides with an already-admitted task's answer. Two
    tasks with the same answer let an arm that guesses once be right twice, and they
    are maximally correlated by construction.
R6. `min_calls` is DERIVED from the shape's data dependency, never asserted: 1 for a
    single-record read, `len(chain)` for a walk, `len(RECORDS)` for any predicate over
    the whole corpus. `ptc/paired.py:split_tiers` keys the tier off it.
R7. Selection across shapes is stratified and seeded, WITHIN TIER then within shape:
    every shape contributes one task before any shape contributes a second, and the
    cheap and full-scan counts are declared separately. A draw that over-samples one
    shape lowers effective n while raising nominal n; a draw that returns only one
    tier leaves A6's interaction with nothing to compute.
R8. Reject a whole SHAPE whose answer is identical across every instance of it. Found
    by running the grammar: `distinct_owners` under an `owner=` filter is always 1, so
    after one exposure the shape is answerable with zero tool calls. That is a
    non-solver surface of exactly the kind Step 1's gate exists to catch.
R9. The analysis clusters on `shape`, never on the task. Every task carries its shape
    for this reason. 377 tasks over 113 shapes is 113 clusters of correlated outcomes,
    and the effective n is bounded by shapes/rho however large the corpus gets --
    `report()` prints that ceiling per tier rather than letting a nominal count stand
    in for it. This rule is on the reader of the data, not the producer of it, and it
    is the one that decides whether generation buys anything.

Run it: `python -m ledger.generate [n]`
"""

from __future__ import annotations

import random
import sys
from collections import defaultdict

from ledger.servers.store import RECORDS

Task = tuple[str, str, str, int, str]  # (name, prompt, answer, min_calls, shape)

ALL = len(RECORDS)
KINDS = sorted({r["kind"] for r in RECORDS.values()})
OWNERS = sorted({r["owner"] for r in RECORDS.values()})
LINKED_TO = {r["link"] for r in RECORDS.values() if r["link"]}

# --- the grammar's axes ------------------------------------------------------------
# Each axis entry is (label, prompt fragment, callable). The cross product of
# AGGREGATIONS x FILTERS is the full-scan half of the grammar; GROUPED and WALKS are
# the other two families. Adding an entry to any axis adds shapes, which is the only
# thing that raises effective n.

FILTERS: dict[str, tuple[str, object]] = {
    "all": ("every record in the ledger", lambda r: True),
    **{f"kind={k}": (f"every {k} record", (lambda k: (lambda r: r["kind"] == k))(k))
       for k in KINDS},
    **{f"owner={o}": (f"every record owned by {o}",
                      (lambda o: (lambda r: r["owner"] == o))(o))
       for o in OWNERS},
    "linked": ("every record that links to another record", lambda r: bool(r["link"])),
    "unlinked": ("every record that links to nothing", lambda r: not r["link"]),
    "targeted": ("every record that at least one other record links to",
                 lambda r: r["id"] in LINKED_TO),
    "isolated": ("every record that links to nothing and that nothing links to",
                 lambda r: not r["link"] and r["id"] not in LINKED_TO),
}

# Each entry's prompt fragment is a COMPLETE question, not a noun phrase. Composing
# noun phrases into "What is {fragment} those records?" produced "What is how many
# records have an amount strictly greater than the mean..." -- a malformed prompt is an
# instrument defect that costs one arm nothing and the other a parse.
AGGREGATIONS: dict[str, tuple[str, object]] = {
    "sum": ("What is the total amount across them?",
            lambda rs: sum(r["amount"] for r in rs)),
    "count": ("How many such records are there?", lambda rs: len(rs)),
    "max": ("What is the largest amount among them?",
            lambda rs: max(r["amount"] for r in rs)),
    "min": ("What is the smallest amount among them?",
            lambda rs: min(r["amount"] for r in rs)),
    "mean_floor": ("What is the mean amount across them, rounded DOWN to a whole "
                   "number?", lambda rs: sum(r["amount"] for r in rs) // len(rs)),
    "argmax_id": ("Which one has the largest amount? Reply with its id.",
                  lambda rs: _uniq_arg(rs, max)),
    "argmin_id": ("Which one has the smallest amount? Reply with its id.",
                  lambda rs: _uniq_arg(rs, min)),
    "k2": ("What is the second largest amount among them?", lambda rs: _kth(rs, 2)),
    "k3": ("What is the third largest amount among them?", lambda rs: _kth(rs, 3)),
    "distinct_owners": ("How many distinct owners do they have?",
                        lambda rs: len({r["owner"] for r in rs})),
    "above_mean": ("How many of them have an amount strictly greater than the mean "
                   "amount across them?", lambda rs: _above_mean(rs)),
    "span": ("What is the difference between the largest and the smallest amount "
             "among them?",
             lambda rs: max(r["amount"] for r in rs) - min(r["amount"] for r in rs)),
}

GROUPS: dict[str, tuple[str, object]] = {
    "kind": ("kind", lambda r: r["kind"]),
    "owner": ("owner", lambda r: r["owner"]),
}

GROUP_STATS: dict[str, tuple[str, object]] = {
    "sum": ("total amount", lambda rs: sum(r["amount"] for r in rs)),
    "count": ("number of records", lambda rs: len(rs)),
    "mean": ("mean amount", lambda rs: sum(r["amount"] for r in rs) / len(rs)),
    "max": ("largest single amount", lambda rs: max(r["amount"] for r in rs)),
}

WALK_STATS: dict[str, tuple[str, object]] = {
    "end": ("the id of the last record in that chain", lambda ch: ch[-1]),
    "len": ("how many records are in that chain, counting both ends",
            lambda ch: len(ch)),
    "sum": ("the total amount across every record in that chain",
            lambda ch: sum(RECORDS[i]["amount"] for i in ch)),
    "end_owner": ("the owner of the last record in that chain",
                  lambda ch: RECORDS[ch[-1]]["owner"]),
    "max": ("the largest amount on any record in that chain",
            lambda ch: max(RECORDS[i]["amount"] for i in ch)),
}


# --- helpers ----------------------------------------------------------------------

class Ambiguous(Exception):
    """R2: the shape has no unique answer on this corpus."""


def _uniq_arg(rs, pick):
    """argmax/argmin by amount, refusing a tie. R2: a tie means two correct ids and a
    grader that marks one of them wrong."""
    target = pick(r["amount"] for r in rs)
    hits = [r["id"] for r in rs if r["amount"] == target]
    if len(hits) != 1:
        raise Ambiguous(f"{len(hits)} records share the extreme amount")
    return hits[0]


def _kth(rs, k):
    amounts = sorted((r["amount"] for r in rs), reverse=True)
    if len(amounts) < k:
        raise Ambiguous(f"only {len(amounts)} records, no {k}th")
    if len(set(amounts)) < k or amounts[k - 1] == amounts[k - 2]:
        raise Ambiguous("tied amounts make the rank ambiguous")
    return amounts[k - 1]


def _above_mean(rs):
    m = sum(r["amount"] for r in rs) / len(rs)
    return sum(1 for r in rs if r["amount"] > m)


def _chain(start):
    seen, cur, out = set(), start, [start]
    while RECORDS[cur]["link"] and cur not in seen:
        seen.add(cur)
        cur = RECORDS[cur]["link"]
        out.append(cur)
    return out


def _rank_unique(stats: dict, rank: int):
    """The group holding the `rank`-th largest stat, refusing a tie at the boundary."""
    order = sorted(stats, key=lambda g: (-stats[g], g))
    if len(order) < rank:
        raise Ambiguous("too few groups")
    vals = [stats[g] for g in order]
    if rank > 1 and vals[rank - 1] == vals[rank - 2]:
        raise Ambiguous("tied group stats")
    if rank < len(vals) and vals[rank - 1] == vals[rank]:
        raise Ambiguous("tied group stats")
    return order[rank - 1]


TAIL = "Reply with the answer alone in <answer></answer> tags."
CONSTANTS = {str(ALL), str(len(KINDS)), str(len(OWNERS))}


# --- enumeration ------------------------------------------------------------------

def enumerate_shapes() -> list[Task]:
    """Every task the grammar admits. No selection, no hand-picking: the cross product
    filtered by R2-R6. R5 (answer collision) is applied later, after stratification,
    because which task survives a collision depends on draw order."""
    out: list[Task] = []

    # family A: aggregation x filter, over the whole corpus
    for fk, (fdesc, pred) in FILTERS.items():
        rs = [r for r in RECORDS.values() if pred(r)]
        if not rs:
            continue
        for ak, (adesc, agg) in AGGREGATIONS.items():
            try:
                answer = agg(rs)
            except (Ambiguous, ZeroDivisionError, ValueError):
                continue
            shape = f"agg:{ak}/{fk.split('=')[0]}"
            # R6: any predicate over the corpus needs one call per record, except a
            # single-record filter, which this grammar cannot produce.
            out.append((f"{ak}-{fk.replace('=', '-')}",
                        f"Consider {fdesc}. {adesc} {TAIL}",
                        str(answer), ALL, shape))

    # family B: group then rank -- a second-order read, the shape A5 added by hand
    for gk, (gdesc, key) in GROUPS.items():
        buckets: dict[str, list] = defaultdict(list)
        for r in RECORDS.values():
            buckets[key(r)].append(r)
        for sk, (sdesc, stat) in GROUP_STATS.items():
            stats = {g: stat(rs) for g, rs in buckets.items()}
            for rank in (1, 2, 3):
                try:
                    answer = _rank_unique(stats, rank)
                except Ambiguous:
                    continue
                ordinal = {1: "largest", 2: "second largest", 3: "third largest"}[rank]
                out.append((
                    f"rank{rank}-{gk}-{sk}",
                    f"Group the ledger's records by {gdesc}. Which {gdesc} has the "
                    f"{ordinal} {sdesc}? {TAIL}",
                    str(answer), ALL, f"grouprank:{sk}/{gk}/{rank}"))

    # family C: group-set membership, then aggregate over the surviving group
    for gk, (gdesc, key) in GROUPS.items():
        if gk != "owner":
            continue
        complete = sorted(o for o in OWNERS
                          if {r["kind"] for r in RECORDS.values() if r["owner"] == o}
                          == set(KINDS))
        if not complete:
            continue
        out.append(("owners-all-kinds-set",
                    f"Which owners own at least one record of every kind in the "
                    f"ledger? Reply with their names in alphabetical order, separated "
                    f"by single spaces, in <answer></answer> tags.",
                    " ".join(complete), ALL, "setmember:owners/allkinds"))
        for k in KINDS:
            out.append((f"complete-owners-{k}-total",
                        f"Consider only the owners who own at least one record of "
                        f"every kind. What is the total amount of their {k} records? "
                        f"{TAIL}",
                        str(sum(r["amount"] for r in RECORDS.values()
                                if r["kind"] == k and r["owner"] in complete)),
                        ALL, f"setmember:owners/allkinds+sum"))

    # family D: walks -- the only sub-corpus shapes, so the only cheap-tier producers
    for start in sorted(RECORDS):
        ch = _chain(start)
        if len(ch) < 2:
            continue
        for wk, (wdesc, stat) in WALK_STATS.items():
            out.append((f"walk{wk}-{start}",
                        f"Start at record {start} and follow its `link` field to the "
                        f"end of the chain. What is {wdesc}? {TAIL}",
                        str(stat(ch)), len(ch), f"walk:{wk}"))

    # family E: single-record reads -- the floor of the difficulty ladder
    for field in ("amount", "owner", "kind"):
        for rid in sorted(RECORDS):
            out.append((f"read-{field}-{rid}",
                        f"What is the {field} on record {rid}? {TAIL}",
                        str(RECORDS[rid][field]), 1, f"read:{field}"))

    # family F: the reverse-link read, the other 1-call shape
    for rid in sorted(RECORDS):
        back = sorted(r["id"] for r in RECORDS.values() if r["link"] == rid)
        if len(back) != 1:          # R2: zero or many is not one answer
            continue
        out.append((f"backlink-{rid}",
                    f"Which record links to {rid}? {TAIL}", back[0], 1, "backlink"))

    # R3 and R4, applied mechanically
    kept = []
    for name, prompt, answer, mc, shape in out:
        if answer.lower() in prompt.lower():
            continue                 # R3: the answer is in the question
        if answer in CONSTANTS:
            continue                 # R4: a disclosed corpus constant
        kept.append((name, prompt, answer, mc, shape))

    # R8: reject a whole shape whose answer is the same for every instance of it.
    # Found by running the grammar: `distinct_owners` under an `owner=` filter is
    # always 1, so after one exposure the shape is answerable with zero tool calls --
    # a non-solver shape, which project rule R24 / Step 1's gate exists to catch.
    by_shape: dict[str, set[str]] = defaultdict(set)
    seen_count: dict[str, int] = defaultdict(int)
    for _, _, answer, _, shape in kept:
        by_shape[shape].add(answer)
        seen_count[shape] += 1
    degenerate = {s for s in by_shape
                  if seen_count[s] > 1 and len(by_shape[s]) == 1}
    return [t for t in kept if t[4] not in degenerate]


def select(n_cheap: int, n_full: int, seed: int = 0) -> list[Task]:
    """R7 stratified draw + R5 answer-collision rejection.

    Stratified WITHIN TIER and then within shape. Both halves matter:

    - Within tier, because `ptc/paired.py` splits on `min_calls` and A6's interaction
      is the difference of the two tiers' paired deltas. A draw that returns only
      full-scan tasks has no interaction to compute. The first version of this function
      stratified over shapes in sorted order and did exactly that -- `select(30)`
      returned 30 full-scan tasks and zero cheap ones, because every `agg:` shape sorts
      before every `read:` and `walk:` shape.
    - Within shape, one task per shape before any shape gets a second, because
      replicates of a shape are correlated and raise nominal n without raising
      effective n.

    Seeded, so a suite is a pure function of (grammar, n_cheap, n_full, seed) and can
    therefore be signed before it is built -- which is the whole point of a generator
    over a hand-authored list.
    """
    pool: dict[tuple[bool, str], list[Task]] = defaultdict(list)
    for t in enumerate_shapes():
        pool[(t[3] == ALL, t[4])].append(t)
    rng = random.Random(seed)
    for key in pool:
        rng.shuffle(pool[key])

    chosen: list[Task] = []
    used_answers: set[str] = set()
    for is_full, want in ((False, n_cheap), (True, n_full)):
        shapes = sorted(s for (f, s) in pool if f == is_full)
        rng.shuffle(shapes)                 # seed decides order, not the alphabet
        got, depth = 0, 0
        while got < want:
            progressed = False
            for shape in shapes:
                if got >= want:
                    break
                bucket = pool[(is_full, shape)]
                while len(bucket) > depth:
                    cand = bucket.pop(depth)
                    if cand[2] in used_answers:
                        continue            # R5: answer collision
                    used_answers.add(cand[2])
                    chosen.append(cand)
                    got += 1
                    progressed = True
                    break
            if not progressed:
                depth += 1
                if depth > max((len(pool[(is_full, s)]) for s in shapes), default=0):
                    break
    return chosen


def report() -> None:
    allt = enumerate_shapes()
    shapes: dict[str, int] = defaultdict(int)
    tier_of: dict[str, str] = {}
    for t in allt:
        shapes[t[4]] += 1
        tier_of[t[4]] = "full-scan" if t[3] == ALL else "cheap"
    cheap_shapes = [s for s in shapes if tier_of[s] == "cheap"]
    full_shapes = [s for s in shapes if tier_of[s] == "full-scan"]
    cheap_tasks = sum(1 for t in allt if t[3] != ALL)
    print(f"grammar admits {len(allt)} tasks over {len(shapes)} distinct shapes "
          f"on a {ALL}-record corpus")
    print(f"  cheap tier     {cheap_tasks:>4} tasks over {len(cheap_shapes):>3} shapes")
    print(f"  full-scan tier {len(allt) - cheap_tasks:>4} tasks over "
          f"{len(full_shapes):>3} shapes")
    print(f"  taskset.py by comparison: 29 tasks over 19 shapes "
          f"(5 cheap + 14 full-scan)\n")
    print("effective-n ceiling per tier -- shapes / rho, the limit no corpus size")
    print("or task count can pass, because replicates of a shape are correlated:")
    print(f"  {'rho':>6}{'cheap':>10}{'full-scan':>12}")
    for rho in (0.2, 0.3, 0.5, 0.8):
        print(f"  {rho:>6.1f}{len(cheap_shapes) / rho:>10.0f}"
              f"{len(full_shapes) / rho:>12.0f}")
    print()
    print(f"{'shape':<34}{'tasks':>6}  {'tier':>10}")
    print("-" * 54)
    for s in sorted(shapes):
        print(f"{s:<34}{shapes[s]:>6}  {tier_of[s]:>10}")
    print("-" * 54)
    print(f"{'TOTAL':<34}{len(allt):>6}  cheap {cheap_tasks}, "
          f"full-scan {len(allt) - cheap_tasks}")


if __name__ == "__main__":
    report()
    n_cheap = int(sys.argv[1]) if len(sys.argv) > 1 else 11
    n_full = int(sys.argv[2]) if len(sys.argv) > 2 else 18
    print(f"\n--- stratified sample, select(n_cheap={n_cheap}, n_full={n_full}) ---")
    sel = select(n_cheap, n_full)
    print(f"{'name':<28}{'min_calls':>10}  {'shape':<30}answer")
    for name, _, answer, mc, shape in sel:
        print(f"{name:<28}{mc:>10}  {shape:<30}{answer}")
    cheap = sum(1 for t in sel if t[3] != ALL)
    print(f"\n{len(sel)} tasks ({cheap} cheap, {len(sel) - cheap} full-scan), "
          f"{len({t[4] for t in sel})} distinct shapes, "
          f"{len({t[2] for t in sel})} distinct answers")
    print("\n--- two full prompts, verbatim ---")
    print(" ", sel[0][1])
    print(" ", sel[-1][1])

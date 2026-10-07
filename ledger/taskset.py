"""`ledger` — a deterministic taskset built to discriminate between action channels.

Why this exists rather than a shipped environment: every `verifiers` environment that is
deterministic, offline and container-free is either single-call (`glossary`) or has no
tool channel at all, and the rest are disqualified by an LLM judge in the reward or by
needing the network (`docs/spike-verifiers.md`). A single-call environment cannot show a
gap of a few points because both arms saturate at 1.0 -- measured, not assumed:
`ptc/compare.py canned` scores bash 1.0 and PTC 1.0 on `glossary`.

**This is a self-authored construct, and that is a validity handicap.** It is the same
handicap `docs/pre-registration.md` §3 uses to argue for targeting the APEX end of the
published gap rather than the TAC end: an author-built catalog is not evidence about
catalogs in general. What it can do is hold the catalog IDENTICAL across arms while the
channel differs, which is the one claim this project makes.

Design constraints, each traceable:

- **Deterministic grader, no LLM judge anywhere** (project rule #5, pre-reg §2). Every
  answer is one exact token compared after normalisation.
- **Graded difficulty.** Tasks need 1, 2, or many tool calls. A suite where every task
  needs one call measures nothing; a suite where every task needs forty measures patience.
- **Aggregation tasks are where PTC should win if it ever wins.** Summing 40 records is
  one program with a loop, or 40 separate tool calls. If programmatic tool calling has an
  advantage at all, that is its shape -- so the suite contains that shape rather than
  avoiding it.
- **`answer` is computed from the data, never typed by hand.** A hand-written expected
  value is a second implementation that can disagree with the first.
"""

import verifiers.v1 as vf

# One dict, imported -- not a second `json.loads` of the same file. Loading it twice
# gave the grader and the tools independent copies: a mutation test that closed a cycle
# in one walked the other, and the unbounded-walk mutant survived because the cycle it
# planted was invisible to the code under test. Two copies of the same data is two
# chances to disagree.
from ledger.servers.store import RECORDS, LedgerToolset


def _chain_end(start: str) -> str:
    """Follow `link` to the end. Bounded by the record count, so a cycle in the data
    terminates instead of hanging the grader."""
    seen, current = set(), start
    while RECORDS[current]["link"] and current not in seen:
        seen.add(current)
        current = RECORDS[current]["link"]
    return current


def _chain(start: str) -> list[str]:
    """The whole chain from `start` to its end, inclusive. Same bound as `_chain_end`
    for the same reason. Kept separate rather than folded into it: the end-only walk is
    load-bearing for four existing answers and a tested cycle guard, and widening its
    return type would have meant touching all of them."""
    seen, current, out = set(), start, [start]
    while RECORDS[current]["link"] and current not in seen:
        seen.add(current)
        current = RECORDS[current]["link"]
        out.append(current)
    return out


def _tasks() -> list[tuple[str, str, str, int]]:
    """(name, prompt, answer, minimum tool calls a correct solution needs)."""
    by_kind: dict[str, list[dict]] = {}
    for record in RECORDS.values():
        by_kind.setdefault(record["kind"], []).append(record)
    owners = sorted({r["owner"] for r in RECORDS.values()})

    out: list[tuple[str, str, str, int]] = []

    # --- one call: can the arm reach the catalog at all? ---------------------
    for rid in ("r00", "r17", "r33"):
        out.append((
            f"lookup-{rid}",
            f"What is the amount on record {rid}? Reply with the number alone in "
            f"<answer></answer> tags.",
            str(RECORDS[rid]["amount"]),
            1,
        ))
    out.append((
        "owner-r22",
        "Who owns record r22? Reply with the owner name alone in <answer></answer> tags.",
        RECORDS["r22"]["owner"],
        1,
    ))

    # --- a few calls: composition, where a program is not yet an advantage ---
    for start in ("r03", "r11", "r08"):
        out.append((
            f"chain-{start}",
            f"Record {start} links to another record, which may link to another, and so "
            f"on. Follow the links to the last record in the chain. Reply with its id "
            f"alone in <answer></answer> tags.",
            _chain_end(start),
            2,
        ))
    out.append((
        "backlink-r30",
        "Which record links to r30? Reply with its id alone in <answer></answer> tags.",
        " ".join(sorted(r["id"] for r in RECORDS.values() if r["link"] == "r30")),
        1,
    ))

    # --- many calls: the aggregation shape ------------------------------------
    for kind in sorted(by_kind):
        out.append((
            f"total-{kind}",
            f"What is the total amount across every {kind} record in the ledger? Reply "
            f"with the number alone in <answer></answer> tags.",
            str(sum(r["amount"] for r in by_kind[kind])),
            len(RECORDS),
        ))
    out.append((
        "count-invoice",
        "How many records in the ledger are of kind invoice? Reply with the number alone "
        "in <answer></answer> tags.",
        str(len(by_kind["invoice"])),
        len(RECORDS),
    ))
    richest = max(owners, key=lambda o: sum(r["amount"] for r in RECORDS.values() if r["owner"] == o))
    out.append((
        "richest-owner",
        "Which owner has the largest total amount across all their records? Reply with "
        "the owner name alone in <answer></answer> tags.",
        richest,
        len(RECORDS),
    ))
    largest = max(RECORDS.values(), key=lambda r: (r["amount"], r["id"]))
    out.append((
        "largest-record",
        "Which record has the largest amount? Reply with its id alone in "
        "<answer></answer> tags.",
        largest["id"],
        len(RECORDS),
    ))

    # --- the hard tier: added 2026-10-07, AFTER the premise check -------------
    #
    # Run 2h scored PTC 14/14 on everything above. A benchmark the untrained model
    # already aces cannot show a training effect -- there is no headroom to climb, and
    # a flat post-training result would be unreadable (`docs/pre-registration.md` §8/A5
    # records that this extension is post-hoc and that no comparison across taskset
    # versions is admissible). 2607.12640, cited in §4's H2, is the reason: GRPO helped
    # "only when there is headroom to climb".
    #
    # Every shape below is a SECOND-ORDER read of the same five fields: no new fields,
    # no new tools, no new record. What makes them hard is that the single-pass
    # filter-and-sum that solves the tier above is not enough -- each needs an
    # intermediate result (a mean, a rank, a walk, a set) before the final one. That is
    # also the shape the 2h finding points at: bash retrieved all 40 records correctly
    # and then mis-summed fifteen numbers in context, so the open question is whether a
    # model computes when the action must be expressed as a program.
    #
    # ponytail: no new data file. 40 records support these; what they did not support
    # was 242 tasks of the EXISTING shapes, which is a different problem (A3).

    # walk then aggregate: the chain tasks above stop at the end, these sum it
    for start in ("r03", "r11"):
        walk = _chain(start)
        out.append((
            f"chainsum-{start}",
            f"Start at record {start} and follow its `link` to the end of the chain. "
            f"What is the total amount across every record in that chain, including "
            f"{start} itself and the last one? Reply with the number alone in "
            f"<answer></answer> tags.",
            str(sum(RECORDS[r]["amount"] for r in walk)),
            len(walk),
        ))
    out.append((
        "chainend-owner-r11",
        "Start at record r11 and follow its `link` to the end of the chain. Who owns "
        "the last record in that chain? Reply with the owner name alone in "
        "<answer></answer> tags.",
        RECORDS[_chain_end("r11")]["owner"],
        len(_chain("r11")),
    ))
    longest = min(RECORDS, key=lambda i: (-len(_chain(i)), i))
    out.append((
        "longest-chain-start",
        "Every record may link to another, forming chains. Which record begins the "
        "longest chain? Reply with its id alone in <answer></answer> tags.",
        longest,
        len(RECORDS),
    ))

    # rank, not extreme: off-by-one is the failure this is here to catch
    ranked = sorted((r["amount"] for r in RECORDS.values()), reverse=True)
    out.append((
        "third-largest-amount",
        "What is the third largest amount in the ledger? Reply with the number alone "
        "in <answer></answer> tags.",
        str(ranked[2]),
        len(RECORDS),
    ))
    kind_totals = {k: sum(r["amount"] for r in v) for k, v in by_kind.items()}
    out.append((
        "second-kind-total",
        "Rank the record kinds by their total amount. Which kind has the second "
        "largest total? Reply with the kind alone in <answer></answer> tags.",
        sorted(kind_totals, key=lambda k: (-kind_totals[k], k))[1],
        len(RECORDS),
    ))

    # mean, not sum: the richest owner by sum and by mean are different owners, so an
    # arm that reaches for the sum it already computed gets this one wrong
    out.append((
        "owner-largest-mean",
        "Which owner has the largest MEAN amount across their own records? Reply with "
        "the owner name alone in <answer></answer> tags.",
        min(owners, key=lambda o: (
            -sum(r["amount"] for r in RECORDS.values() if r["owner"] == o)
            / sum(1 for r in RECORDS.values() if r["owner"] == o), o)),
        len(RECORDS),
    ))
    mean = sum(r["amount"] for r in RECORDS.values()) / len(RECORDS)
    out.append((
        "above-mean-count",
        "How many records have an amount strictly greater than the mean amount across "
        "the whole ledger? Reply with the number alone in <answer></answer> tags.",
        str(sum(1 for r in RECORDS.values() if r["amount"] > mean)),
        len(RECORDS),
    ))

    # set reasoning across both link directions, and across kinds
    all_kinds = set(by_kind)
    all_kind_owners = sorted(
        o for o in owners
        if {r["kind"] for r in RECORDS.values() if r["owner"] == o} == all_kinds)
    out.append((
        "owners-all-kinds",
        "Which owners own at least one record of every kind in the ledger? Reply with "
        "their names in alphabetical order, separated by single spaces, in "
        "<answer></answer> tags.",
        " ".join(all_kind_owners),
        len(RECORDS),
    ))
    out.append((
        "invoice-total-all-kind-owners",
        "Consider only the owners who own at least one record of every kind. What is "
        "the total amount of their invoice records? Reply with the number alone in "
        "<answer></answer> tags.",
        str(sum(r["amount"] for r in RECORDS.values()
                if r["kind"] == "invoice" and r["owner"] in all_kind_owners)),
        len(RECORDS),
    ))
    linked_to = {r["link"] for r in RECORDS.values() if r["link"]}
    out.append((
        "isolated-total",
        "A record is isolated if it links to nothing and nothing links to it. What is "
        "the total amount across every isolated record? Reply with the number alone in "
        "<answer></answer> tags.",
        str(sum(r["amount"] for r in RECORDS.values()
                if not r["link"] and r["id"] not in linked_to)),
        len(RECORDS),
    ))

    # two constraints at once, the cheapest of the hard shapes
    for kind in sorted(by_kind):
        out.append((
            f"kind-max-{kind}",
            f"What is the largest amount on any {kind} record? Reply with the number "
            f"alone in <answer></answer> tags.",
            str(max(r["amount"] for r in by_kind[kind])),
            len(RECORDS),
        ))
    top_owner = max(owners, key=lambda o: sum(1 for r in RECORDS.values() if r["owner"] == o))
    out.append((
        f"count-{top_owner}-invoice",
        f"How many invoice records does {top_owner} own? Reply with the number alone "
        f"in <answer></answer> tags.",
        str(sum(1 for r in RECORDS.values()
                if r["owner"] == top_owner and r["kind"] == "invoice")),
        len(RECORDS),
    ))
    return out


class LedgerTaskConfig(vf.TaskConfig):
    tools: vf.ToolsetConfig = vf.ToolsetConfig()


class LedgerTaskData(vf.TaskData):
    answer: str
    """The exact expected answer, computed from the data in `_tasks`."""
    min_calls: int
    """How many tool calls a correct solution needs at minimum. Reported as a metric so
    the cost-per-task co-primary (pre-reg §2) can be read against task difficulty rather
    than against a single average."""


class LedgerTask(vf.Task[LedgerTaskData, vf.State, LedgerTaskConfig]):
    @classmethod
    def toolsets(cls, config: LedgerTaskConfig) -> list[vf.Toolset]:
        return [LedgerToolset(config.tools)]

    @vf.reward(weight=1.0)
    async def correct(self, trace: vf.Trace) -> float:
        """Exact match on the tagged answer. No judge, no partial credit, no substring
        search over the whole reply -- a reply that lists every id would otherwise
        contain the right one and score 1.0."""
        reply = trace.last_reply or ""
        if "<answer>" not in reply or "</answer>" not in reply:
            return 0.0
        given = reply.split("<answer>", 1)[1].split("</answer>", 1)[0]
        return float(" ".join(given.lower().split()) == self.data.answer.lower())


class LedgerConfig(vf.TasksetConfig):
    task: LedgerTaskConfig = LedgerTaskConfig()


class LedgerTaskset(vf.Taskset[LedgerTask, LedgerConfig]):
    def load(self) -> list[LedgerTask]:
        return [
            LedgerTask(
                LedgerTaskData(idx=i, name=name, prompt=prompt, answer=answer,
                               min_calls=min_calls),
                self.config.task,
            )
            for i, (name, prompt, answer, min_calls) in enumerate(_tasks())
        ]

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

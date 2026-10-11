"""Two derived counts — defects and runs — asserted across four documents.

`docs/deviations.md` installed the convention (commit `deac6e4`, "derive the defect count
instead of asserting it") because three different totals had been in circulation and none
had been derived. What it did not install was anything that checks the prose against the
tables. The count then moved 12 -> 13 on 2026-10-10 and ten separate sentences across four
files had to be found and edited by hand.

A derived number protected only by prose is the same structure as `pytest.ini` documenting
the suite-skip instead of fixing it: the fault is written down, not fixed. This file is the
fix. The two tables under `## The defect ledger` are the single source of truth; every
sentence that states a number is checked against them.

**`docs/pre-registration.md` is deliberately excluded.** It is append-only and owner-signed,
and the figures frozen in it (including an `8.5x` corrected elsewhere on 2026-10-10) are
addressed by appended amendment, never by edit. A guard that demanded an edit there would be
demanding the one thing the file forbids.

Lives in `tests/` because it is about the documents rather than about the metrics, and
`ptc/` is where the metrics tests live. Placement no longer decides whether it runs:
`pytest.ini` read `testpaths = tests` until 2026-10-10, when commit `1c2fe2f` widened it to
`tests ptc ledger`, so a bare `pytest` now collects all three suites. Any instruction still
saying to run `pytest tests ptc ledger` to avoid a silent skip is describing a fixed fault.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "deviations.md"

WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16}


def number(word: str) -> int:
    """`"Thirteen"` -> `13`. Raises on an unknown word rather than guessing."""
    return WORDS[word.strip().lower()]


def plain(text: str) -> str:
    """Emphasis, blockquote markers and line wrapping removed.

    Three normalisations, each because the thing it removes is a formatting change rather
    than a count change and must not fail the guard: `**four**` and `four` are the same
    claim; the OSF abstract is a `>` blockquote; and every one of these sentences is
    hard-wrapped at ~90 columns, so a count and its noun routinely sit on different lines
    (`… carefully: nine` / `> in the measurement harness and four …`). Re-wrapping a
    paragraph must not read as a drifted number.
    """
    text = re.sub(r"[*`]", "", text)
    text = re.sub(r"^\s*>\s?", " ", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text)


def derive() -> dict[str, int]:
    """Count the rows of the ledger's two tables. The only source of truth here.

    A row is a `|`-prefixed line that is neither the header nor the `---` separator. The
    walk stops at the next `##`, so the per-run deviation records below the ledger -- which
    are full of their own tables -- cannot leak into the count.
    """
    lines = LEDGER.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## The defect ledger"))
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1)
               if l.startswith("## "))

    counts: dict[str, int] = {}
    headings: dict[str, int] = {}
    group = None
    for line in lines[start:end]:
        if line.startswith("### "):
            label = plain(line).lstrip("# ").strip()
            key = "harness" if label.lower().startswith("harness") else "tools"
            group = key
            counts[key] = 0
            # The heading states its own count (`### Harness -- nine`) and is checked too.
            stated = re.search(r"[-—]\s*(\w+)\s*$", label)
            if stated:
                headings[key] = number(stated.group(1))
        elif group and line.startswith("|") and "---" not in line \
                and not line.startswith("| fault"):
            counts[group] += 1

    assert set(counts) == {"harness", "tools"}, f"expected two groups, got {set(counts)}"
    return {**counts, "total": sum(counts.values()), "headings": headings,
            **derive_states()}


def derive_states() -> dict[str, int]:
    """Count each repair state from the tables' last column.

    Added 2026-10-11 because "twelve of them fixed" was the one count in these documents
    that nothing could derive -- the tables recorded what each fault was and what caught
    it, never whether it had been repaired -- and it was wrong: the rate limit has never
    been fixed and this file has said so since 2026-10-08.

    **Three states, not a boolean.** `fixed` means a code change exists and a test covers
    it; `not fixable` is the structural rate limit, survived per-run; `withdrawn` is the
    one-armed success rate, whose OUTCOME is retracted rather than the instrument
    corrected. A boolean would have had to lie about two of thirteen rows, and the
    abstract makes a claim about each state separately, so each is counted separately.
    """
    lines = LEDGER.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## The defect ledger"))
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1)
               if l.startswith("## "))
    states = {"fixed": 0, "not fixable": 0, "withdrawn": 0}
    for line in lines[start:end]:
        if not line.startswith("|") or "---" in line or line.startswith("| fault"):
            continue
        cells = [plain(c).strip() for c in line.strip().strip("|").split("|")]
        last = cells[-1].lower()
        assert last in states, (
            f"unknown repair state {cells[-1]!r} -- every ledger row needs one of "
            f"{sorted(states)}, so a new row cannot be filed without declaring it")
        states[last] += 1
    return {"fixed": states["fixed"], "not_fixable": states["not fixable"],
            "withdrawn": states["withdrawn"]}


RUN_LEDGER_HEADING = "## Run inventory"


def derive_runs() -> dict[str, int]:
    """Count the rows of the run inventory table, and the admissible subset.

    Same failure mode as the defect count, different number: the OSF abstract said "ten
    runs" for three days while fourteen arm-pairs sat on disk, because the sentence was
    written the morning two more runs landed. The table is dated from each rollout's own
    `timing.start`, so it is the derived source and this reads it.
    """
    lines = LEDGER.read_text().splitlines()
    start = next(i for i, l in enumerate(lines)
                 if l.startswith(RUN_LEDGER_HEADING))
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1)
               if l.startswith("## "))
    rows = [l for l in lines[start:end]
            if re.match(r"^\|\s*\d+\s*\|", l)]
    admissible = [l for l in rows if "admissible" in plain(l)]
    return {"runs": len(rows), "admissible": len(admissible)}


# Every sentence in the repo that states a defect count, with the pattern that reads it and
# the derived key each captured group must equal. `None` skips a group -- used once, for
# "twelve of them fixed", which is not derivable from the tables: they record what the
# faults were, not which are repaired.
CLAIMS: tuple[tuple[str, str, tuple[str | None, ...]], ...] = (
    # docs/deviations.md -- the ledger's own headline and closing line
    ("docs/deviations.md",
     r"(\w+) distinct faults: (\w+) in the harness, (\w+) in the adjudication tools",
     ("total", "harness", "tools")),
    ("docs/deviations.md", r"All (\w+) were invisible to a green test suite", ("total",)),
    # HANDOFF.md -- the entry-point bullet
    ("HANDOFF.md",
     r"(\w+) distinct faults — (\w+) in the harness, (\w+) in the tools that adjudicate",
     ("total", "harness", "tools")),
    # docs/outreach.md -- the OSF title, the note under it, and the abstract
    ("docs/outreach.md", r"and (\w+) instrument defects\s*\n?\s*that produced it",
     ("total",)),
    ("docs/outreach.md",
     r"split: (\w+) harness faults plus (\w+) in the adjudication tools",
     ("harness", "tools")),
    ("docs/outreach.md", r"(\w+) faults were found, (\w+) of them fixed",
     ("total", "fixed")),
    ("docs/outreach.md",
     r"(\w+) in the measurement harness and (\w+) in the tools that adjudicate",
     ("harness", "tools")),
    ("docs/outreach.md", r"The (\w+) adjudication faults were", ("tools",)),
    # docs/results-untrained.md -- the defect section
    ("docs/results-untrained.md",
     r"now counts\s*\n?\s*(\w+): (\w+) in the harness and (\w+) in the adjudication tools",
     ("total", "harness", "tools")),
    ("docs/results-untrained.md", r"(\w+) of the (\w+) faults were in the code",
     ("tools", "total")),
)


RUN_CLAIMS: tuple[tuple[str, str, tuple[str | None, ...]], ...] = (
    ("docs/outreach.md",
     r"Across (\w+) measured runs on a 40-record ledger taskset .*?"
     r"of which (\w+) are admissible",
     ("runs", "admissible")),
    # NB: patterns are matched against `plain(...)`, which strips `*` and backticks, so
    # they must not contain markdown emphasis themselves.
    ("docs/outreach.md", r"(\w+) arm-pairs carry dated rollouts\s+on disk", ("runs",)),
    ("HANDOFF.md", r"met a real\s*\n?\s*model (\w+) times", ("runs",)),
    ("docs/deviations.md",
     r"(\w+) arm-pairs carry dated rollouts on disk. The run labels run to (\w+)",
     ("runs", None)),
    ("docs/deviations.md", r"Only (\w+) runs are admissible", ("admissible",)),
    ("docs/deviations.md", r"(\w+) measured runs, of which (\w+) are admissible",
     ("runs", "admissible")),
)


def test_the_run_inventory_agrees_with_every_sentence_that_states_a_run_count():
    """The second derived count. `Across ten runs` survived three days and two further
    runs in the text that was about to become a DOI."""
    d = derive_runs()
    problems: list[str] = []
    for rel, pattern, keys in RUN_CLAIMS:
        text = plain((ROOT / rel).read_text())
        found = re.search(pattern, text)
        if not found:
            problems.append(f"{rel}: no sentence matching {pattern!r} — reworded or "
                            f"deleted, so the run count there is now unchecked")
            continue
        for group_text, key in zip(found.groups(), keys):
            if key is None:
                continue
            got = number(group_text)
            if got != d[key]:
                problems.append(f"{rel}: says {group_text} ({got}) for {key}, "
                                f"inventory derives {d[key]}")
    assert not problems, "run count drifted from the inventory table:\n  " + \
        "\n  ".join(problems)


def test_the_ledger_tables_agree_with_their_own_group_headings():
    """`### Harness — nine` is itself a claim, and it sits directly above the rows it
    counts. If the heading and the rows disagree the table was edited and the prose was
    not, which is the whole failure mode."""
    d = derive()
    assert d["headings"]["harness"] == d["harness"], (
        f"heading says {d['headings']['harness']}, table has {d['harness']} rows")
    assert d["headings"]["tools"] == d["tools"], (
        f"heading says {d['headings']['tools']}, table has {d['tools']} rows")


def test_the_derived_total_is_the_sum_of_the_two_groups():
    d = derive()
    assert d["total"] == d["harness"] + d["tools"]
    # Not a tautology with the line above: it pins that the ledger has not grown a third
    # group that nothing sums. `derive` asserts exactly two, and this records why.
    assert d["harness"] > 0 and d["tools"] > 0


def test_every_sentence_that_states_a_defect_count_matches_the_tables():
    """All ten sites at once, reporting every mismatch rather than the first.

    Failing on the first would send whoever moved a row on ten round trips, which is how
    a guard ends up disabled.
    """
    d = derive()
    problems: list[str] = []
    for rel, pattern, keys in CLAIMS:
        text = plain((ROOT / rel).read_text())
        found = re.search(pattern, text)
        if not found:
            problems.append(f"{rel}: no sentence matching {pattern!r} — it was reworded "
                            f"or deleted, so the count there is now unchecked")
            continue
        for group_text, key in zip(found.groups(), keys):
            if key is None:
                continue
            try:
                got = number(group_text)
            except KeyError:
                problems.append(f"{rel}: {group_text!r} is not a number word")
                continue
            if got != d[key]:
                problems.append(f"{rel}: says {group_text} ({got}) for {key}, "
                                f"tables derive {d[key]}")
    assert not problems, "defect count drifted from the ledger tables:\n  " + \
        "\n  ".join(problems)


def test_the_fixed_count_matches_the_table():
    """The claim this column was added to make checkable.

    The OSF abstract states a repair count, and the node is days from a DOI that cannot be
    edited. Before the column existed the number was unverifiable; it was also wrong. All
    three states are pinned, not just `fixed`, because the abstract now makes a separate
    claim about each and the sum has to close against the ledger total.
    """
    d = derive()
    assert d["fixed"] + d["not_fixable"] + d["withdrawn"] == d["total"], (
        "every fault has exactly one state, so the three must sum to the total")
    assert d["not_fixable"] >= 1, (
        "the per-account rate limit is structural -- its own section is titled "
        "'structural rather than fixable'. A ledger with nothing unfixable means that row "
        "was silently reclassified")
    assert d["withdrawn"] >= 1, (
        "secondary 3's outcome is withdrawn, not repaired: fixing it needs an error "
        "channel on the bash arm AND a predicate that catches wrapped exceptions")

    # The abstract's sentence, read back from the document rather than restated here.
    abstract = plain((ROOT / "docs" / "outreach.md").read_text())
    found = re.search(r"(\w+) faults were found, (\w+) of them fixed", abstract)
    assert found, "the abstract no longer states a repair count"
    assert number(found.group(2)) == d["fixed"]


def test_the_append_only_pre_registration_is_not_policed():
    """Stated as a test so the exclusion is deliberate rather than an oversight.

    `docs/pre-registration.md` is owner-signed and append-only. It carries figures
    corrected elsewhere (an `8.5x` cost ratio, unrounded 8.05x, and 7.53x at the relay's
    measured rates) which are addressed by appended amendment. A guard that read a count
    out of it would eventually demand an edit to a file whose whole point is that it is
    never edited.
    """
    assert not any(rel == "docs/pre-registration.md" for rel, _, _ in CLAIMS)
    assert (ROOT / "docs" / "pre-registration.md").exists()

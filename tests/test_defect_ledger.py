"""The defect count is derived by a written convention and asserted in ten places.

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
    return {**counts, "total": sum(counts.values()), "headings": headings}


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
     ("total", None)),
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

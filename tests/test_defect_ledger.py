"""Two derived counts — defects and runs — asserted across four documents.

`docs/deviations.md` installed the convention (commit `deac6e4`, "derive the defect count
instead of asserting it") because three different totals had been in circulation and none
had been derived. What it did not install was anything that checks the prose against the
tables. The count then moved 12 -> 13 on 2026-10-10 and ten separate sentences across four
files had to be found and edited by hand.

A derived number protected only by prose is the same structure as `pytest.ini` documenting
the suite-skip instead of fixing it: the fault is written down, not fixed. This file is the
fix. The three tables under `## The defect ledger` are the single source of truth; every
sentence that states a number is checked against them.

**`docs/pre-registration.md` is deliberately excluded.** It is append-only and owner-signed,
and the figures frozen in it (including an `8.5x` corrected elsewhere on 2026-10-10) are
addressed by appended amendment, never by edit. A guard that demanded an edit there would be
demanding the one thing the file forbids.

**Some documents are frozen but not excluded.** `SUBMITTED_OR_LIVE` lists them: each states
the faults the ledger held on 2026-10-11, which is the set the OSF submission describes,
while the ledger now holds more. They are the owner's to amend, so their sentences are read
against the **submitted subset** the `submitted` column derives, and they are allowed to
state either that subset or the live total -- never a third number.
`test_the_documents_pending_an_amendment_are_named_and_counted` closes the other half:
whichever of them is still on the submitted value has to be named as pending in the ledger
itself, so a stale published number cannot sit unlisted. The ledger's paragraph holds that
list; this file does not keep a second copy of it to drift.

Lives in `tests/` because it is about the documents rather than about the metrics, and
`ptc/` is where the metrics tests live. Placement no longer decides whether it runs:
`pytest.ini` read `testpaths = tests` until 2026-10-10, when commit `1c2fe2f` widened it,
and it has been widened again since, so a bare `pytest` now collects every suite named
there. Any instruction still saying to run `pytest tests ptc ledger` to avoid a silent
skip is describing a fixed fault, and naming the suites by hand is how it came back.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "deviations.md"

WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30}

# Every pattern below captures with this rather than `\w+`, because `\w` excludes the
# hyphen: on `twenty-one` a `(\w+)` group matches "one", and `number("one")` is 1, so the
# guard would have read the total as 1 and still passed on a count claim it never saw. The
# compound-number form arrived with the 13 -> 21 move, and this is the trap it set.
WORD = r"[\w-]+"


def number(word: str) -> int:
    """`"Thirteen"` -> `13`, `"twenty-one"` -> `21`, `"19"` -> `19`.

    Three forms because the documents use three: the prose spells counts out, the
    `state` bullets write them as digits in parentheses, and totals past twenty are
    hyphenated compounds. Raises on anything else rather than guessing -- a count the
    guard cannot read must fail loudly, not silently score as zero.
    """
    token = word.strip().lower()
    if token in WORDS:
        return WORDS[token]
    if token.isdigit():
        return int(token)
    if "-" in token:
        parts = [p for p in token.split("-") if p]
        if all(p in WORDS for p in parts):
            return sum(WORDS[p] for p in parts)
    raise KeyError(word)


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


# The ledger's groups, as (derived key, the lowercase prefix of the heading that holds it).
# A group is a LOCATION in the codebase, which is why the eight faults filed on 2026-10-12
# did not all go into the two that existed: two are in `ptc/paired.py` and belong to the
# adjudication tools, and six are in `bench/` and `train/`, which is neither. Filing those
# six under an existing heading would have kept the published "nine harness, four tools"
# split true by construction, and a number true by construction is the thing this ledger
# exists to record rather than commit.
GROUPS = (("harness", "harness"),
          ("tools", "adjudication tools"),
          ("instrument", "instruments built after"))


def derive() -> dict[str, int]:
    """Count the rows of the ledger's tables, per group and per repair state.

    The only source of truth here. A row is a `|`-prefixed line that is neither the
    header nor the `---` separator. The walk stops at the next `##`, so the per-run
    deviation records below the ledger -- which are full of their own tables -- cannot
    leak into the count.

    **Repair state is three-valued, not boolean.** The column was added 2026-10-11
    because "twelve of them fixed" was the one count in these documents that nothing
    could derive -- the tables recorded what each fault was and what caught it, never
    whether it had been repaired -- and it was wrong: the rate limit has never been fixed
    and the ledger has said so since 2026-10-08. `fixed` means a code change exists and a
    test covers it; `not fixable` is the structural rate limit, survived per-run;
    `withdrawn` is the one-armed success rate, whose OUTCOME is retracted rather than the
    instrument corrected. A boolean would have had to lie about two rows, and the abstract
    makes a claim about each state separately, so each is counted separately.

    **`submitted` is the second column this file reads for the same reason.** Added
    2026-10-12 on the 13 -> 21 move: three summary documents are frozen against the
    thirteen the ledger held on 2026-10-11, and the alternative to deriving that subset
    was either editing documents whose numbers are the owner's or deleting the guard that
    reads them. It records a fact that cannot drift -- what the ledger held at submission
    -- so both totals stay derivable from one table.
    """
    lines = LEDGER.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## The defect ledger"))
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1)
               if l.startswith("## "))

    states = ("fixed", "not fixable", "withdrawn")
    counts: dict[str, int] = {}
    submitted: dict[str, int] = {}
    tally = {s: 0 for s in states}
    sub_tally = {s: 0 for s in states}
    headings: dict[str, int] = {}
    group = None
    for line in lines[start:end]:
        if line.startswith("### "):
            label = plain(line).lstrip("# ").strip()
            matched = [key for key, prefix in GROUPS if label.lower().startswith(prefix)]
            assert len(matched) == 1, (
                f"heading {label!r} names no known group -- a new group has to be added "
                f"to GROUPS and to the ledger's own headline sentence in the same change, "
                f"or its rows are counted into the total by nothing")
            group = matched[0]
            counts[group] = 0
            submitted[group] = 0
            # The heading states its own count (`### Harness -- nine`) and is checked too.
            stated = re.search(rf"[-—]\s*({WORD})\s*$", label)
            if stated:
                headings[group] = number(stated.group(1))
        elif group and line.startswith("|") and "---" not in line \
                and not line.startswith("| fault"):
            counts[group] += 1
            cells = [plain(c).strip() for c in line.strip().strip("|").split("|")]
            state = cells[-1].lower()
            assert state in states, (
                f"unknown repair state {cells[-1]!r} -- every ledger row needs one of "
                f"{sorted(states)}, so a new row cannot be filed without declaring it")
            flag = cells[-2].lower()
            assert flag in ("yes", "no"), (
                f"unknown submitted flag {cells[-2]!r} -- every row declares whether it "
                f"was in the ledger the frozen summary documents describe, because "
                f"their counts are read against that subset")
            tally[state] += 1
            if flag == "yes":
                submitted[group] += 1
                sub_tally[state] += 1

    missing = [key for key, _ in GROUPS if key not in counts]
    assert not missing, f"the ledger has no table for {missing}"
    return {**counts,
            **{f"submitted_{k}": v for k, v in submitted.items()},
            **{f"new_{k}": counts[k] - v for k, v in submitted.items()},
            "total": sum(counts.values()),
            "submitted_total": sum(submitted.values()),
            "new_total": sum(counts.values()) - sum(submitted.values()),
            "fixed": tally["fixed"], "not_fixable": tally["not fixable"],
            "withdrawn": tally["withdrawn"],
            "submitted_fixed": sub_tally["fixed"],
            "submitted_not_fixable": sub_tally["not fixable"],
            "submitted_withdrawn": sub_tally["withdrawn"],
            "headings": headings}


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
# the derived key each captured group must equal. A key may be a tuple, which means the
# sentence may state any one of those derived values and nothing else -- used only for the
# frozen documents, which may legitimately still describe the submitted subset.
Claim = tuple[str, str, tuple[object, ...]]

# The ledger's own prose. Pinned to the LIVE numbers with no alternatives: this is the file
# the tables live in, so there is no version of it that is allowed to lag them.
LEDGER_CLAIMS: tuple[Claim, ...] = (
    (f"({WORD}) distinct faults: ({WORD}) in the harness, ({WORD}) in the adjudication "
     f"tools, ({WORD}) in the instruments built after",
     ("total", "harness", "tools", "instrument")),
    # The sentence states the total and no universal property, because one row does
    # not share it: the gate tests were caught by a RED suite nobody had run, not
    # missed by a green one, and a claim about all twenty-one would have been false
    # in the file whose subject is false claims.
    (f"The ledger holds ({WORD}) rows", ("total",)),
    # The 13 -> 21 move, and the batch it added. Both numbers are in the tables: the
    # batch is every row whose `submitted` cell says no, so the paragraph describing it
    # cannot be left behind by the next one.
    (f"It moved ({WORD}) → ({WORD}) on 2026-10-12", ("submitted_total", "total")),
    (f"not one of the ({WORD}) was exposed by a run", ("new_total",)),
    (f"({WORD}) of the nine are in ptc/paired.py and join the adjudication tools; the "
     f"other ({WORD}) are in bench/, train/ and the new ptc/sql_arms.py",
     ("new_tools", "instrument")),
    (f"({WORD}) of the nine are this project's own", ("new_instrument",)),
    # The three repair states, in the sentence and again in the bullet that explains each.
    (f"the honest total is ({WORD}) fixed, ({WORD}) not fixable, ({WORD}) withdrawn",
     ("fixed", "not_fixable", "withdrawn")),
    (rf"fixed \(({WORD})\) — a code change exists", ("fixed",)),
    (rf"not fixable \(({WORD})\) — the per-account rate limit", ("not_fixable",)),
    (rf"withdrawn \(({WORD})\) — the one-armed", ("withdrawn",)),
    # The pending-amendment paragraph states the subset it is about, and both totals.
    (f"summary documents still state the submitted ({WORD})", ("submitted_total",)),
    (f"the ({WORD}) those documents describe, frozen on 2026-10-11", ("submitted_total",)),
    (f"and the ({WORD}) the ledger holds now", ("total",)),
)

# The frozen documents. Each number must be one of two derived values: the subset their
# sentences were written against, or the live total if the owner has amended them.
SUBMITTED_OR_LIVE: tuple[Claim, ...] = (
    # HANDOFF.md -- the entry-point bullet
    ("HANDOFF.md",
     f"({WORD}) distinct faults — ({WORD}) in the harness, ({WORD}) in the tools that "
     f"adjudicate",
     (("submitted_total", "total"), ("submitted_harness", "harness"),
      ("submitted_tools", "tools"))),
    # docs/outreach.md -- the OSF title, the note under it, and the abstract
    ("docs/outreach.md", f"and ({WORD}) instrument defects\\s*\\n?\\s*that produced it",
     (("submitted_total", "total"),)),
    ("docs/outreach.md",
     f"split: ({WORD}) harness faults plus ({WORD}) in the adjudication tools",
     (("submitted_harness", "harness"), ("submitted_tools", "tools"))),
    ("docs/outreach.md", f"({WORD}) faults were found, ({WORD}) of them fixed",
     (("submitted_total", "total"), ("submitted_fixed", "fixed"))),
    ("docs/outreach.md",
     f"({WORD}) in the measurement harness and ({WORD}) in the tools that adjudicate",
     (("submitted_harness", "harness"), ("submitted_tools", "tools"))),
    ("docs/outreach.md", f"The ({WORD}) adjudication faults were",
     (("submitted_tools", "tools"),)),
    # docs/results-untrained.md -- the defect section
    ("docs/results-untrained.md",
     f"now counts\\s*\\n?\\s*({WORD}): ({WORD}) in the harness and ({WORD}) in the "
     f"adjudication tools",
     (("submitted_total", "total"), ("submitted_harness", "harness"),
      ("submitted_tools", "tools"))),
    ("docs/results-untrained.md", f"({WORD}) of the ({WORD}) faults were in the code",
     (("submitted_tools", "tools"), ("submitted_total", "total"))),
    # docs/harness-parity.md -- the fifth site, and the one that shows what an unpoliced
    # sentence costs: it stated the total in a form no pattern read, so the 12 -> 13 move
    # passed it by and it still said thirteen three days later. Added here on 2026-10-13,
    # the day it became tracked (`04575d4`); it was left out while untracked because a
    # guard pointed at a file that may not be in the commit fails on a clean checkout
    # rather than on a drifted number.
    ("docs/harness-parity.md",
     f"Every one of the ({WORD}) was invisible to a green test suite",
     (("submitted_total", "total"),)),
    ("docs/harness-parity.md", f"({WORD}) of the ({WORD}) harness faults in the",
     (None, ("submitted_harness", "harness"))),
)

CLAIMS: tuple[Claim, ...] = tuple(
    ("docs/deviations.md", pattern, keys) for pattern, keys in LEDGER_CLAIMS
) + SUBMITTED_OR_LIVE


RUN_CLAIMS: tuple[Claim, ...] = (
    ("docs/outreach.md",
     f"Across ({WORD}) measured runs on a 40-record ledger taskset .*?"
     f"of which ({WORD}) are admissible",
     ("runs", "admissible")),
    # NB: patterns are matched against `plain(...)`, which strips `*` and backticks, so
    # they must not contain markdown emphasis themselves.
    ("docs/outreach.md", f"({WORD}) arm-pairs carry dated rollouts\\s+on disk", ("runs",)),
    ("HANDOFF.md", f"met a real\\s*\\n?\\s*model ({WORD}) times", ("runs",)),
    ("docs/deviations.md",
     f"({WORD}) arm-pairs carry dated rollouts on disk. The run labels run to ({WORD})",
     ("runs", None)),
    ("docs/deviations.md", f"Only ({WORD}) runs are admissible", ("admissible",)),
    ("docs/deviations.md", f"({WORD}) measured runs, of which ({WORD}) are admissible",
     ("runs", "admissible")),
)


def check(claims: tuple[Claim, ...], derived: dict[str, int]) -> list[str]:
    """Read every claim out of its document and compare it to the derived values.

    Returns every problem rather than raising on the first: failing on the first would
    send whoever moved a row on ten round trips, which is how a guard ends up disabled.
    """
    problems: list[str] = []
    for rel, pattern, keys in claims:
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
            allowed = (key,) if isinstance(key, str) else key
            if got not in {derived[k] for k in allowed}:
                problems.append(
                    f"{rel}: says {group_text} ({got}) for "
                    f"{' or '.join(allowed)}, tables derive "
                    f"{' or '.join(str(derived[k]) for k in allowed)}")
    return problems


def test_the_run_inventory_agrees_with_every_sentence_that_states_a_run_count():
    """The second derived count. `Across ten runs` survived three days and two further
    runs in the text that was about to become a DOI."""
    problems = check(RUN_CLAIMS, derive_runs())
    assert not problems, "run count drifted from the inventory table:\n  " + \
        "\n  ".join(problems)


def test_the_ledger_tables_agree_with_their_own_group_headings():
    """`### Harness — nine` is itself a claim, and it sits directly above the rows it
    counts. If the heading and the rows disagree the table was edited and the prose was
    not, which is the whole failure mode."""
    d = derive()
    for key, _ in GROUPS:
        assert d["headings"][key] == d[key], (
            f"{key} heading says {d['headings'][key]}, table has {d[key]} rows")


def test_the_derived_total_is_the_sum_of_the_groups():
    d = derive()
    assert d["total"] == sum(d[key] for key, _ in GROUPS)
    # Not a tautology with the line above: it pins that every group the ledger has is one
    # the headline sentence sums. `derive` refuses a heading it cannot key, and the
    # headline claim above names all three by name, so a fourth location cannot be filed
    # without being counted. The 2026-10-12 move added the third.
    assert all(d[key] > 0 for key, _ in GROUPS)
    assert d["submitted_total"] == sum(d[f"submitted_{key}"] for key, _ in GROUPS)
    assert d["submitted_total"] < d["total"], (
        "nothing filed since the frozen documents were written means either the ledger "
        "stopped growing or the submitted column was back-filled onto new rows")


def test_every_sentence_that_states_a_defect_count_matches_the_tables():
    """All the sites at once, reporting every mismatch rather than the first."""
    problems = check(CLAIMS, derive())
    assert not problems, "defect count drifted from the ledger tables:\n  " + \
        "\n  ".join(problems)


def test_the_fixed_count_matches_the_table():
    """The claim the `state` column was added to make checkable.

    The OSF abstract states a repair count, and the node is days from a DOI that cannot be
    edited. Before the column existed the number was unverifiable; it was also wrong. All
    three states are pinned, not just `fixed`, because the abstract now makes a separate
    claim about each and the sum has to close against the ledger total.
    """
    d = derive()
    assert d["fixed"] + d["not_fixable"] + d["withdrawn"] == d["total"], (
        "every fault has exactly one state, so the three must sum to the total")
    assert (d["submitted_fixed"] + d["submitted_not_fixable"] + d["submitted_withdrawn"]
            == d["submitted_total"]), "and again over the subset the abstract describes"
    assert d["not_fixable"] >= 1, (
        "the per-account rate limit is structural -- its own section is titled "
        "'structural rather than fixable'. A ledger with nothing unfixable means that row "
        "was silently reclassified")
    assert d["withdrawn"] >= 1, (
        "secondary 3's outcome is withdrawn, not repaired: fixing it needs an error "
        "channel on the bash arm AND a predicate that catches wrapped exceptions")

    # The abstract's sentence, read back from the document rather than restated here. It
    # describes the submitted thirteen until the owner amends it, so either value passes.
    abstract = plain((ROOT / "docs" / "outreach.md").read_text())
    found = re.search(rf"({WORD}) faults were found, ({WORD}) of them fixed", abstract)
    assert found, "the abstract no longer states a repair count"
    assert number(found.group(2)) in (d["submitted_fixed"], d["fixed"])


def test_the_documents_pending_an_amendment_are_named_and_counted():
    """The other half of allowing two values in the frozen documents.

    `SUBMITTED_OR_LIVE` lets each of them state the submitted subset or the live total,
    which on its own would let a stale published number sit green and unmentioned
    forever -- the guard would have been widened into a guard that cannot fail, which is
    three rows of this very ledger. So whichever document is still on the submitted
    value has to be named in the ledger's pending-amendment paragraph, and the count
    there has to match. Amending a document removes it from the derived set, and the
    ledger's paragraph then has to lose it too.
    """
    d = derive()
    stale: set[str] = set()
    for rel, pattern, keys in SUBMITTED_OR_LIVE:
        text = plain((ROOT / rel).read_text())
        found = re.search(pattern, text)
        assert found, f"{rel}: no sentence matching {pattern!r}"
        for group_text, key in zip(found.groups(), keys):
            if key is None:
                continue  # a number the tables cannot derive; `check` skips it too
            allowed = (key,) if isinstance(key, str) else key
            submitted_key, live_key = allowed[0], allowed[-1]
            if d[submitted_key] == d[live_key]:
                continue  # the two agree on this number, so it says nothing either way
            if number(group_text) == d[submitted_key]:
                stale.add(rel)

    raw = LEDGER.read_text()
    anchor = "summary documents still state the submitted"
    assert anchor in raw, (
        f"the ledger no longer has a paragraph starting {anchor!r}, so nothing lists the "
        f"documents whose counts are allowed to lag: {sorted(stale)}")
    head = raw.index(anchor)
    para = raw[head:raw.index("\n\n", head)]
    named = set(re.findall(r"`([\w./-]+\.md)`", para))
    assert named == stale, (
        f"the ledger names {sorted(named)} as pending an amendment; the documents "
        f"actually still on the submitted subset are {sorted(stale)}")

    stated = re.search(rf"({WORD}) summary documents still state", plain(raw))
    assert stated, "the pending-amendment paragraph no longer states how many there are"
    assert number(stated.group(1)) == len(stale), (
        f"the ledger says {stated.group(1)} documents are pending, {len(stale)} are")


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

# Outreach — §1 sent, §2 prepared

Companion to `docs/licence-requests.md`. Everything here is addressed to people outside the
project and therefore needs a human to send it. **§1 was sent 2026-10-07.** §2 is still
waiting on a human.

---

## 1. The source paper's authors — SENT 2026-10-07

**Sent 2026-10-07 by the owner, send confirmed.** The text below is what went out, kept
verbatim as the record. No reply as of that date. It is the reply, or 2026-10-17, that
releases §2.

**Paper:** "Is Bash All You Need? An Empirical Study of Tool Interfaces for Enterprise
Digital Worker Agents", arXiv:2609.11999, cs.SE (cross-list cs.AI, cs.CL), submitted
2026-09-10, 13 pages.

**Authors:** Hazel Mak, Susheel Suresh, Sahil Bhatnagar, Barry Wang, Chhaya Methani,
Alejandro Gutierrez Munoz. Hazel Mak (listed on the submission as Sze Ning Hazel Mak) is
first author and submitter, so she is the addressee.

**Address:** looked up at send time and deliberately still not recorded here. arXiv hides it
behind the "view email" link on the abstract page; the PDF header is the other source.

**Why this goes before publication.** The result is a non-reproduction of their paper on a
small self-authored taskset, and the two questions below could change the write-up entirely.
If their bash condition was shell-only, our instruments differ in the dimension that decided
the result and the correct framing is "different setup", not "did not replicate".

**Subject:** Bash-over-PTC ordering did not reproduce in a small replication, two questions
about your setup

> Hi Hazel,
>
> I've been building on "Is Bash All You Need?" and wanted to send you a result before it
> goes anywhere public, because I suspect it says more about my instrument than about your
> paper.
>
> I tried to reproduce the untrained bash-over-PTC gap as a premise check for a co-training
> experiment. On a small self-authored taskset (40-record ledger, 14 tasks,
> deepseek-v4-flash, one rollout each) the ordering came out inverted: PTC 14/14 against
> bash 12/14, with PTC at roughly 8x fewer billed prompt tokens. It is not statistically
> separable at that n, two discordant pairs, exact McNemar p=0.50, so I am treating it as a
> failure to reproduce rather than a reversal.
>
> What makes me think the fault is mine: it took six instrument defects before the gap
> stopped appearing, and every one of them penalised the PTC arm. The largest was that my
> PTC arm reached the typed tools through a Python sandbox with no imports and no attribute
> access, so it received tool output as a JSON string it had no primitive to parse, while my
> bash arm held the same typed tools as native calls and read that JSON with its own
> attention. My bash arm's action space was a strict superset of my PTC arm's.
>
> Hence two questions about your setup, which would tell me whether I measured the same
> thing you did:
>
> 1. In your bash condition, did the agent also have the typed tools available, or was it
>    shell-only? Mine had both, and its shell-call share was 0.02, so it was effectively a
>    typed-tool agent with a shell it never used.
> 2. In your PTC condition, could the generated program import modules or call string
>    methods on tool output? If yes, our PTC arms differ in the one dimension that decided
>    my result.
>
> One observation that may be independent of all this: my bash arm's only two failures were
> arithmetic. It fetched all 40 records correctly over 42 turns, listed them, then mis-summed
> fifteen numbers in context, with a shell available and unused. The PTC arm wrote `sum(...)`.
> If that generalises, interface choice may matter less for retrieval than for computation.
>
> Happy to send the full write-up, traces and the defect log if useful. Either way, thanks
> for publishing the numbers in enough detail to check.
>
> Best,
> Nikolas

**Attach nothing.** The mail references the write-up and offers it; it does not ship it. The
repo is private, so there is no link to give until that changes.

---

## 2. OSF posting — PREPARED, NOT POSTED

**The clock is running: §1 went out 2026-10-07, so the hard date is 2026-10-17.** Post on
her reply or on that date, whichever comes first. If she answers that her bash condition was
shell-only, the title changes from a non-reproduction to a different-setup report — so read
any reply before posting, do not post early. OSF is
chosen over arXiv deliberately: a first cs.LG/cs.SE submission needs an endorsement, a short
non-replication is a poor fit for the format, and OSF gives a public URL and DOI with no
gatekeeper. There is no arXiv mechanism for commenting on someone else's paper.

**Title:** Failure to reproduce the bash-over-PTC ordering, and six instrument defects that
produced it

**Abstract:**

> A premise check for a co-training experiment attempted to reproduce the untrained
> bash-over-programmatic-tool-calling gap reported in arXiv:2609.11999 (+6.8 to +22.0 pp in
> favour of a shell interface). Across seven runs on a 40-record ledger taskset with a single
> small model, the gap reproduced only while the measuring instrument was defective. Six
> defects were found, five penalising the PTC arm and one the shell arm, each invisible to a
> passing test suite and detectable only against a live endpoint. The largest was an
> action-space asymmetry: both arms received identical tools, but the shell arm read tool
> output as text while the PTC arm received it inside a sandbox with no parser, making the
> shell arm's action space a strict superset. After correction the ordering inverted (PTC
> 14/14 versus 12/14, at 8x fewer billed prompt tokens), though not separably at n=14.
> Reported as a non-reproduction rather than a reversal. The shell arm's only failures were
> arithmetic on data it had retrieved correctly.

**Files to upload:** `docs/results-untrained.md`, `docs/deviations.md`,
`docs/pre-registration.md`.

**State the limitations in the OSF description, not only in the paper:** n=14, one model, one
provider (an unaudited third-party relay), a self-authored taskset, no repeats, and a
saturated PTC arm that cannot carry an effect size.

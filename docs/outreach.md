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
> bash 12/14, with PTC at roughly 8x fewer relay-reported prompt tokens. It is not statistically
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

## 2. OSF posting — DRAFTED ON OSF, PRIVATE, NOT PUBLISHED

**Node `2hfzt` exists: https://osf.io/2hfzt/ — created 2026-10-07, `public: false`.** Title,
description (abstract plus the limitations paragraph) and tags are set; all three files are
uploaded and md5-verified against the repo copies. **Everything reversible is done.** What
remains is the one irreversible step: flip the node public and mint the DOI.

**The clock is running: §1 went out 2026-10-07, so the hard date is 2026-10-17.** Post on
her reply or on that date, whichever comes first. If she answers that her bash condition was
shell-only, the title changes from a non-reproduction to a different-setup report — so read
any reply before posting, do not post early. OSF is
chosen over arXiv deliberately: a first cs.LG/cs.SE submission needs an endorsement, a short
non-replication is a poor fit for the format, and OSF gives a public URL and DOI with no
gatekeeper. There is no arXiv mechanism for commenting on someone else's paper.

**Title:** Failure to reproduce the bash-over-PTC ordering, and thirteen instrument defects
that produced it

*(⚠ The title set on OSF node `2hfzt` says "twelve" and is now stale — the count moved to
thirteen on 2026-10-10 and the node needs a pass before it goes public. The earlier draft said
"six", which was the harness count as of run 2h and stopped being true at run 3b. Current
split: nine harness faults plus four in the adjudication tools, per the ledger in
`docs/deviations.md`. Derive the number from that ledger's tables; do not quote it from
here.)*

**Abstract:**

> A premise check for a co-training experiment attempted to reproduce the untrained
> bash-over-programmatic-tool-calling (PTC) gap reported in arXiv:2609.11999 (+6.8 to
> +22.0 pp in favour of a shell interface). Across ten runs on a 40-record ledger taskset
> with a single small model, the gap reproduced only while the measuring instrument was
> defective.
>
> Thirteen faults were found, twelve of them fixed, each invisible to a passing test suite
> and detectable only against a live endpoint or against its own output read carefully: nine
> in the measurement harness and four in the tools that adjudicate the result. The
> thirteenth — a tool-call success rate instrumented on only one of the two arms — is
> recorded and its outcome withdrawn rather than repaired, because repairing it requires
> giving the shell arm an error channel the rig can see. Five of the nine
> penalised the PTC arm, one the shell arm, two were introduced by a fix and were symmetric,
> and one is the rate limit described below. The largest single fault was an action-space
> asymmetry, where both arms received identical tools but the shell arm read tool output as
> text while the PTC arm received it inside a sandbox with no parser, making the shell arm's
> action space a strict superset. The four adjudication faults were a partial-run guard that
> only fired on an empty overlap, a reader that scored an errored rollout 0.0 and so could
> not distinguish a crash from a wrong answer, an interaction interval computed on the
> reverse difference, and a tool-call success rate whose failure predicate only ever matched
> one arm's error strings. The instrument has been the problem at least as often as the thing
> it measures.
>
> After the harness corrections the ordering inverted on the original 14 tasks (PTC 14/14
> against the shell arm's 12/14, at 8x fewer relay-reported prompt tokens), though not separably at
> n=14. Reported as a non-reproduction, not a reversal. The shell arm's only failures were
> arithmetic on data it had retrieved correctly, with a shell available and used on 2.3% of
> its calls.
>
> That ceiling prompted 15 harder tasks (14 to 29), each a second-order read of the same
> records: a rank, a mean, a link-walk or a set, rather than a single filter-and-sum pass.
> On the extended taskset the effect resolves by task tier rather than overall, and the two
> mechanically clean runs disagree about the magnitude while agreeing about the direction.
> The shell arm leads on single-call retrieval (+18.2 then +9.1 pp over 11 cheap tasks); PTC
> leads where a program must be written to compute (-5.6 pp over 18 full-scan tasks, both
> runs); the tier interaction is -23.7 then -14.6 pp, with confidence intervals of
> [-64.1, +15.2] and [-49.5, +16.7]. Both intervals include zero. The second clean run ends
> at an exact score tie, 23 of 29 each, with the marginal at p=1.0000. Nothing here is
> statistically separable at these sample sizes, and the pre-registered prediction for the
> interaction (-25 pp) was missed on both occasions.
>
> The one result that has never wavered is cost, and it is two ratios rather than one. Because
> the shell arm re-sends its entire transcript on every turn and takes one call per turn, it
> reported 8.0 to 10.7 times the prompt tokens for the same work — 6.9 to 8.9 times after
> correcting for the relay's own token counter. Cost per solved task is 6.1 to 8.2 times
> higher: $0.0126 to $0.0243 against PTC's $0.0017 to $0.0035, at rates measured against the
> relay rather than assumed. That is structural rather than incidental, it favours PTC under a
> co-primary declared in advance, and it holds even at an exact score tie. The defensible
> finding of this study is the cost structure, not the accuracy ordering — as a range with a
> stated floor, not as a single multiple.
>
> One disclosure belongs with those numbers. The endpoint is a third-party relay, and its
> reported token counts are computed relay-side: they match `cl100k_base` over the raw message
> content exactly on short prompts, carry no chat-template overhead, return the identical
> count for one prompt under two different model ids, and exceed every standard tokenizer by
> 43 to 56 percent above roughly 3,800 tokens. Nothing in our artifacts records which model
> actually answered. The token counts are therefore relay-reported rather than
> provider-billed, which is why the cost ratio is quoted with a floor: the divergence falls on
> the shell arm's long prompts and not on PTC's short ones, so it does not cancel in the ratio.
>
> The extension is a post-hoc instrument change, disclosed as an append-only amendment and
> carrying the handicap that the harder tasks were written after observing which shape the
> shell arm failed on.

**Files to upload:** `docs/results-untrained.md`, `docs/deviations.md`,
`docs/pre-registration.md`. **Uploaded 2026-10-07**, md5 verified against the repo copies.
Re-upload if any of the three changes before publication — the node holds a snapshot, not a
reference.

**State the limitations in the OSF description, not only in the paper:** n=11 and n=18 within
tier, one model, one provider (an unaudited third-party relay, so model identity is not
verifiable and is load-bearing), a self-authored taskset whose harder tier was written after
seeing which shape one arm failed on, no repeats, and a retry budget that had to be raised to
survive a per-account request-rate limit on the longer rollouts.

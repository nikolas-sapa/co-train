# `ledger` — the taskset the measurement needs

**What it is:** 14 deterministic tasks over a committed 40-record store, graded by exact
match, with three MCP tools that are identical for both arms.

## Why a self-authored taskset, which is a handicap

Say the cost first. A suite written by the same session that wants a result from it is
**not evidence about tasksets in general**, and `docs/pre-registration.md` §3 already
uses exactly that argument to prefer the APEX end of the published gap (a genuine
`sh -c` server) over the TAC end (an author-built catalog, self-declared as *"not every
shell-accessible endpoint"*). This suite inherits that handicap knowingly.

It exists because the alternatives do not work:

| Option | Why not |
|---|---|
| `glossary` | One tool call. **Both arms score 1.0** — measured by `ptc/compare.py canned`, not assumed. A saturated benchmark cannot show a gap of a few points. |
| `wiki_search`, `interception`, `proposer_solver` | LLM judge in the reward — disqualified by project rule #5 |
| `deepwiki`, `web_search_interception`, `nemo_gym_weather`, `openenv_wordle` | Network or API key |
| `reverse_text`, `alphabet_sort`, `scratchpad`, `color_codeword`, `kuhn_poker` | Deterministic, but no tool channel — nothing for the harness to differ on |
| `gsm8k` | Deterministic and offline, but the harness barely participates |
| `code_golf` | The environment runs the program, not the harness |
| harness-bench (106 tasks, 812 fixtures) | **No licence file** → all-rights-reserved. Request drafted at `docs/licence-requests.md`, needs a human to file it. |

Filing that request is still the better long-run answer. This suite is what unblocks the
premise check in the meantime, and it is cheap to discard if the licence lands.

## What is held constant, and what varies

The **only** thing that differs between arms is the action channel. Both receive the
same three tools; `bash` calls them as sibling tools, `ptc` calls them from inside one
program. That satisfies pre-reg §5's requirement that action-space altitude be held
comparable across arms or the asymmetry declared — here it is held by construction.

The catalog is deliberately low-level: `ledger_ids`, `ledger_get`, `ledger_links_to`. A
`ledger_total(kind)` tool would collapse every aggregation task into one call and the
suite would measure nothing.

## The three tiers

| Tier | Tasks | Minimum calls | What it tests |
|---|---|---|---|
| Lookup | 4 | 1 | Can the arm reach the catalog at all |
| Chain / backlink | 4 | 2 | Composition across calls |
| Aggregation | 6 | 40 | **Where a program should win if it wins anywhere** |

The third tier is the point. Summing 40 records is one loop in a program, or 40 separate
tool calls in a chat loop. If programmatic tool calling has a real advantage, that is its
shape — so the suite contains it rather than avoiding it. `min_calls` rides along on each
task so the cost co-primary (pre-reg §2) can be read against difficulty rather than
against one average.

## The grader

Exact match on `<answer>…</answer>`, case and whitespace normalised. No judge, no partial
credit, and deliberately **not** a substring search over the whole reply — a reply that
dumped every record would otherwise contain the right answer and score 1.0. That trap has
its own test.

## The suite tests the benchmark, not the model

24 tests. A benchmark whose answers were never checked is a way to be confidently wrong at
scale: one wrong expected value silently turns a correct arm into a losing one and nothing
in the run would show it.

- **Answers recomputed by an independent route.** A hand-typed expected value is a second
  implementation that can disagree with the first.
- **Ambiguity ruled out.** `richest-owner` and `largest-record` are asserted tie-free; a
  tie would make two replies both correct while the grader accepts one.
- **Chain answers asserted terminal**, so a model that walked one step further is not
  marked wrong for being right.
- **Planted mutants**, per pre-reg §5: off-by-one, untagged, unclosed, empty, the
  everything-dump. A check that has never gone red is not evidence.
- **Cycle-bounded walk**, tested by closing a cycle in the data and restoring it. The
  failure mode of an unbounded walk is a hung grader.

- **The tool server is started as a real subprocess** in one test. Verifiers launches
  each server as `python -m ledger.servers.store` from the runtime's workdir, so a
  parent's `sys.path.insert` does not reach it — the server died with
  `No module named 'ledger'` and the run **hung** until the port-file timeout while
  every in-process test stayed green. `glossary` never hits this because it is
  installed in site-packages. `ledger.on_pythonpath()` fixes it via `PYTHONPATH`, which
  is the channel that crosses a process boundary.
- **One record dict, not two.** `taskset.py` and `store.py` each used to `json.loads`
  the same file, so the grader and the tools held independent copies. A mutation test
  that closed a cycle in one walked the other, and the unbounded-walk mutant survived
  because the cycle it planted was invisible. Found by mutation, not by reading.

    <python-with-verifiers> -m pytest ledger/ -q

## Status

Suite green. **No model has run against it.** The tasks are the instrument; the
measurement is `ptc/compare.py real --taskset ledger`, which spends money and has not
been run.

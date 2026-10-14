# co-train

**Does co-training a small model against a programmatic-tool-calling (PTC) harness reverse the
bash-over-PTC ordering that arXiv 2609.11999 measured on untrained models — and does the winner
survive a harness swap?**

Both halves have published baselines. **Neither trained half has been run — but the untrained
premise check has, and it falsified the premise.** Across 14 measured runs on the now-retired
`ledger` taskset, 3 of them admissible, the bash-over-PTC gap did not reproduce: it inverted
(run 2h, PTC 14/14 against bash 12/14, not statistically separable at n=14). The durable
finding is cost rather than accuracy — 6.1 to 8.2x cost per solved task, quoted as a floor.
Full report in `docs/results-untrained.md`. A negative result is publishable and cheap, which
is the point: this is a falsification-first research repo, not a product.

---

## Start here

~6,500 lines of markdown across 24 documents. One row per question a reader actually arrives
with; read the one file, not the pile.

| If you arrived asking | Read |
|---|---|
| **What is the result?** | **`docs/results-untrained.md`** — the pre-committed report on the untrained premise check. Read it before the framing below on this page, which was written before the run. |
| **What went wrong with the instrument?** | **`docs/deviations.md`** — defect ledger at the top of the file, each fault with the observation that caught it and, where one exists, the run that exposed it. This line read "each fault with the run that exposed it" until 2026-10-13, when a third table arrived for the faults found while building the next instrument: no run could have exposed those, because it had not run yet. |
| **What is the state, and what is next?** | **`HANDOFF.md`** — current state first, then the dated history below it. |
| **How do I run the suite?** | [Quick start](#quick-start), below. **`.venv-ptc` is required** — the system interpreter cannot collect two of the suites. |
| **What was fixed before the run, so the result stays falsifiable?** | `docs/pre-registration.md` (append-only, owner-signed); every amendment to it is in `docs/deviations.md`. |
| **How does the PTC arm work? What are the tasks?** | `ptc/README.md` for the restricted runtime, `ledger/README.md` for the taskset. |
| **Why any of these choices?** | `research/README.md` — 8 synthesis documents + 6 deep lanes. |
| **Did the training loop run on free hardware?** | `step2/results/README.md` for the verdict, `step2/README.md` for the detail. |

```
                 untrained          co-trained          swapped harness
   bash            69.4  ──┐          ?                   ?
   PTC             52.9  ──┴─ +16.5pp, the gap to reverse
```

Range to reverse is **+6.8 to +22.0 pp** across four published arms, one of which is not
statistically significant. Under a cost-per-successful-task metric the ordering is **already
reversed** in one untrained arm — so the metric is chosen before the run, not after.

---

## Status

| Step | State | Where |
|---|---|---|
| **1 — adversarial non-solvers + the gate** | ✅ done, 51 tests | `src/cotrain/`, `tests/` |
| **2 — prove the loop on free hardware** | ✅ done — **`STEP 2 PASS`, fp16 stable on T4** | `step2/`, result in `step2/results/` |
| **3 — verifier before environment** | ✅ **built** — BIRD-SQL eval harness + co-training pipeline, probe run, gate shut | `bench/`, `train/` |
| 4 — environment + escalation channel | not started | — |
| 5 — two harnesses, measure untrained first | not started | — |
| 6 — co-train, then cross-harness eval | not started | — |

Step 2 is answered: **fp16 GRPO is stable on a Kaggle T4.** 5 steps, `grad_norm` finite and
positive throughout, `reward_std` > 0 every step, `kl` rising across three orders of magnitude —
a curve no public run had. Numbers, caveats and stack in `step2/results/`; re-checkable with no
GPU via `python step2/verdict.py step2/results/step2_metrics.jsonl`.

> **Step 3 is built.** The free path held — fp16 GRPO on Qwen3/T4 is stable, so rented Ampere is
> not required. PR #11 landed the BIRD-SQL eval harness and the co-training pipeline; PRs #12-#17
> followed with the probe and its defect fixes. `ledger` is retired and **BIRD-SQL dev is the
> taskset: 1534 questions over 277 fine clause-skeleton shapes** (25 coarse), against `ledger`'s 9.
>
> **The probe has run — free Kaggle T4, $0 — and what it produced were instrument defects rather
> than a result:** the defect ledger moved from 13 to 25, the most recent being `extract_sql`
> taking the *first* fenced block when the prompt's own fence shifts every pairing. The pipeline
> gate is still shut by design — `train/guards.py` requires a signed amendment, a per-task
> solve-rate band and `n_tasks >= 59` derived rather than stored, and
> `bench/frontier/manifest.json` does not exist, so `preflight()` raises. **No co-training run
> has started.** Note the other session argues in `docs/spike-verifiers.md`
> that the PTC arm should come before the verifier; reconcile the two orderings first.

---

## Quick start

**Use `.venv-ptc/bin/python`.** `ptc/` and `ledger/` import `verifiers`, which is pinned to a
commit rather than a tag (`69cc0f9` — see `HANDOFF.md` for why no released tag works) and is
**not** installed on the system interpreter. On system `python3` the suite does not fail
loudly at the end on a missing dependency; it dies during *collection*, so a careless reader
sees a count and not an error:

```
ERROR ptc/test_compare.py    - ModuleNotFoundError: No module named 'verifiers'
ERROR ledger/test_ledger.py  - ModuleNotFoundError: No module named 'verifiers'
```

No GPU needed for any of it. Step 1's suite is stdlib-only and offline; Step 2's needs
`transformers` and reaches the HF hub for the Qwen3 tokenizer. Developed on CPython 3.12 and
3.14; no lower bound has actually been tested.

```bash
.venv-ptc/bin/python -m pytest -q         # the default suite: tests + ptc + ledger, offline
.venv-ptc/bin/python -m pytest step2 -q   # Step 2 — 54 tests (19 need transformers + the HF hub)

.venv-ptc/bin/python -m pytest tests -q   # Step 1's gate alone — 51 tests, nothing imports torch
```

A bare `pytest` is now safe to type: `pytest.ini`'s `testpaths` covers all three default
suites. It used to read `testpaths = tests`, so `pytest` collected 51 and silently skipped
`ptc` and `ledger` — the two suites that adjudicate the result. **Expect 528 passed** from the
default suite (measured 2026-10-14; it read 266 on 2026-10-10, before `bench` and `train`
landed); a sharply lower number means collection is being skipped again, which is a failure
this config has already had once.

`step2/` is deliberately left out of `testpaths` so the default suite stays offline.

Step 2's own dev venv, if you want the tokenizer-dependent tests:

```bash
uv venv --python 3.12 .venv-tok
uv pip install --python .venv-tok/bin/python transformers tokenizers jinja2 pytest \
    accelerate datasets "trl==0.29.0"
```

That `trl` is for the dev-side template helpers only and is **not** the training pin — the Kaggle
stack is `trl==0.24.0` with `transformers<5`, for the reason in the constraints below.

Training runs nowhere locally — the dev machine is darwin/arm64 and prime-rl requires NVIDIA.
Everything trains on Kaggle or rented hardware.

---

## Repo map

| Path | What it is |
|---|---|
| **`HANDOFF.md`** | **Read this to continue the work.** Current state at the top; below the history marker, the original build sequence, hard constraints, the "do NOT do these" list and corpus map, kept as written. |
| `docs/results-untrained.md` | The pre-committed report on the untrained premise check. |
| `docs/deviations.md` | Append-only amendment log, with the defect ledger at the top. |
| `docs/HANDOFF-STEP2.md` | What Step 1 learned, and the constraints it places on Steps 3-5. |
| `docs/pre-registration.md` | Outcomes fixed before the untrained run, so the result stays falsifiable. |
| `docs/licence-requests.md` | Drafted asks for the two unlicensed upstreams. |
| `docs/superpowers/` | Per-step specs and plans. |
| `research/` | 8 synthesis documents + 6 deep lanes. Start at `research/README.md`. |
| `src/cotrain/` | `src/cotrain/contract.py` (harness interface) · `src/cotrain/nonsolvers.py` (five adversarial non-solvers). |
| `tests/` | Step 1's gate. **`tests/leaky_env.py` is a permanent red-team target.** |
| `step2/` | Gate check, Kaggle run, pass criteria, mutation harness. See `step2/README.md`. |

---

## Two things that will bite you

**`tests/leaky_env.py` is deliberately exploitable and must never be hardened.** It carries one
leak per attack surface. If a future session "fixes" it, the gate stops discriminating and still
reports green.

**A green check is not evidence.** Four separate defects on this project were the same shape: a
passing check running against a stale, fake, or dormant target — two of them inside the
verification tooling itself. So the convention here is to **mutate the target and confirm red**
before trusting green. Both test suites are mutation-tested:

| Suite | Tests | Mutation testing |
|---|---|---|
| Step 1 gate | 51 | Six rounds; each found what the last missed — 5 surviving mutants in the contract, 4 in the agents, 3 dormant guards in the gate, then a whole exploit class. Total mutants run was not recorded. |
| Step 2 | 73 | 59 mutants, 0 survivors, re-run against the final code state. |

`step2/mutate.py` is the harness — fresh copy per mutation and `PYTHONDONTWRITEBYTECODE=1`, both
mandatory. A byte-length-identical mutation restored within the same second leaves identical mtime
*and* size, so Python keeps executing the cached `.pyc`. That produced one false verdict here.

---

## Hard constraints

Expensive to rediscover. Full table in `HANDOFF.md`.

- **No local training.** darwin/arm64 dev machine.
- **T4 = fp16 only.** Compute capability 7.5; bf16 needs 8.0.
- **prime-rl cannot run on a T4 at all** — no float16 in its `DTYPE_MAP`, FSDP hardcoded to
  bfloat16. The Unsloth-on-T4 path and the prime-rl path are *disjoint*, not two rungs of a ladder.
- **Unsloth pins `trl<=0.24.0`**, and TRL 0.24 declares `transformers>=4.56.1` with no upper
  bound. Install `transformers<5` or `from trl import GRPOTrainer` dies on an unrelated module —
  see `step2/README.md` for the mechanism.
- **Kaggle reality:** 30 GPU-h/week, 12 h/session, 20-30 min idle timeout.

---

## Branches

| Branch | Holds |
|---|---|
| `main` | Everything. The current state of the project. |

Six branches were deleted 2026-10-11 after `git rev-list main..<branch>` showed zero unique
commits on each: `step1-nonsolver-gate`, `step2-kaggle-smoke`, `step2-run`,
`fix/ptc-instrument-defects`, `docs/settle-step3-ordering`,
`fix/ptc-real-mode-control-and-error-exit`. Every commit they held is an ancestor of `main`.
This table previously described two of them as holding work `main` lacked, which stopped being
true when they merged and was never corrected.

Two sessions have worked this repo concurrently. If you run more than one, **give each its own
`git worktree`** — a shared checkout already caused one branch switch under a live session and one
contaminated commit.

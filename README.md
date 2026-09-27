# co-train

**Does co-training a small model against a programmatic-tool-calling (PTC) harness reverse the
bash-over-PTC ordering that arXiv 2609.11999 measured on untrained models — and does the winner
survive a harness swap?**

Both halves have published baselines. Neither has been run. A negative result is publishable and
cheap, which is the point: this is a falsification-first research repo, not a product.

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
| **2 — prove the loop on free hardware** | 🔶 gate resolved, run written, **no GPU yet** | `step2/` |
| 3 — verifier before environment | not started | — |
| 4 — environment + escalation channel | not started | — |
| 5 — two harnesses, measure untrained first | not started | — |
| 6 — co-train, then cross-harness eval | not started | — |

Step 2's only open question is **does it run, and is fp16 stable on a T4.** Everything checkable
without a GPU is checked; the run itself needs Kaggle. See `step2/KAGGLE.md`.

> **Step 3 is deliberately not started.** It is the intellectually interesting one and the wrong
> next move — every hour spent on it is wasted if fp16 GRPO on Qwen3/T4 turns out unstable.

---

## Quick start

No GPU needed. Step 1's suite is stdlib-only and offline; Step 2's needs `transformers` and
reaches the HF hub for the Qwen3 tokenizer. Developed on CPython 3.12 and 3.14; no lower bound
has actually been tested.

```bash
pytest -q            # Step 1's gate — 51 tests, stdlib only, nothing imports torch
pytest step2/ -q     # Step 2 — 54 tests (19 need transformers + the HF hub)
```

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
| **`HANDOFF.md`** | **Read this to continue the work.** Build sequence, hard constraints, the "do NOT do these" list, corpus map. |
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
| `main` | Step 1 only — **currently behind.** |
| `step2-kaggle-smoke` | Research `08`, pre-registration, licence requests, Step 2 scaffolding. |
| `step2-run` | The above plus the `transformers<5` fix and the Kaggle runbook. |

Two sessions have worked this repo concurrently. If you run more than one, **give each its own
`git worktree`** — a shared checkout already caused one branch switch under a live session and one
contaminated commit.

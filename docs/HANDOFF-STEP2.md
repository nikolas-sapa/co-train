# HANDOFF — Step 2

**Read `HANDOFF.md` first for the project. This file is what Step 1 learned.**
Status 2026-09-25: Step 1 built and merged. 51 tests. Nothing has touched a GPU yet.

---

## What Step 1 actually produced

| File | What it is |
|---|---|
| `src/cotrain/contract.py` | harness interface — `Act` / `Policy` / `Env` / `rollout` |
| `src/cotrain/nonsolvers.py` | five adversarial non-solvers |
| `tests/leaky_env.py` | two stub environments: one deliberately broken, one sound |
| `tests/test_gate.py` | the gate — 12 assertions, both directions |
| `tests/test_contract.py`, `test_nonsolvers.py`, `test_stub_envs.py` | unit layers |

`pytest -q` → 51 passed, CPU only, stdlib only, nothing imports torch.

**`tests/leaky_env.py` is a permanent red-team target. It is deliberately exploitable
and must never be hardened.** It carries one leak per R1a surface plus one per agent.
If a future session "fixes" it, the gate stops discriminating and still reports green.

---

## Five non-solvers, not four

RDI's Agent-Eval Checklist specifies four. Its own text calls the checklist
"a minimum bar", and the gate was **measurably blind** to the class RDI's own
scorecard is dominated by — observation-channel leakage (WebArena 812 tasks
~100%, OSWorld 369 tasks 73%). So there is a fifth, `Echo`.

| Agent | Predicate | Source text |
|---|---|---|
| `Null` | `score == 0`, `expect=0` | "Its score is your floor. If it's not zero, something is wrong." |
| `RandomAgent` | universal over 32 seeds | "if it significantly outperforms the null agent…" |
| `Inject` | `attack - control ≈ 1.0` | "If scores change, your judge is compromisable." |
| `Tamper` | `attack - control ≈ 5.0` | "If it scores above zero, your isolation is broken." |
| `Echo` | `== 0` on sound | not RDI's — the leakage class, added because the gate could not see it |

**Baseline is computed, not configured.** RDI gives no formal definition; the null
agent's score *is* the floor, so `Null` runs first and the others are scored against it.

---

## Constraints Step 1 places on Steps 3-5

These are not suggestions. The gate enforces them, and an environment that
violates one fails the gate rather than failing silently.

1. **`get_reward()` takes no agent-supplied argument. Ever.** Asserted in
   `_Landed.__init__` on the wrapped env, so it survives the Step 4 swap.
   This is R1 and R4 expressed in a type signature.
2. **A harness exposes `bash` XOR `ptc`, never both.** `Bash+Tool` has the lowest
   median shell calls *and* the highest failure rate in both benchmarks — adding a
   catalog alongside a shell degrades it rather than diluting it.
3. **The environment must accept at least five consecutive actions before terminating.**
   The gate pins exact accepted-action counts. Measured: three of five predicates
   reject a single-shot environment. If Step 4 needs single-shot, the gate needs
   revising alongside it — stated in `contract.py` so it is not discovered late.
4. **Observations must never carry anything that redeems for reward.** `Echo` submits
   the longest token it has seen after four look-steps. This is the only defence
   against the leakage class.
5. **No LLM judge in the reward path.** `Inject` is a standing architectural guard:
   any reward delta between its attack and control arms means a judge appeared.

---

## Corrections Step 1 forced into the research

1. **The thesis number was the wrong pair.** Corrected in `HANDOFF.md`. Gap is
   +6.8 to +22.0 pp, one arm not significant, and under cost-per-successful-task
   the ordering is already reversed in one untrained arm.
2. **The corpus carries two incompatible PTC definitions** and never flags it.
   2609.11999 is multi-turn; 2608.06370 is single-shot *inside a shell subprocess*,
   compared only against JSON tool calling with **no bash arm**. The bash-over-PTC
   ordering exists only in the multi-turn one. Do not import the single-shot
   definition on the strength of the shared name.
3. **The RECEIPT ablation is five tiers, not three**: 45% → 9% → 19% → 44% → 100%.
   `+PoC constraints` at 44% is still *below* naive self-judgment at 45%. Nothing
   clears baseline until role separation. R6: harden fully or not at all.
4. **RDI's Agent-Eval Checklist is not in the corpus.** Fetched from
   `rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/` during Step 1.
5. **Step 1 implements only R24's second clause.** R24 also asks you to run your
   strongest scaffold with a self-refinement loop against the verifier. That half
   is still owed, later, with a real model.

---

## Do Step 2 next, not Step 3

Step 3 (the verifier) is the intellectually interesting one and it is the wrong
next move. Every hour spent on it is wasted if fp16 GRPO on Qwen3/T4 turns out
unstable, and that is a genuine unknown — the corpus says you are in "a narrow
but travelled corridor" with **no public Qwen3 fp16 GRPO loss/KL curves on T4**.

Step 2 is also cheap and bounded: does it run, and is fp16 stable. Five steps.

Settled, do not re-litigate: Kaggle `NvidiaTeslaT4` (= T4 x2), **Unsloth** not raw
TRL, fp16, LoRA rank 16-32, Qwen3-0.6B, `use_vllm=False`, free tier, no local
training (dev machine is darwin/arm64).

**Verify before writing training code:** TRL raises at `grpo_trainer.py:1981-1982`
if the chat template is not prefix-preserving. Check that on Qwen3-0.6B first —
it is a hard gate, not a knob. Escape hatch if it fails: proxy the model call,
which LEGO-RL and OpenForgeRL both do.

Log from run 1: gradient norm, `mean_response_length`, token entropy, `reward_std`.
Garg's collapse signatures: lr 1e-4 → policy collapse and entropy to zero (3e-5
stable); off-policy reuse of 16 steps → collapse mid-run; removing the group-mean
baseline → gradient blowup. Stay on-policy. Set `mask_truncated_completions=True`
and `NCCL_CUMEM_ENABLE=0`.

---

## Method that repeatedly paid off

**Mutation-test your tests, not just your code.** Every review round on Step 1
found something the previous round missed — 5 surviving mutants in the contract,
4 in the agents, 1 deferred, 3 dormant guards in the gate, then a whole exploit
class. A test suite that has never been observed failing is not evidence.

`.superpowers/sdd/2026-09-23-step1-nonsolver-gate/mutate.py` is the harness.
**Fresh copy per mutation and `PYTHONDONTWRITEBYTECODE=1`, both mandatory.** A
byte-length-identical mutation restored within the same second leaves identical
mtime and size, so Python keeps executing the cached `.pyc`. `-p no:cacheprovider`
disables pytest's cache, not Python's. This produced one false verdict here.

Four defects on this branch were the same shape: **a green check running against a
stale, wrong, or dormant target.** Two were in the verification tooling itself.

---

## Known holes, stated so nothing implies more coverage than it earns

- **Token unforgeability is a proxy.** 64 fresh instances plus a length check
  collapses any *instance*-derived token; a **global** counter would pass both.
- **`_Landed` counts accepted steps without inspecting what `step()` returns.**
  An environment that accepted actions and then ignored them reads as live.
- **`Echo` is heuristic.** Longest unseen token after four looks. Misses base64,
  splits across observations, mid-word embedding, and any leak shorter than the
  prose around it.
- **A call site passing `expect=None` explicitly** weakens its own check. Inherent
  to mutation-testing a test suite; the defence is review of that file.
- **OSWorld's exploit class** (VM state manipulation + public gold files) is not
  expressible by a bash-only tamper agent. Recorded, not closed.
- **BenchJack is not publicly released** ("preparing BenchJack for public release"),
  so Step 3's plan to run it is blocked on an absent repo — the third after
  Harness-Bench and OpenForgeRL. Step 3 needs a fallback.
- **A re-review truncated mid-report** while attacking `Echo`. It had already found
  one leak shape we missed; assume more exist.

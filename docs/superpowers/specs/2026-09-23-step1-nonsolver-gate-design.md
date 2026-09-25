# Step 1 — The Non-Solver Gate

**Status:** design, awaiting approval. No implementation code written.
**Date:** 2026-09-23
**Supersedes nothing.** Implements build-sequence Step 1 from `HANDOFF.md`.

---

## 1. What this step is

Four adversarial non-solver agents plus the contract they run against, built
*before* the environment and verifier exist. The deliverable is not "four
agents" — it is a **falsification gate** that later steps cannot quietly break,
and the agent-harness contract that writing the agents forces us to commit to.

Primary source is Berkeley RDI's **Agent-Eval Checklist**
(`rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/`), fetched directly this
session. It was **not** captured in the research corpus — `research/05` carries
only an RDI blog quote, a 7-row exploit table and three incidents. The strings
"Agent-Eval Checklist", "null agent", "non-solver" and "state-tamper" appear
nowhere in `05`, `07` or `lanes/bench.md` (bench.md has "baseline" only). The
handoff's attribution was correct; the corpus just never recorded it, which is
consistent with the standing caveat that retrieval was degraded throughout the
research phase.

## 2. Corrections this step folds in

Three numbers in `HANDOFF.md` are wrong or incomplete. They are corrected here
and the handoff should be amended.

**2.1 The thesis number is the wrong pair.** `+21.8-24.5 pp` is labelled
**bash vs Tool-only** at `tokens.md:100-105`. Bash vs *PTC* is never tabulated
in the lane. Recomputed from Table 1 (`tokens.md:69-92`):

| Arm | Bash | PTC | Bash - PTC | 95% CIs |
|---|---|---|---|---|
| TAC / Opus-4.8 | 69.4 | 52.9 | +16.5 | disjoint |
| TAC / GPT-5.5 | 67.1 | 45.1 | +22.0 | disjoint |
| APEX / Opus-4.8 | 48.5 | 40.1 | +8.4 | disjoint |
| APEX / GPT-5.5 | 44.6 | 37.8 | +6.8 | **overlap 40.8-41.5** |

Gap to reverse is **+6.8 to +22.0 pp**, and in one of four arms it is not
significant. On cost, TAC/GPT-5.5 already favours PTC ($0.54 vs $0.56; 242k vs
377k tokens) — so under a cost-per-successful-task metric the ordering is
**already reversed in one untrained arm**. Consequence for Step 5: choose the
metric before the untrained run, or the result is unfalsifiable after the fact.

**2.2 The RECEIPT ablation is five tiers, not three.** Per bench.md R6:
**45% (self-judgment) -> 9% (browser-bound verdict alone) -> 19% (+isolation) ->
44% (+PoC constraints) -> 100% (+role separation).** The handoff's 3-tier
summary hides that `+PoC constraints` at 44% is still *below* naive
self-judgment at 45%. Nothing clears baseline until role separation, which
alone does 44 -> 100 (R5). R6: harden fully or not at all.

**2.3 R24 is only half-implemented by this step.** R24 verbatim asks you to
"run your own strongest scaffold with a self-refinement loop against your
verifier and try to break it" — the opposite of four trivial agents. This step
implements R24's second clause only: "then verify your hack-detector fires on a
hack you plant yourself. A green anti-cheat check that has never gone red is not
evidence." The strongest-scaffold half remains owed, later, with a real model.

## 3. The four agents and their predicates

The handoff flattens these into "any non-solver above baseline => broken".
The primary source specifies **four different tests**:

| Agent | Source text | Predicate |
|---|---|---|
| null | "takes no actions. Its score is your floor. If it's not zero, something is wrong." | `score == 0` |
| random | "takes random actions... if it significantly outperforms the null agent on some tasks, those tasks may have evaluation gaps" | `score == null_score` (see 3.1) |
| prompt-injection | "tries to influence LLM judges. If scores change, your judge is compromisable." | `delta_score == 0` |
| state-tampering | "modifies the evaluation environment instead of solving tasks. If it scores above zero, your isolation is broken." | `score == 0` |

### 3.1 Operationalizing "significantly"

The source's "significantly outperforms the null agent on some tasks" presumes
a task pool with sampling noise. Step 1 has no task pool, so the threshold
collapses to exactness: on a sound environment null scores 0, therefore random
must also score exactly 0, over N=32 seeds. Any nonzero mean is a leak, not
noise. The "significantly" machinery (and the per-task breakdown it implies)
is deferred to Step 4 when a pool exists, and is recorded here so that the
looser reading is not silently inherited later.

**Baseline is computed, not configured.** The source gives no formal definition
of baseline; the null agent's score *is* the floor. So null runs first and the
other three are scored relative to it. There is no constant to get wrong.

**The prompt-injection agent becomes an architectural guard.** Its defined
target is LLM judges, and handoff anti-pattern #5 bans an LLM judge from the
reward path outright. Rather than ship dead code, this agent asserts the
*absence* of a judge in the reward path and fails the build if one appears.
Anti-pattern #5 becomes mechanical instead of remembered.

**The state-tampering agent has five probes, not one.** `05` adds a corollary
beyond the handoff — R1a: "the exploit surface includes the runtime, not just
the application" — enumerating `$PATH`, test-framework plugin hooks, shared
containers, uninitialized memory, and **the filesystem path the verifier itself
reads from**. Three of RDI's eight exploits sit below the task layer. One probe
per surface.

## 4. The contract

Three surfaces, forced by R2 and R3. The agent touches only the first and
produces the second; the third is unreachable from inside.

- **Execution instance** — where the agent acts. Disposable.
- **Submission interface** — the agent submits an artifact. The only channel
  between instances (R2: "connected only by the submission interface").
- **Verification instance** — replays the artifact from a **fresh snapshot**
  under a restricted action vocabulary (R3), and mints the verdict token (R4).

Encoded minimally:

    Observation = str
    Act = (kind, payload)  where kind in {bash, ptc, submit, escalate}

    class Policy(Protocol):
        def act(self, obs: Observation) -> Act | None   # None = no action

    class Env(Protocol):
        def reset(self) -> Observation
        def step(self, act: Act) -> tuple[Observation, bool]
        def get_reward(self) -> float                   # no agent-supplied args

`get_reward()` taking no agent input is R1 and R4 expressed in the type
signature rather than in a review checklist.

**Action space rationale.** Four kinds is the smallest set satisfying the
corpus: `bash` must admit **composed multi-command strings** (Table 3:
composition 88-97% across every shell arm, median 4.0 commands per call on TAC
— a one-command-per-action type would be wrong on arrival); `ptc` is
"restricted Python program over the typed catalog, no shell or other action
channel"; `submit` is R3's interface; `escalate` is the escape hatch, which the
corpus shows is load-bearing (90.6% with fallback / 60.1% without / 87.5% plain
agent — removing it is worse than not compiling at all).

**Constraint: a harness exposes `bash` XOR `ptc`, never both.** Adding a
catalog alongside a shell is measurably *degrading*, not merely redundant
(`tokens.md:140`, verbatim): "Bash+Tool has the lowest median shell calls per
shell-using task combined with the highest failure rate and lowest retry rate
in both benchmarks — adding a catalog alongside the shell reduces shell use
without improving the reliability of the remaining shell calls." Lowest usage
*and* highest failure. The four kinds are the union across harnesses, not the
menu within one episode. `contract.py` enforces this rather than documenting it.

**Which PTC.** The corpus carries two incompatible PTC definitions from two
papers and never flags the difference:

| | 2609.11999 | 2608.06370 |
|---|---|---|
| Execution | unstated | native shell subprocess |
| Observation | unstated | stdout |
| Turns after execution | multi-turn (delta tool calls -4.0 / -3.0) | zero; stop middleware kills the loop |
| Compared against | bash, Bash+Tool, Bash+Synthesis, Tool-only | JSON tool calling only, **no bash arm** |

This project is built on **2609.11999's multi-turn PTC** — the bash-over-PTC
ordering exists only there. 2608.06370's PTC executes *inside a shell
subprocess*, which would partially collapse the bash/PTC axis this project
measures. Recorded so that the single-shot definition is not imported later by
accident on the strength of the shared name.

The contract already admits both without change: a single-shot harness returns
`done=True` from the first `step()`. No special case needed.

**Decision, not assumption:** `escalate` is **in** the action space.
`lanes/bench.md` is silent on in-space vs side channel. R34 wants escalation
volume per task as a defect prior, which requires it in the recorded
trajectory; and a side channel would be unreachable by the random agent, making
it untestable by this very gate.

**Deferred deliberately:** multi-format tool-call parameterization. The DCAS
-44.2 pp result and "a single-scaffold result is not a result" concern
*training* across formats. At this seam the agents emit actions directly, never
tool-call text. Step 5 concern, not Step 1.

## 5. The leaky fixture, and why it is permanent

Four agents that all score 0 against nothing prove nothing — they are
indistinguishable from four broken agents. So Step 1 ships a **deliberately
exploitable fixture** that every agent demonstrably fires on:

- **nonzero score for an empty trajectory** -> **null fires**. This is the
  FieldWorkArena class: "Validation never checks answer correctness" —
  `validate()` only checks the last message's role, and sending `{}` suffices.
  Without this leak the fixture cannot make null fire, only three of four
  agents are proven, and section 8's eight assertions are unreachable.
- reward on any action, scaled by action count -> **random fires** (beats null)
- score read from an agent-writable file (violates R1) -> **tamper fires**
- writable `$PATH` (R1a surface 1) -> **tamper fires**
- a stub judge in the reward path -> **inject fires**

The fixture is **kept permanently** as a bidirectional canary. CI asserts both
directions on every run:

- agents **FIRE** on the fixture (proves the agents have teeth)
- agents **SILENT** on the real environment (proves the environment is sound)

This is R24's second clause, R31's both-ways requirement ("the reference
solution must PASS, and a deliberately broken solution must FAIL"), and the
project's own standing rule that a check must be shown capable of failing. It
catches the specific rot where an agent degrades into a no-op and starts
passing everything — which a one-directional gate reports as green.

R31's promotion is the reason to take this seriously: OpenAI dropped SWE-bench
Verified after finding **59.4% of audited problems had flawed tests**, in the
benchmark whose entire premise was human verification. Broken ground truth is
not a tail risk.

## 6. Files

Four files. No package scaffolding, no config, no plugin registry.

    src/cotrain/contract.py     the three-surface contract + Act/Policy/Env
    src/cotrain/nonsolvers.py   the four agents, tamper carrying five probes
    tests/leaky_env.py          the deliberately exploitable fixture (permanent)
    tests/test_gate.py          four predicates, asserted both directions

Local, CPU-only, no GPU and no network. This is why the handoff calls it the
cheapest high-value work in the plan.

## 7. Non-goals

- Not the real environment (Step 4). The fixture is not a draft of it.
- Not the verifier (Step 3). R1-R6 constrain this contract but are not built here.
- Not a trainer, not RL plumbing, not TRL/Unsloth integration. Nothing in this
  step imports torch.
- Not R24's strongest-scaffold half.
- Not multi-format tool-call support (Step 5).
- Not OSWorld's exploit class: `05` records no mechanism for it and the RDI
  post attributes it to VM state manipulation plus public gold files, which a
  bash-only tamper agent cannot express. Known hole, recorded not closed.

## 8. Testing

One `tests/test_gate.py`, assert-based, no framework beyond pytest (already
installed). Eight assertions: four predicates x two directions. The fixture is
the mutant; the real environment, when it exists, is the reference.

## 9. Open items this step does not resolve

- **BenchJack is not publicly released** ("still preparing BenchJack for public
  release"), so Step 3's plan to run it is blocked on a repo that is not there —
  the same failure mode as Harness-Bench and OpenForgeRL. Step 3 needs a
  fallback plan.
- **APEX's "bash" arm is a benchmark-provided MCP code-execution server, not a
  raw shell** (`tokens.md:61`). The bash arm is not the same substrate across
  the two benchmarks, which is a confound in the gap this project is built on.
- `lanes/tokens.md` is **silent** on stdout/stderr separation, exit codes,
  truncation limits, timeouts, cwd persistence, and shell statefulness. Those
  are free choices here, and are recorded in `contract.py` as choices.
- The lane carries **no Protocol, ABC, base class or harness interface** at all
  — every Python block in it is nano-rlm implementation source (compaction
  constants, `truncate_tool_output`, prompt assembly), not an abstraction
  anyone proposed for swapping harnesses. There is no prior art to conform to,
  so the contract in section 4 is this project's own and should be treated as
  unvalidated rather than inherited.

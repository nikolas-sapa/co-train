# 08 — Gap closure (2026-09-25)

Closes the eight items left open by `07-prior-art-closure.md` and the **Known unknowns**
in `HANDOFF.md`. Read after `07`. Supersedes `07`'s novelty assessment, which was built on
four papers and an abstract-level read of one of them.

**Method.** Five parallel lanes plus direct source reading. Retrieval was still degraded:
`WebSearch` is broken in this harness (Bedrock rejects the tool type). Everything here is
`curl`/`gh`/arXiv-API/OpenAlex/HuggingFace-API or a repo clone. Four of the five lanes were
killed mid-run by a shared budget-pool exhaustion and resumed; **every load-bearing claim
below was re-verified independently against the primary artifact** (paper full text, repo,
or committed run log) rather than taken from a lane report.

**Clones read for this doc** (`~/scratch/cotrain-gap/src/`):
`verifiers` 69cc0f9 · `prime-rl` 13c82f0 · `prime-agent` e260085 · `nano-rlm` b425f2d ·
`benchjack` (Apache-2.0) · `trustworthy-env` (MIT).

---

## 0. Verdict table

| # | Item | Result | Build plan? |
|---|---|---|---|
| 1 | Novelty: harness **type** as the RL independent variable | **Not found. Thesis survives.** | **CHANGES** (framing) |
| 1b | Novelty: transfer measurement joined to harness-native training | **Scooped 4x, one of them at 2B** | **CHANGES** |
| 2 | Prime Intellect source vs `contract.py` | `contract.py`'s "no prior art" premise is false | **CHANGES** |
| 3 | prime-rl "at least one NVIDIA GPU" | Confirmed, and it is **bf16-only** — worse than the handoff says | **CHANGES** |
| 4a | Harness-Bench code | **Found.** 106 tasks real. **No licence.** | **CHANGES** |
| 4b | OpenForgeRL code | **Found** behind an `aka.ms` vanity link. **No licence.** | **CHANGES** |
| 4c | BenchJack | **Shipped**, Apache-2.0 — but it is not the tool Step 3 assumes | **CHANGES** |
| 5 | Full texts of 2607.21557 and 2605.27922 | Three corpus claims falsified | **CHANGES** |
| 6 | 2609.11999 reception + APEX confound | Zero citations; **confound refuted**; a worse one found in TAC | **CHANGES** |
| 7 | fp16 GRPO on Turing | **Unknown falsified in part** — a real Kaggle 2×T4 Qwen3-0.6B fp16 GRPO log exists | **CHANGES** |
| 8 | Counter-evidence to "shrink the action space" | **Found, strong, with an inverted U** | **CHANGES** |

Everything inert is in §9. Nothing inert appears above.

---

## 1. Novelty check

### 1.1 The one gap that survives

**No paper trains the same model against a shell harness and against a
programmatic-tool-calling harness and compares the two.** Harness type as the independent
variable, model held constant, is unoccupied.

Search coverage, so the negative is auditable — 20 arXiv API queries with hit counts:
`all:"harness-native"` (5) · `"cross-harness"` (6) · `"cross-scaffold"` (3) ·
`"harness transfer"` (9) · `"programmatic tool calling"` (2) · `"code-as-action"` (34) ·
`"CodeAct"` (21) · `"executable code actions"` (2) ·
`abs:"tool interface" AND abs:"reinforcement learning"` (4) ·
`abs:"action interface" AND abs:"reinforcement learning"` (22) ·
`abs:"code actions" AND abs:"reinforcement learning"` (1) ·
`abs:"bash" AND abs:"reinforcement learning"` (4) · `abs:"shell" AND abs:"GRPO"` (2) ·
`abs:"agent harness" AND abs:"reinforcement learning"` (15) ·
`abs:"tool calling" AND abs:"GRPO"` (60) · `abs:"action format" AND abs:"agent"` (3) ·
`abs:"unseen harness"` (1) · `abs:"held-out harness"` (2) · `abs:"tool-use interface"` (3) ·
`abs:"Is Bash All You Need"` (0). Plus 13 Google Scholar queries, 13 OpenAlex calls, 3 HF
papers lookups, and full-text greps of seven downloaded papers.
**Not closed:** Semantic Scholar 429'd on every attempt in the primary sweep; DCAS
2608.06113 is PDF-only and was not text-extracted.

**Closest near-miss, and it is close enough to steal from: arXiv 2603.01209, "Agents Learn
Their Runtime: Interpreter Persistence as Training-Time Semantics."** Exactly the design
shape this project wants, one layer down the stack: it isolates a single runtime property
as a training-time variable, holds "task instances, prompts, tools, model, and supervision
fixed", generates matched trajectories differing only in that property, fine-tunes
identical Qwen3-8B on each, and runs a **2×2 train-runtime cross-evaluation**. Differences:
the variable is interpreter statefulness *within* CodeAct rather than shell vs PTC, and it
is SFT on matched traces, not RL.

Its result is a direct warning about our Step 6: *"solution quality is statistically
indistinguishable across conditions, but token cost and stability differ substantially"* —
with a persistence-trained model hitting missing-variable errors in ~80% of episodes when
moved to a stateless runtime. **Consequence: pre-register token cost and stability as
primary outcomes alongside score, or a null on score will read as "no effect" when the real
effect was in cost and failure mode.**

### 1.2 The other half of the thesis is gone

`07` claims: *"DCAS measured cross-harness degradation without training. LEGO-RL and
OpenForgeRL trained without measuring transfer. Nobody joined the two."* **That is false,
four times over.** All four were found by one arXiv query the lanes never ran
(`all:"harness" AND all:"GRPO"`), which returns 30 hits.

**(a) OpenForgeRL itself did it — in the paper `07` cites.** §5.2, Table 5, verified in the
v3 full text. Verbatim: *"We compare two OpenForge-Claw models built from the same tasks and
the same training recipe, **differing only in which harnesses generate their rollouts**
(for both SFT distillation and RL)... **For the ZeroClaw-only model, OpenClaw and Codex are
unseen.**"* ClawEval pass@1, all from Qwen3-30B-A3B-Thinking:

| Training (SFT+RL) | ZeroClaw | OpenClaw | Codex |
|---|---|---|---|
| None (base) | 32.5 | 11.4 | 12.2 |
| ZeroClaw only | 46.0 (+13.5) | **14.7 (+3.3)** | **16.8 (+4.6)** |
| ZeroClaw+OpenClaw+Codex | 48.5 (+16.0) | 20.9 (+9.5) | 32.5 (+20.3) |

Transfer is **positive** but attenuated 3-4× out of harness. Multi-harness training is best
everywhere, *including on ZeroClaw itself* (48.5 vs 46.0). `07` read only the abstract.

**(b) arXiv 2609.04518 — "What Does Multi-Harness RL Learn? Credit Assignment and
Portability in Coding Agents"** (2026-09-03). The tightest scoop and the most useful paper
found in this entire effort. One Qwen3-8B warm start, frozen task-harness records from
Aider / OpenHands / Qwen Code / SWE-agent, **a sealed SWE-bench Verified oracle**, four
source harnesses **plus a minimal harness held out of training**, 24,000 evaluations.

- **"The evaluation harness is the dominant variable: across 24,000 sealed evaluations it
  moves the mean solve rate from 2.14% to 9.27%, a factor of 4.3, where the training recipe
  moves it by 1.16."**
- The GRPO grouping rule (Cross vs Within) is **not** significant: +0.25 pp,
  95% CI [−0.48, +1.02]; seed range 0.42-0.45 pp exceeds the effect.
- **"Cross-harness credit yields configuration adaptation and no more portable capability
  than within-harness credit."**
- **"Multi-harness RL reports should state the grouping boundary and test under an unseen
  harness."**

**(c) arXiv 2609.13739 — HarnessBandit, "Joint Learnability-Transferability Scheduling."**
Joins the two halves by name. Qwen3.5-**2B** across six harnesses on ClawGym, evaluated on
ClawEval with a **held-out harness**. After each GRPO update it measures *learnability*
(mean absolute advantage on the batch) and *transferability* (cosine between a
low-dimensional gradient sketch of the current harness and EMAs of the others). This is at
our order of magnitude, not 30B.

**(d) arXiv 2609.22247 — CHART, harness-rotation curriculum.** DCAS's overfitting plus a
measured mitigation: *"training under a fixed harness makes the behavior harness-local,
overfit to that harness's surface form."* Static harness augmentation **fails** — "a small
harness pool saturates that [reward] gap early, while a large pool dilutes the per-harness
signal too thinly." Rotating curriculum reaches parallel search on **89% of held-out turns
vs at most 5% for static pools**, and transfers to a new task and search environment
(+5.6 pp pass@1).

Two more the corpus missed, both the same proxy pattern: **ClawGym II (2608.16798)** —
black-box RL through harnesses, serving proxy at the model boundary, prefix-tree trajectory
reconstruction, mix-harness training, Qwen3-30A3B +9.98 (OpenClaw) / +14.81 (Claude Code)
over 200-400 stable steps; and **Polar (2605.24220)** — proxy + token-faithful trajectory
reconstruction, Qwen3.5-4B on SWE-bench Verified: **+22.6 Codex, +4.8 Claude Code, +0.6
Qwen Code, +6.2 Pi**. That 22.6-vs-0.6 spread is "some harnesses are substantially harder
to learn" measured independently, **two months before OpenForgeRL**.

### 1.3 What the thesis is now

Not "does harness shape matter under training" (answered), not "does harness-native
training transfer" (answered, four times, positively but attenuated). It is:

> **Does the bash-over-PTC ordering — the one harness axis with a large measured untrained
> gap — survive training, at a scale nobody has tried?**

And 2609.04518 supplies the null hypothesis to beat: the effect will be **configuration
adaptation, not capability**, and the *evaluation* harness will dominate whatever the
training does. Plan for that result rather than being surprised by it.

**Also: this area is now ~10 papers in 5 months, three of them in September 2026 alone.**
`07`'s "risk worth naming" has materialised. Two things still favour going ahead: the
shell-vs-PTC axis is genuinely untouched, and a negative result is cheap and publishable.

---

## 2. Prime Intellect source vs our contract

### 2.1 `contract.py`'s stated premise is false

`src/cotrain/contract.py` opens with a `ponytail:` note: *"there is no prior art to conform
to. research/lanes/tokens.md carries no Protocol, ABC, base class or harness interface
anywhere."* The second sentence is true. The conclusion does not follow.

`verifiers` v1 — MIT, pure Python, `>=3.11,<3.15`, **no torch, no platform gate** — ships
all of it as library code:

| Ours | Theirs | Where |
|---|---|---|
| `Env` Protocol (`reset`/`step`/`get_reward`) | `Env(ABC, Generic[ConfigT])` — taskset + agents + `run(task, agents)` + `finalize` | `verifiers/v1/env.py:76` |
| `HarnessKind = Literal["bash","ptc"]` | `Harness(ABC, Generic[ConfigT])` + **13 installed harnesses** | `verifiers/v1/harness.py:34` |
| `Policy` Protocol (`act(obs) -> Act`) | `Client(ABC).get_response(dialect, body, sampling, …) -> Response` | `verifiers/v1/clients/client.py:30` |
| `Act(kind, payload)` | *no framework action type* — each harness owns its own | — |
| `rollout(env, policy, max_steps)` | `Rollout.open/step/abort/close` | `verifiers/v1/rollout.py:55` |
| `get_reward()`, no agent input (R1/R4) | `@vf.reward` on the `Task`, args injected by name (`task`, `trace`, `runtime`) | `verifiers/v1/utils/decorators.py:119` |

The corpus missed it because the lane that should have caught it (`tokens.md`) quotes
nano-rlm *implementation* source, and nano-rlm really has no such protocol — its only
`Protocol` is `BuiltinTool` (`src/rlm/tools/base.py:34`: `name`, `schema()`,
`execute(args, context) -> ToolOutcome`), a tool interface, not an Env or a Policy. The
abstraction lives one layer up, in `verifiers`, which no lane read.

### 2.2 Action representation and tool results, in prime-agent

- **Action = a content block in the assistant message.**
  `AssistantMessage.content: (TextContent | ThinkingContent | ToolCall)[]`
  (`packages/ai/src/types.ts:212-214`), with
  `ToolCall { type: "toolCall"; id; name; arguments: Record<string, any>; thoughtSignature? }`
  (`:181-187`). `AgentToolCall` is literally
  `Extract<AssistantMessage["content"][number], { type: "toolCall" }>`
  (`packages/agent/src/types.ts:40`). There is no `Act`; the action is a typed member of the
  transcript.
- **Tool result = its own message role, not OpenAI's.**
  `ToolResultMessage { role: "toolResult"; toolCallId; toolName; content: (TextContent | ImageContent)[] }`
  (`packages/ai/src/types.ts:228-232`). Tools return
  `AgentToolResult<T> { content; details: T; terminate? }`
  (`packages/agent/src/types.ts:332`) — **two channels**: `content` goes to the model,
  `details` to logs/UI. Ours has one (`Observation = str`).
- **Deny gate:** `beforeToolCall -> { block?: true, reason? }` blocks execution and the loop
  emits an error tool result in its place; `afterToolCall` can replace
  `content`/`details`/`isError`/`terminate` field-by-field (`types.ts:48-74`).

### 2.3 The non-LLM seam exists in both stacks, and is load-bearing in their own tests

- **prime-agent, in-process:** `Agent({ streamFn })`, where
  `StreamFn = (...args: Parameters<typeof streamSimple>) => ReturnType<typeof streamSimple>`
  (`packages/agent/src/types.ts:25`), defaulted at `agent.ts:245`
  (`options.streamFn ?? streamSimple`). **Their own suite drives the entire agent loop with
  a `MockAssistantStream` instead of a model** (`packages/agent/test/agent.test.ts:96`,
  `:149`, `:212`). A non-LLM policy supplies `streamFn` and returns synthetic `toolCall`
  blocks. `packages/agent/src/proxy.ts` is the same idea over the wire, with an exhaustive
  serialized-options map so "proxy transport cannot silently drop what direct transport
  sends."
- **verifiers, over the wire:** `POST /v1/chat/completions` on a localhost server routes
  each call to a `Client` (`interception/server.py:4`). `Harness.launch`'s contract is
  verbatim: *"The interception is the contract, not the process: a harness may run its loop
  in-process instead of launching a program, as long as every model call goes through
  `endpoint` + `secret`"* (`harness.py:284-312`).
- **nano-rlm:** no seam of its own. `make_client()` returns a plain `AsyncOpenAI` with a
  configurable `base_url` (`src/rlm/client.py:42-57`). Point it at your own server.

### 2.4 Where we diverge, and whether it matters

**Divergence 1 — their seam is the model call; ours is the action. MATTERS.**
Both Prime Intellect stacks put the policy seam at *messages in, completion out*. Our
`Policy.act(obs) -> Act` sits one level lower. Consequence: **our non-solvers cannot drive
a real harness**, because a real harness parses actions out of a completion in its own wire
dialect. Step 1's gate therefore tests our own stub harnesses, which is the right first
thing (it gates the *verifier*, not the harness) — but the spec should say so plainly:
**the gate's coverage stops at the stub boundary.** Reaching `bash` or `claude_code` means
emitting `tool_calls` JSON, i.e. becoming a `Client`.

**Divergence 2 — we name actions in the framework; they do not. MATTERS, in our favour.**
`ALLOWED: dict[HarnessKind, frozenset[ActKind]]` + `permits()` make bash XOR ptc a
type-level invariant. verifiers has no framework action type; the equivalent is per-harness
config — `BashHarnessConfig.edit: bool` ("set `--env.agent.harness.edit false` for a
bash-only agent", `harnesses/bash/harness.py:41`) and
`RLM builtin_tools: list[Literal["bash","edit","fetch","ipython"]]`
(`harnesses/rlm/harness.py:30,82`). Theirs is configurable, ours is checkable. Keep ours.
But record that XOR is **our reading** of `tokens.md:140`, not a published rule.

**Divergence 3 — reward signature. MATTERS; we are stricter than the reference.**
Ours: `get_reward() -> float`, no arguments, always. Theirs:
`@vf.reward async def rewarded(self, trace: vf.Trace, runtime: vf.Runtime) -> float` — the
reward function is handed the agent's own trace. Their shipped example
`environments/bash_interception/bash_interception/taskset.py` then scores
`await runtime.run(["test","-e",sentinel])`, i.e. it reads a path the agent's own bash could
have written (the reward is that it was *not* written). **R1 is our rule, not a Prime
Intellect one, and their reference environment would fail it as written.** No change to our
design — but do not import theirs uncritically.

**Non-divergence worth copying.** `Slot = tuple[str, str, str]` —
*"(base_url, model_secret, state_secret): model inference and task state deliberately use
separate capabilities"* (`interception/base.py:24-30`). That is R5 role separation as two
capabilities rather than a type signature. Stronger than ours. Take it at Step 3.

### 2.5 Three things in verifiers that change the build plan

**(a) Both arms of our axis already exist as installed harnesses.**
`verifiers/v1/harnesses/` ships `bash`, `browser_use`, `claude_code`, `codex`,
`hermes_agent`, `kimi_code`, `mini_swe_agent`, `null`, `openclaw`, `pi`, `prime_agent`,
`rlm`, `terminus_2`.
- **bash arm** = `bash`, with `edit: false` for shell-only.
- **PTC arm** = `rlm` with `builtin_tools=["ipython"]`. Module docstring: *"RLM over ACP,
  with MCP tools exposed as pre-imported IPython skills"* (`harnesses/rlm/harness.py:1`) —
  a program over a typed catalog with no shell channel. That is **2609.11999's PTC
  definition**, not 2608.06370's.
- **Tool-only baseline** = `null` (`EXECUTES_CODE = False`) plus MCP tools.
Step 5 is largely already built, by the lab whose harness the corpus was planning to fork.

**(b) Harness choice is one CLI flag.** prime-rl's eval entrypoint documents
`--env.agent.harness.id bash` (`src/prime_rl/entrypoints/eval.py:30`) and
`HarnessConfig.id` defaults to `"bash"` (`configs/harness.py:27`). Train under one, evaluate
under another. The *mechanism* for cross-harness transfer is shipped; only the shell-vs-PTC
*measurement* is unpublished.

**(c) The tool gate we were going to build is already there.**
`SUPPORTS_TOOL_INTERCEPTION` (`harness.py:38`) hands the rollout a `/tool` gate so a hook
can deny a call and the model sees the policy's result in its place.
`environments/bash_interception` demonstrates both outcomes: `@vf.stop` blocks a proposed
command *before the harness sees it*, `@vf.intercept` substitutes a synthetic tool result
and lets the rollout continue. That is Step 4's escalation channel plus part of Step 1's
tamper surface, with a worked example.

### 2.6 Should we conform to verifiers instead of our own contract?

Partly, and not yet.

- **Keep `contract.py`.** 120 lines, encodes R1-R4 as types, and 51 Step-1 tests are pinned
  to it. Conforming now means rewriting the gate against an async, config-driven,
  container-oriented framework to gain nothing this step needs.
- **Delete the false premise.** The docstring claiming no prior art must name `verifiers` v1
  and state why we still diverge (§2.4). Leaving it is how a future session re-derives a
  worse copy of a shipped abstraction.
- **Adopt at Step 5.** Implement a `verifiers` `Client` whose `get_response` is our policy,
  and let `bash` and `rlm` be the two harnesses. `Act` then becomes what we *parse from* a
  completion for telemetry, not what the framework executes.
- **Copy two things on paper now:** the model/state secret split, and `AgentToolResult`'s
  two-channel result — the latter is the cheap fix to `Observation = str` when hack
  telemetry lands at Step 4.

---

## 3. prime-rl's GPU constraint — confirmed, and harder than the handoff says

**The claim, verbatim** (`README.md:72`, in-repo source, not the docs site):

> "Currently, you **need at least one NVIDIA GPU to use prime-rl**."

**Three facts the handoff does not carry:**

1. **T4 is not merely untested — the trainer has no fp16 at all.**
   `DTYPE_MAP = {"bfloat16": torch.bfloat16, "float32": torch.float32}`
   (`src/prime_rl/trainer/model.py:98-101`) — **float16 is not a member** — and FSDP is
   `MixedPrecisionPolicy(param_dtype=torch.bfloat16, reduce_dtype=DTYPE_MAP[config.reduce_dtype])`
   (`model.py:471`). `reduce_dtype` is configurable; `param_dtype` is not. LoRA
   (`trainer/lora.py:40`) and weight transfer (`worker/weight_transfer.py:39`) also hardcode
   bf16. T4 is compute capability 7.5 with no bf16, so **prime-rl cannot train on a T4 at
   all** — not "slowly", not at all.
2. **The tested floor is Ampere, and the pinned wheels have no sm_75 cubin.**
   `README.md:68`: *"We develop and test on NVIDIA RTX 3090/4090/5090, A100, H100, H200, and
   B200."* No Turing. The `flash-attn` extra's own comment says the wheels *"carry sm_80 /
   sm_90 / sm_100 / sm_120 cubins"* (`pyproject.toml:77-79`), and `resolve_auto_attn` falls
   through to `flash_attention_2` for anything below SM90 (`model.py:913-928`) — a backend
   with no cubin for the card.
3. **Every GPU dependency is `sys_platform == 'linux'`** (`pyproject.toml:54-74`: torch,
   vllm, flash-attn, torchtitan, mamba-ssm, nvidia-ml-py…). On darwin/arm64 the extras
   resolve to nothing. "No local training" is enforced by dependency markers, not convention.

**Consequence.** The handoff's escape hatch — "migrate to TRL/prime-rl when renting proper
hardware" — needs "proper" pinned: **Ampere or newer, Linux.** A rented T4 does not unlock
prime-rl; it is the same dead end as Kaggle. The Unsloth-on-T4 path and the prime-rl path
are **disjoint, not two rungs of one ladder**. What does carry across both is `verifiers`
(pure Python, MIT, runs on darwin/arm64), so environment, harness and verifier work is done
once even though the trainer is not portable.

---

## 4. The three repos the corpus could not locate — all three found

### 4a. Harness-Bench — `github.com/Qihoo360/harness-bench`

112★, Python, pushed 2026-06-23, 5.2 MB, not archived. The URL is in **footnote 1** of the
paper, not the arXiv metadata: *"Our code and data are available at
https://github.com/Qihoo360/harness-bench. Additional resources… at
http://www.harness-bench.ai/"* (both HTTP 200).

**The 106 tasks are really there.** Git tree (1507 entries, not truncated): exactly 106
directories under `tasks/`, `001-file` … `106-release-approval-gate-plan`, and the counts
match the paper's category table (22 SWE / 14 Data-BI / 15 Workspace / 13 Knowledge /
12 Office / 12 Vertical / 11 Long-running / 7 SRE = 106). Per-task files: `task.yaml` ×106,
`oracle_grade.py` ×106, `prompt.txt` ×99, `ground_truth.json` ×90, **`llm_rubric.py` ×86**,
`hooks.py` ×28, `verify_oracle.py` ×6, plus 812 real fixture files (`.pdf`, `.docx`, `.csv`,
`.jpg`, `.png`, prompt-injection ticket corpora). It also ships 12 harness adapters
(`codex`, `openclaw`, `zeroclaw`, `nullclaw`, `nanoclaw`, `nanobot`, `hermes`, `moltis`,
`picoclaw`, `fairyclaw`, `generic_cli`, `demo`), a runner, `usage_proxy.py`,
`extract_proxy_trace.py`, and the grading stack.

**Licence: NONE.** GitHub API `license: null`; `LICENSE`, `LICENSE.txt`, `LICENCE`,
`COPYING`, `NOTICE` all 404; no licence section in the (Chinese) README. **Public but
all-rights-reserved by default.** The *paper* is CC BY 4.0; the code and tasks are not.

**Build plan:** read it, do not vendor it. It is the reference design for oracle grading and
proxy-based usage capture, and 86 of 106 tasks carry an LLM rubric, which our rule #5 bars
from a reward anyway (§5.2). Filing an issue asking for a licence is a cheap high-value move.

### 4b. OpenForgeRL — `github.com/MSR-Orchard/OpenForge-RL`

17★, Python, **default branch `master`** (so `trees/main` 404s — probably what stalled the
earlier attempt), created 2026-08-03, pushed 2026-08-07, 11.8 MB. The v3 "added github
link" is not a `github.com` string at all — it is the Microsoft vanity link
**`https://aka.ms/OpenForge-RL`**, verified `301 → https://github.com/MSR-Orchard/OpenForge-RL`.

**The recording proxy is real and is the substantial part.**
`openforgerl/proxy/vllm_proxy.py` is **58 KB** (plus a 43-byte re-export shim and
`tests/test_proxy_server.py`), with `recorded_io_pairs`, `_record_streaming_io_pair()`,
`"finish the session and return the recorded io_pairs"`, and
`OPFORGE_VLLM_PROXY_RECORD_ORIGINAL_REQUEST`. README: *"the harness calls what looks like a
normal OpenAI-compatible endpoint; the proxy serves the request and records every
prompt/response pair. This is what makes an unmodified harness trainable."*

**Licence: NONE** (API `license: null`, no root LICENSE; the only LICENSE files are vendored
third-party ones). Same posture as Harness-Bench.

**Build plan:** the proxy pattern is now shipped code from three independent groups
(OpenForgeRL, Polar, ClawGym II) plus two libraries (`verifiers` interception,
prime-agent `proxy.ts`). Treat "proxy the model call" as the settled, boring choice.

### 4c. BenchJack — shipped, but it is not what Step 3 assumes

`github.com/benchjack/benchjack` — **exists**, **Apache-2.0**, 46★, Python, created
2026-04-15, pushed 2026-05-25, 11 open issues, topics include `reward-hacking` and
`vulnerability-scanner`. Org has 1 public repo. Not on PyPI (404) or npm (404). Paper:
**arXiv 2605.12673**, *"Do Androids Dream of Breaking the Game? Systematically Auditing AI
Agent Benchmarks with BenchJack"* (Wang, Li, Mang, Cheung, Sen, Song; submitted 2026-05-12).

**But read what it is.** BenchJack is a **static + LLM source-code audit pipeline that scans
a benchmark repository** — Semgrep, Bandit, Hadolint, a Docker analyser, a trust mapper, plus
"AI-powered deep inspection" that **invokes the `claude` or `codex` CLI as a subprocess**
(`server/ai_runner.py`; README: *"BenchJack invokes `claude --print`, which requires an
active session"*). It emits V1-V8 findings and generates proof-of-concept exploit code, and
streams to a web dashboard. macOS/Linux, Python 3.11-3.13, deps `fastapi`, `uvicorn`,
`semgrep`, `bandit`. It is **not** a runtime attacker that plays your environment.

`HANDOFF.md` Step 3 says *"Then run BenchJack against it."* That works — it will scan our
repo — but the sentence should say what it buys: **a source audit against the V1-V8 taxonomy,
not an adversarial rollout.**

**The four toy agents are not in BenchJack.** Grepping the repo for
null/random/state-tampering/prompt-injection agents returns only a Semgrep rules file. They
come from the **RDI blog's Agent-Eval Checklist**, verbatim from the primary source
(`moogician.github.io/blog/2026/trustworthy-benchmarks-cont/`, HTTP 200, 2026-04-08, Wang /
Mang / Cheung / Sen / Song):

> "Run a **null agent** that takes no actions. Its score is your floor. If it's not zero,
> something is wrong. Run a **random agent** that takes random actions. If it significantly
> outperforms the null agent on some tasks, those tasks may have evaluation gaps. Run a
> **prompt injection agent** that tries to influence LLM judges. If scores change, your
> judge is compromisable. Run a **state-tampering agent** that modifies the evaluation
> environment instead of solving tasks. If it scores above zero, your isolation is broken."

**This is the source `HANDOFF.md` cites and the corpus never contained** — correction (c)
confirmed. Note the four predicates are **four different tests**, not one uniform
"above baseline": null → *exactly zero*; random → *not significantly above null*;
injection → *scores do not change*; tampering → *zero*. Our Step-1 gate already implements
"four predicates × two directions" with per-predicate semantics
(`tests/test_gate.py:1`), so it matches the primary source. Good.

Also note the blog still reads *"We're preparing BenchJack for public release"* — it was
written before the repo shipped. **The corpus's "not located" was a stale-blog artifact, not
a missing artifact.** Second tool in the same family, also real: **`moogician/trustworthy-env`**
(MIT, 62★) — dual LLM + **Z3 formal** detector, 8-stage audit, exploit generator,
`poc_verifier.py` (52 KB), and *runtime* verification via
`detect.py audit --run-cmd "python3 evaluator.py"`. That is closer to "attack my verifier"
than BenchJack is, and it is MIT rather than unlicensed.

**Build plan:** Step 3 keeps its BenchJack step, re-scoped to "source audit". Add
`trustworthy-env --run-cmd` for the runtime half. The four toy agents stay ours — they are a
checklist item, not a shipped tool, and we already built them.

---

## 5. Full texts — three corpus claims falsified

### 5.1 OpenForgeRL (2607.21557 v3)

- **Cross-harness transfer exists.** §5.2 / Table 5 — see §1.2(a). `07`'s "no transfer test"
  is wrong.
- **"Some harnesses are substantially harder to learn" is a controlled result**, model fixed
  at Qwen3-30B-A3B-Thinking. §5.1 Table 4, ClawEval pass@1: base 26.1 (ReACT) / 32.5
  (ZeroClaw) / 11.4 (OpenClaw) / 12.2 (Codex); SFT 36.2 / 44.5 / 16.7 / 21.1. Untrained
  spread is ~3×. Verbatim: *"the harnesses that support adding custom tools directly (ReACT
  and ZeroClaw) reach the highest performance"* and *"SFT+RL bring large gains on every
  harness except OpenClaw, which only has moderate gains while consuming far longer prompts
  and contexts than the others."*
- **No arm is a plain shell.** All four are tool-calling harnesses. The thesis is not scooped
  on the axis — but see the next point.
- **§5.3 is the closest published result to our actual question, and it points the right
  way.** Verbatim: RL *"reduces generic shell calls from 22.6% to 13.9% of all tool calls
  and redistributes them toward dedicated service tools"*, interpreted as *"RL teaches the
  model to reach for the right specialized tool instead of falling back on a
  general-purpose shell."* Performance rose at the same time. **That is behavioural evidence
  that training moves an agent off bash and onto typed tools — the direction our thesis
  predicts — measured, but as a behaviour share, never as a bash-arm-vs-PTC-arm score.**
  Add shell-call share to the run-1 health signals; it is a cheap, published, comparable
  number.
- **Mechanism** (§3.2): proxy collects terminal reward and prompt-response pairs, then
  reconstructs `τ = (s^H_t, a_t, r_t)` with `r_t = γ^(T−t) · r_T`, **γ = 1.0** — i.e. flat
  credit over every model call in the rollout. Turn caps are rejected as unreliable
  (*"some harnesses (e.g. Codex) do not expose a turn limit, and a 'turn' is defined
  inconsistently across harnesses"*) in favour of a **wall-clock timeout per rollout**.
  Errored rollouts are **discarded entirely**, DAPO-style, because *"a partial rollout can
  inject misleading training signal (e.g. a correct prefix that receives a negative
  reward)"* — better credit assignment for partials is left to future work.
- **Scale floor.** Claw: 30B-A3B MoE, policy training on **one node of 8× B200**, rollout
  pods capped at 2 CPU / 2 GB on Azure D128ads v5, veRL, batch 8 × group 8. GUI: 8B. **No
  result below 8B.** Nothing here says 0.6-1.7B works; nothing says it fails.
- Reward is *"typically task success"* — terminal, environment-supplied, no LLM judge in the
  reward path.

### 5.2 Harness-Bench (2605.27922)

- **It is not a second measurement of the bash-vs-PTC gap. Clean negative:** the full text
  contains **zero** occurrences of "shell", "bash", "programmatic", or "code execution". The
  six configurable harnesses are OpenClaw, ZeroClaw, Hermes, Moltis, NullClaw, NanoBot —
  all "long-running runtime" or "lightweight runtime" agent servers — plus Codex as a
  model-bound reference point. **2609.11999 remains the only measurement of our axis, and it
  is still unreplicated and first-party.**
- **"106 oracle-checkable tasks" is overstated.** The inclusion criterion is verbatim
  *"Oracle-checkability, meaning success can be verified by **deterministic checks or a
  specified rubric**"* (§3.2), and the aggregate is
  `TaskScore = Security × Completion × Process` with
  `Process = (Robustness + ToolUse + Consistency)/3` scored by **LLM process rubrics**
  (§3.4). Consistent with `llm_rubric.py` in 86 of 106 task dirs. **An LLM judge is in the
  aggregate score**, which our rule #5 bars from a reward. Usable subset:
  `Security × Completion` only — and they do report every component separately.
- **Two design elements worth stealing.** (i) `Security ∈ {0,1}` as a *multiplicative* gate
  for permission/secret violations — a hack makes the whole task score zero, which is
  stronger than a penalty term. (ii) §3.3 verbatim: *"Reference artifacts, hidden answers,
  and evaluator scripts are **not exposed to the agent during execution**"*, with a
  setup → execution → judge pipeline and four evidence streams (final workspace state,
  execution trace, usage statistics, validator outputs). That is R2 as a pipeline shape.
- **The most useful finding for a small-model project** (§4.3): *"stronger model backends
  tend to achieve higher mean scores while exhibiting **lower cross-harness variance**…
  weaker or less robust backends show larger variance across harnesses."* **Harness effects
  are largest at low capability.** At 0.6-1.7B we should expect a *bigger* harness effect
  than these papers report at frontier scale — which is good for signal, and is an argument
  for the small-scale experiment rather than against it.
- Limitations, verbatim: *"focuses on controlled, sandboxed offline workflows, improving
  reproducibility at the cost of coverage of live services… evaluates complete harness
  configurations, so observed differences should be interpreted as configuration-level
  effects… some process-level scores rely on rubric-based or LLM-assisted assessment."*

---

## 6. Has 2609.11999 been reproduced or critiqued? And the APEX confound

**Nobody has cited it.** Zero, by five independent routes: OpenAlex `cited_by_count = 0` on
W7212495599 and `filter=cites:W7212495599` → 0; Google Scholar returns the paper with no
"Cited by" link at all; HF papers shows no citing works; arXiv full-text grep across seven
downloaded related papers finds no reference; Semantic Scholar 429'd. The paper is 15 days
old. **The project's load-bearing measurement is unreplicated, uncriticised, and
first-party (Microsoft evaluating interfaces for its own Copilot line). That risk is
unchanged and remains the single biggest premise risk.**

**The APEX confound is refuted by the paper's own appendix.** `tokens.md:61` is right that
APEX's Bash arm is the benchmark's MCP code-execution server, but the inference is wrong.
§4.2: *"We retain its 20 typed application tools and use its code-execution server as
**Bash**: a guardrailed Unix shell over the workspace (Appendix B.2)."* Appendix B.2 is
decisive: *"The APEX-Agents snapshot combines the application servers in Table 8 with a
**Unix `sh -c` server**. Shell execution enforces filesystem restrictions,
environment-variable scrubbing, and execution limits **rather than a Python-only
restriction**."* MCP is the transport; the semantics are arbitrary `sh -c`. The paper
pre-empts exactly this suspicion, because its PTC arm is defined (§3) as a restricted
program over the catalog with **no shell or other action channel**. **APEX bash ≠ PTC. Not a
PTC-vs-PTC comparison in disguise.**

**But a worse construct-validity problem sits in the other benchmark.** TAC's bash arm has
no MCP layer at all — the authors built their own 60-tool typed catalog, and Appendix B.1
admits verbatim: *"The typed catalog covers task-relevant service APIs and workspace
operations, **not every shell-accessible endpoint**."* So TAC's Tool-only and PTC arms are
handicapped by an author-built, self-declared-incomplete catalog, while APEX's 20 typed
tools are benchmark-native. **The larger TAC delta (+16.5 / +22.0 pp) is the one to
discount; the smaller APEX delta (+8.4 / +6.8 pp) is the better-controlled number.** Plan
Step 5 against the conservative end of the range, and treat +6.8 pp as the gap to reverse.

**One datum to take into the build:** TAC tool-call **success rate** is PTC **65.2%** vs
Bash **92.1%** (Table 2). A third of PTC calls simply fail on an untrained model. That is
the headroom training is supposed to claim, and it is a far better leading indicator than
task score — add it to the run-1 metrics.

---

## 7. fp16 GRPO on Turing — the standing unknown is falsified in part

`HANDOFF.md`: *"no public log shows Qwen3 GRPO fp16 loss/KL curves on T4."* **One exists for
loss/grad/reward.** Verified by downloading the artifacts, not from a report:

**`huggingface.co/rkkzone/qwen3-0.6b-math-l45-grpo-adapter`** (created 2026-05-17), which
ships `training_logs.json` (114 KB) and `hardware_profile.json`:

- **Hardware:** `world_size=2`, both ranks `"device_name": "Tesla T4"`, `runtime_seconds`
  21161.9 (**5.9 h**), `peak_vram_allocated_gb` **2.40** per rank, paths under
  `/kaggle/working` → **Kaggle, 2× T4**.
- **Precision, decoded from `training_args.bin`:** `fp16 = True`, `bf16 = False`,
  `fp16_full_eval = False`, `fp16_opt_level = "O1"`, **`use_vllm = False`**.
- **Model:** Qwen3-0.6B (a QLoRA-SFT'd, fp16-merged base), GRPO, LoRA adapter.
- **The run:** 84 logged rows covering steps 1→314, one full epoch.
  **Zero non-finite values anywhere** across `loss`, `grad_norm`, `reward`,
  `learning_rate`, `completions/mean_length`. `grad_norm` max **4.52**. `reward` 0 → 0.409 →
  0.330. `completions/mean_length` 394 → 434, stable. `loss ≡ 0` because `beta=0` and
  `num_iterations=1`.
- **Why reward went flat is not numerics:** `frac_reward_zero_std` runs **0.56-1.00**, so
  most groups have zero advantage — **reward-signal starvation**, the exact failure our R33
  dispersion screening is meant to catch. A sibling run from the same author sets
  `beta=0.04`, completed, and merged to `zannvznn/qwen3-0.6b-math-l45-grpo-merged-fp16-v3`
  (`merge_metadata.json`, `torch_dtype: float16`) — **so the KL term was on and the run
  finished** — but published no log.

**This is our Step-2 configuration almost exactly** (Kaggle T4×2, fp16, Qwen3-0.6B,
`use_vllm=False`) and it ran clean for 5.9 h at 2.4 GB. Restate the unknown precisely:
**no public *KL* curve exists; loss/grad/reward curves now do.**

**The mechanism, from source — and a correction to the corpus.** Unsloth's
`_FORCE_FLOAT32_FALLBACK` (`unsloth/models/loader.py:118-127`) is
`gemma3`, `gemma3text`, `gemma3n`, `gemma4`, `glm4_moe`, `gpt_oss`, **`qwen3_5`**,
**`qwen3_moe`** — with verbatim comments *"Qwen3.5 GDN layers produce NaN grad norms in
float16 training"* and *"Qwen3-MoE (Qwen3-30B-A3B): float16 NaNs grad norms in the
backward"*. **Dense `qwen3` is not on the list** (model_type `"qwen3"` dispatches to
`FastQwen3Model`, `loader.py:943,951`).

So the corpus's claim — "Gemma-3's fp16 failure is architecture-specific and does not apply
to Qwen3" — is **true for dense Qwen3-0.6B/1.7B and false for Qwen3.5 and Qwen3-MoE**, which
sit on the same forced-float32 list for the same reason. **Model choice is now load-bearing:
do not "upgrade" to Qwen3.5-0.8B.** That is precisely what crashed on Kaggle T4 in open
issue #7506, and open issue #11533 (2026-09-22) explains why: for a FORCE_FLOAT32 arch the
selection branch is entered *either* when fp16 was asked for *or when the device has no
bf16*, and then picks bf16 unconditionally — *"on the second of those two conditions that
picks the one dtype the device cannot run"* — raising
`expected mat1 and mat2 to have the same dtype, but got: BFloat16 != Half`.

**There is an architectural reason dense Qwen3 is safe, and it checks out in source.**
Qwen3 has **QK-norm**: `self.q_norm = Qwen3RMSNorm(self.head_dim, …)` and `self.k_norm`,
applied pre-RoPE (`transformers/models/qwen3/modeling_qwen3.py:237-238, 252-253`).
`modeling_qwen2.py` has **zero** `q_norm` occurrences — verified. And the Qwen2 fp16 failure
mode was exactly attention-logit overflow (QwenLM/Qwen3 #910: *"Q @ K^T 就会出现大值，它超出了
fp16 表示范围，于是变成了 inf/-inf，后面经过 softmax 就变成了 nan"*). QK-norm bounds the quantity
that used to overflow. That is a real mechanism, not an absence of evidence.

**Unsloth's fp16-on-Turing path is by design, not a workaround.** `models/rl.py`'s
mixed-precision block, injected into the generated `UnslothGRPOTrainer`:
`use_bf16_amp = (not float16) and _bf16_supported(); args.fp16 = not use_bf16_amp;
ACCELERATE_MIXED_PRECISION = 'fp16'`, with comments *"Device-aware bf16 check (CUDA/XPU/HIP),
so V100/T4 never pick bf16"* and *"fp16 autocast over fp32 master weights is the normal
V100/T4 recipe (#4082)"*. `SUPPORTS_BFLOAT16 = get_device_capability()[0] >= 8`, and Unsloth
**monkeypatches `torch.cuda.is_bf16_supported`** to return that — which closes a real
loophole, because `is_bf16_supported(including_emulation=True)` returns **True on T4/V100**
(it only checks that a bf16 tensor can be allocated), so transformers' own bf16 guard never
fires. There are dedicated regression tests: `tests/test_grpo_autocast_disabled.py` and
`tests/python/test_v100_fullft_precision.py`, the latter executing *"the REAL template block
extracted from rl.py source"* against mocked inputs on the no-bf16 path.

**Raw TRL — one real hazard, and it is version-scoped.** The handoff's PR is
**TRL #2738, merged 2025-02-04** — body verbatim *"Adds datatype argument for vllm in grpo
Trainer/Config, T4 in collab need fp16 and vllm defaults to bf16 :)"*. On TRL **`main`**,
`grpo_trainer.py:509-513` casts **unconditionally** for quantized models:
`if _is_quantized_model: for param in model.parameters(): if param.requires_grad:
param.data = param.data.to(torch.bfloat16)` (a QLoRA recommendation, with
`autocast_adapter_dtype` unavailable for quantized models). With `fp16=True` the GradScaler
then hits `NotImplementedError: "_amp_foreach_non_finite_check_and_unscale_cuda" not
implemented for 'BFloat16'` — seen in the wild on a Colab T4 (unsloth #3992, closed
"should be fixed now" 2026-06-18).

**It does not reach the Step 2 stack, and I checked rather than assumed:**
`param.data.to(torch.bfloat16)` and `_is_quantized_model` both have **zero occurrences at
tags v0.24.0 and v0.25.0** (1,843 and 1,972 lines) and appear only on `main` (3,463 lines).
Unsloth pins `trl<=0.24.0` (`step2/README.md`), so **TRL main + 4-bit + fp16 is broken by
construction, and that combination is exactly the one `step2/README.md` already rules out**
on independent grounds. Two findings converging on the same conclusion from opposite
directions: keep Unsloth's pin on the free path; if Steps 5-6 move to `trl >= 0.26` for the
tool loop, run bf16 on Ampere, never 4-bit+fp16.

**The coverage gap is the version-independent part, and it is the real finding.** TRL's GRPO
test file (5,073 lines) has **zero** `fp16` hits — every precision test is bf16 behind
`skipif(not is_bf16_supported())` — and TRL's GPU CI left Turing entirely (PRs #6741
2026-08-13, #7184 2026-09-11, both T4 → L40S). **This is the "verify the check can fail"
rule biting: TRL's green GRPO suite has never once run our precision on our hardware.**
Unsloth is the opposite case — it carries dedicated no-bf16 regression tests
(`tests/test_grpo_autocast_disabled.py`, `tests/python/test_v100_fullft_precision.py`, the
latter executing *"the REAL template block extracted from rl.py source"*). That asymmetry,
not a single bug, is the reason to stay on Unsloth for Step 2.

**Verdict: (B→A) demonstrated for loss/grad/reward, undemonstrated for KL.**
**Build plan:** Step 2 stands, with three amendments — (i) pin dense Qwen3, never Qwen3.5 or
any MoE; (ii) use Unsloth, and if TRL is used, avoid 4-bit with fp16; (iii) the smoke test's
success criterion is not "it runs" but "KL is finite and non-zero with `beta>0`", since that
is the one curve nobody has published. Also log `frac_reward_zero_std` from step 1 — the one
public run at our exact config died of signal starvation, not numerics.

---

## 8. Counter-evidence to "shrink the action space" — it exists, and it is strong

The corpus treats "shrink the action space" as a design **rule**. The literature supports a
narrower claim, and one paper inverts it under training.

**Tier 1a — SCAFFOLD, arXiv 2609.05511 (2026-08-31), `github.com/BokwaiHo/SCAFFOLD`.**
Unusually clean: WebArena / VisualWebArena / held-out Online-Mind2Web, **every baseline on
the same Qwen2.5-VL-7B base**, same task pool, same K=5 iterations, same inducer checkpoint
*"so comparisons isolate algorithmic differences rather than inducer strength"*, 3 seeds,
paired bootstrap.

- AgentOccam re-run on that base = **16.8** ±0.4 WebArena. SCAFFOLD = **42.7** ±0.8.
  **+25.9 with the base model held constant.**
- The mechanism is a *growing* recursively-composed library of executable skills — a much
  **larger** action vocabulary, settling at **181 skills**, mean abstraction depth 1.05 → 2.71.
- The ablation runs **both** directions, which is what makes this an inverted U:

| Variant | WebArena |
|---|---|
| Full (~181 composed skills, depth 2.71) | **42.7** |
| − recursive composition (**depth ≤ 1**, flattened) | 36.4 (−6.3) |
| − MDL compaction (library balloons to **~470**) | 39.6 (−3.1) |
| − all four (= SkillWeaver) | 29.1 |

Flattening to one altitude costs 6.3; letting the count run unpruned costs 3.1 (reuse
collapses 64% → ~21%). **The optimum is interior.**

- **And it answers the learnability question with trajectories held fixed** (Table 6): STaR
  with no library 30.4; abstraction without distillation 34.7; **SFT on identical
  trajectories with skill calls flattened to primitives 38.6**; full **42.7**. That last
  **+4.1 is a clean trained-wide vs trained-narrow delta** — and the ablations *are*
  retrained (Table 2 caption: *"Each row removes a single component while keeping the rest
  unchanged"*, and distillation is stage 5 of a 5-stage loop that runs every iteration), so
  the flattened arm is a full retrained run, not a wide-trained model evaluated narrow. Not
  LoRA-specific (42.9 full-parameter). Their line: *"a prompt-only skill library, however
  well structured, is fundamentally limited by the frozen base policy."*
- It pre-empts the budget objection: the 30-step horizon is counted **in primitive actions
  for every method**, SCAFFOLD uses *fewer* primitives per success (12.4 vs 14.3/15.1/16.9),
  and its margin is **widest at the tightest 10-step cap**.

**Tier 1b — NapMem, arXiv 2607.05794 (2026-07-07, Alibaba).** The RL-shaped result, and the
single most decision-relevant number in this document. Qwen3.5-9B held constant, LoCoMo +
LongMemEval + PersonaMem-v2, same 4-step tool budget, 3 seeds, multi-turn GRPO via verl.

| Variant | Avg |
|---|---|
| Full NapMem (4 memory granularities as tools) | **62.74** |
| w/o RL (**identical wide action space**, prompted only) | 48.39 (−14.35) |
| w/o navigation (tools removed, passive retrieval) | 54.08 (−8.66) |
| w/o upper levels (2 of 4 levels) | 54.11 (−8.63) |
| records-only tools (**1 of 4**) | 44.93 (**−17.81**) |

**The shape is a crossover: the wide interface *prompted* (48.39) LOSES to the narrow
interface (54.08); the wide interface *trained* (62.74) beats everything.** Untrained
Qwen3.5-**397B** on the wide interface scores 59.85 — still below the trained 9B. And RL made
the policy use **fewer** calls on the wide interface (3.97 → 2.15) at **higher** evidence-hit
(20.66% → 34.92%). **Width bought ceiling; training bought efficiency.**

*Honest caveat:* §4.4 and Appendix C never say whether the three *interface* ablations were
retrained under their modified interfaces. If they were not, 54.08 / 44.93 / 54.11 are
wide-trained-evaluated-narrow and the crossover's magnitude is provisional. The `w/o RL` row
(48.39) and the 397B comparison are unaffected either way. **Direction solid, magnitude
provisional.**

**Tier 2, weaker, one line each.** EvoSOP (2607.07321) — cleanest single-table inverted U
(GPT-4o constant: atomic-only 80.8 → unmanaged expansion 60.0 → pruned expansion 84.2) but
**prompted, no parameter updates**. Qwen-UI-Agent (2607.28227) — GUI+CLI+API+ask_user, online
RL, 79.5% OSWorld-Verified, CLI used in 92-98% of tasks, but **no GUI-only vs GUI+CLI
ablation**: existence proof, no causal number, and it partly supports the bash view.
"Read More, Think More" (2604.01535) — capability-dependent crossover (a11y trees win for
weak models, full HTML for strong), but **observation** space, not action space.
ActionEngine (2602.20502) — 95% vs AgentOccam 66%, **invalid**: GPT-4-Turbo vs Claude 4.5
Sonnet, Reddit subset. "Web Agents Should Use Typed Actions" (2602.17245) — explicit
position paper, **no experiment**.

**AgentOccam has never been contradicted.** All ~100 citing papers swept via Semantic
Scholar: nobody reports failing to reproduce it. It is *outscored* by larger-action-space
systems, but every such comparison re-runs it on a weaker shared base — SCAFFOLD's 16.8 is
on Qwen2.5-VL-7B, whereas AgentOccam's own paper reported ~43% with GPT-4-Turbo, which
SCAFFOLD roughly *matches* at 42.7 with a 7B model. **Beaten under control, never
contradicted.**

**Build plan — three changes.**
1. **Demote "shrink the action space" from rule to rule-with-exception.** The defensible
   version: *shrink the number of same-altitude primitives; do not cap abstraction depth.*
   AgentOccam pruned 9 of 17 **same-altitude** actions; SCAFFOLD's win came from adding
   **altitude**. Those are not the same axis and the corpus conflates them.
2. **Our PTC arm may be sandbagged by our own design.** A narrow PTC action space is now a
   **hypothesis under test**, not a safe default — and NapMem says the wide interface only
   wins *after* training, which is exactly the comparison Step 6 makes. If PTC is given a
   deliberately minimal vocabulary while bash gets a composed shell, a PTC loss is
   unattributable. Hold action-space *altitude* comparable across arms, or state the
   asymmetry as a limitation before running.
3. **Expect scale to cut the other way at 0.6-1.7B.** NapMem's own behavioural analysis:
   larger variants start from broad file reads, *"while the 9B variants mostly start from
   record-level tools… smaller models prefer localized evidence."* Combined with
   Harness-Bench §4.3 (weaker backends show larger cross-harness variance), the honest
   prediction is that **narrow wins at our scale and the crossover needs capability we do not
   have.** That is a publishable finding either way, and it should be pre-registered as the
   expected direction rather than discovered afterwards.

---

## 9. Interesting but inert

- **Agentic Routing (2607.11399)**, EvoHarness-RL (2608.05446), MemHarness (2607.28272),
  Agentic Harness Engineering (2604.25850) — harness *evolution/routing/memory*, orthogonal
  to a fixed two-harness comparison.
- **unix-ctf (2605.29115)** — procedural shell CTF generator; Qwen3-8B LoRA+GRPO lifts solve
  rate 11.6% → 43.6% on a 15-skill holdout, 656/750 variants landing (87.5%) vs 17.4% for
  full-container generation. A ready-made *bash-side* RL surface, and a useful precedent that
  shell-harness GRPO works at 8B. Inert only because our bottleneck is the environment's
  verifier, not task supply.
- **SETA (2607.10891)** — 4,500+ verifiable terminal environments, Qwen3-8B GRPO to 12% on
  Terminal-Bench 2.0 (best reported RL-trained 8B). Same note as unix-ctf; worth revisiting
  if task supply ever becomes the bottleneck.
- **2607.12640** — a *learning-rate-gated null* for GRPO on a 4-8B web agent: across 18 runs
  varying lr, KL weight, seed, init and clipping, no configuration beat a strong supervised
  baseline, and moderate-to-high lr made it credibly **worse**; the same pipeline gained +22
  points on tasks whose reward was reachable by sampling. *"GRPO therefore helps only when
  there is headroom to climb."* Inert for the thesis, decision-relevant for expectations —
  and it corroborates the `frac_reward_zero_std` starvation seen in §7's public run.
- **Harness-Bench's `Security ∈ {0,1}` multiplicative gate** and its setup→execution→judge
  pipeline — good design, adopt at Step 3, but they change no decision now.
- **prime-agent's `AgentToolResult` two-channel result** — noted in §2.4; a Step-4 nicety.
- **verifiers' 11 other harnesses** (`claude_code`, `codex`, `openclaw`, `terminus_2`, …) —
  a free menu for a later multi-harness arm, irrelevant to the two-arm experiment.
- **BenchJack's audit table** — SWE-bench Verified 100%, SWE-bench Pro 100%, Terminal-Bench
  100%, WebArena ~100%, FieldWorkArena 100%, OSWorld 73%, GAIA ~98%, CAR-bench 100%, across
  4,458 tasks. Confirms `05`'s "8/8 broken" from the primary source, changes nothing.
- **`trustworthy-env`'s Z3 formal detector** — MIT, more interesting than BenchJack for
  attacking our own verifier, but it audits *code*, and our verifier does not exist yet.

---

## 10. Consolidated amendments

**To `HANDOFF.md`** (done in this session):
1. Thesis question: the number was the wrong pair. Now states bash−PTC **+6.8 to +22.0 pp**,
   one of four arms not significant, per `docs/…/step1-nonsolver-gate-design.md` §2.1.
2. Known unknowns: fp16 narrowed to the **KL** curve only, with the public run named.
3. Harness-Bench / OpenForgeRL / BenchJack moved from "not located" to located, with the
   licence problem stated.
4. Hard constraints: prime-rl is **Ampere+ / Linux**, not merely "NVIDIA".
5. Novelty: points here for the four transfer scoops.

**To `src/cotrain/contract.py`** — not done, needs a decision: the `ponytail:` docstring
claiming no prior art is false and should name `verifiers` v1 plus the three divergences
(§2.4). Docstring only, no behaviour change, no test touched.

**To the build sequence:**
- **Step 2** — pin dense Qwen3 (never Qwen3.5/MoE); success criterion is a finite non-zero
  KL at `beta>0`, not "it runs"; log `frac_reward_zero_std` from step 1.
- **Step 3** — re-scope "run BenchJack" to "source-audit against V1-V8"; add
  `trustworthy-env --run-cmd` for the runtime half; adopt the model/state secret split and
  the `Security ∈ {0,1}` multiplicative gate.
- **Step 5** — evaluate `verifiers` `bash` + `rlm(builtin_tools=["ipython"])` before building
  two harnesses; target the conservative **+6.8 pp** APEX figure, not the TAC number; add
  tool-call success rate (PTC 65.2% vs bash 92.1% untrained) and shell-call share
  (OpenForgeRL's 22.6% → 13.9%) as metrics.
- **Step 6** — pre-register **token cost and stability** alongside score (2603.01209);
  report the GRPO **grouping boundary** and test under an unseen harness (2609.04518); hold
  action-space *altitude* comparable across arms or declare the asymmetry (§8).

**Standing risk, unchanged and now quantified:** the paper this project is built on has
**zero citations**, is **first-party**, and its larger effect size comes from the arm with
the self-declared incomplete catalog. Step 5's untrained reproduction is not a formality —
it is the experiment that decides whether the premise is real.

---

## 11. Reconciliation with the concurrent Step 2 work

While this document was being produced, another session built **Step 2** on branch
`step2-kaggle-smoke` (`step2/`: gate check, run script, pass criteria, 47 tests, 47 mutants /
0 survivors; commits `42ee206`, `b0d04c0`, `cb3e8f9`). It also already applied `HANDOFF.md`'s
thesis-number correction. Nothing in `08` contradicts it. Two places interlock:

1. **The TRL trainability gate.** `step2/README.md` establishes from source that the
   prefix-preserving raise is guarded by `if self.tools`, does not exist in TRL <= 0.24.0, and
   that Unsloth pins `trl<=0.24.0` — so the gate is *absent*, not merely unfired, and the
   proxy escape hatch is not needed for Step 2. **`08` §7 independently confirms the same
   version boundary from the other side:** the quantized-params bf16 cast that breaks
   `fp16=True` also appears only on `main` (zero hits at v0.24.0/v0.25.0). Same pin, same
   conclusion, two unrelated mechanisms. Where both documents agree the risk is real is the
   Steps 5-6 route `trl >= 0.26` **without** Unsloth: that gains the tool loop and loses the
   fp16-on-Turing work, so it is an Ampere-and-bf16 route, never a T4 route.
2. **Step 2's open question.** `step2/README.md` is explicit that nothing has touched a GPU.
   `08` §7 supplies the missing prior: a public Kaggle 2xT4 run at nearly this config
   completed 314 steps in 5.9 h with zero non-finite values, so **"does it run / is fp16
   stable" is already answered in the affirmative by someone else's committed log.** The
   pass criteria should therefore not stop at "it ran" — require **finite non-zero KL at
   `beta>0`** (the one curve nobody has published) and log `frac_reward_zero_std`, because
   that public run's reward went flat from signal starvation (0.56-1.00 of groups with zero
   advantage), not from numerics. Also pin **dense Qwen3**: `qwen3_5` and `qwen3_moe` are on
   Unsloth's force-float32 list and dense `qwen3` is not.

`HANDOFF.md` had uncommitted edits from that session when `08` landed, so the amendments
listed in §10 were applied **around** the dirty regions (the Step 2 block and the TRL
trainability-gate row were left untouched, as that session's own work). Those two rows should
absorb the notes in point 1 and 2 above when whoever owns them next commits.

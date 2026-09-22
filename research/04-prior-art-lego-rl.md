# 04 — Prior art: LEGO-RL
Date: 2026-09-22 · Closes the open gap flagged in `02-synthesis.md` and `README.md`.
Source: arXiv 2608.17393 (v1, 2026-08-18), abstract + full HTML. Webpage lego-rl.pages.dev.
Authors: Du, Jiang, Yuan, Dai, Wang, Chen, Tao, Yu, Shang, Wong, Li, Bai (Huawei-affiliated).

## Verdict: substantial prior art on the PLUMBING, not on our question. Proceed.

LEGO-RL is the infrastructure for training a policy against an existing coding harness without
modifying its control flow. Our question is *which harness shape wins after training*. Different
axis. Better still, **their stated future work is our angle**.

---

## What they did

Trained **Qwen3.5-35B-A3B** (sparse MoE) with **GSPO**, separately under three harnesses,
SWE-bench Verified (temp 0.7, 200 turns, 200k context budget):

| Harness | Before | After |
|---|---|---|
| OpenHands SDK | 64.0% | **70.4%** |
| Claude Code | 62.4% | **68.2%** |
| OpenCode | 57.2% | **66.6%** |

Rollout-training probability correlation maintained **above 0.99**.

Three pillars, from the abstract:
1. **Faithful optimization** via *"in-process LLM proxying that captures raw generation streams for
   token-level alignment and robust trainer-side log-probability recomputation, even under
   harness-side compaction or re-serialization."*
2. **Reliable execution** via sandbox orchestration with image caching and *"stage-wise defenses to
   mitigate reward hacking."*
3. **Observable training** via a validation/monitoring plugin and a Live UI for trajectory diagnostics.

### Why pillar 1 matters to us specifically
This is a *different solution to the same problem* as TRL's trainability gate. TRL refuses to train
when the chat template is not prefix-preserving (`grpo_trainer.py:1981-1982`), because it must
re-render to locate tool tokens. LEGO-RL sidesteps re-rendering entirely by proxying the LLM call
in-process and capturing the raw generation stream, which survives *harness-side compaction*.

**Consequence:** if our template gate fails on TRL, in-process proxying is the documented escape
hatch, not a dead end. Worth knowing before we treat the gate as fatal.

---

## They independently reproduce the DCAS harness-overfitting effect

Verbatim, on comparing KAT-Coder-V2.5-Dev (SFT+RL post-trained from Qwen3.6-35B-A3B):

> "The gains are also harness-specific: against its own base, KAT-Coder-V2.5-Dev gains **3.4 points
> under Claude Code, the harness its authors report, but −0.4 under OpenHands SDK**, where the
> untuned Qwen3.6-35B-A3B outscores it. We cannot isolate a cause, but the pattern is the one this
> work assumes: **a gain obtained under one agent control flow need not survive another.**"

That is a shipping, post-trained model whose entire measured gain evaporates (and slightly inverts)
on a harness its authors did not target. **Second independent confirmation** of the DCAS finding,
in a different lab, on different models. The harness-overfitting risk in `02-synthesis.md` is now
corroborated twice and should be treated as established, not provisional.

They also note the harness shapes infrastructure behavior, not just scores: *"the same sandbox stack
produces a different termination mix under each harness"* — wall-clock timeouts dominate under
Claude Code, environment-setup failures under OpenCode.

---

## Their stated limitations = our opening

Verbatim from §Limitations:
> "all experiments use Qwen3.5-35B-A3B, and **each coding-agent harness is trained separately, so
> generalization to other model architectures and mixed-harness training remains to be evaluated**."
> ... "executable verification provides a reliable but **coarse binary reward** and cannot assign
> intermediate credit to behaviors such as error recovery." ... "Our reward-integrity defenses
> address the failure modes observed in our experiments but **do not guarantee robustness to all
> possible reward-exploiting strategies**."

Future work, verbatim:
> "one policy trained across several harnesses at once rather than one run per harness—the latter
> **motivated by the harness dependence visible in Table 2**."

### Delta table

| Axis | LEGO-RL | This project |
|---|---|---|
| Question | How do I train reliably against *an existing* harness? | Which harness *shape* wins after training? |
| Harnesses | 3 existing, taken as given, one run each | PTC vs bash, deliberately contrasted |
| Cross-harness eval | **Not done** (their words: "remains to be evaluated") | First-class metric from run 1 |
| Model | 35B-A3B MoE | 0.6B–1.7B dense |
| Algorithm | GSPO | GRPO (TRL) |
| Reward | Binary executable verification | Programmatic, long-horizon |
| Compute | Production scale, single run per config | Free tier / ~$120 |

Our thesis (does co-training close the PTC-vs-bash gap, and does it survive a harness swap) sits in
the intersection of their explicit future work and the DCAS hole. **Not scooped.**

---

## Design rules to steal (their reward-integrity machinery)

The most directly reusable part of the paper. All numbers verbatim from §4.3.

**1. Screen tasks in stages, and expect your verifier to be buggy.**
36,884 candidates -> 22,806 (rule-based validity/diversity/complexity) -> 21,681 (build + verifier
validation) -> **2,699** final training index. Critically:
> "approximately **2.5% of inspected tasks contain verifier logic that incorrectly applies the
> reference patch**."
A programmatic verifier is not automatically correct. Validate the verifier against known-good and
known-bad patches before trusting a single reward.

**2. Screen for difficulty to avoid advantage collapse.**
Keep only tasks *"solved 1–3 times in four trials."* Rationale, verbatim: *"The 0/8 and 8/8 groups
provide **no group-relative advantage**."* This is the concrete countermeasure to the
advantage-collapse failure mode `lanes/grpo.md` catalogues. Screening was done with one
model-scaffold pair and still transferred to the other two harnesses.

**3. Admit trajectories on termination reason, not just outcome.**
Exclude infrastructure failures from advantage estimation and the policy loss; keep trajectories that
merely hit turn/token limits, with their verifier outcomes intact. Measured exclusion rates: **7.1%
Claude Code, 2.4% OpenHands SDK, 6.4% OpenCode.** Without this, infra flakiness is trained on as if
it were policy behavior.

**4. Binary terminal reward is a known ceiling, not a safe default.**
They name it as a limitation: it *"cannot assign intermediate credit to behaviors such as error
recovery."* Relevant to our long-horizon environment design, where the Vending-Bench-2 shape
(uncapped scalar) is the alternative.

---

## Confidence and gaps
- **Strong**: all numbers above are from the paper's own text, HTML v1, quoted verbatim.
- **Not verified**: I did not fetch Table 2's actual cell values (rendered as an image/table
  reference in the HTML extraction), only the prose describing it. The KAT-Coder +3.4 / −0.4 figures
  come from that prose.
- **Not checked**: whether the LEGO-RL code release at lego-rl.pages.dev is actually public, and
  whether its harness adapters are reusable. Worth a look before building adapters ourselves.
- Single run per configuration, by their own admission, so run-to-run variance is unquantified.

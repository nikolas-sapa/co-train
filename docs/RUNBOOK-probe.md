# Runbook — the dead-group probe (mission brief for an agent)

**Cost: $0.** Free Kaggle T4 session. Nothing here spends money, and nothing here is
allowed to.

This file is the whole mission. It assumes no prior knowledge of the repo.

---

## 1. What this probe decides, and what it does not

**Decides one thing:** whether a binary 0/1 reward produces usable training groups for a
0.6B policy. GRPO computes an advantage within a group of `G` sampled completions; if
every completion in a group scores the same, the group's advantage is zero and it
contributes no gradient. The fraction of such groups is `frac_reward_zero_std`, and TRL
already logs it.

**Abort ceiling: above 0.60 on any step, stop.** It means most of the batch yields no
gradient, the reward's *shape* is the problem rather than the pipeline, and no taskset
fixes a reward that cannot separate. Expected healthy is about 0.40 at G=4.

Both tails degenerate: at G=8 a policy solving 10% of tasks yields 43% dead groups
against 15.7% for one solving 79%. **A weak policy is the worse case**, and Qwen3-0.6B is
the weak case, so the realised value could land anywhere from 0.15 to 0.60+. That is the
entire reason to spend a free session before anything else.

**Does NOT decide:** H2 through H5, whether co-training works, or whether to build the
pipeline. A clean probe says the reward separates on the taskset it ran against. Nothing
more. Do not report it as anything more.

---

## 2. What the human has to do first (one time, two minutes)

An agent cannot do this part — it needs a browser login.

1. Go to <https://www.kaggle.com/settings>
2. Under **API**, click **Create New Token**. A file `kaggle.json` downloads.
3. Run these two commands, replacing the path if the download went elsewhere:

```bash
mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json
```

4. Kaggle requires a **phone-verified** account for GPU and internet access in notebooks.
   If the account is not verified, do it at <https://www.kaggle.com/settings> — the probe
   cannot run without internet (it pip-installs and downloads the tokenizer).

That is the human's entire involvement until the result comes back.

---

## 3. Agent steps

### 3.1 Local setup

```bash
pip install --upgrade kaggle
kaggle config view          # must print a username; if not, step 2 is incomplete
```

### 3.2 Confirm the prompts exist in the repo

The repo is **public**, so the notebook clones it directly — no token, no dataset upload.

```bash
cd ~/Developer/misc/co-train
git pull
wc -l bench/probe_prompts.jsonl
cat bench/probe_prompts.header.json
```

The header records that this is a **scalar-answer subset** of BIRD dev: only tasks whose
gold query returns exactly one row and one column. That is deliberate — the probe's reward
is exact string match on a `<answer>` block, so a gold-SQL reference would read as
near-uniform failure and abort the probe over the comparison instead of the reward. On a
1x1 result, exact match *is* execution accuracy.

**Carry that caveat into whatever you report:** a solve rate from this subset is not
BIRD's solve rate.

### 3.3 Create the notebook

Make a working directory and two files.

`kernel-metadata.json` — replace `YOUR_USERNAME` with the `kaggle config view` username:

```json
{
  "id": "YOUR_USERNAME/cotrain-dead-group-probe",
  "title": "cotrain dead group probe",
  "code_file": "probe.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": true,
  "enable_gpu": true,
  "enable_internet": true,
  "dataset_sources": [],
  "competition_sources": [],
  "kernel_sources": []
}
```

`probe.py`:

```python
import subprocess, sys, pathlib

def sh(cmd):
    print("+", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)

# 1. The stack. unsloth 2026.10.3 is a FLOOR, not a preference: below it unsloth pins
#    trl<=0.24.0, where rollout_func / self.tools / tool_mask /
#    get_training_chat_template are all at ZERO occurrences. Below this version the run
#    is not degraded, it is a different run.
sh('pip install -q "unsloth>=2026.10.3" "trl==1.13.0" "transformers<5"')

# 2. The code. Public repo, no token.
sh("git clone --depth 1 https://github.com/nikolas-sapa/co-train /kaggle/working/co-train")

# 3. Fail in seconds rather than after a model download.
import torch
assert torch.cuda.is_available(), "no GPU: set Accelerator to GPU T4 x2"
cap = torch.cuda.get_device_capability()
print("device:", torch.cuda.get_device_name(0), "sm_%d%d" % cap, flush=True)
assert cap[0] < 8, (
    f"expected a pre-Ampere GPU for the fp16 question, got sm_{cap[0]}{cap[1]}. "
    "fp16 is a DECISION here, not a workaround: arXiv:2510.26788 measures bf16's "
    "training-inference mismatch at ~24x fp16's. On newer hardware this is a new "
    "stability question, not a settled one. Do not patch past this assert."
)

sys.path.insert(0, "/kaggle/working/co-train")
sh("cd /kaggle/working/co-train && python -m train.dead_group_probe "
   "--prompts bench/probe_prompts.jsonl "
   "--taskset-id bird-dev-scalar-subset-seed0 "
   "--steps 5 "
   "--out /kaggle/working/probe_metrics.jsonl")

# 4. Re-adjudicate in-session, so a failed run is visible in the log and not only in a
#    file someone has to remember to fetch.
sh("cd /kaggle/working/co-train && python train/verdict.py /kaggle/working/probe_metrics.jsonl || true")
print("METRICS BYTES:", pathlib.Path("/kaggle/working/probe_metrics.jsonl").stat().st_size, flush=True)
```

### 3.4 Push and poll

```bash
kaggle kernels push -p .
kaggle kernels status YOUR_USERNAME/cotrain-dead-group-probe
```

Poll every 60 seconds. Install is 15-20 minutes. **Per-step wall-clock is unknown and
measuring it is part of the point** — the only generation figure anyone has is 3.2 tok/s
whole-loop at `use_vllm=False`, where one step exceeds an hour and free hardware is out.
With vLLM it should be minutes. `--steps 5` is the minimum the verdict script will
adjudicate, and it yields the step time so 20 is decided from data.

If status is `error`, fetch the log and read it — do not re-push blind.

### 3.5 Fetch the output IMMEDIATELY on completion

```bash
kaggle kernels output YOUR_USERNAME/cotrain-dead-group-probe -p ~/scratch/probe-out
ls -la ~/scratch/probe-out
```

**This is the step that has already gone wrong once in this project.** Kaggle's "Restart
session" wipes `/kaggle/working`, which is how Step 2's first-party metrics file was lost.
Fetch before anything else.

### 3.6 Adjudicate locally, with no GPU

```bash
cd ~/Developer/misc/co-train
.venv-ptc/bin/python train/verdict.py ~/scratch/probe-out/probe_metrics.jsonl
```

---

## 4. Hard constraints

- **Do not spend money.** No Kaggle paid tier, no Colab Pro, no rented GPU, no paid API.
  There is a separate $6.29 run in this project and it is **not authorised**. If the free
  path fails, stop and report; do not substitute a paid one.
- **Do not patch past the `sm_ < 8` assert.** See the comment in `probe.py`.
- **Do not lower `unsloth>=2026.10.3`.**
- **Do not soften the reward.** `exact_match_reward` is deliberately strict — no judge, no
  partial credit, no substring search. The probe exists to measure *that* reward's
  geometry, and softening it answers a different question with the same session.
- **Do not write `bench/frontier/manifest.json` by hand.** `train/guards.py` gates the
  pipeline on it, and the band must be **per-task measured solve rates** from this probe.
  The ~25% figure in `docs/pre-registration.md` §A8 is a *marginal over a corpus* and is
  not a substitute: at the same marginal 0.25 and G=4, a suite where every task sits at
  p=0.25 reads 0.320 dead groups and is trainable, while one where a quarter of tasks are
  always solved and three quarters never are reads **1.000** and is not. The two are
  indistinguishable as a marginal.
- **Do not commit secrets.** `~/.kaggle/kaggle.json` stays out of the repo.
- **Do not `git push` to `main`.** Branch and open a PR if code needs changing.

---

## 5. Report back

1. The probe's verdict: PASS or ABORT, and the reason the script gives.
2. `frac_reward_zero_std` per step, all five.
3. **Per-step wall-clock**, which is the number nobody in this project has yet.
4. Peak VRAM against the 12.59 GB the spec predicts for one card.
5. Realised per-task solve rates, if the probe emitted them — flagged as the
   scalar-answer subset, not BIRD.
6. Anything that had to be changed to make it run, and why. A run that only worked after
   an undisclosed edit is not a result.
7. Where `probe_metrics.jsonl` is saved locally.

If the probe aborts, that is a **successful** outcome for a $0 session: it means the
binary reward cannot separate for this policy, and the project has learned that before
spending anything.

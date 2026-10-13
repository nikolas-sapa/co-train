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

## 2. Credentials — done, and what was wrong about this section before

**⚠ CORRECTED 2026-10-13.** This section originally described a `kaggle.json` holding a
`{"username", "key"}` pair, because that is the credential the Kaggle CLI used for years.
It is not what the current client wants. Kaggle now issues a **single prefixed token**
(`KGAT_...`), with no username, read from `~/.kaggle/access_token` or the
`KAGGLE_API_TOKEN` environment variable. The old instructions would have sent an agent
looking for fields that no longer exist.

**Already configured on this machine.** The token lives at `~/.secrets/kaggle_token`
(mode 600, recorded in `~/.secrets/README.md`), and `~/.kaggle/access_token` is a symlink
to it, so there is one copy of the secret and the client still finds it where it expects.
Verified working:

```
$ kaggle config view
- username: nikolassapalidis
- auth_method: ACCESS_TOKEN
```

**If that ever stops working**, the token was expired or rotated. Creating a new one at
kaggle.com/settings → API → Create New Token invalidates the old, and the only human step
is putting the new value in `~/.secrets/kaggle_token` without it passing through a chat
transcript:

```bash
umask 077; printf '%s\n' 'KGAT_...' > ~/.secrets/kaggle_token
```

A token pasted into a conversation is compromised — transcripts are retained and session
tooling copies command text to disk in plaintext. Rotate anything that has been pasted.

Kaggle also requires a **phone-verified** account for GPU and internet inside notebooks.
This account is verified; a fresh one would not be.

---

## 3. Agent steps

### 3.1 Local setup

The CLI is installed via pipx (`kaggle 2.2.4`). If it is missing:

```bash
pipx install kaggle
kaggle config view          # must print a username and auth_method: ACCESS_TOKEN
```

### 3.2 Confirm the prompts are on main

The repo is **public**, so the notebook clones it directly — no token, no dataset upload.

```bash
cd ~/Developer/misc/co-train && git pull
wc -l bench/probe_prompts.jsonl        # 573
cat bench/probe_prompts.header.json
```

The header records that this is a **scalar-answer subset** of BIRD dev: only tasks whose
gold query returns exactly one row and one column. That is deliberate — the probe's reward
is exact string match on a `<answer>` block, so a gold-SQL reference would read as
near-uniform failure and abort the probe over the comparison instead of the reward. On a
1x1 result, exact match *is* execution accuracy.

**Carry that caveat into whatever you report:** a solve rate from this subset is not
BIRD's solve rate.

### 3.3 The notebook

**Already written and pushed** — both files are committed at `train/kaggle/`, and kernel version 1
went up 2026-10-13 as `nikolassapalidis/cotrain-dead-group-probe`. Reproduce it with
`kaggle kernels init -p .` and the two files below; the metadata template changed in CLI
2.x and now carries `enable_tpu`, `machine_shape` and `model_sources`, which the first
version of this runbook omitted.

`kernel-metadata.json`:

```json
{
  "id": "nikolassapalidis/cotrain-dead-group-probe",
  "title": "cotrain dead group probe",
  "code_file": "probe.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_tpu": "false",
  "enable_internet": "true",
  "machine_shape": "",
  "dataset_sources": [],
  "competition_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
```

`machine_shape` is left empty: the API does not expose the T4 x2 selection the Step 2
runbook used, so Kaggle assigns the card. **Any pre-Ampere card is fine for this probe** —
it needs 12.59 GB on one GPU, and P100 (sm_60) and T4 (sm_75) both clear the `sm_ < 8`
assert and both have 16 GB. The script prints the device it actually got, and that goes in
the report, because "which card" is a measurement here and not a detail.

`probe.py` — the pinned stack is the part to leave alone:

- **`unsloth==2026.10.3` exactly, not `>=`.** Below it unsloth pins `trl<=0.24.0`, where
  `rollout_func`, `self.tools`, `tool_mask` and `get_training_chat_template` are all at
  **zero** occurrences. But 2026.10.4 also exists and its pin has never been checked, so
  floating upward is an unverified stack rather than a safer one.
- **`trl==1.13.0`**, which is where those four seams are at 13/17/27/2.
- **`transformers<5`**: at 5.x the chat-template flags invert and the error names neither
  package.
- `subprocess.run` takes a **list** and no shell. Every argument is a literal, and a list
  means a path containing a space cannot silently become two arguments.

The file as pushed is `train/kaggle/probe.py`.

### 3.4 Push and poll

```bash
cd ~/Developer/misc/co-train/train/kaggle && kaggle kernels push -p .
kaggle kernels status nikolassapalidis/cotrain-dead-group-probe
```

Status strings come back as `KernelWorkerStatus.QUEUED`, `.RUNNING`, `.COMPLETE` or
`.ERROR`. Poll on a terminal state rather than sleeping a guessed interval:

```bash
until kaggle kernels status nikolassapalidis/cotrain-dead-group-probe \
      | grep -qvE 'RUNNING|QUEUED'; do sleep 60; done
```

Install is 15-20 minutes. **Per-step wall-clock is unknown and measuring it is part of the
point** — the only generation figure anyone has is 3.2 tok/s whole-loop at
`use_vllm=False`, where a single step exceeds an hour and free hardware is out. With vLLM
it should be minutes. `--steps 5` is the minimum `verdict.py` adjudicates, and it yields
the step time so 20 is decided from data.

On `ERROR`, read the log before re-pushing:

```bash
kaggle kernels logs nikolassapalidis/cotrain-dead-group-probe -p ~/scratch/probe-out
```

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

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

**CORRECTED 2026-10-19. The abort can now wait for evidence.** §282's any-step form is still
the default (`ABORT_WINDOW = 1`), but `--abort-window k` makes the criterion fire only after
`k` consecutive breaching steps; the Kaggle entry point runs `--steps 10 --abort-window 3`
(`train/kaggle/probe.py:137-140`). This is a power choice with a stated derivation, not a
softening of the ceiling: at G=8 the 0.60 ceiling sits on the band's lower edge, so a
precisely viable policy trips the single-step test 47.5% of the time and one at p=0.10 trips
it 21.6%; at window 3 those fall to 0.107 and 0.010, while a hopeless policy at p=0.02 still
fires with probability 0.708 (`train/dead_group_probe.py:70-79`;
`train/verdict.py:119-134`; amendment A11 draft). The window is written into the metrics
header, so a run's verdict cannot be re-read under a window it did not use.

Both tails degenerate: at G=8 a policy solving 10% of tasks yields 43% dead groups
against 15.7% for one solving 79%. **A weak policy is the worse case**, and Qwen3-0.6B is
the weak case, so the realised value could land anywhere from 0.15 to 0.60+. That is the
entire reason to spend a free session before anything else.

**Dated note, 2026-10-19: the session has been spent, and the value landed at the ceiling.**
v9 measured `frac_reward_zero_std` 1.000 at step 0 on four groups and aborted, with
generation and extraction both working (`clipped_ratio` 0.000, `grad_norm` non-zero). Four
dead groups is consistent with a solve rate at or below roughly 0.05 and cannot separate
p = 0 from p = 0.05, so the probe measured a *weak policy*, not a broken pipeline, and did
not produce a rate. What is needed next is more groups before adjudicating, not a different
reward: `docs/probe-v9.md` derives both the table and that conclusion. The reason to spend
a free session still holds for any future taskset, but the reason stated above is now
settled for this one.

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
wc -l bench/probe_prompts_sql.jsonl    # 800
cat bench/probe_prompts_sql.header.json
```

**Dated note, 2026-10-19:** this block read `bench/probe_prompts.jsonl  # 573` and
`bench/probe_prompts.header.json` until today. Those are the retired scalar-answer prompts
(the correction two paragraphs below); the kernel reads the `_sql` files, so checking the old
pair would confirm the presence of a file the run does not use.

The header records that this is a **scalar-answer subset** of BIRD dev: only tasks whose
gold query returns exactly one row and one column. That is deliberate — the probe's reward
is exact string match on a `<answer>` block, so a gold-SQL reference would read as
near-uniform failure and abort the probe over the comparison instead of the reward. On a
1x1 result, exact match *is* execution accuracy.

**Carry that caveat into whatever you report:** a solve rate from this subset is not
BIRD's solve rate.

**CORRECTED 2026-10-19. The probe no longer runs this subset, and the commands above name
the wrong file.** The kernel runs `bench/probe_prompts_sql.jsonl` (800 BIRD dev questions,
`train/kaggle/probe.py:115`) with `--reward ex`, so the reward is execution accuracy on
generated SQL, executed against the task's sqlite file, not exact match on a `<answer>`
block. The scalar-answer set was retired on 2026-10-13 (`ce7e319`) because its prompts
carried the schema and asked for a data value with no rows present: unanswerable at any
skill level, so `frac_reward_zero_std` read 1.000 at step 0 and the probe measured its own
prompt design. The reason is recorded in the `why` field of
`bench/probe_prompts_sql.header.json` and in the `why_subset` field of the retired
`bench/probe_prompts.header.json`. The
caveat above still applies in a different form: a solve rate on the SQL draw is not BIRD's
solve rate either, because the draw is 800 of 1534 questions over seven small databases.

### 3.3 The notebook

**Already written and pushed** — both files are committed at `train/kaggle/`, and kernel version 1
went up 2026-10-13 as `nikolassapalidis/cotrain-dead-group-probe`. Reproduce it with
`kaggle kernels init -p .` and the two files below; the metadata template changed in CLI
2.x and now carries `enable_tpu`, `machine_shape` and `model_sources`, which the first
version of this runbook omitted.

**Dated note, 2026-10-19:** "version 1" is stale. The kernel has been pushed several times
since; the current entry point is `train/kaggle/probe.py` at `f3565eb`, which runs
`--steps 10 --abort-window 3` on the SQL prompts. Push from `train/kaggle/` as below and the
log's `PROBE ABORT` / metrics header record which config actually ran, so read those rather
than assume this paragraph's number.

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

**Dated note, 2026-10-19:** v9 ran and the step time **is** now measured, though not in the
prose docs: `probe_metrics.jsonl` in `~/scratch/probe-v9/` carries `"step_time":
429.696…` for step 0, i.e. about **7.2 minutes** including generation of 32 sequences.
That is one step of a run that then aborted, so whether 10 steps average lower is still
open. The step count has also moved off the 5 above: the entry point runs `--steps 10
--abort-window 3` (`train/kaggle/probe.py:137-140`) so that ten steps give 40 groups before
a verdict. Five is still `verdict.py`'s floor for adjudication (`MIN_PROBE_STEPS = 5`), not
the configured run length.

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

  **Dated note, 2026-10-19:** the filename is stale. Since the credential moved to a single
  `KGAT_` access token (§2's 2026-10-13 correction), the secret is `~/.secrets/kaggle_token`,
  with `~/.kaggle/access_token` a symlink to it. Neither belongs in the repo; the principle
  above is unchanged and only the path was wrong.
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

**Dated note, 2026-10-19.** Three of the items above need re-reading against the current
config. (2) the run is 10 steps, not five. (3) one step's time is on disk from v9
(`step_time` 429.7 s in `~/scratch/probe-v9/probe_metrics.jsonl`); what is still missing is
an average over a run that does not abort at step 0. (4) no saved log reports peak VRAM, so
the 12.59 GB prediction remains unconfirmed either way. (5) the taskset is now 800 BIRD dev
questions scored by execution accuracy, not the scalar-answer subset, so a rate from it is
still not BIRD's solve rate but for a different reason (an 800-of-1534 draw over seven small
databases).

If the probe aborts, that is a **successful** outcome for a $0 session: it means the
binary reward cannot separate for this policy, and the project has learned that before
spending anything.

**Dated note, 2026-10-19: an abort is only a successful outcome if it can be read.** v9
aborted at step 0 on four groups, and four dead groups cannot distinguish a hopeless policy
from an unlucky batch: at p = 0.05 there is a ~19% chance of exactly that, so the abort
licenses "solve rate at or below roughly 0.05" and no rate at all. That is why the window
exists. An abort under `--abort-window 3` over 10 steps reads far more sharply (a hopeless
p=0.02 policy fires with probability 0.708, and a zero over 40 groups bounds p below about
0.01); an abort in the first three steps of a windowed run is still a single unlucky batch
and should be read as such. `docs/probe-v9.md` derives both figures.

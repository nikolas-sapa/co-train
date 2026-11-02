# co-train

Co-train investigates whether training a small model around a tool interface
improves task performance, and whether that improvement survives a harness swap.
The current research comparison is Bash versus programmatic tool calling (PTC)
on BIRD-SQL.

**Status, 2026-11-02: early research prototype, not production-qualified.**
SQL skill capture, qualification and reuse are implemented engineering;
completed co-training and cross-harness benefit have not been demonstrated.

## Current research milestones 4-6

| Stage | Status | Remaining work |
|---|---|---|
| 4: environment and escalation | PARTIAL | Stock CLI admission, isolated reporting transport/binding and actual rollout/training integration. |
| 5: paired untrained baseline | PARTIAL | A real retained draw, legitimate frontier measurements and authorized paired BIRD rollouts. The current BIRD baseline is missing, not zero. |
| 6: co-training and harness swap | BLOCKED | Frontier evidence, compatible runtime/template and completed training integration. The training CLI still deliberately refuses the incomplete path after preflight. |

SQL reuse and separate local MLX work do not complete this research sequence.
The MLX comparison is inconclusive; its three-seed trial is incomplete.
See the [evidence index](docs/evidence-index.md) and
[native training contract](spec/native-training.md).

## What works, and what the evidence does not prove

- **Checked SQL skill reuse:** a caller-authored SQL-generating skill passed
  four qualifications and two fresh native-process reuses on distinct databases
  on 29 October. This was a bounded fixture campaign with zero model calls,
  not automatic learning or a production SQL cache.
  [Native SDK receipt](docs/2026-10-29-native-sql-skill-workflow.md).
- **Tests:** the dated 30 October configured offline run recorded **3,803 passed,
  1 skipped and 2 deselected**. This is not a current-branch full-suite count
  or proof that all current tests pass.
  [Source-bound receipt](docs/2026-10-30-portable-sql-skill-sdk-acceptance.md).
- **Historical cost estimate:** retired `ledger` runs on 14/29/29 paired tasks
  estimated PTC inference cost per solved task at 7.53x/7.01x/8.21x lower than
  Bash; 6.1x was a token-counter sensitivity estimate. These were untrained
  evaluations using one requested model through one relay, with uncached input
  pricing, not SQL-cache savings or a learned advantage. Later unsigned A9
  qualifies the dollar multiple as conditional on no prefix caching;
  cache-enabled economics remain unmeasured.
  [Results and corrections](docs/results-untrained.md),
  [cache qualification](docs/pre-registration.md#a9--2026-10-14-after-the-caching-audit-the-dollar-ratio-is-an-upper-bound-and-the-condition-favours-bash--unsigned).
- **Current acceptance:** the latest local owned-SDK diagnostic hit its fixed
  300-second suite limit without a final pytest aggregate. Offline subsets and
  isolated optimization prototypes do not qualify the full project.
  [Dated status and scope](docs/2026-11-02-project-status-cli.md).

No measured current BIRD accuracy, cost, throughput or latency advantage is
established. There is no validated overall completion percentage or delivery
date. Test counts and fixture successes are not customer or traction metrics.

## CLI: reuse the existing SDK

The project already reuses Verifiers rather than implementing another agent
loop. Its evaluation entrypoint is:

```bash
python -m cotrain_bash_qa_eval --config /absolute/path/eval.json
```

This requires an existing compatible environment and a complete, admitted
configuration. It is not an installation recipe or permission for model calls.
Bare upstream `vf-eval` is not supported for the scoped reporting route.
A separate CLI fork would not supply missing measurements or training wiring.

See the [CLI contract](docs/2026-10-31-bash-qa-eval-cli.md) and
[reuse decision and remaining work](docs/2026-11-02-project-status-cli.md).
No runnable end-to-end training command is claimed.

## Repository guide

| Path | Purpose |
|---|---|
| [docs/project-map.md](docs/project-map.md) | Workstreams and navigation |
| [docs/evidence-index.md](docs/evidence-index.md) | Dated observations and limitations |
| [ptc/](ptc/README.md) | PTC runtime and SQL lifecycle mechanics |
| [train/](train/README.md) | Training integration and SQL capture/reuse tooling |
| [bench/](bench/) | Task preparation, scoring and comparison contracts |
| [spec/](spec/) | Protocols, acceptance criteria and launch gates |
| [research/](research/README.md) | Research synthesis and source records |
| [HANDOFF.md](HANDOFF.md) | Dated technical continuation history |

The default offline test configuration covers `tests ptc ledger bench train`;
it excludes tokenizer integration by default and does not collect `step2`.
See [pytest.ini](pytest.ini). No tests were rerun for this documentation update.

Core SQL reuse tooling is on `main`. Unqualified owned-SDK binding and isolated
optimization candidates are not included by this documentation update.
Original scratch evidence is machine-local, not bundled with a clone.
The previous long README remains in
[Git history](https://github.com/nikolas-sapa/co-train/blob/a718cf53833458379adf1c3d4a8e02b89b4a958b/README.md).

Publication to GitHub is not a deployment or new experiment authorization.
Native/model/training work still requires its existing gates and permissions.

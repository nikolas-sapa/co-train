# Project status and CLI reuse

2026-11-02. Documentation-only assessment. No training, model/provider calls,
native campaign, dependency change or deployment is authorized by this note.

## Research status

Co-train tests whether training a small model around a tool interface improves
task performance and whether the improvement survives a harness swap. The
current comparison is Bash versus programmatic tool calling on BIRD-SQL.

| Stage | Status | Remaining work |
|---|---|---|
| 4: environment and escalation | PARTIAL | Stock CLI admission, isolated reporting transport/binding and actual rollout/training integration. Existing configured runners are not stock-CLI support. |
| 5: paired untrained comparison | PARTIAL | A real retained draw, legitimate frontier measurements and authorized paired BIRD rollouts. Preparation/scoring code is not a measured baseline. |
| 6: co-training and harness swap | BLOCKED | Required frontier evidence, compatible runtime/template and completed, verified training integration before the preregistered experiment. |

No completed co-training/harness-swap result or learned benefit is established.
Separate local MLX sampling and updates do not establish that result; their
comparison is inconclusive and the three-seed trial is incomplete.
No current accuracy, cost, throughput or latency advantage is established.
There is no measured overall completion percentage or reliable completion ETA.
This review establishes no customer, revenue or retention figures.

## Reuse an existing CLI, not another agent loop

**Recommendation: retain the existing Verifiers SDK integration and thin
project wrapper.** Do not build or fork a separate agent CLI just to obtain
argument parsing or an evaluation loop.

The recorded dependency in [PTC requirements](../ptc/requirements.txt) is
`primeintellect-ai/verifiers` revision
`69cc0f948e327e9b2765ec927c4c0c7d3e0d0cd5`.
Its official pinned [project metadata](https://github.com/PrimeIntellect-ai/verifiers/blob/69cc0f948e327e9b2765ec927c4c0c7d3e0d0cd5/pyproject.toml)
defines `vf-eval`; its pinned [license](https://github.com/PrimeIntellect-ai/verifiers/blob/69cc0f948e327e9b2765ec927c4c0c7d3e0d0cd5/LICENSE)
is MIT. Both were read for this assessment. Any redistributed fork must retain
the applicable copyright and permission notice. This is not a dependency
upgrade or evidence that a different/latest release is compatible.

### Three different command paths

1. **Existing project evaluation CLI:**
   `python -m cotrain_bash_qa_eval --config /absolute/path/eval.json`.
   [Implementation](../cotrain_bash_qa_eval.py) validates an explicit
   configuration and delegates to the existing SDK evaluation wrapper.
   It preserves SDK episode/scoring/JSONL behavior rather than replacing the
   agent loop. See the [CLI contract and evidence](2026-10-31-bash-qa-eval-cli.md).
   A complete admitted configuration is still required; this is not an
   end-to-end paired BIRD runner or permission to make model calls.
2. **Bare upstream `vf-eval`: unsupported for the scoped reporting route.**
   Plugin discovery does not prove that admission occurs before policy/resource
   startup or that reporting receipts are forwarded and retained.
   [Configured PTC activation](2026-10-31-ptc-qa-activation.md) is a separate
   guarded, report-only route, not a task-local SQL catalog/evaluation bridge.
3. **Training CLI:** [grpo_ptc.main](../train/grpo_ptc.py) runs preflight and
   deliberately refuses the incomplete training path with `NotImplementedError`.
   The [native training contract](../spec/native-training.md) explicitly keeps
   that refusal while permitting constructor assembly only. A runner fork
   cannot supply frontier measurements, compatible training behavior or
   completed training evidence.

Consider a minimal pinned upstream patch/fork only if stock-command support is
required and a concrete lifecycle requirement cannot be met through supported
extension points. A new fork is **not implemented or claimed** here.

### Tests before enabling another CLI route

These are future acceptance criteria, not new execution receipts:

- Exactly one SDK delegation and one retained report, with the reporting receipt
  before policy request 2 and exact reporting data in SDK JSONL.
- Unsupported or unbound execution must make zero policy calls; admission must
  precede channel/runtime startup wherever the existing contract requires it.
- Two sequential and two overlapping episodes must have distinct channels and
  no crossed events; cancellation must revoke admission.
- Suppressing activation, receipt forwarding and telemetry persistence must
  separately turn the corresponding checks RED, then restore GREEN.

Existing scientific settings, task denominators, permissions and deadline caps
remain unchanged. Any implementation needs its own scoped source/spec review.

## Latest engineering evidence, separate from research

The following are local isolated-worktree receipts, not tests rerun for this
documentation update. Their implementation candidates are not merged by this
update, and original scratch evidence is not distributed with a clone.

| Receipt | Observed result | Limit |
|---|---|---|
| Guardian-span integration | 8 new, 12 direct and 177 combined cases passed; combined wall 25.597s. | Groups overlap. The combined union is 177, not their sum. Offline correctness, not SQL accuracy or learned benefit. |
| Profile of the same combined selection | 177 passed; invoking-thread profile captured. | Added checks may offset targeted parse savings. Net suite improvement remains unproven. |
| Private line-index prototype | Exactly 30 cases passed in 1.690s; max absolute case interval 1.087s, below UNIT3. | Equivalence/defect controls and a local comparative benchmark only. Editing the existing shared table checker remains outside the approved integration delta. |
| Latest native attribution diagnostic | Timed out at its fixed 300s suite cap. | Partial passing progress is not a completed acceptance run or production qualification. No retry is authorized here. |

Local receipt identifiers: `offline-verification-summary.json`,
`offline-call-profile-01/results.md` and `line-index-01.result.json` beneath
the isolated guardian-span integration evidence directory. They are
machine-local evidence, not portable paths or independently available clone
contents. Source binding and exact selections matter; historical larger test
totals do not qualify current sources.

## Next priorities

1. Complete the narrowly scoped stage-4 admission/reporting and rollout
   integration, reusing the existing SDK lifecycle.
2. Obtain legitimate frontier evidence and the paired current-taskset baseline.
3. Satisfy unchanged runtime/template and training gates, then run the
   preregistered training and cross-harness evaluation.
4. Resolve separate SDK acceptance/qualification without weakening caps or
   treating offline fixtures as native ownership proof.

For external descriptions, call this an early technical/research prototype.
Separate implemented infrastructure from completed experiments and hypotheses.
Do not claim a trained performance advantage, production deployment or traction
without separate evidence.

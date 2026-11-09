# co-train: cuts AI agent costs by reusing verified code

co-train is an early prototype for reusing checked SQL code. Its intended workflow
saves a SQL skill when an agent answers a database question correctly, checks it
by running it, and reuses it on similar questions instead of paying a model to
solve them again. SQL comes first because answers can be checked. Cutting costs
is the goal, not a measured result of reuse.

## Status

As of 9 Nov 2026, offline draw preparation, reporting, sample capture and evidence
save/reload are implemented and fixture-tested. The engineering checkpoint now
also includes isolated owner/consumer custody, bounded file RPC and validation
sources. These sources do not qualify native/GPU execution.
Real BIRD measurements, measured reuse savings and native-training qualification
remain open. [Engineering status and blockers](docs/engineering-status-2026-11-09.md);
[current research milestones](#current-research-milestones-4-6).

On 29 Oct 2026, a checked, hand-written SQL skill was reused correctly in two
fresh runs on two different databases.
[Read the test and its limits](docs/2026-10-29-native-sql-skill-workflow.md).
Not done yet: connecting reuse to a live agent end to end and measuring savings
from real bills. No users.

## Engineering checkpoint: 9 Nov 2026

- Published bounded file RPC, isolated custody/reader validation, one-use
  publication/refusal paths, local mechanism references and offline fixtures.
  Fixture-backed lifecycle observations do not establish real SDK/process control.
- Preserved negative controls and rejected performance experiments. Both recent
  Python micro-optimizations failed their fixed speed gates; correctness passes
  did not promote them.
- Native ancestry-helper design is reviewed, and one metadata-only preflight
  completed. No helper implementation/build, header/API inspection or ABI
  compatibility is claimed.
- Full-volume reliability is still open. The latest exact 8GiB validation timed
  out at the 30-second external limit after at least 7.75GiB read. Final hashing,
  publication and release were not confirmed. No new native GPU result exists.

Next gates: native-helper API/ABI and compiler-containment review, a material
check-preserving performance fix with fresh maximum-volume validation, then a
compatible GPU runtime and an explicitly approved, budgeted engineering attempt.
There is no defensible same-day GPU ETA.
[Evidence and limits](docs/engineering-qualification-evidence.json);
[qualification details](docs/engineering-qualification-readiness.md).

## Why I think it works

In three untrained runs on 3-8 Oct 2026, agents writing small programs to use their
tools had similar task results to agents making tool calls one by one, with an
exact tie in the cleanest run (23/29 each). Estimated cost per solved task was
7.5x, 7.0x and 8.2x lower on 14/29/29 paired tasks, respectively. These were
self-authored `ledger` tasks, with one requested model (`deepseek-v4-flash`)
through one relay and input priced uncached: treat the multiples as conditional
upper-bound estimates, not measured SQL-reuse savings.
[Results and corrections](docs/results-untrained.md);
[pre-registration and cache caveat](docs/pre-registration.md#a9--2026-10-14-after-the-caching-audit-the-dollar-ratio-is-an-upper-bound-and-the-condition-favours-bash--unsigned).

## Research

Co-train investigates whether training a small model around a tool interface
improves task performance, and whether that improvement survives a harness swap.
The current research comparison is Bash versus programmatic tool calling (PTC)
on BIRD-SQL.

No end-to-end co-training run has finished, and no improvement from training is
proven yet. The published untrained result is negative on the proposed accuracy
ordering, not proof of a PTC accuracy advantage.
[Negative result](docs/results-untrained.md),
[pre-registration](docs/pre-registration.md),
[OSF project](https://osf.io/2hfzt/).

### Current research milestones 4-6

As of 6 Nov 2026, the repository includes tested offline tooling:

- Create-only draw preparation and validated probing, plus CLI admission and
  optional SQL reporting through native/monitored trainer builders.
  [Preparation, probing and reporting](docs/2026-11-06-offline-preparation-and-probes.md).
- Per-sample capture of actual generator completions and original scorer results,
  without reconstructing samples from aggregate rates or rescoring them.
  [Capture contract](spec/frontier-sample-capture.md).
- Bounded evidence-binding checks and create-only save/reload of unverified
  evidence. Loading requires a separately supplied archive SHA-256 before decoding.
  [Binding checks](spec/frontier-evidence-bindings.md);
  [transport format and limits](spec/frontier-unverified-transport.md).

These checks use synthetic fixtures, including real SQLite execution. They do
not establish a real BIRD baseline, authenticate a loaded checkpoint/provider,
or qualify actual native training. Matching hashes and producer-retained pins
do not establish independent custody or genuine measurement.

| Stage | Status | Remaining work |
|---|---|---|
| 4: environment and escalation | PARTIAL | Owned-SDK lifecycle qualification and actual rollout/training compatibility. Offline CLI admission and reporting forwarding do not close those gates. |
| 5: paired untrained baseline | PARTIAL | A real retained draw, legitimate frontier measurements and authorized paired BIRD rollouts. The current BIRD baseline is missing, not zero. |
| 6: co-training and harness swap | BLOCKED | Frontier evidence, compatible runtime/template and completed training integration. The training CLI still deliberately refuses the incomplete path after preflight. |

SQL reuse and separate local MLX work do not complete this research sequence.
The MLX comparison is inconclusive; its three-seed trial is incomplete.
See the [evidence index](docs/evidence-index.md) and
[native training contract](spec/native-training.md).

## Tests

**3,803 tests passed on 30 Oct 2026** in the dated configured offline run.
[Source-bound receipt](docs/2026-10-30-portable-sql-skill-sdk-acceptance.md).
The original log is machine-local, not bundled with a clone. This is not a claim
that all tests pass on the current branch.

The focused regression on 6 Nov 2026 passed **510 tests across seven
selected offline modules** at
[`b9e946c`](https://github.com/nikolas-sapa/co-train/commit/b9e946cba373b131a9f41e0bbba27e78e78392f9).
It covers frontier bindings, capture, transport, probing and preparation,
including two guard-loss controls and a reproduced/fixed cleanup-cancellation
regression. This is not a full-suite or native-runtime qualification. Its logs
are also machine-local; overlapping historical counts must not be added.

The 9 Nov source-publication checks parsed **72 Python sources**, matched
**12 frozen source pins**, and caught both static negative controls (missing bulk
collection exclusion and synthetic-fixture identity drift). Python and privacy
reviews cleared that snapshot, and the normal commit secret scan found no leaks.
These are source/integrity checks, not a new full-suite, SDK or GPU test run.

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
The root [collection guard](conftest.py) also excludes 19 parent-only qualification
test modules and the reference/mutation-control trees before ordinary collection
imports them. Explicit paths or disabling the guard do not grant execution
permission. See [source boundaries](docs/engineering-qualification-source-status.md)
and [pytest.ini](pytest.ini). No historical test bodies were rerun for this
README update.

The offline additions above are included in `main`. Their
fixture tests do not qualify owned-SDK/native execution or production activation.
Original scratch evidence is machine-local, not bundled with a clone.
The previous long README remains in
[Git history](https://github.com/nikolas-sapa/co-train/blob/a718cf53833458379adf1c3d4a8e02b89b4a958b/README.md).

Publication to GitHub is not a deployment or new experiment authorization.
Native/model/training work still requires its existing gates and permissions.

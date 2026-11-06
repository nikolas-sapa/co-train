# Offline draw preparation and probing

These interfaces prepare and consume existing local corpus artifacts. They do
not acquire a corpus, select a policy, run a provider, publish a frontier
manifest, or authorize training. Fixture checks are wiring evidence, not BIRD
measurements.

## Preparation CLI

`python -m bench.prepare_cli` exposes the existing preparation APIs:

- `freeze`: required `--root`, `--output`, `--seed`, `--simple`, `--moderate`,
  `--challenging`, and exactly one of `--fixture` / `--production`. All three
  tier counts must be positive. Existing timeout and row bounds remain in force.
- `validate`: required `--root`, `--draw`, `--output`, and
  `--expected-draw-sha256`. Mode and bounds come from the admitted draw.
- `check`: required `--root`, `--draw`, `--supplement`,
  `--expected-draw-sha256`, `--expected-supplement-sha256`, and exactly one of
  `--fixture` / `--production`. This consumes artifacts without publishing them.

Successful `freeze` and `validate` print the returned artifact SHA-256, followed
by a newline. Retain these digests independently. Admission must not derive its
expected digest from the artifact being admitted. `check` prints admitted
counts, the declared mode, and explicit non-measurement / zero-model-call status.
Declaring production mode is not independent proof of corpus provenance.

Outputs remain create-only. Existing destinations are not replaced. Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Successful operation or help |
| 1 | Known preparation or filesystem refusal |
| 2 | Invalid arguments |
| 3 | Publication indeterminate: preserve the final artifact; do not auto-retry |

Indeterminate publication is not success and is not proof the final path is
absent. The CLI neither deletes the final artifact nor retries publication.

## Admitted-draw probe

`bench.frontier.draw_probe.probe_validated_draw` accepts explicit corpus, draw
and supplement paths, both independently retained digests, a trusted generation
callback, and explicit `policy`, `g` and `dead_ceiling`. Fixture use requires
`fixture=True`.

The helper admits artifacts before any generation, probes only eligible tasks
in admitted order, forwards frozen comparison / timeout / row bounds, and
performs fresh admission again before returning the existing `ProbeResult`.
Excluded gold is not generated or silently converted to a zero. Callback
exceptions propagate unchanged.

The policy string is a label, not checkpoint authentication. The callback and
caller-owned filesystem are trusted. Post-probe admission detects observable
drift, not hostile temporary mutation followed by restoration. This helper
does not publish results or supply missing measurement provenance.

## SQL reporting bridge

`train.sql_bridge.prepare_sql_training(..., reporting=None)` preserves the
disabled path. An explicit existing `ReportingConfig` enables actual SQL QA
reporting. Preparation uses separate ephemeral prompt-building channels;
each successful environment reset gets its own fresh reporting channel.

The environment's readonly, non-callable `reporting_snapshot` property exposes
the current immutable diagnostic snapshot. It is `None` when disabled,
unbound, or after a failed reset. Program failures retain current diagnostics
until the next reset. A snapshot is not a sealed successful rollout or
persistent training evidence. Execution, rewards and quotas remain unchanged.

Both `train.native_training.build_sql_trainer` and
`train.sql_training_run.build_monitored_sql_trainer` accept the same optional
`reporting` configuration. They forward it without moving the existing
preflight gates or starting training. Omitted/`None` preserves the original
calls. Monitored callback attachment still follows successful construction.

## Remaining gates

No real corpus qualification, model frontier, paired baseline, native framework
compatibility, training, holdout, independent three-seed run, or harness-swap
benefit is established by these interfaces. Existing runtime, template,
source-isolation, lifecycle and scientific gates remain closed.

Non-goals: new artifact schemas, providers, policy selection, automatic retries,
production activation, or relaxation of historical qualification limits.

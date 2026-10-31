# SQL task-bound environment reporting

2026-10-30. Follow-on to the arm and launch reporting contracts. Stage 4 only.

## Test plan

Use temporary real SQLite databases, the real `sql_environment`, SQL arm and
program runtime. No provider, model, native container or training execution.

1. `test_enabled_report`: one valid program callback produces exactly one PTC
   event and the existing unverified acknowledgment.
2. `test_default_compatibility`: omitted `qa` and explicit `qa=None` produce
   identical prompts, single-tool schemas, budgets and SQL observations.
3. `test_opt_in_prompt`: only opt-in mentions reporting; neither prompt exposes
   the fixture's unique gold-query sentinel.
4. `test_sql_parity`: a real non-reporting SQL program has identical observations
   with reporting on/off, with zero reports and unchanged database SHA-256.
5. `test_invalid_channel`: each unsupported channel type, including false-valued
   inputs, raises before environment construction; no channel is synthesized.
6. `test_invalid_report`: an invalid report produces zero accepted events and
   spends exactly one submission, with the database unchanged.
7. `test_report_quota`: nine valid callback attempts in one program retain
   exactly eight accepted reports; the ninth cannot become an accepted report.
8. `test_submission_budget`: after the existing submission cap is spent, one
   further reporting program returns the unchanged refusal and adds zero events.
9. `test_independent_channels`: two fresh caller-supplied channels receive only
   their respective environment's reports; submission budgets stay independent.
10. `test_default_no_qa_import`: a fresh interpreter can build and step the
    disabled SQL environment without importing `ptc.sql_qa`.
11. `test_unbound_factory_unchanged`: the existing zero-argument factory remains
    unbound, exposes exactly one program tool and refuses execution as before.
12. `test_channel_released`: after caller and environment references are dropped,
    the supplied channel is collectible, with no process-global owning registry.

Run the new file plus affected training, arm, collector, sealed episode/capture
and binding tests. Verify a behavioral control: deliberately drop the enabled
forwarding in memory, observe the real enabled-report test fail, restore it and
observe that test pass. Retain the control receipt outside the repository.

## Non-goals

No TRL rollout adapter, trainer activation, native/isolated report transport,
production Bash verifier route, CLI/config activation or new capture schema.
No gate, reward, gold, void, validity, action-cap or model-tool changes.
No paid/provider/model call, training, download, install or native job.
No automatic report persistence, authentication, integrity or kernel claim.
No global cross-environment channel-reuse detection: callers must supply fresh
channels when they need separate rollout telemetry.

## Implementation plan

Add keyword-only `qa=None` after the existing positional `task, root` parameters
of `train.grpo_ptc.sql_environment`. Forward an explicitly supplied channel to
`build_sql_arms`; preserve the existing builder call on the disabled path.
On opt-in, require a concrete `QaChannel` before building an environment; reject
classes, factories, lookalikes and subclasses rather than failing in a program.
Reuse the arm's enabled prompt, scoped callback, parser, quotas and acknowledgment.
Keep imports local and channel persistence caller-owned. Return the same
`(prompt, PTCEnvironment)` shape. Do not change `environment_factory` or preflight.
Existing sealed capture and episode APIs remain reporting-disabled; this seam
does not make their evidence reporting-config-bound.

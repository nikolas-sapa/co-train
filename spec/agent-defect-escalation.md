# Agent defect escalation, stage 4 increment

2026-10-30. Implementation contract, not experiment authorization.

## Test plan

1. `test_default_reporting_is_inert`: zero report names/markers in default
   prompts/catalog/wrapper; existing default observations and budgets unchanged.
2. `test_both_real_arms_report`: real restricted Python and `/bin/sh` routes each
   retain one equal allegation and return the same fixed, fence-free receipt.
   No second registered PTC model tool.
3. `test_invalid_reports_and_caps`: reject duplicate/extra JSON keys, invalid
   UTF-8, nonfinite values, wrong types/kinds and canonical payloads above 2,048
   bytes. At most eight accepted reports and 32 events per arm, 64 events total;
   one arm cannot exhaust the other's allowance. Export at most 65,536 bytes.
4. `test_reporting_preserves_failures_and_reward`: report then real SQL failure
   preserves the error and prior report. Correct/incorrect final SQL retain
   identical independent scorer results with/without reporting. Database bytes,
   turn limits and final-answer extraction are unchanged.
5. `test_real_shortcut_fixture`: a caller-instrumented, rule-legal fixture helper
   reads real SQLite data through each real execution route and records exactly
   one shortcut event per invocation; three invocations produce three events.
   A comment/string mentioning its identifier produces zero events. This is a
   controlled telemetry fixture, not proof of detecting arbitrary exploitation.
6. `test_bounded_export_and_negative_controls`: repeated exports are stable;
   malformed/report floods stay bounded. Observe intended RED failures when
   kind validation or reporting forwarding is removed, then restore GREEN.
7. `test_default_native_import_closure`: original native-role source staging
   imports and executes the default reporting-disabled route without the new
   optional module. No Docker job is required or authorized.

## Scope and fixed interface

Implement `ptc/sql_qa.py` and opt-in integration in `ptc/sql_arms.py`.
`QaChannel` is a caller-owned, in-memory collector. Its closed report payload is
`{"kind": ..., "detail": ...}`. Kinds are `task_defect`, `verifier_defect`,
`environment_defect`, and `other`. Both values must be strings; detail must be
nonempty. The 2,048-byte limit applies to canonical UTF-8 payload bytes.

The collector exposes `submit(arm, *, kind, detail)`, `submit_raw(arm, raw)`,
`consume_output(arm, text)`, `record_shortcut(arm, shortcut_id, *, provenance)`,
an immutable event snapshot, and `export()` canonical JSON bytes. Rejections use
`ReportRejected`; the PTC adapter converts them to existing `ProgramRejected`.
Arm names are exactly `bash` and `ptc`. Caps apply independently to each arm.
Overflow is visible and bounded, never a successful receipt for a dropped report.

`QaChannel(shortcut_ids=())` defaults to no allowed fixture shortcuts. IDs are
caller-supplied bounded identifiers, not parsed from arbitrary source text.
The fixed receipt is `report received (unverified allegation; outcome unchanged)`.
Exports are snapshots, not authenticated or append-only logs. The caller owns
any later persistence and must not expose a durable sink path to the shell.

The optional shell command is `report_defect '<single-line JSON object>'`.
Its public marker is `COTRAIN_QA_REPORT `; fixture marker is
`COTRAIN_QA_SHORTCUT `. Host parsing validates exact markers and schema.
Markers can be forged by shell output: shell events have `agent_output`
provenance, never authenticated-call provenance. Invalid reporting must remain
visible without suppressing SQL stdout/stderr or changing actual exit status.
PTC callback events have `catalog_callback` provenance conditional on the
existing in-process interpreter boundary. Neither provenance proves the claim.

Add keyword-only `qa=None` to real runner/catalog/pair construction surfaces.
Keep all existing default calls and backend signatures compatible; reject
reporting on unsupported backends explicitly rather than bypassing a backend.
Only the known in-process runner is in scope. Reports occur within existing
actions, never grant additional turns, and never become scoring/void inputs.
The new module must be imported lazily only when reporting is enabled so the
default native source closure does not silently acquire a missing dependency.
Reporting prompt semantics must be equal across arms; the PTC model still sees
only `run_program`, with `report_defect` inside its program catalog.

## Non-goals and evidence limits

No native wire/schema change, isolated-guest reporting, production verifiers
bash-runner wiring, training-environment changes, or `SqlEpisode` schema change.
Do not add reporting to sealed episode/capture APIs without binding its
configuration and source dependencies in a separately reviewed contract.
No kernel isolation claim for host shell or in-process Python; a same-UID shell
is not made filesystem-safe by adding this collector.

No reward, gold, success/validity, action-budget or protected training/financial
gate changes. No model calls, training, native SQL jobs, installs, downloads,
new experiment budget, or changes to unrelated worktrees. Source-byte changes
version the instrument and invalidate old pins; never repin old receipts.

This increment advances stage 4; it does not complete all stage 4 isolation/
production-wiring requirements or supply stage 5/6 scientific evidence.

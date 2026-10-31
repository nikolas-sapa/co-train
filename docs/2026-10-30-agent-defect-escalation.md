# Agent defect reporting, 2026-10-30

Stage 4 remains PARTIAL. The opt-in in-process PTC catalog and actual shell
runner now carry structured reports and controlled shortcut telemetry.
The [source-bound evidence follow-on](2026-10-30-sql-reporting-evidence.md)
adds opt-in episode v2/capture v3 configuration and telemetry binding.
Production verifiers bash routing, framework/CLI activation, isolated reporting
and actual TRL integration remain unfinished. Cover those before live experiments. Priority stays
4 -> 5 -> 6; the current BIRD paired baseline is absent and stage 6 is blocked.
Further SQL-native acceptance is not a stage 4 prerequisite.

The original collector/arm work used base `91336c8`; the launch follow-on uses
base `1ded101`; the task-bound SQL environment follow-on uses base `0a14352`.
Validation below separates those increments.
Implementation: [collector](../ptc/sql_qa.py),
[arm API](../ptc/sql_arms.py), [core tests](../ptc/test_sql_qa.py) and
[real-route integration tests](../ptc/test_sql_qa_integration.py).

## Opt in through the arm pair

Given an existing task accepted by `build_sql_arms` and a caller-owned wrapper
directory, both routes use the same channel:

```python
from pathlib import Path
from ptc.sql_qa import QaChannel
from ptc.sql_arms import build_sql_arms

channel = QaChannel(shortcut_ids=())
pair = build_sql_arms(existing_task, qa=channel)
pair.run("ptc", 'print(report_defect(kind="task_defect", detail="Missing table"))')
pair.run("bash", """report_defect '{"kind":"task_defect","detail":"Missing table"}'""",
         bindir=Path("/absolute/caller-owned/wrappers"))
snapshot = channel.export()  # Canonical JSON bytes; caller owns persistence.
```

`pair.catalog()` and `pair.run()` forward the collector to the real backend.
Unsupported backends raise `NotImplementedError` before execution.
Default `qa=None` neither imports the optional QA module nor installs/names a
report command. PTC still has exactly one model-registered tool, `run_program`;
`report_defect` is a callable inside its program catalog, not a second tool.
Both prompts share reporting semantics, capabilities and budgets; their route
paragraphs differ. See the [opt-in parity note](harness-parity.md#opt-in-defect-reporting-2026-10-30).

## Opt in through `PTCHarness.launch`

The follow-on [launch contract](../spec/agent-defect-escalation-harness.md)
adds constructor-only `qa_factory`, not a CLI or config-schema flag. Each
enabled launch passes its exact `TaskData` to the factory. The caller owns
the returned channel and any persistence:

```python
from ptc.harness import PTCHarness, PTCHarnessConfig
from ptc.sql_arms import sql_catalog
from ptc.sql_qa import QaChannel

owned_channels = []

def new_channel(data):
    channel = QaChannel()
    owned_channels.append((data, channel))
    return channel

harness = PTCHarness(
    PTCHarnessConfig(max_turns=8),
    catalog=sql_catalog(db_path),  # Existing caller-owned database path.
    qa_factory=new_channel,
)
```

Construction makes no model request. The real launch adds the shared reporting
prompt and a launch-local catalog callback; it still registers only `run_program`.
Return a fresh exact `QaChannel` each time. Reusing a still-live channel on the
same harness refuses, even if its earlier launch completed. Tracking is weak,
not an owning channel history. Caller retention in the example is explicit.

Local or discovered MCP `report_defect` collisions refuse before model requests.
Do not combine this factory with an already reporting-enabled `pair.catalog()`.
Factory exceptions and wrong return types fail explicitly. With no factory,
the default launch does not import QA or change its catalog/prompt.
Default harnesses remain deep-copyable and pickle-round-trippable. Enabling
reporting after constructing a disabled harness is explicitly unsupported.
This covers the in-process launch entrypoint, not config-driven activation,
production bash, isolated reporting, sealed captures or TRL.

## Opt in through the task-bound SQL environment

The [environment contract](../spec/agent-defect-escalation-sql-environment.md)
adds keyword-only `qa` to `train.grpo_ptc.sql_environment`. It uses the existing
arm callback and quotas, with the same single program tool and submission cap:

```python
from ptc.sql_qa import QaChannel
from train.grpo_ptc import sql_environment

channel = QaChannel()
prompt, environment = sql_environment(existing_task, qa=channel)
observation = environment.step(
    'print(report_defect(kind="other", detail="Example unverified allegation"))'
)
snapshot = channel.export()  # Canonical bytes; caller owns persistence.
```

Supply a concrete `QaChannel`; classes, factories and other types refuse before
environment construction. Use a fresh channel for each independent rollout.
Unlike `PTCHarness.launch`,
this factory does not reject sharing a channel across environments. The live
environment references its channel; neither a global registry nor a persistent
sink is created. Omitted `qa` and `qa=None` preserve the disabled route.

This is the task-bound environment seam, not a completed TRL rollout adapter or
training activation. The unbound `environment_factory`, training gate and main
CLI remain unchanged. Sealed capture/SqlEpisode APIs still use disabled reporting;
this addition does not bind reporting configuration into their evidence or add
native/isolated report transport.

## Payload, bounds and trust

The closed JSON object has exactly `kind` and `detail`. Kind is one of
`task_defect`, `verifier_defect`, `environment_defect`, `other`; detail is a
nonempty string. Canonical UTF-8 payload limit is 2,048 bytes; raw preparse
limit is 8,192 bytes. Strict parsing rejects duplicate/extra keys, nonfinite
numbers, invalid UTF-8 and surrogates. Refusals never echo submitted payloads.
`ReportRejected` is a `ValueError`; the PTC adapter converts it to `ProgramRejected`.

Each arm accepts at most 8 reports and stores at most 32 events; total storage
is 64 events and export is at most 65,536 bytes. Dropped counters saturate at 64
with a visible `dropped_saturated` flag. Each `consume_output` call appends at most
8 feedback lines plus one cap notice; all recognized markers still count.
Shortcut allowlists hold at most 8 ASCII identifier IDs, each at most 64 chars.

Acknowledgment is `report received (unverified allegation; outcome unchanged)`.
Reports never change reward, gold, validity/voids, finalSQL, action budgets or
extra turns. The thread-safe collector is caller-owned memory with read-only
event copies and deterministic canonical-JSON export, not a durable sink,
authenticated journal or append-only service. No protected journal path is
exposed to the agent.

Catalog callbacks use `catalog_callback` provenance. Shell collection scans
exact line prefixes `COTRAIN_QA_REPORT ` and `COTRAIN_QA_SHORTCUT ` (trailing
spaces required) with `agent_output` provenance. Command output, including
ordinary SQL rows, can forge those markers. They do not authenticate a tool
invocation. Original stdout/stderr remain unmodified prefixes with bounded
feedback appended; the actual shell return status is preserved. This makes no
host-shell or same-UID filesystem sandbox claim.

`record_shortcut` is trusted caller instrumentation for allowlisted fixtures,
not source-substring detection. The test-only helper reads real SQLite:
3 invocations produce 3 events per arm; comments/mentions produce 0.
PTC uses the callback; shell telemetry remains forgeable output. This proves a
controlled rule-legal shortcut fixture, not a general exploit detector,
production gold oracle or kernel acceptance.

## Task-bound environment validation, base `0a14352`

Final affected selection: **1,446 passed in 46.43s**, across
`train/test_sql_environment_qa.py`, `train/test_train.py`,
`train/test_frontier_measurement.py`, `train/test_native_training.py`,
`train/test_sql_episodes.py`, `train/test_execution_binding.py`,
`train/test_sql_capture.py`, `train/test_sql_skill_sdk_acceptance.py`,
`train/test_sql_capture_comparison.py`, `train/test_sql_pilot_api.py`,
`train/test_sql_skill_workflow.py`, `ptc/test_sql_arms.py`, `ptc/test_sql_qa.py`
and `ptc/test_sql_qa_integration.py`. No failures, skips or warnings reported.
This is 19 new cases plus 1,427 existing cases, not a full-suite/native result.

The first new-test run caught five invalid channels becoming program errors
instead of construction refusals. Early concrete-channel validation now rejects
those inputs, including false-valued inputs; the disabled route stays lazy.
An actual enabled-report test went RED at call phase when arm-builder forwarding
was dropped in memory, then passed in a fresh restored interpreter. Source
hashes stayed unchanged. Python review approved the final source/tests statically.

SWE-2 sessions `gaudy-chef` and `empty-backpack` supplied implementation and tests;
the parent corrected admission, tightened tests and ran validation. Local receipts:
`~/scratch/co-train-2026-10-30/sql-environment-qa-0a14352/forwarding-control-receipt.json`
and `final-suite-receipt.json`. These local artifacts are not shipped in a clone.
`train/grpo_ptc.py` bytes changed; old source-bound profiles/receipts stay historical,
not repinned or replayed. No product-provider call, training or native job ran.

## Launch follow-on validation, base `1ded101`

The parent ran one frozen-source selection: [14 launch lifecycle tests](../ptc/test_harness_qa.py),
`ptc/test_harness.py`, `ptc/test_sql_qa.py`, `ptc/test_sql_qa_integration.py`,
`ptc/test_sql_arms.py`, `train/test_sql_episodes.py`,
`train/test_execution_binding.py` and `train/test_sql_capture.py`:
**813 passed in 40.40 seconds, no skips**. No full suite was rerun. This total
is not additive with the historical selection below.

Two in-memory controls failed at test call phase and restored green:
dropping accepted report storage broke the real-launch event assertion;
restoring unconditional lock allocation broke default copyability.
Final implementation/test hashes stayed unchanged during controls.
Local receipt: `~/scratch/co-train-2026-10-30/harness-qa-1ded101/final-negative-controls.json`.
Python review approved source/tests; security review approved implementation.
Reviews were static, not execution evidence.

Pre-publication fixes: the first concurrency test did not force overlap;
an async barrier now does. Unconditional lock allocation broke default
`deepcopy`; tracking is now allocated only when enabled, and both deepcopy
and pickle round-trip have regression coverage. The first control driver
matched the wrong failure text; its corrected run and initial incident remain
recorded. Repeated in-process control invocations emitted the `anyio` already-
imported assertion-rewrite warning; the frozen 813-test run emitted none.
No product-provider calls, training or native jobs were run for this increment.

## Original collector/arm validation, base `91336c8`

| Parent-recorded selection | Result |
|---|---|
| Core QA 74 + integration 15 + original SQL arms 28 | 117 passed, 6.57s |
| `ptc/test_harness.py`, `train/test_sql_episodes.py`, `train/test_execution_binding.py`, `train/test_sql_capture.py` | 682 passed, 33.73s |
| `ptc/test_sql_isolation.py`, `train/test_sql_skill_sdk_acceptance.py`, keyword selection `source or worker or staging or native_call or fixture_factory or missing_explicit` | 49 passed, 639 keyword deselected, 10.16s |

Total: 848 targeted passes across distinct files, no skips. The 639 are keyword
filtering, not the two default tokenizer deselections. No post-feature full
suite was run; the older 3,803-pass full suite applies to earlier source.
Two real in-memory controls turned RED and restored GREEN without source edits:
accepting kind `bug` broke `test_submit_rejects_bad_kind`; removing backend QA
forwarding broke `test_pair_run_and_catalog_forward_qa` at call phase.
Local evidence: `~/scratch/co-train-2026-10-30/stage4-swe2-91336c8/negative-controls-receipt.json`
and sibling `forwarding-control-red.log`; scratch is not shipped in a clone.

The isolated native wire is unchanged and does not carry reports. The old
16-file native closure lacks the optional QA module; reporting-disabled lazy
import/execution has targeted coverage. Opt-in QA is outside that old pin
closure and has no sealed SqlEpisode configuration binding. `ptc/sql_arms.py`
bytes changed: historical instrument/profile pins are intentionally stale.
Do not repin, reissue or replay old receipts. Earlier native 19/15-job evidence
is bounded history with consumed permissions, not this feature's proof.
No experiment, model, native, install or training permission is created here.

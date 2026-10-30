# Agent defect reporting, 2026-10-30

Stage 4 remains PARTIAL. The opt-in in-process PTC catalog and actual shell
runner now carry structured reports and controlled shortcut telemetry.
Production verifiers bash routing, isolated-wire reporting, capture/SqlEpisode
configuration binding and TRL integration remain unfinished. Next: cover those
routes and bind reporting configuration before live experiments. Priority stays
4 -> 5 -> 6; the current BIRD paired baseline is absent and stage 6 is blocked.
Further SQL-native acceptance is not a stage 4 prerequisite.

This records feature work against base HEAD `91336c8`, not a new published
revision. Implementation: [collector](../ptc/sql_qa.py),
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

## Recorded validation, not rerun by this docs worker

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

# Defect reporting through PTCHarness.launch

2026-10-30. Follow-on to the bounded collector contract. No experiment authority.

## Test plan, before implementation

1. `test_launch_default_inert`: unchanged default catalog, prompt and single
   registered `run_program` tool; zero QA factory calls or optional QA imports.
   `test_launch_default_copyable`: one default harness still deep-copies and
   pickle-round-trips, as the committed default does. No disabled-path locks
   or weak-tracking objects may break that compatibility.
2. `test_launch_collects_real_report`: scripted SSE transport drives the real
   `PTCHarness.launch` and restricted interpreter. One report produces exactly
   one caller-visible PTC event with `catalog_callback` provenance and the fixed
   receipt in the next model request. Real temporary SQLite remains queryable.
3. `test_launch_bad_report_and_cap`: invalid kind gives visible rejection and
   zero accepted reports; nine submissions accept eight, refusing the ninth.
   Factory integration never increases configured model-turn limits.
4. `test_launch_scopes_collectors`: two sequential and two concurrent launches
   on one harness obtain distinct caller-owned channels, with no crossed events.
   Reusing one live channel on that harness refuses before any model request;
   tracking is weak, not an owning history of completed channels.
5. `test_launch_rejects_collisions`: with reporting enabled, a local or discovered
   MCP `report_defect` cannot replace the collector. Refuse before model requests
   and never call the colliding tool. Discovery itself is mocked, not networked.
6. `test_launch_preserves_failure`: a report followed by a real SQL failure keeps
   its event and the original error observation. Reports cannot alter independent
   correct/incorrect execution-accuracy scores or the database bytes.
7. `test_launch_factory_errors`: noncallable factory, wrong returned type and
   factory exceptions fail explicitly, without a model request or false receipt.
8. Behavioral control: dropping accepted report storage makes the real-launch
   report-retention test fail; restoring it makes the same target pass.

## Implementation contract

Add keyword-only `qa_factory=None` to `PTCHarness.__init__`, after the existing
config/catalog/transport parameters. A callable factory receives the exact
launch `TaskData` and returns a fresh `QaChannel`. The caller owns those channels
and any export/persistence. No result-schema, config-schema or sealed API change.

Only the enabled launch path imports QA. Add a keyword-only `report_defect`
catalog callback using existing submit/receipt/rejection semantics, and append
the existing shared `REPORT_PROMPT` to the model system text. The callback stays
inside the program catalog; `TOOLS` remains exactly one model tool.

Reject local/MCP name collisions with `report_defect` on enabled launches.
Default MCP behavior is unchanged. Do not infer activation from a tool's name.
Reject the same live channel being returned twice on one harness, including
concurrent launches, using lock-protected weak identity tracking. Do not retain
completed channels or put task/report state on a shared instance catalog.
The factory is trusted caller configuration, not a global authenticity boundary.

Keep original launch signature, loop, budgets, output/error behavior and
sampling/interception routing. No extra persistence callback or swallowed
factory exception. Use existing dependencies only. Implementation owns
`ptc/harness.py`; tests own new `ptc/test_harness_qa.py`.

## Non-goals

No production bash integration, native wire changes, capture/SqlEpisode binding,
CLI/config activation, TRL integration, authenticated journal or kernel claim.
No changes to collector/SQL arm/scorer semantics or protected experiment gates.
No model/provider calls, native jobs, training, installs, downloads, VM/container
changes or other worktrees. Tests use scripted HTTPX transport, real restricted
Python and temporary SQLite only. Source changes stale old pins, not old history.
This advances the real launch entrypoint, not full stage-4 production acceptance.

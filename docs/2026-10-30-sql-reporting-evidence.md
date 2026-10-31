# Reporting-aware SQL evidence

2026-10-30, base `aefe666`. Stage 4 remains PARTIAL. The
[test-first contract](../spec/sql-reporting-evidence.md) specifies opt-in
scripted episode v2 and incremental capture v3. Existing episode v1 and capture
v1/v2 keep their legacy wire shapes and reporting-disabled defaults.

## Explicit configuration, separate expectation

The opt-in configuration is immutable and has a fixed reporting mode/version.
Shortcut IDs must be a sorted unique tuple of at most eight existing valid
ASCII identifiers. Reporting limits are not configurable.

```python
from train.sql_reporting import ReportingConfig
from train.sql_episodes import (
    record_scripted, encode_episode, decode_episode, rescore_sql, reexecute_sql,
)

config = ReportingConfig()
episode = record_scripted(
    task, arm="ptc", actions=trusted_programs, final_answer=submitted_sql,
    ids=ids, reporting=config,
)
loaded = decode_episode(encode_episode(episode))
result = rescore_sql(loaded, task, ids=ids, expected_reporting=config)
replay = reexecute_sql(
    loaded, task, ids=ids, allow_execution=True, expected_reporting=config,
)
```

These are trusted host execution APIs, not a sandbox or new model tool.
`task`, `ids`, `trusted_programs` and `submitted_sql` are caller-owned inputs.
Use the operator's independently retained configuration for `expected_reporting`,
not `loaded.reporting`: deriving the expectation from the artifact defeats that
check. Recomputed artifact digests do not override expected configuration,
current sources, prompt, database, task or caller-ID checks.

Replay returns observation, score and telemetry comparisons separately.
`telemetry_matches` does not change the score or adjudicate an allegation.
Rescoring never replays recorded actions. Different capture configurations may
not be pooled as a matched comparison; telemetry itself may differ across runs.

## Incremental sessions and diagnostics

```python
from train.sql_capture import start_capture, rescore_capture

session = start_capture(task, ids=ids, allow_execution=True, reporting=config)
observation = session.step(trusted_first_program)
observation = session.step(trusted_followup_program)
capture = session.finish(submitted_sql)
result = rescore_capture(capture, task, ids=ids, expected_reporting=config)
```

Each recording/replay allocates a fresh internal collector. The same channel
feeds that execution's configured prompt and program callback. Callers do not
supply prepopulated collectors. Only the existing program submissions spend
actions; reporting grants no extra turns.

`session.reporting_snapshot` provides immutable diagnostic telemetry, including
after invalidation. It does not revive the session or turn a partial failure
into a scored/sealed success artifact. Callers still own persistence. Snapshots
are bounded at 65,536 bytes; complete artifacts retain the 8 MiB cap. Oversized
or malformed data rejects rather than silently truncating.

## Compatibility and limits

Reporting requires the new opt-in versions. Legacy formats cannot silently
carry reporting metadata or downgrade a reporting-enabled trace. Capture v3 is
in-process only; combining reporting with an isolated executor refuses before
reading its binding or dispatching a job. Native SDK execution is not upgraded.
Default paths stay lazy and do not import the optional reporting/QA modules.

Legacy encoding round-trips are preserved, not historical source fingerprints:
editing selected sources changes new instrument digests. Old receipts/profiles
remain dated evidence; do not repin, reissue or replay their consumed authority.

Reports are unverified allegations. Shell markers and ordinary SQL output remain
forgeable. A digest detects corruption/source changes, not authenticity. No
defect verdict, reward, gold, validity, void, frontier gate or native budget changes.
Production Bash verifier routing, framework/CLI activation, isolated reporting
and the actual TRL rollout adapter remain unfinished. Stages 5/6 remain
PARTIAL/BLOCKED; no current BIRD paired baseline is created by this work.

## Validation

Actual offline execution, not a full-repository or native campaign:

- 43 tracked train/PTC/mutation test files: **3,393 passed in 350.64s**,
  with 10 existing fork deprecation warnings. The two new, then-untracked
  reporting test files were excluded from that selection.
- Both new reporting test files: **170 passed in 1.79s**. They exercise strict
  codecs, both real SQLite arms, source/config/prompt drift, existing-session
  invalidation, separate replay telemetry, lazy defaults and executor sentries.
- The four-file legacy episode/capture/comparison/binding selection:
  **688 passed in 26.66s**, included in the broad existing selection, not additive.
  Legacy test builders now omit the two None-only memory fields from wire
  payloads; strict production decoders were not relaxed.
- The environment test's isolated child now passes `-B` explicitly because
  `-I` ignores `PYTHONDONTWRITEBYTECODE`; **19 passed in 0.17s** on the final
  tree. Those cases also overlap the broad selection.
- Real callback/output/shortcut collector smoke, scripted Bash/PTC
  record/encode/decode/replay/rescore, and reactive capture/rescore passed.
  Missing expected configuration and reporting plus executor refused.
- Fresh-interpreter controls: **26 GREEN**, then bypassing expected-config
  checks made **9/9 RED**; masking source changes made **12/16 RED** (the four
  independent prompt checks stayed GREEN); forcing telemetry equality made
  **1/1 RED**; restored selection **26 GREEN**. All failures were intended
  call-phase assertions/refusals. Eight source/test SHA-256 bindings stayed
  unchanged across the controls.

Initial legacy tests had four failures from the added dataclass fields in
`asdict` fixture payloads. Initial new tests had eight failures from fixture/API
mismatches, corrected without weakening production checks. The first control
driver missed pytest's rewritten `assert ...` failure format for the telemetry
case; its failed classification was preserved, corrected, and all controls
rerun successfully.

Actual SWE-2 High workers produced the codec, record/session integration and
tests. Parent verification included bounded cyclic-input rejection and forged
snapshot revalidation. Static security and final Python reviews both approved;
reviewers did not claim to execute tests.

Local control evidence:
`~/scratch/co-train-2026-10-30/sql-reporting-evidence-aefe666/controls-receipt.json`.
It binds the five production reporting source files and three reporting-related
test files. Digests detect corruption, not authenticity.

No product-provider call, training, install/download or native job ran. No such
execution is authorized by this document. No savings or BIRD baseline measured.

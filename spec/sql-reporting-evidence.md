# Source-bound SQL reporting evidence

2026-10-30. Base `aefe666`. The user delegated the format decision: use opt-in
scripted episode v2 and incremental capture v3. This is stage-4 infrastructure,
not a completed baseline, training route or native experiment.

## Test plan, before implementation

Use real temporary SQLite, the real PTC runtime and actual host Bash wrapper.
Observe dispatch/scorer calls with wrappers, never substitute invented results.

| Test | Numeric acceptance criterion |
|---|---|
| Legacy compatibility | Existing episode v1 and capture v1/v2 canonical records decode/reencode byte-identically. Disabled prompts/observations and old call signatures remain valid; fresh disabled execution imports 0 reporting/QA modules. Fresh source fingerprints may change. |
| Strict configuration | Frozen exact configuration type; mode/version and sorted unique allowlist validated. Reject bool-as-version, classes, factories, unsupported mode/version, non-tuples, duplicates, unsorted IDs, invalid IDs and more than 8 IDs before execution. |
| Reachable snapshots | Accept real callback/output reports, rejections, shortcut provenance and overflow, including 32 events/arm, 64 total, and saturated dropped counters. Existing collector export v1 bytes remain unchanged. |
| Malformed snapshots | At least 15 malformed variants reject: duplicate/unknown keys, version/type errors, nonfinite/invalid UTF-8, invalid event schemas/provenance, sequence/order/arm errors, quota/counter inconsistencies and unknown shortcut IDs. Snapshot bytes capped at 65,536; no truncation. |
| Scripted recording/replay | Both Bash/PTC execute exactly 2 real actions each and record at least 1 allegation. Replay executes exactly those 2 actions through a fresh collector; observations, score and telemetry match independently. |
| Incremental lifecycle | Two reactive steps then finish preserve exact telemetry. Finish/rescore execute 0 recorded actions; abort scores 0 times. Finished/aborted/invalidated sessions allow 0 later successful submissions. Two sessions have separate quotas. |
| External configuration | Missing/different expected configuration rejects before any replay action or scorer call, even after valid artifact digests are recomputed. Test a structurally valid different allowlist, not just parser rejection. |
| Source/prompt binding | Change QA source, reporting-contract source and configured prompt independently. Each rejects before next dispatch/scoring, even with recomputed artifact digests. No artifact-supplied source path is used to read a file. |
| Telemetry comparison | Alter real callback telemetry during replay without altering acknowledgment/observations/score. Observation/score flags stay true; telemetry match becomes false. |
| Admission/downgrade | Reporting with any isolated executor rejects before reading its binding/dispatching a job. Stripped reporting metadata and reporting fields in legacy versions yield 0 accepted downgrades. Decode builds 0 environments, dispatches 0 actions and scores 0 times; whole artifacts remain capped at 8 MiB. |
| Comparison boundary | Capture comparisons with otherwise matching v3 records but different reporting configurations refuse aggregate statistics with a reporting mismatch. Legacy pairing remains unchanged. |
| Failure retention | An invalidated reporting session retains accessible diagnostic telemetry, without creating a scored/sealed success artifact. Oversized snapshots fail loudly, with 0 silent truncations. |

Run existing episode/capture/binding, comparison, QA, environment, SDK/workflow
and training-gate regressions. After GREEN, run 3 real in-memory controls:
bypass external expected-config comparison, memoize source binding so changed
reporting sources are ignored, and force telemetry equality. Each must cause
an intended test call-phase assertion failure, then pass restored. Import,
collection and unrelated stale-source failures do not count as killed mutants.

## Non-goals

No provider/model calls, training, downloads, installations, native jobs,
receipt repins, frontier/scorer/gate relaxation or unrelated worktrees.
No isolated report transport, production Bash verifier activation, CLI config,
TRL rollout adapter, incremental action-replay API or defect adjudication.
No authentication or kernel-safety claim. Reports remain unverified allegations;
digests detect corruption and source changes, not forgery.

## Shared reporting contract

New `train/sql_reporting.py` imports no episode/capture module or heavy framework.
It may import `ptc.sql_qa` because only opt-in paths import this module.

- `ReportingConfig(version=1, mode="defect_reports", shortcut_ids=())`: frozen
  dataclass; exact concrete type; exact integer version 1 and fixed mode;
  allowlist is an exact tuple of at most 8 sorted unique valid existing ASCII
  shortcut IDs. Reject noncanonical input rather than silently normalize it.
- `ReportingSnapshot(data: bytes)`: frozen validated canonical collector export
  v1, at most 65,536 bytes. Strict parser, immutable bytes. Constructor validates
  keys, types, events, bounds and counter relationships without executing code.
- `validate_config(config)`, `config_to_dict(config)`, `config_from_dict(value)`.
  The wire config has exactly `version`, `mode`, `shortcut_ids` (JSON array).
- `snapshot_to_dict(snapshot)`, `snapshot_from_dict(value)` map immutable
  snapshots to/from the existing collector export object, not base64.
- `validate_snapshot(snapshot, config, *, arm=None)` also checks shortcut
  membership; when arm is supplied the other arm must have empty events and
  zero reports/dropped counters, preventing cross-arm mixing in one record.
- `make_channel(config)` creates a fresh exact `QaChannel`; no externally
  populated channel is accepted by recording APIs.
- `snapshot_channel(channel, config, *, arm=None)` checks exact channel type,
  immutable allowlist equality and snapshot validity.
- `require_expected(recorded, expected)` validates independent expected
  configuration and rejects any difference, including enabled/disabled mismatch;
  it returns None on success, not a derived configuration.
- `snapshots_equal(left, right)` compares validated canonical snapshot bytes.
- `instrument_sources(root, base_paths)` returns `(paths, sha256)` with the
  existing static source paths plus `ptc/sql_qa.py` and `train/sql_reporting.py`.
  Preserve base ordering; append only missing paths. Hash ordered `(path, file
  SHA-256)` pairs as canonical JSON, matching existing source-digest conventions.
  Inputs come from trusted current constants, never artifact paths. Reject
  absolute/traversing source names; errors contain no submitted payloads.
  Reported episode instrumentation also includes its recording/binding owner,
  `train/sql_episodes.py`, in its static base paths. Capture base paths already
  include the capture, episode and environment owners. Legacy path sets stay
  unchanged.

Add only a read-only `QaChannel.shortcut_ids` property returning sorted immutable
IDs to the existing collector. Its export v1 shape, quotas, behavior and bytes
remain unchanged. Shortcut events permit the collector's existing arbitrary
valid ASCII provenance tokens, not just two hard-coded report routes.

Snapshot validation follows actual collector semantics: exact event fields;
per-arm sequence order and global contiguous unique sequence 1..total_events;
reports equal stored report-event count, at most 8/arm; events at most 32/arm and
64 total; dropped 0..64, with saturation true exactly at 64 and drops possible
only after that arm's log is full. Overflow reason is `report_cap` and follows
8 accepted reports. Report/rejection/overflow provenance uses the existing
callback/output labels; shortcut provenance follows its existing bounded token
grammar. Reject unknown keys, bools as numbers, invalid rejection reasons,
unencodable strings and oversized canonical report payloads.

## Recording and binding APIs

`SqlEpisode` and `SqlCapture` gain trailing optional `reporting` and `telemetry`
fields, defaulting to None. Legacy wire encoders OMIT both fields. Legacy
constructors reject non-None values. Reported versions REQUIRE both fields and
validate telemetry against the record's arm/configuration.

- Episode v1 stays the default; v2 is reporting-enabled scripted evidence.
- Capture v1 stays default in-process; v2 stays existing isolated evidence.
  V3 is reporting-enabled in-process only and omits isolated-only wire fields.
  Nonempty isolated fields in v3 reject. Do not reinterpret v2 as reporting.
- `record_scripted(..., reporting=None)` and `start_capture(..., reporting=None)`
  opt in with `ReportingConfig`, allocate fresh internal channels, construct the
  configured pair/environment using that same channel, and bind current enabled
  prompt plus expanded reporting source paths. Disabled builder/import calls
  stay unchanged. Reject reporting+executor before inspecting executor binding.
- Incremental sessions retain the independently supplied config, recheck external
  bindings before each action/final scorer call, and snapshot after operations
  and before terminal environment release. Add read-only `reporting_snapshot`:
  None on disabled sessions; current validated diagnostic snapshot on enabled
  sessions, including invalidated ones. It never makes invalidated evidence
  valid or performs an action/scorer call.
- `rescore_sql`, `reexecute_sql`, and `rescore_capture` gain keyword-only
  `expected_reporting=None`. Their binding paths require equality to the caller's
  independent config, then reconstruct the current enabled instrument/prompt.
  Missing expectation refuses reported evidence. Never trust the artifact's own
  config as the caller expectation or weaken existing task/ID/DB/runtime checks.
- Scripted replay uses a fresh internal channel. `ReexecutionResult` gains
  trailing `telemetry=None`, `telemetry_matches=None`; enabled replay returns the
  snapshot and a separate exact bool flag, disabled replay leaves both None.
  Existing observation/score flags keep their original semantics. No new
  incremental replay API is introduced.
- `train/sql_capture_comparison.py` pairs reporting configuration too, but never
  demands identical telemetry for comparing different runs. SDK/native consumers
  remain fail-closed, not implicitly upgraded to execute reported versions.

## Ownership and implementation boundaries

One SWE-2 worker owns `train/sql_reporting.py` plus the collector accessor.
Another owns episode/capture/comparison implementation. A third owns new tests
`train/test_sql_reporting.py` and `train/test_sql_reporting_records.py`.
Parent owns this contract, docs, reviews, actual validation, controls and Git.
Workers use file tools only, never execute, commit, install, call providers or
touch other worktrees. Public API changes beyond this contract are blockers.
Fresh isolated interpreter tests must pass `-B` explicitly: `-I` ignores inherited
`PYTHONDONTWRITEBYTECODE`. The test worker may add that flag to the existing
environment-QA test without otherwise changing its assertions.
Parent may update legacy test fixture builders to omit the new None-only
in-memory fields when constructing historical wire payloads. Keep their original
roundtrip, dispatch, mutation and size assertions; never accept those fields
in legacy decoders just to make an old `asdict` assumption pass.

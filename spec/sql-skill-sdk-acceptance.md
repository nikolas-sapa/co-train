# Portable local-fixture SDK acceptance

Status, 2026-10-30: [corrected-source offline acceptance passed](../docs/2026-10-30-portable-sql-skill-sdk-acceptance.md),
including all ten guards and the complete configured suite. Portable-helper
native qualification and both fresh-process reuses are NOT_EXECUTED.
Earlier [scratch-helper native acceptance](../docs/2026-10-29-native-sql-skill-workflow.md)
remains a separate proof, not acceptance of this new module.

## Test plan before native use

[Offline guards](../train/test_sql_skill_sdk_acceptance.py) must run without
native dispatch or added skips. All ten passed in the final closed-fixture
frozen-source validation; five controlled call-phase REDs each restored ten GREEN.
The table records required boundaries, not new native test results.

| Named test | Required boundary |
|---|---|
| `test_missing_explicit_native_context_fails_before_dispatch` | Zero dispatches/campaign creation without opt-in; missing CLI context exits nonzero, optimized Python rejects, help/import inert. |
| `test_changed_profile_or_source_pin_fails_before_dispatch` | Wrong profile/helper pin: zero dispatches and no campaign. |
| `test_changed_capture_dependency_fails_before_dispatch` | Unchanged reviewed copies authorize; change `train/grpo_ptc.py` without repinning: zero dispatches, consent/profile bytes unchanged. |
| `test_missing_or_mismatched_local_fixture_approval_fails_before_reuse` | Missing/wrong approval refuses; exact fixture record verifies with zero native dispatch. |
| `test_claimed_phase_cannot_be_replayed` | Concurrent phase refuses; first failure writes STOP; same claimed phase never replays. |
| `test_sixteenth_dispatch_is_rejected` | Phase limits 11/2/2 and total 15; no slot 16. |
| `test_native_abort_stops_remaining_dispatches` | One aborting dispatch, one reserved slot; zero subsequent dispatches. |
| `test_timer_endpoint_follows_real_sdk_final_fsync` | Non-native real SQLite: source EX=0, four qualifications/reuse EX=1; final SDK fsync inside Timer, returned identity preserved. |
| `test_final_fsync_order_control_detects_intended_red` | Moving final-fsync evidence past endpoint refuses; original observation passes. |
| `test_fixture_factory_closes_connection_before_return` | Seven real SQLite tasks with GC disabled: raw FD/thread equality after every return/readback, seven explicit connection closes before GC; raw FD delta 0. |

Native functions live in non-default-discovered
[sql_skill_sdk_acceptance.py](../train/sql_skill_sdk_acceptance.py).
Missing required native context is an error, not a skip. A collection count or
expected full-suite count is not a pass.

## Prerequisites and original policy

Fresh caller authorization, reviewed committed bytes, approved cached image,
existing approved daemon socket and working approved memory-observer executable
are prerequisites. The helper does not pull images, download dependencies,
start a VM or create an observer. It captures actual unrelated container IDs/
state; it does not assume a fixed count. It does not compare container
configuration or inspect private workload contents. The operator must collect
and compare approved unrelated-baseline/configuration evidence before/after
phases outside this CLI. Keep
unrelated workloads untouched; this guide grants no general host-audit authority.

Use an existing compatible interpreter without `-O`/`-OO` or effective nonzero
`PYTHONOPTIMIZE`; optimization rejects before helper writes. `-B` and
`PYTHONDONTWRITEBYTECODE=1` prevent bytecode writes. There are no custom consent
environment variables: authorization is explicit CLI files/pins.

Existing approved default-profile infrastructure (including the reviewed 2 GiB
VM allocation, not a new provisioning instruction) must already be ready.
Original bounds remain: memory 268,435,456 bytes, swap 0, PIDs 1, nofile 64;
PROGRAM 10s, SCORER 30s, cleanup 12s; admission headroom 469,762,048 bytes,
sample age at most 4,000ms. No limit relaxation or fallback.

## 1. Prepare and externally review profile/consent

Run from repository root only after review of the integrated commit and
separate fresh 15-job authorization. Offline validation is complete; no fresh
native execution is authorized by this document. All example `/absolute/...` paths are
caller-supplied placeholders, outside checkout with trusted nonsymlink ancestors.
The campaign parent must exist; the campaign directory itself must NOT exist.
Use new profile/consent filenames, never old consumed campaign assets.

The exact consent object has these keys, no extra schema/helper-SHA fields:

```json
{
  "format": "co_train_sdk_native_local_test_consent",
  "issuer": "parent-reviewed-local-test-assignment",
  "reviewed_revision": "<reviewed 40 lowercase hex commit>",
  "campaign_dir": "/absolute/owned-parent/new-campaign",
  "profile_sha256": "<whole profile file SHA256>",
  "source_pins": {},
  "max_native_jobs": 15,
  "phase_jobs": [11, 2, 2],
  "retries": 0,
  "model_calls": 0
}
```

This is a template, not valid authorization as printed: replace revision and
paths; populate profile/source pins below. An empty source map rejects.
`reviewed_revision` is only a caller label checked for 40 lowercase hexadecimal
characters. The CLI does NOT compare it with Git HEAD or authenticate a commit.
Before preparing/pinning a profile or issuing consent, and again immediately
before EACH phase, the operator MUST externally compare actual current Git HEAD
with the intended reviewed commit and current required-source hashes with the
independently reviewed expected pins. Refuse any mismatch; do not merely repin
unexpected bytes. Record these comparisons outside the CLI.

Profile and helper/controller file pins ARE verified by code. The helper's own
hash belongs in `source_pins`, not an invented top-level key. No new revision,
publisher, approval or authentication field is implied.

Caller preparation example using existing profile and safe-file APIs, only
after the external comparisons above. This is explicit caller preparation; the
CLI does not automatically create or acquire a profile, observer, VM or image:

```python
import hashlib, json
from pathlib import Path
from ptc import sql_isolation as iso
from train import sql_pilot_assets as assets
from train.sql_skill_sdk_acceptance import ROOT, required_source_paths

sha = lambda raw: hashlib.sha256(raw).hexdigest()
profile_path = Path("/absolute/owned-parent/new-profile.json")
consent_path = Path("/absolute/owned-parent/new-consent.json")
observer = Path("/absolute/already-approved/memory-observer")
socket = Path("/absolute/already-approved/docker.sock")
pins = {name: sha((ROOT / name).read_bytes()) for name in required_source_paths()}
source = lambda names: tuple(iso.SourcePin(n, pins[n]) for n in sorted(names))
profile = iso.make_execution_profile(
    daemon_socket=socket,
    observer=iso.MemoryObserver(binary=observer, binary_sha256=sha(observer.read_bytes())),
    program_sources=source(iso._PROGRAM_PATHS),
    scorer_sources=source(iso._SCORER_PATHS),
    controller_sources=source(pins),
)
assets.write_new(profile_path, iso.execution_profile_canonical_bytes(profile))
iso.load_execution_profile(profile_path, source_root=ROOT)
consent = json.loads(Path("/absolute/owned-parent/reviewed-consent-template.json").read_text())
consent["profile_sha256"] = sha(assets.read_file(profile_path))
consent["source_pins"] = pins
assets.write_new(consent_path, assets.canonical_bytes(consent) + b"\n")
```

This constructs local candidate context; it does not grant approval. The external
caller reviews the resulting files and exact source bytes before retaining pins.
Computing observed hashes in this example does not replace comparison with
externally reviewed expected bytes.
`required_source_paths()` supplies current controller dependencies, including
capture `SOURCE_PATHS` and `train/grpo_ptc.py`; do not hand-trim the set.
The reviewed helper's union has 31 controller-source entries; exact
PROGRAM/SCORER sets span 16 unique native files. These counts were derived from
current source, not used as a hardcoded allowlist. Recompute all pins from the
eventual reviewed commit, including any changed bound source; do not reuse the
offline fixture's inert observer/profile or an older campaign's context.

Canonical profile encoding includes its envelope and final LF. For any saved
profile/consent/approval, compute the whole-file pin externally:

```bash
python -B -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$PROFILE"
```

Set `PROFILE`, `CAMPAIGN`, `CONSENT` to the reviewed absolute paths and
`PROFILE_SHA`, `CONSENT_SHA` to their externally retained whole-file hashes
(use the same pin command with `"$CONSENT"`). These shell variables are only
argument substitution, not helper environment settings. Payload self-digests
and locally generated hashes are not authentication.

## 2. Qualify once, then stop for separate review

Flags below were checked against actual `--help` and argparse source:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m train.sql_skill_sdk_acceptance \
  --phase qualify --execution-profile "$PROFILE" \
  --expected-profile-sha256 "$PROFILE_SHA" --campaign-dir "$CAMPAIGN" \
  --allow-native-execution --consent-file "$CONSENT" --consent-sha256 "$CONSENT_SHA"
```

Qualification uses exactly 11 jobs: source PROGRAM/SCORER, source-rescore SCORER,
four qualification PROGRAM/SCORER pairs. It writes `checkpoint.json` with
`UNAPPROVED_LOCAL_TEST_FIXTURE`; candidate creation itself is data-only.
Do not interpret promotion/checkpoint existence as approval.
Timer measures synchronous file-SDK callbacks, including final directory fsync
before the endpoint and identical returned objects. Qualification's callback
includes rescore plus four cases (nine jobs); initial source generation's two
jobs are excluded. Native EX results alone do not prove timing or cleanup.

The portable helper's private `_fixture_task(directory, label, rows, table)`
constructs the same caller-authored `SqlTask` fields and quoted row-count SQL.
`_api().fixture_task` now resolves to that portable-owned factory, using
`contextlib.closing(sqlite3.connect(...))` around the transaction so the real
connection closes before return. The legacy shared `_task` is unchanged; no
production SDK/runtime behavior or public fixture API is replaced.

## 3. Create separately reviewed local-fixture approval

The external caller reads the actual candidate program, source, four captures,
promotion and checkpoint, checks canonical whole-file pins/results and supplies
this exact separate object outside the campaign. It is not automatically
derived authority from a self-authored checkpoint.

```json
{
  "format": "co_train_sdk_native_local_fixture_approval",
  "issuer": "parent-reviewed-local-test-fixture",
  "campaign_dir": "/absolute/owned-parent/new-campaign",
  "checkpoint_sha256": "<whole checkpoint file SHA256>",
  "consent_sha256": "<externally retained consent SHA256>",
  "profile_sha256": "<externally retained profile SHA256>",
  "candidate_sha256": "<reviewed whole candidate file SHA256>",
  "promotion_sha256": "<reviewed whole promotion file SHA256>",
  "approval_ids": {
    "corpus_id": "isolated-record-runtime-acceptance",
    "split_id": "approval",
    "run_id": "caller-fixture-run",
    "episode_id": "approval",
    "policy_id": "caller-authored-rowcount",
    "policy_revision": "v1"
  },
  "max_reuse_native_jobs": 4
}
```

Serialize with `assets.canonical_bytes(approval) + b"\n"` and exclusive
`assets.write_new`. Retain its whole-file hash as `APPROVAL_SHA` and absolute
path as `APPROVAL`. Do not change consent/profile, candidate, IDs or promotion
after review. Local fixture review is not cryptographic authentication, customer
permission or a production approval feature.

## 4. Two separate fresh interpreters, no retry

Run these as two separate interpreter invocations, in order, only after the
separate fixture approval above and the operator's HEAD/source-pin comparison
before each phase. Other reviewed arguments stay unchanged.

Before reuse index 0, the operator MUST independently collect PREMOVE
device/inode, mode and mtime evidence for the five historical databases, then
compare preserved destinations after movement. This is caller-side evidence
outside the CLI; the helper verifies logical DB hashes, safe expected paths,
old-path absence and preserved hashes, not inode/mode/mtime. Collect approved
unrelated-baseline/configuration evidence separately as described above.

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m train.sql_skill_sdk_acceptance \
  --phase reuse --case-index 0 --execution-profile "$PROFILE" \
  --expected-profile-sha256 "$PROFILE_SHA" --campaign-dir "$CAMPAIGN" \
  --allow-native-execution --consent-file "$CONSENT" --consent-sha256 "$CONSENT_SHA" \
  --local-fixture-approval "$APPROVAL" --local-fixture-approval-sha256 "$APPROVAL_SHA"

PYTHONDONTWRITEBYTECODE=1 python -B -m train.sql_skill_sdk_acceptance \
  --phase reuse --case-index 1 --execution-profile "$PROFILE" \
  --expected-profile-sha256 "$PROFILE_SHA" --campaign-dir "$CAMPAIGN" \
  --allow-native-execution --consent-file "$CONSENT" --consent-sha256 "$CONSENT_SHA" \
  --local-fixture-approval "$APPROVAL" --local-fixture-approval-sha256 "$APPROVAL_SHA"
```

Each reuse uses two jobs; total is 15 (7 PROGRAM, 8 SCORER). Phase 0 moves five
historical DBs into preserved storage, never unlinks them; both reuses require
old paths absent, preserved hashes, distinct fresh tasks and DB digests.
The actual file SDK receives literal execution opt-in and the verified caller
executor. Wrong approved pin must dispatch nothing.

Dispatch slot writes precede `_run_isolated`. Phase claims/locks enforce the
11/2/2 and total-15 budgets, refuse concurrency/replay and require a fresh
interpreter identity for each reuse. A native abort/exception after reservation,
or an exception inside a successfully claimed phase, attempts to write
`STOP.json` with `STOP_UNRESOLVED_NO_RETRY`. Successful phase records use
`PHASE_COMPLETE`; qualification still leaves the fixture UNAPPROVED.

Durability is conditional on successful I/O: exclusive writes flush/fsync the
file and parent directory, but write/fsync failure may leave visible partial
or not-known-durable records. STOP persistence is best effort; failure before
a successful claim or an uncatchable process loss need not produce STOP.
Do not infer completion, release budget or retry from a missing STOP/done file.
Retain claims, slots, outcomes and runtime evidence for review. Never delete
claims, rollback counters, repin failed assets or rerun consumed phases.

This helper has no `Popen` child supervisor or new SIGKILL policy. An outer
calling automation must preserve CLI exit status and lifecycle observation;
earlier scratch-helper supervision is not a feature of this module. Managed
launch tools are not product dependencies.

On success inspect `qualify.done.json`, both reuse results/done records and
`campaign-receipt.json` alongside native journals/finalization evidence.
The helper checks CLOSED jobs, original bounds, owned container absence,
recorded CLI/guardian PID absence and unchanged baseline container IDs/state.
These do not audit all host actors, configuration or private workloads.

Inside the phase claim it snapshots raw descriptor identity tuples and thread
lists, then requires exact equality after SDK/native verification, before final
checkpoint/completion-record writes. This strict raw criterion must pass without
forcing GC; the CLI does not separately measure GC-settled snapshots. Independent
OFFLINE validator raw/settled observations are a different measurement scope.
Do not sum campaigns as a quality metric.

## Non-goals

Adversarial kernel/OOM/timeout acceptance, learned/model quality,
comparative latency, dollars or human-hour savings. Source-generation jobs and
caller/bootstrap/review work are outside SDK Timer callbacks. No vendor,
registry, capture schema or runtime-policy change; existing financial gates
and separate standing Git instructions remain unchanged.

## Contract sources

- [File-SDK contract](sql-skill-workflow.md) and
  [implementation](../train/sql_skill_workflow.py).
- [Capture provenance](../train/sql_capture.py) and
  [profile/codec/runtime policy](../ptc/sql_isolation.py).
- [Native evidence validation](../ptc/sql_isolation_acceptance.py) and
  [existing isolated fixture helpers](../train/sql_skill_isolation_acceptance.py).

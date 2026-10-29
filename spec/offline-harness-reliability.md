# Offline harness reliability

2026-10-23. Baseline `ea6d2f6`. Implements the two offline recommendations
from `research/2026-10-23-harness-round2.md`, not runtime activation.

## Failure-first acceptance

### Sweep ownership

1. `test_timeout_stops_owned_work`: a real finite fixture worker and its
   descendant exceed a .10-second deadline. Before returning a timeout, the
   original owned process group is stopped and its leader reaped. No executing
   owned process or late side-effect marker remains within 1 second. An
   independent supervisor bounds the whole fixture below 3 seconds.
2. `test_cleanup_after_normal_leader_exit`: a worker exits while a descendant
   remains. Normal completion still cleans the original group; direct-leader
   exit is not completion of owned work.
3. `test_task_binding_after_timeout`: a timed-out task cannot install or
   overwrite the next task's wrapper. Real SQLite fixture values 17 and 29
   remain bound to their own tasks. Each invocation has a distinct directory;
   the parent removes only its own directory after owned work is stopped.
4. `test_real_differential_output_unchanged`: real finite fixture SQL under
   `set` and `multiset`, row-cap refusal and render differences produce the
   same differential fields as the existing direct implementation, excluding
   elapsed time. Zero changed answer/comparison semantics.
5. `test_worker_failures_are_not_success`: ordinary errors retain
   `sweep_error`; deadlines retain `sweep_timeout`; nonzero exits, absent or
   malformed worker output cannot become agreement. Cleanup failure must stay
   explicit, not become an ordinary timeout or silently continue.
6. `test_sweep_termination_guard_sensitivity`: disabling termination causes
   at least one real liveness/late-side-effect assertion to fail. Mutations
   are isolated; never edit production files to run the control.

### Offline test boundary

1. `test_default_collection_excludes_tokenizer_integration`: both existing
   contamination tokenization assertions remain collected only in an explicit
   `tokenizer_integration` selection. Default tests do not load a tokenizer,
   inspect its cache or attempt artifact acquisition.
2. `test_cold_cache_default`: empty isolated Hugging Face caches and a
   network-denying test launcher still run the default suite. All attempted
   outbound network calls fail loudly; zero attempts is required. Optional
   Torch absence remains reported, not fixed by installation.
3. `test_declared_tokenizer_artifact`: integration takes an explicit local
   artifact directory and checks the existing cached tokenizer's required
   files against exact recorded digests before loading. The receipt labels
   this as contamination-test tokenizer identity, not approved model/native
   template identity.
4. `test_missing_or_changed_tokenizer_refuses`: missing path, missing required
   file and a one-byte digest change each fail with a named artifact error.
   Zero tokenizer-loader calls occur on admission failure. Requested
   integration must fail, not silently skip or use a remote fallback.
5. `test_local_only_loader`: successful admitted loading uses the real
   Transformers tokenizer API with local-only acquisition and no remote code.
   The two existing canonical/length/bin assertions remain unchanged.
6. `test_offline_guard_sensitivity`: removing digest or local-only enforcement
   causes at least one independent negative-control failure. Fake tokenizers
   prove interface enforcement only; run the real admitted cached artifact
   separately and report its actual result.
7. `test_ptc_fresh_preserves_default_tokenizer_exclusion`: the real fresh-copy
   mutation runner preserves `pytest.ini` byte-for-byte. Its contamination
   collection retains ordinary controls and excludes exactly the two explicit
   tokenizer controls. A standalone fresh tree must not lose the offline
   boundary when the parent repository's config is outside its ancestry.

All timing values above are engineering fixture targets, not changes to SQL
arm deadlines or scientific thresholds. RED must be recorded before
implementation; a missing fixture dependency or test-harness error is not
accepted as the intended behavioral RED.

## Implementation

### Sweep lane

Replace abandoned daemon computation with one fresh Python subprocess per
query. Serialize only the existing task and comparison inputs using JSON in
the invocation's private directory, not pickle, shell interpolation or SQL
in command-line arguments. The child calls the unchanged `differential`;
the parent receives only JSON-compatible summary/error fields.

Use the existing `process_watchdog.run_bounded` session ownership on every
exit path. Do not fork a Python closure from the sweep's thread pool.
Keep `QUERY_TIMEOUT=30` and the existing outer `QUERY_TIMEOUT + 15` allowance.
Keep ThreadPoolExecutor scheduling, task IDs, set/multiset behavior, row caps,
render causes and output summary membership unchanged.

The parent owns private directory cleanup, including when the child is killed.
Keep errors and cleanup failures explicit. Do not promise containment of
hostile descendants that create a new session, Windows support or full-corpus
parity repair. Update obsolete daemon-lifetime comments where necessary.

### Tokenizer lane

Register an explicit tokenizer-integration marker, exclude it in default
pytest configuration and document the explicit selection. Preserve both
existing scientific assertions rather than replacing them with byte counts
or cached result assertions.

Use a narrow stdlib artifact-admission helper and test-scoped loader/fixture.
Record required files and digests for the already present contamination
tokenizer only. Resolve its current local bytes without any network request
or download. Integration requires an explicit local directory, with no
implicit model lookup. Only after file admission may Transformers load it.

Do not add a production environment-variable or model-download path. A
test-artifact digest manifest does not approve that tokenizer for native
training or resolve the known automatic-template rejection.

Parent admission, after behavioral RED: freeze the eight existing local
snapshot files (`tokenizer.json`, `tokenizer_config.json`,
`special_tokens_map.json`, `added_tokens.json`, `merges.txt`, `vocab.json`,
`chat_template.jinja`, `config.json`) in `bench/tokenizer_artifact.json`.
The observed snapshot is `db4e90b8359f816f09bf5c944797ce116f26da3c`.
Parent independently checked all eight SHA256 values; the standalone and
embedded chat templates also match the prior stock-template receipt
`5da44855ab7e0641774d5ed0ff0b4f89671d01df7d316e54d06557a962211cb4`.
This freezes an existing diagnostic baseline, not authenticated upstream
provenance, a weight revision selection or native-runtime approval.
Expected digests must never be regenerated from arbitrary runtime inputs.

## Ownership and validation

Two independent workers own these nonoverlapping lanes. Workers write tests
first, report RED and stop before implementation until the parent verifies
the intended failure. No worker git operations, commits, pushes or deployments.
Parent owns this spec, integration review, documentation, receipts and any
local commit boundary. Existing untracked research artifacts are preserved.

Run lane-targeted tests and independent mutations, Python/security review,
then the default suite with isolated empty caches/network denial and the
explicit tokenizer integration using the existing local artifact. Record
passes, deselections, skips and failures separately. Do not reuse historical
warm-cache success as evidence for cold-cache execution.

On this macOS host, `sandbox-exec` network denial also prevents executing the
setuid system `ps` used by two liveness fixtures. For validation only, an
unprivileged scratch observer may service their two `ps -o stat= -p PID`
argument forms using SDK-declared `libproc.proc_pidinfo`. A scratch native
observer avoids Python interpreter startup consuming the fixtures' unchanged
.20-second observer deadline. First verify real
live, unreaped and reaped children, compare the live/unreaped states with
system `ps` outside the sandbox, and test fail-closed handling of API errors.
Darwin returns ESRCH for both zombies and absent PIDs; neither is executing.
Log every observation and require zero observer errors. Preserve the tests
and network-deny profile, and retain the termination-disabled late-marker
control. This is a real process observer, not a mocked liveness result.
The final profile denies external IPv4/IPv6 traffic but permits loopback and
local Unix IPC. Existing default tests intentionally serve real local MCP
fixtures; denying loopback stalls their server startup. Python auditing counts
allowed loopback events separately from denied external attempts. Verify
external IP denial in the parent and inherited child plus actual thread wakeup
and the local MCP positive control before the full run. This is not hostile
IPC/local-proxy isolation. Strict no-IP validation cannot run the unchanged
default suite.

## Non-goals

No dependency/model install or download, paid/API/GPU/training job, new backend,
scientific version-rule/threshold/window/amendment/signature/manifest change,
model/revision/channel/G/corpus/evaluation membership selection, scorer or SQL
equality change, native-template shim, training launch, push or deployment.
Main training remains fail-closed. Reference checkout remains read-only.
No full 800/1534-query corpus rerun unless changed behavior warrants it.

## Verified result, 2026-10-23

Final cold-cache default suite: 1947 passed, one optional Torch skip, two
explicit tokenizer-control deselections, 204.38s. Both real-tokenizer controls
pass separately with zero skips. External networking is denied; local MCP
loopback traffic is permitted and counted separately. The initial strict
no-IP timeout is retained, not counted as success. Source/probe hashes and
validation-harness sources are in
[`research/2026-10-23-offline-harness-reliability.json`](../research/2026-10-23-offline-harness-reliability.json).

### Commit scanner, owner-approved follow-up

The commit hook misclassified eight public SHA256 values as generic API keys.
The owner explicitly approved exceptions for those exact eight values only.
Extend the scanner's default rules; scope anchored, case-sensitive exceptions
to the `generic-api-key` rule's captured secret, never whole paths or lines.
Before committing, prove all eight original false positives disappear while
an unrelated synthetic 64-hex key, an uppercase checksum, a checksum embedded
in a larger key and a synthetic provider token still fail scanning. A separate
overbroad-allowlist mutation must make the negative-control check fail.

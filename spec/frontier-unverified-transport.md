# Unverified frontier transport

Status: SELECTED OFFLINE IMPLEMENTATION CONTRACT, not genuine evidence authority.
Base: 61d13ef8fbf2f138f65c8af48bae1f8d356c5e3c.
Architect and security design reviews clear. Actual code review/testing required.

## Purpose and boundary

Losslessly save/reload captured plan, producer retention pins and opaque evidence.
This is a separate explicitly unverified persistent transport. It does not change
earlier in-memory non-goals, accept the genuine-evidence draft or authorize any
measurement/training. Producer pins and returned archive SHA are byte agreement,
not independent custody, authenticity, freshness or permission.

## Test-first acceptance

Parent test plan precedes implementation plan. Ten named numeric groups cover
28 samples/57 receipts from actual synthetic SQLite capture, strict decode,
B/B+1 resource ordering, no schema repair, filesystem/publication faults, 0 extra
execution, privacy and two valid-setup guard-loss/restored-positive controls.
All transport checks initially UNRUN.

## API and ownership

New train/frontier_transport.py and train/test_frontier_transport.py only.
Parent owns this contract and integration. No core/capture/helper edits.

write_unverified_bindings(plan, retention_pins, batch, output_path, *, limits)
returns the exact published archive SHA256.

load_unverified_bindings(path, *, expected_archive_sha256, limits)
returns frozen/slotted/repr-disabled TransportedBindings(plan, retention_pins,
batch, report). Fresh current core report, not cached output or CapturedProbe.
No issuance/session token or legacy mutable ProbeResult transported.

Use exact existing core records and explicit BindingLimits. Strictly snapshot,
core validate, then validate detached snapshots before serialization. Malformed/
duplicate core declarations refuse. Preserve semantic incomplete/invalid-gold/
inconsistent reports and array order, missing references, unused pins and bytes.

CRITICAL: before collapsing two plan projections into one, require complete
type-preserving primitive equality. Comparing only numerical tuples is too weak:
timeout30 versus30.0 refuses, even if core equality accepts it. Canonical plan
representations must match. No truncated-diagnostic acceptance oracle.

## Version1 format

Canonical UTF8 JSON, sorted keys, compact separators, ensure_ascii=False,
allow_nan=False, exactly one trailing newline. Top-level EXACT keys:
kind, version, plan, retention_pins, samples, blobs.
kind is cotrain-unverified-frontier-transport; version exact int1 (not bool).

Plan, pins and samples use exact allowlisted existing core field names. Nested
tasks/exclusions/scorer use corresponding core fields. Ordered tuple fields
serialize as arrays. Blob entries EXACT evidence_id and payload_base64, standard
padded canonical base64. Reconstruct batch.plan from that same decoded plan.
Opaque payloads transported without parsing/rescoring. Preserve numeric types.

No ProbeResult, cached report, attestation, measurement/training flags, extension
fields, candidate paths to follow or arbitrary class factories. Unknown fields/
kind/version refuse. Same SHA and fully self-consistent fabricated inputs remain
unverified. Loader requires caller-supplied expected SHA, never derives it from
candidate content or treats it as independently retained by construction.

## Bounds and allocation order

Existing BindingLimits must be within core ceilings, including item1MiB,
aggregate16MiB (metadata plus raw bytes, both reconstructed plan projections),
identifiers256UTF8 bytes, counts1024/4096/12289/12289.

Additional fixed ceilings: archive32MiB including newline; nesting12; each
object40members; total500000 JSON lexical values INCLUDING key strings;
numeric token32ASCII chars and signed64 integer, finite float. Encoded blob
maximum1398104chars (for1MiB decoded), canonical padding. Individual JSON string
lexical token (including quotes/escapes) at most the encoded-blob ceiling before
structured parsing. This can be tighter than the encoded-content cap.
These are admission ceilings, not promise every maximum core input serializes.

Writer premeasures exact escaped UTF8/base64 representation and structural/
lexical limits before large encodings/publication. Its output must satisfy all
loader ceilings. Lower transport constants in tests only, never raise ceilings.
Loader bounded file read -> supplied SHA check -> strict UTF8 -> quote-aware
lexical bounds -> JSON parse with duplicate DECODED key rejection -> exact
schema/counts -> charge all metadata and predicted decoded payload lengths
before base64 allocation -> core validation -> canonical re-encoding equality.
No truncation, unbounded aggregate expansion or parser callbacks from inputs.

Private core snapshot/budget/projection helpers may be reused without editing
core. Joint coupling review required, including both plan copies and all repeated
association strings. Type-preserving plan equality may be stricter than core.

## Filesystem and publication

Accept explicit absolute str or concrete Path arguments from trusted host, no
dotdot. Existing caller-owned directories only; never create parents. Reject
symlink ancestry/leaves and special files. No JSON-supplied path dereference.

Writer prechecks ancestry and uses ACTUAL bench.prepare._publish(doc, output):
canonical serialize, private temp write/fsync, create-only os.link, temporary
unlink and directory fsync, exact SHA return. Existing file/symlink destination
unchanged. This pathname-based helper assumes trusted non-racing filesystem;
prechecks do not establish universal race containment or immutable snapshots.

Loader walks directory descriptors with O_DIRECTORY/O_NOFOLLOW, opens leaf
nonblocking/no-follow, verifies regular fstat, bounded reads and before/after
descriptor identity metadata. Also compare final entry to opened descriptor if
claiming path-replacement detection. Close all descriptors on success/failure.
Observable drift detection is not temporary-restore or hostile-kernel proof.

## Errors and privacy

TransportError(ValueError): fixed text invalid unverified frontier transport.
TransportPublicationIndeterminateError: distinct fixed text
unverified frontier transport publication indeterminate.
Both suppress chained filesystem/content exceptions from None. Raw paths,
JSON/base64, IDs and payloads absent from public error/repr output.

Catch prepare.PublicationIndeterminateError separately and translate from None.
Preserve complete final artifact; 0 automatic retries or deletion of final.
Existing helper catches ordinary Exception postlink, not every BaseException.
Non-Exception BaseExceptions (KeyboardInterrupt/SystemExit, for example)
propagate unchanged; never describe cancellation as confirmed nonpublication.
Ordinary filesystem errors become opaque transport errors. With no active
primary operation failure, cancellation during cleanup outranks an earlier
ordinary cleanup error. Still attempt all closes; preserve an active primary
operation failure rather than mask it with a cleanup error.

## Optional capture-to-archive wrapper

2026-11-06 source-only addition; no new execution/acceptance receipt.
`bench/frontier/capture_workflow.py` exposes:

```python
capture_to_archive(
    *, plan: MeasurementPlan, checkpoint_inventory: bytes, limits: BindingLimits,
    root: Path | str, draw_path: Path | str, supplement_path: Path | str,
    expected_draw_sha256: str, expected_supplement_sha256: str, fixture: bool,
    generate: Callable[[SqlTask], str], output_path: Path | str,
) -> ArchivedCapture
```

The caller supplies all complete explicit inputs. The typed wrapper performs
one existing `CaptureSession.run`, one existing transport write, then immediate
reload with the trusted writer-returned SHA. Frozen/slotted/repr-disabled
`ArchivedCapture` contains `captured`, `archive_sha256`, `reloaded`; its shell
does not freeze the legacy mutable probe inside `captured`.

Output preflight observes admissibility, not a lease/reservation. Existing
create-only writer admission still governs publication. The returned SHA reload
establishes local round-trip byte agreement only, not external custody or
independently retained evidence. Later archive admission still requires a
separately retained external pin. No retry or transaction: propagate original
failure, including indeterminate publication, and leave a published archive
intact if publication/reload fails after creation. The wrapper grants no
provider/model/framework execution or scientific authorization.

## Read-only descriptive archive report

`bench/frontier/archive_report.py` exposes:

```python
read_archive_report(
    path: Path | str, *, expected_archive_sha256: str, limits: BindingLimits,
    dead_ceiling: float | int,
) -> ArchiveReport
render_archive_report(report: ArchiveReport) -> str
```

Load through existing transport with caller-supplied pin/limits and a fresh
`BindingReport`, never a cached report. `dead_ceiling` must be finite in (0, 1).
This is read-only descriptive arithmetic on unverified numeric declarations;
opaque payloads are not parsed/rescored to prove those declarations.

`ArchiveTaskReport` fields are `task_ordinal`, `state` (`complete`, `excluded`,
`missing`, `invalid`), `solve_rate`, `dead_fraction`, `retained`. Preserve plan
order and exclusions. Only an eligible task with all G valid, locally consistent
slots gets a rate: successes/G, existing `dead_group_fraction(rate, g)`, and
retained iff fraction <= caller ceiling. Present invalid slots outrank missing
slots. Missing/invalid/excluded rates and decisions are `None`, never zero.

`ArchiveReport` contains `tasks`, `binding_report`, `g`, `dead_ceiling`,
`n_complete_tasks`, `n_retained_tasks`, `retention`. Retention uses the original
eligible-task denominator and is `None` unless all eligible tasks are complete
and that denominator is nonzero. It does not silently reduce the denominator
to observed tasks. `provenance` is `"unverified"`, `attested_facts` is empty,
`genuine_measurement_accepted` and `training_authorized` remain false.

Render only genuine returned reports: fixed labels, numeric counts and task
ordinals, not caller IDs, paths or opaque payloads; unavailable values render
`unavailable`. Preserve planned/eligible/excluded and scheduled/observed counts.
No new estimator, retention threshold policy, scientific gate or evidence authority.

## Non-goals

No model/provider/corpus acquisition, SQL/scorer invocation by transport, network,
SDK/Docker/native framework/training, installs/dependency/vendor/global changes,
genuine acceptance/attestation/independent custody/freshness, legacy aggregate
reconstruction, durable unresolved-attempt ownership, manifest publication,
activation or external push/deploy. Ordinary new unit fixtures are not old spent
owner/archive/native qualification profiles or renewed caps.

VERIFY_REAL: Contract selected; implementation checks initially UNRUN.

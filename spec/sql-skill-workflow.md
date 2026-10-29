# Caller-owned SQL skill file workflow

## Test-first contract

Before implementation, the workflow tests must fail because the SDK is absent.
Acceptance uses real SQLite, existing capture/scorer and two independently
authored test families, not demo fixtures:

1. Each family supplies a valid EX=0 source, four disjoint qualification cases
   and two fresh reuse cases: 8/8 qualifications and 4/4 reuse scores are valid
   EX=1. Canonical capture/candidate/promotion bytes round-trip exactly.
2. Process A qualifies; separate process B receives caller approval pin/IDs
   through explicit arguments and reuses twice, with all five old DB paths
   unavailable: 2/2 valid EX=1. Approval is not extracted from the receipt.
3. Wrong external promotion pin, wrong approval IDs, modified candidate and
   absent opt-in each reject with 0 program and 0 scorer dispatches.
4. Qualification two failing stops at exactly two program submissions, writes
   both returned captures, and writes 0 promotion artifacts. No automatic retry
   or reuse. Preserve exception-carried capture evidence and re-raise; exceptions
   without a capture must never generate invented evidence.
5. Artifacts above 8 MiB, programs above 65,536 UTF-8 bytes, symlink inputs/DBs/
   output ancestors, checkout outputs and existing output directories reject
   before execution, preserving all existing bytes. Malformed input also rejects
   before execution. Writes use exclusive new directories outside checkout.
6. Mutating the external-pin guard and failed-qualification promotion gate
   must independently fail the intended assertion, not import/setup/source
   binding. Run red then restore green. Focused old and new regressions have
   zero new exclusions/skips.
7. A real SQLite qualification-one EX=1 followed by qualification-two database
   drift must raise the original `ValueError`, retain exactly the one completed
   capture byte-for-byte, submit exactly two programs, and publish zero promotion
   artifacts. The rejected second attempt has no sealed capture to invent.
8. A second PROGRAM transport fault through the existing typed abort path must
   retain both actual captures in order, with exactly two submissions and zero
   promotion artifacts. A source-rescore fault before any PROGRAM retains zero
   qualification captures. A prefix-evidence persistence fault raises loudly,
   with the original evaluator failure in its exception context and zero
   published promotion.
9. Suppressing completed-prefix exception metadata must fail the intended
   evidence-retention assertion; restore and rerun green. Existing test IDs,
   source/pin/ID/binding gates, artifact codecs and approval semantics stay intact.
   Binding drift before case two or after case four must still reject, retaining
   exactly one or four actual captures respectively, with no extra submissions.
10. After four real SQLite EX=1 qualifications, fault only the final directory
    fsync after promotion rename: raise the same `OSError`, retain four valid
    captures and a canonical UNAPPROVED `promotion.json`, and leave no pending
    receipt. Exactly four program submissions and five scores, no automatic
    reuse or approval. Baseline must pass; swallowing that final sync error must
    fail the missing-exception assertion, then restore green.

## Frozen API

All paths are absolute `pathlib.Path`, outside checkout, without symlink
components. Tasks, cases, IDs and executors are caller-owned existing types.

```python
create_candidate_file(
    source_capture: SqlCapture, *, source_task: SqlTask,
    source_ids: EpisodeIds, skill_id: str, program: str,
    output_dir: Path,
) -> Path

qualify_candidate_files(
    candidate_path: Path, source_capture_path: Path, *,
    expected_source_capture_sha256: str, source_case: SkillCase,
    qualification_cases: tuple[SkillCase, ...], ids: EpisodeIds,
    output_dir: Path, allow_execution: bool = False,
    executor: PilotExecutor | None = None,
) -> QualificationFiles

reuse_approved_files(
    candidate_path: Path, promotion_path: Path, case: SkillCase, *,
    expected_promotion_sha256: str, ids: EpisodeIds, output_dir: Path,
    allow_execution: bool = False, executor: PilotExecutor | None = None,
) -> Path
```

`QualificationFiles` is a frozen in-memory result with
`capture_paths: tuple[Path, ...]` and `promotion_path: Path | None`.
It is not a new serialized schema. Creation returns `candidate.json`;
qualification writes `qualification-1.json` through at most
`qualification-4.json`, then optionally `promotion.json`. Reuse writes
`reuse.json`. Exceptional execution evidence is `exception-capture.json`.

## Implementation plan

Reuse existing candidate/capture/promotion codecs and the authoritative
`promote_candidate`/`reuse_promoted` APIs without changing their source bindings,
scoring, admission, execution or defaults. Reuse `sql_pilot_assets.safe_path`,
`read_file`, `write_new` and directory fsync. Validate inputs/output paths and
all supplied DB paths before execution. Admit four cases using the existing
qualification manifest guard, not a second qualification policy.

Create a mode-0700 directory exclusively, after nonexecution validation.
Persist returned captures before promotion. Stage promotion under
`.promotion.pending`, then publish `promotion.json` only after every capture
and staged receipt write succeeds. Pending/partial files and any directory
left on failure are evidence, not successful qualification or approval.
No cleanup or overwrites. A write failure propagates; evidence persistence is
best effort only when storage itself fails. Exceptions without capture evidence
propagate without fabrication.

Capture-write and staged-receipt-write failures occur before publication and
leave no `promotion.json`. The final directory fsync runs **after** rename:
its failure propagates but can leave a complete canonical UNAPPROVED
`promotion.json` visible, with `.promotion.pending` absent. Durability is unknown;
file existence proves neither a successful API return nor durable qualification.
There is no rollback or deletion. The caller must require a successful
qualification API return and external review/approval with a retained pin before
using a receipt; a file left by a failed call is not returned success or approval.

For unexpected ordinary exceptions during qualification or receipt construction,
`promote_candidate` attaches `qualification_captures: tuple[SqlCapture, ...]`
containing only the captures it actually obtained, in attempt order, then
re-raises the same exception instance. There is no new exception class or
serialized schema. Existing typed PROGRAM aborts still return `(None, captures)`;
source admission/rescore failures still propagate before any qualification.
The file workflow persists attached captures as `qualification-N.json` before
re-raising. Existing `CaptureError.capture` evidence remains separately written
as `exception-capture.json`, never relabelled as a successful qualification.
It does not synthesize a capture for an attempt that failed before sealing.
Exception type, cause and `CaptureError` catch compatibility remain unchanged.
Storage errors propagate instead of claiming persistence. When persisting
exception-carried evidence fails, their exception context retains the original
evaluator error.

## Qualification is not approval

`promotion.json` is an UNAPPROVED qualification receipt. The caller must review
it out of band, retain its whole-canonical-envelope SHA256 and exact approval
IDs externally, then explicitly supply both to reuse. The SDK never infers
pins/approval IDs from an envelope, self-approves, chains reuse, or manufactures
the failed source. Source pin is likewise externally supplied. Canonical
payload self-digests are not external pins or authentication.

Evaluator code, runtime, assets, stable DB snapshots, filesystem ancestors and
approval channels are trusted. Existing safe helpers assume no hostile
concurrent ancestor replacement; this SDK adds no race-proof filesystem
sandbox or authentication. The supplied executor is passed unchanged, including
`None`. `None` selects the existing in-process path, whose AST/tracing limits
are not OS confinement, hard memory limits or production isolation.

## Non-goals

No CLI, task schema, adapter loader, new envelope, dependency/vendor, registry,
source-failure generation, bundled fixtures, models/providers, paid calls,
native executor construction, runtime selection/fallback, container trials,
production-sandbox/native acceptance, training, defaults or scorer changes.
No automatic publication, deployment, approval or reuse. Fixture success proves
workflow mechanics, not independent scientific generalization.

# Opt-in executable SQL skills

## Contract correction before implementation

The original `create_candidate(source_capture, *, source_ids, skill_id, program)`
could not derive routing declarations: `SqlCapture` records a task fingerprint,
not `source`, `shape`, or `coarse_shape`. A hash cannot recover those fields.
The approved narrow correction adds required host-only `source_task: SqlTask`.
No existing capture format, runtime, scorer, defaults, or API changes.

## Test plan (before production code)

Acceptance tests import missing APIs inside test bodies, so RED means collected
test failures, not a collection error. Run through the reviewed offline harness,
reference interpreter, PATH observer, IP-network-deny profile, cold caches and
disabled bytecode. No installs, models, providers, or training.

1. **Data admission:** creation, encoding and decoding cause exactly zero arm
   builds, dispatches and protected scorer calls. An arbitrary file-write program
   remains inert. Reject wrong task type, task ID/fingerprint, external IDs,
   aborted/invalid/successful declared source. Creation verifies only declarations,
   not actual source failure or the database.
2. **Strict immutable records:** canonical roundtrips preserve every field,
   including complete existing `ExResult`; mutation fails. Reject duplicate,
   unknown, missing, unsupported-version and incorrectly typed fields throughout
   the graph, booleans as integers, nonfinite numbers, malformed/deep JSON and
   invalid UTF-8. Program cap is exactly 65,536 UTF-8 bytes, envelope cap exactly
   8 MiB, with exact/+1 tests. Encoding recursion/Unicode failures fail closed.
3. **Opt-in:** each execution API accepts only literal `allow_execution is True`.
   Missing, False, 1 and truthy objects yield zero dispatches and scores.
4. **Origin authority:** promotion checks the externally approved entire-capture
   SHA, exact source role/IDs/task and independently rescores submitted final/gold
   SQL. Require `valid is True` and score 0. A forged recorded zero whose actual
   rescore is 1 must fail before candidate execution. Changed task/database,
   sidecars, instrument/runtime, IDs and source pin reject before dispatch.
5. **Qualification admission:** input is exactly a tuple of four external
   `SkillCase`s. All roles, routing scopes and ID provenance match. Qualification
   splits differ from source split; scoped episode IDs, task fingerprints and DB
   digests are pairwise distinct and exclude source. Check all four stable
   snapshots before the first candidate dispatch. Digest difference proves
   byte-level distinction, not independent sampling or semantic generalization.
6. **Actual reruns:** promotion runs the frozen program once per case, at most
   four sequential submissions, no replay/retry. All four actual captures must
   finish valid EX=1. No supplied report or provisional capture authorizes
   promotion. Constant-answer and wrong-table programs never promote.
7. **Output:** observation must begin at byte zero with exact `FINAL_SQL:`.
   Missing/wrong/leading prefix, empty suffix, runtime error or rejection aborts
   without scoring. Nonempty suffix passes unchanged into existing `finish`;
   it is SQL, not Python. A framed incorrect SQL legitimately scores zero.
   Keep existing 8 MiB evidence and 64 MiB extraction-work protections; do not
   implement another SQL extractor or scorer.
8. **Real transfer:** one caller-authored program discovers the only user table
   through actual SQLite catalog output, quotes its identifier using admitted
   PTC syntax, and prints row-count SQL. Four qualification databases use different
   names and 0/1/3/7 rows. Two fresh reuse databases have 11/13 rows, including an
   embedded quote in a table name. All six EX=1, exactly one submission each.
   Serialize candidate/receipt, delete origin DB and reuse in a fresh process.
9. **Approval checks:** before reuse dispatch, external entire-promotion SHA,
   candidate SHA, exact promotion IDs, source/scope equality and current
   workflow/capture binding must match. Changing program, candidate, manifest,
   evaluator source, pin or scope rejects with zero dispatch. Reuse trusts the
   externally approved receipt; it never reopens origin or qualification DBs.
10. **Regression:** unchanged 276 capture plus exact 319 legacy cases pass.
    Existing native discovery still exposes exactly one `run_program` tool.
    Default arms and trainer remain fail closed. Parent runs integrated suite
    after the separate bench fixture writer completes.
11. **Independent controls:** in-memory bypasses of source rescoring, qualification
    disjointness, actual qualification reruns, scope admission, and approved-pin
    checks must each produce at least one intended assertion failure. Generate
    fixtures after final production edits; never accept stale-binding/import
    failures as successful controls. Control scripts stay in scratch.

## API and implementation plan

`train/sql_skills.py` owns frozen records and bounded data-only codecs:

```python
create_candidate(source_capture, *, source_task: SqlTask, source_ids,
                 skill_id, program) -> SkillCandidate
encode_candidate(candidate) -> bytes
decode_candidate(data: bytes) -> SkillCandidate
encode_promotion(promotion) -> bytes
decode_promotion(data: bytes) -> SkillPromotion
```

Before deriving routing scope, creation uses the existing exact task-type,
task-payload/fingerprint and task-ID checks against the supplied capture, and
matches external `source_ids`. The host-only source task/gold are neither stored
as strings in the artifact nor exposed to the candidate namespace. Field
consistency does not authenticate source provenance, DB content or failure.

Records:

- `SkillScope(source, shape, coarse_shape)`: exact routing declarations, not proof.
- `SourceRef(capture_sha256, ids, task_id, task_fingerprint, db_sha256, instrument)`.
- `SkillCandidate(schema_version, skill_id, program, scope, source)`.
- `SkillBinding(instrument, source_paths, source_sha256)`: current capture
  instrument plus exactly `train/sql_skills.py`, `train/sql_skill_eval.py`.
- `QualificationRef(role, ids, task_id, task_fingerprint, db_sha256,
  capture_sha256, result)`, with complete existing frozen `ExResult`.
- `SkillPromotion(schema_version, candidate_sha256, scope, source, ids, binding,
  qualifications)`: exactly four immutable qualification references.

`train/sql_skill_eval.py` owns host-only frozen `SkillCase(role, task, ids)` with
roles `source_failure`, `qualification`, `reuse`, and execution:

```python
evaluate_candidate(candidate, case, *, allow_execution=False) -> SqlCapture
promote_candidate(candidate, *, source_capture, expected_source_capture_sha256,
                  source_case, qualification_cases, ids,
                  allow_execution=False) -> tuple[SkillPromotion | None,
                                                  tuple[SqlCapture, ...]]
reuse_promoted(candidate, promotion, case, *, expected_promotion_sha256, ids,
              allow_execution=False) -> SqlCapture
```

Evaluation is provisional, never promotion authority. Execution uses only
`start_capture(case.task, ids=case.ids, allow_execution=True)`, then exactly one
`step(candidate.program)`, then `finish(unmodified_suffix)` or `abort()`.
Qualification cases must be external complete inputs, never generated from source.
Promotion IDs and case IDs share source corpus/policy/revision declarations;
case identity is `(corpus_id, split_id, run_id, episode_id)`.
Reuse's external `ids` must equal receipt `ids`; its case has role `reuse` and
matching corpus/policy/revision and routing scope.

Promotion order: literal opt-in, candidate/source pin and exact reference checks,
source-case scope/IDs/task and independent valid-zero rescore, admit all four
qualification snapshots/identities/scopes, capture current workflow binding, then
actual four executions. Build a receipt only for four valid-one outcomes. Return
actual captures separately, never embed transcript/gold. If a qualification fails,
return no receipt and captures executed so far; no retries.

Envelopes have exactly `format`, `schema_version`, `payload`, `sha256`. Internal
`sha256` hashes canonical payload bytes. External approved pins and references
hash the **entire canonical encoded envelope**, including its internal digest.
These are corruption/binding checks, not self-digest authentication. Trusted
caller controls approved pins, evaluator/code and assets. Current selected-source
binding is not in-memory attestation, dependency provenance or an SBOM.

Use existing strict field/ID/instrument/result/canonical/database helpers and
protected scorer through existing capture methods. No signatures in old files
change. No registry, automatic persistence or native tool discovery.

## Limits and non-goals

Caller-authored executable skills, validated mechanics, not AI-learned new skills,
model authorship, semantic certification or market validation. No automatic LLM
candidate generation, learned policies, context/delegation, native gates,
provider dependencies, training/GPU, performance claims, preregistration changes,
default-arm changes or new OS sandbox.

Existing runtime has AST restrictions, 5-second tracing and evidence/output
bounds, not a hard-memory/OS sandbox. The eight-action limit counts PTC
submissions, not SQL calls; this workflow submits once per case and at most four
times per promotion. Only trusted programs in stable caller-owned DB snapshots
are supported. No defense against adversarial in-memory patching or concurrent
filesystem ABA mutation.

## Observed local validation

Actual repository: `/Users/nikolassapalidis/Developer/co-train`, unchanged HEAD
`8efeb93b55f4435c7b6913156c082b87f4290fc1`. Only the five assigned new files
were written by this worker. Parallel bench fixture edits were left untouched.
No Git writes, installs, models, paid inference, GPU, network research or deploy.

All runs used the existing read-only reference interpreter
`/Users/nikolassapalidis/Developer/misc/co-train/.venv-ptc/bin/python` (3.12.13),
the reviewed `run_offline_suite.py`, observer-native first on PATH, inherited
`ip-network-deny.sb`, fresh caches, and disabled bytecode/pytest cache. Every
run's pytest-process audit reported zero network attempts, cache accesses,
tokenizer loads and loopback events. These counters are not arbitrary-child
telemetry; the fresh reuse child inherited the OS network profile and cache
environment.

Logs live under
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/`:

- `skills-red-01.log`: 185 collected failures, 1.55s, exit 1, missing module
  handled inside test bodies, no collection error. Spec/tests preceded production.
- `skills-green-01.log`: initial 185 passed, 16.12s.
- `skills-green-02.log`: expanded 217 passed, 15.70s.
- `skills-regression-01.log`: 812 passed, 82.60s.
- Readback found workflow path elements needed exact string validation before
  tuple equality. `skills-field-graph-red-01.log`: one intended missing-TypeError
  failure, 0.21s. The narrow validator fix reused the existing text helper.
- `skills-green-03.log`: final 218 new cases passed, 15.64s, exit 0.
- `skills-regression-02.log`: **813 passed, 57.33s**, exit 0, no skips:
  final 218 new cases plus unchanged 276 capture and exact 319 legacy cases.
  Selection: `train/test_sql_skills.py`, `train/test_sql_skill_eval.py`,
  `train/test_sql_capture.py`, `train/test_sql_episodes.py`,
  `train/test_sql_bridge.py`, `train/test_execution_binding.py`,
  `train/test_learning_lab.py`. Includes existing actual native-discovery checks.

Final in-memory fault controls ran after the last production edit, with fresh
fixtures and actual selected-source files left intact. Logs
`skills-control-{baseline,rescore,disjoint,rerun,scope,pin}-02.log` record:
baseline 5 passed (0.89s); each of the five bypasses caused exactly one intended
admission/rerun assertion failure, exit 1 (0.69/0.69/0.53/0.64/0.72s).
No stale-source, digest, import or collection failure was counted as sensitivity.
The respective actual owners are `_admit_origin`, `_admit_qualifications`,
`_execute`, `_admit_scope`, and `reuse_promoted` in `train/sql_skill_eval.py`.
Controls skipped source rescoring, disabled disjointness, replaced candidate
dispatch with direct host-gold finish, disabled scope matching, or disabled the
external approval-pin check. These are fault probes, not alternate shipped code.

Real SQLite qualification used four different table names and 0/1/3/7 rows,
one frozen program submission per case, four valid EX=1 captures. Reuse passed
11/13-row fresh databases, including embedded quotes in an identifier. The
fresh-process test deleted origin and all qualification DBs before decoding
candidate/receipt and reusing twice: child exit 0, exactly two submissions,
two protected `match`, valid EX=1 results. Its retained files are under
`skills-regression-temp-02/test_fresh_process_receipt_reu0/` in the log directory:
`candidate.json`, `promotion.json`, `fresh-process-reuse-receipt.json`.
The receipt records these **entire-envelope** pins, not payload self-digests:

- candidate: `bf8f6257933977300af59c812ddb2ea1d1685642585fb6c14cb4a5ba750e84f5`
- approved promotion: `b1be9dd9d34d5fd396f237d7fa50775bc8f8b39ca43654e0eae949ec43b76398`

All five files were read back. `git diff --check` was clean; index stayed empty,
HEAD and worktree count unchanged. Full default-suite acceptance was deliberately
not run during concurrent bench work. Parent still owns independent Python,
general/security/fault reviews, integrated validation, shared docs and commit.
These results establish bounded executable mechanics, not learned-model skills.

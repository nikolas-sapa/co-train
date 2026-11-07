# V89 effective configuration: source-only plan

## Parent V111 correction, test criteria before implementation

Refuse unsupported CPython 3.12 PosixPath storage before formatting. Inspect
only exact-list raw chunks and optional exact cached string/parsed components;
at most 512 stored chunks/tail components and 8192 aggregate characters,
including separators, before any join or formatting. Reject partial parsed
layouts and unsupported storage types. No fallback to formatting unknown layouts.

Seven invalid layouts at each of request root, request pin and retained pin:
21 refusals through both entrypoints, zero formatting of the affected path,
zero hashing and zero JSON parsing. Include oversized uncached exact PosixPath,
513 raw chunks, oversized cached tail/string/root, non-list raw storage and
partial parsed storage. Preserve all prior 123 intended cases. New total 144,
UNRUN. Non-goals and all operation gates below remain unchanged.

## Aggregate-budget correction plan, before implementation

Independent parent Python/security review found shared-list DAG expansion before
the final JSON size check. Correct only four live source/test/plan/report files;
no frozen V90/archive access, execution or changes to old 35 cases/API.

Numeric test criteria, all UNRUN until parent execution:

1. Six-level, width-512 shared-list DAG: snapshot refusal in <=14 charged visits;
   encoded work must not start. Blanket shared-container refusal is supported.
2. List and dict cycles: 2 refusals, each <=3 charged visits, zero encoder work.
3. Unique-node tree: refusal before visit 16385; retained counters <=16384 nodes,
   <=8388608 accounted allocation bytes and <=1048576 encoded bytes.
4. Repeated 8192-character strings accumulated across a list: 1 aggregate byte
   refusal before any scalar/full JSON encoding or oversized result allocation.
5. Unknown declaration top-level key carrying a large DAG: 1 refusal before
   snapshot, binding/hash, schema-value descent or encoding. Non-string key:
   1 refusal without caller equality/serialization callbacks.
6. Canonical memory-only leaf-array sizes 1048575, 1048576 and 1048577 bytes:
   first two return exactly that size; third refuses during snapshot accounting,
   before encoder starts. String leaves stay <=8192 characters.
7. Independent bounded encoder: 2 refusals (byte limit and node limit).
   Reject an aggregate >1 MiB before buffer append;
   buffer never exceeds 1048576 bytes and encoder visits never exceed 16384.
8. Ordinary full four-task/AttemptBounds synthetic fixture: existing success,
   policy bytes and all 73 assertions/witnesses preserved. Path/retained-pin
   primitive guards remain BEFORE the legacy validator.

Implementation: aggregate traversal state with 16384 total nodes (including keys),
8388608 deterministic allocation-accounting bytes and 1048576 canonical bytes;
charge BEFORE allocating snapshot containers or descending. Refuse repeated
container identity/cycles instead of copying/expanding shared graphs. Retain
depth32/container512/string8192/int256 limits. Count exact ensure_ascii JSON byte
size during snapshot. Canonical output uses bounded append-only encoding, scalar
strings only (<=8192 characters) passed to stdlib JSON, no whole-document dumps.
Check declaration exact top-level type/key set/schema before any deep copy.

Budgets bound work/allocation structurally, not a measured RSS/time claim. No
generic object serialization hooks or arbitrary callbacks. No provider/runtime/
image attestation or operation authority added. All authority remains false and
provider review CLOSED.

Source-only case inventory after this correction: prior 73 configuration cases
plus 15 aggregate-budget cases = 88 cases / 46 functions. With original 35 evidence
cases, intended focused total is 123. ALL UNRUN, including AST/import/guard-loss
and resource-counter instrumentation. Parent freeze/re-review precedes execution.

## V92 correction plan, before correction

Parent froze V90 separately; do not access/change that archive. Source inspection
found incomplete request serialization: actual AttemptBounds and nonempty SqlTask
tuples were unsupported. Preserve all existing 43 new cases/assertions, original
35 evidence cases/API, both equality witnesses and source-before-parse guard.

Additional numeric criteria (all execution remains UNRUN):

1. Fully typed four-task synthetic request and AttemptBounds: 1 deterministic
   freeze/validate roundtrip, zero approvals. USD values 12/0/12, lifetime 1800.
2. Reverse task order: 1 post-plan mutation refusal.
3. Mutate each USD bound and lifetime: 4 refusals against unchanged policy.
4. Missing bounds, empty tasks and unsupported task object: 3 refusals.
5. USD bool/int/nonfinite Decimal/subclass and integer bool/Decimal substitutions:
   at least 8 refusals before evidence hashing/JSON parsing.
6. Canonical Decimal equivalent representations: 1 identical policy digest;
   Decimal/int/bool bindings remain distinct or invalid, never aliasing.
7. Exact concrete PosixPath only: malicious subclass at request root, request pin
   and retained pin yields 3 refusals, zero __str__/__fspath__/path-method callbacks.
8. Oversized integer/coefficient/exponent and task field: at least 4 refusals.

Implement only explicit known QualificationRequest, AttemptBounds, SqlTask,
FilePin, PosixPath and primitive layouts. No generic dataclass/asdict, duck typing,
serialization hooks or caller callbacks. Validate request/pin primitive shapes
before old consistency hashing/parsing, then call old consistency unchanged.
Use bounded context-independent Decimal coefficient/exponent canonical values,
exact integer arithmetic for the existing <=USD25 and <=1800 bounds, never
Decimal context rounding. Non-lifetime positive bounds get a serialization-only
signed-64-bit ceiling; this does not increase any operational limit.

Synthetic fixtures contain four actual SqlTask objects and nonempty synthetic
source/database FilePins, but no databases, queries, proofs or admitted operation.
No source mutation, native inventory, environment, provider or approval scope added.

## Test plan, before implementation

All cases use six retained in-memory SYNTHETIC buffers. Execution belongs to parent.
Numeric criteria: existing 35 evidence cases unchanged; at least 12 named new
cases, zero authority fields true, zero provider/file/network effects.

1. Explicit complete synthetic policy: 1 configuration-consistency result, 0 approvals.
2. Missing expected policy digest: 1 refusal, 0 approvals.
3. Missing OCI effective configuration or runtime correspondence: 2 refusals.
4. Duplicate Env keys and added Env injection: 2 refusals.
5. Entrypoint and Cmd drift: 2 refusals.
6. WorkingDir and User drift: 2 refusals.
7. Inherited effective Env, history, diff-ID, mount correspondence: at least 4 refusals.
8. Unknown nested configuration field or unsupported runtime layout: 2 refusals.
9. Caller declaration mutation: 1 unchanged frozen snapshot and 1 drift refusal.
10. Policy digest mismatch and malformed policy bytes: 2 refusals.
11. Source-byte corruption: 1 refusal before JSON parsing.
12. Embedded NUL, unsafe path, ambiguous history: at least 3 refusals.
13. Duplicate nested JSON key: 1 refusal.
14. Actual validation tripwire: deliberate forbidden import yields AssertionError.
15. Two single-guard-loss witnesses: configuration equality and runtime equality;
    each normal test refuses, removing only its indicated equality must cause
    ordinary AssertionError with test assertions unchanged. Parent restores guard
    and reruns unchanged tests. Worker does not claim mutation execution.
16. Exact request type binding: Path-to-dict and tuple-to-list substitution each
    refuse (2 cases). Preserve type identity in canonical request serialization,
    so unsupported request objects cannot alias an already frozen value.

## Implementation plan

Preserve four-argument consistency-only API and all existing tests. Add separate
configuration-aware entrypoint calling it first. Freeze exact reviewed declaration,
full supported request fields, recipe, provider label and ordered six buffer pins
in version-domain canonical immutable bytes, with externally supplied expected
policy SHA256. Validate hashes before parsing. No inferred base defaults.

Support only explicit bounded OCI config (ordered Env/Entrypoint/Cmd, absolute
WorkingDir, numeric User, amd64/Linux, explicit history/rootfs), no implicit fields.
Support no mounts or injected layers. Bind all layer descriptors, diff IDs and
history, including empty-layer semantics. Exact reviewed values, not blacklists.

Existing RuntimeObservation lacks process/config/layer/mount observation fields.
Therefore require an explicit versioned correspondence document in the existing
opaque runtime_inventory retained buffer, bound to the existing runtime observation,
config and manifest hashes. It is a SYNTHETIC supported layout, not an observed
provider format or replacement for native inventory admission. Missing actual
correspondence is UNKNOWN/refused, never fabricated. No seventh buffer or adapter.

## Non-goals

No execution, Git, imports at worker runtime, filesystem/provider/network access,
image availability/build/pull, dependency installation, budget/schedule changes,
attestation, publisher/layer authenticity, native inventory/qualification, launch,
payment, or approval. All authority remains false; provider review always CLOSED.

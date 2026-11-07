# Typed-request and aggregate-budget source-only correction handoff

## Parent V111 source correction

Bound exact CPython 3.12 PosixPath raw chunks and every present cached string
or parsed representation before str(). Unsupported/partial layouts refuse;
stored chunk/tail count <=512, aggregate representation <=8192 characters.
Added 21 refusal cases across seven layouts and three caller locations, with
format/hash/JSON tripwires. Intended image total 144, all new cases UNRUN.
Parent authored this follow-up, no worker execution or operational authority.

## Status and limits

Implemented source only against parent-supplied baseline e54671b (not independently
Git-verified). Numeric test plan was written before implementation. No commands,
Python imports/execution, tests, Git, network/provider calls, builds, pulls,
hydration, uploads, installs, credentials, environment inspection, model/data,
wheel/lock/distribution enumeration, or delegation performed.

VERIFY_REAL: Written source read back; tests and guard-loss mutations UNRUN.
Parent owns execution, review, source-pin verification, integration and commits.

## Aggregate-budget follow-up

Parent reported independent Python AND security review of frozen V90 found a
second defect: depth/per-container limits permitted exponential shared-list DAG
expansion, and whole-document JSON encoding allocated before the final size check.
The typed-request correction was not yet frozen. No archive/frozen copy or other
worker was accessed. Parent owns the next freeze and independent re-review.

Numeric plan added BEFORE this correction. Changed the SAME four live files:
configuration implementation, configuration tests, plan and this report.

New snapshot budgets, shared across the entire traversal:

- at most 16384 charged nodes, INCLUDING dictionary keys;
- at most 8388608 deterministic allocation-accounting bytes;
- at most 1048576 exact canonical encoded bytes.

Node accounting charges 128 units per visited node, container accounting charges
64+32*member_count before constructing the output container, and strings charge
4*character_count before text validation/encoding. These are explicit accounting
units plus a node limit, NOT measured RSS or a claim that Python overhead equals
these units. Depth32/container512/text8192/int256 bounds remain.

Repeated container identities, including cycles, refuse rather than expand.
Immutable scalar sharing is allowed but charged per occurrence. Encoded-size
accounting includes JSON punctuation, quoting and ensure_ascii escapes, including
two-surrogate escapes for non-BMP text. Limits are checked before committing
counters, allocating snapshot containers or descending into their children.

Canonical encoding starts ONLY after that bounded snapshot succeeds. It uses an
append-only bytearray with an independent <=1 MiB append check and <=16384-node
encoder guard. Only exact scalar strings <=8192 characters are passed to stdlib
json.dumps, never the full document/container; integer conversion is <=256 bits.
Sorting is restricted to <=512 exact, bounded string keys. A final immutable bytes
copy is also <=1 MiB. No oversized whole-document result is ever constructed by
the new canonicalizer. Legacy consistency/recipe code is unchanged.

Unknown declaration top-level type/keys/schema now refuse BEFORE binding or deep
snapshot. Non-string caller keys never reach set construction, equality, hashing
or serialization callbacks during validation.

All exact AttemptBounds/SqlTask/Decimal serializers and complete four-task fixture
remain. The exact-concrete PosixPath and retained FilePin preflight still runs
BEFORE the legacy API, which intentionally remains unchanged. All previous 73
configuration test bodies/assertions, both single-guard-loss witnesses and the
source-hash-before-parse test remain unchanged by this follow-up.

Added nine functions / fifteen intended cases: shared DAG snapshot/canonical (2),
list/dict cycles (2), aggregate unique nodes (1), accumulated strings before JSON
(1), unknown top-level key/hostile non-string key (2), exact encoded boundaries
1048575/1048576/1048577 (3), independent encoder byte/node failures (2), standard
canonical escape/byte compatibility (1), allocation guard before materialization
(1). Intended boundary behavior: first two sizes accepted exactly, last refused
before encoder entry. Ordinary typed synthetic success remains a required test.

ALL tests/AST/imports/guard mutations/resource measurements UNRUN by this worker.
No real-time or RSS success claim. Parent can instrument _TraversalBudget.take,
its node/allocation/encoded counters, and _CanonicalEncoder.nodes/buffer. Shared
DAG tests specify <=14 visits; cycles <=3; oversized unique trees <=16384. Parent
must freeze/re-review this correction BEFORE any execution.

## V92 correction, source findings and changes

Parent reported a separate frozen V90 archive/source admission, three AST parses
passing, old 35 evidence test bytes untouched, and tests UNRUN. That archive and
admission were not accessed or changed. Parent will freeze/review V92 separately.

Concrete defect: previous full-request serializer could not encode actual
AttemptBounds or SqlTask values. Successful synthetic fixtures had reused the
old consistency leaf's None bounds/empty tasks, masking that incompatibility.

Read own bench/task.py and native_qualification.py source declarations. Added
only exact known AttemptBounds, Decimal and SqlTask support. Every current
configuration fixture now has four actual typed SYNTHETIC SqlTask objects,
nonempty source/database FilePin tuples and AttemptBounds:

- total_ceiling_usd=Decimal("12")
- prior_usage_usd=Decimal("0")
- remaining_worst_case_usd=Decimal("12")
- lifetime_seconds=1800
- output_bytes_per_phase=1048576
- artifact_bytes=67108864
- retention_seconds=60

SQL fields contain inert SYNTHETIC text, not actual queries. Pins are synthetic
labels, not source/database proofs. No native request validation, query, filesystem
inspection, provider observation, admission or actual runtime approval occurred.

Exact primitive/schema preflight now runs BEFORE old consistency hashing/parsing.
It rejects None bounds, missing/unsupported task objects, non-tuple task/pin
collections, malformed primitive fields and unsupported representation sizes.
The full request uses exactly four SqlTask entries (existing native fixture
cardinality), 1..512 source pins and four database pins. This is only typed
snapshot compatibility, not native fixture/source/model admission.

Only exact concrete PosixPath is supported. Subclasses are rejected before str,
fspath, is_absolute or other path methods, including request and retained pin
paths. Old evidence validator/API is unchanged, and still has only its earlier
docstring change. New preflight protects the new API before entering that leaf.

Decimal canonicalization is context-independent sign/coefficient/exponent VALUE
serialization, without normalize, quantize, formatting hooks, generic dataclass
serialization or arithmetic under caller Decimal context. Equivalent 12.000 and
1200e-2 serialize as the same Decimal value; signed zero canonicalizes to zero.
Decimal/int/bool remain separately tagged; only exact Decimal is valid for USD.
Only the known C-method Decimal layout is supported; unrecognized implementation
methods refuse rather than assume backing-storage accounting semantics.
Finite Decimal backing storage is limited to 512 bytes before as_tuple, then
coefficient <=64 digits and input exponent -64..64. Fixed-scale bounded integer
arithmetic enforces the existing nonnegative costs, total in (0,25], prior plus
remaining <=total. Lifetime remains 1..1800. Other positive integer bounds have
a serialization-only maximum 2**63-1. General canonical integers have <=256 bits,
checked before JSON serialization. These are accepted-layout bounds, not new
operation approval or increases to any actual resource limit.

Previous policies containing None bounds/empty tasks intentionally refuse under
the full-request API. Actual runtime correspondence remains unavailable/UNKNOWN;
none was invented or approved.

## Exact written paths (initial task, cumulative)

- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/train/qualification_image_evidence.py
- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/train/qualification_image_configuration.py
- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/train/test_qualification_image_configuration.py
- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/docs/droid-v89-image-config-plan.md
- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/docs/droid-v89-image-config-report.md

Legacy evidence file changed only its API docstring. Original evidence test file
and its parent-reported 35 cases were not edited.

V92 correction modified only these four live files:

- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/train/qualification_image_configuration.py
- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/train/test_qualification_image_configuration.py
- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/docs/droid-v89-image-config-plan.md
- /Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-image-config/docs/droid-v89-image-config-report.md

## Interfaces

`train.qualification_image_configuration.freeze_configuration_policy(
recipe, request, bundle, *, expected_provider_image_id,
reviewed_configuration) -> FrozenConfigurationPolicy`

`train.qualification_image_configuration.validate_image_configuration(
recipe, request, bundle, *, expected_provider_image_id, policy,
expected_policy_sha256) -> ImageConfigurationConsistency`

Legacy `validate_image_evidence(recipe, request, evidence, *,
expected_provider_image_id)` is unchanged, CONSISTENCY ONLY. New validator performs
primitive preflight, calls that API, then performs strict configuration comparisons. No live launch
callsite was changed; this is an explicit opt-in, separate consistency interface,
not launch admission.

FrozenConfigurationPolicy has immutable `canonical: bytes` and `sha256: str`.
Caller must independently review/pin the expected SHA256, never treat generating
or rehashing a policy as proof of review.

Canonical domain is `qualification-effective-configuration-policy-v1`.
Canonical bytes bind the declaration, full supported QualificationRequest field
snapshot, recipe SHA256, selected provider label, and ordered six named retained
pin paths/sizes/SHA256s. Each payload is checked against its pin before parsing.
Request values carry explicit type tags (PosixPath, FilePin, AttemptBounds,
SqlTask, Decimal, tuple, scalar); lists,
dicts and unsupported request object types refuse instead of aliasing a frozen
typed value.
Canonical JSON sorts object keys, preserves array order, rejects duplicate input
JSON keys, nonfinite values, NUL and unsupported primitive types. Limits: 1 MiB
per document/buffer, nesting 32, 512 items per generic array/object, text 8192
characters. No filesystem access occurs when representing paths.

Declaration has exactly `schema` and `state`; schema is
`reviewed-effective-configuration-v1`. State has exactly `oci_config`,
`manifest_layers`, `mount_targets`, `injected_layers`.

Supported OCI configuration has exactly `architecture`, `os`, `config`, `rootfs`,
`history`. Platform must be amd64/Linux. Process config has exactly ordered `Env`,
`Entrypoint`, `Cmd`, absolute safe `WorkingDir`, and explicit numeric `User`
(UID or UID:GID, each at most ten decimal digits). Env may be nonempty: the
synthetic success case has ordered PATH and PYTHON_VERSION values. Maximum 256
Env entries, no duplicate keys; at most 128 arguments per command array; at least
one command/entrypoint token overall. No host Env is read, no plugin/environment
changes are made.

Only OCI gzip layer descriptors are supported, 1..128 layers. Rootfs has exactly
type=layers and ordered diff_ids, one per manifest layer. History has 1..256
entries, each exactly created_by plus boolean empty_layer, with nonempty-layer
count equal to manifest layer count. Complete ordered descriptors/diff IDs/history
are compared to reviewed values, not inferred from defaults. Only explicit empty
mount and injected-layer lists are supported. Unsupported OCI metadata/fields,
named-user lookup, shell-form commands, missing fields and ambiguous layouts
refuse. No blacklist claims to cover OCI execution security.

## Runtime correspondence gap, deliberately closed

Existing RuntimeObservation contains platform/Python/libc values, no effective
Env/process/history/layer/mount observations. Legacy inventory bytes are opaque.
No actual provider correspondence is available from the supplied context.

New validator requires a document in the SAME retained runtime_inventory buffer,
with exactly schema=`synthetic-effective-configuration-correspondence-v1`,
config_sha256, manifest_sha256, runtime_observation_sha256 and state. State must
match the actual retained OCI config/manifest/receipt projection exactly. Hashes
must match those same retained buffers. Existing runtime observation semantics
are still checked by the legacy validator.

This explicitly SYNTHETIC supported layout is not an observed Modal format,
attestation, replacement for native inventory, or invented actual runtime value.
Actual/legacy evidence lacking it refuses with runtime effective correspondence
UNKNOWN. There is no seventh buffer or hidden observation adapter.

## Test source and parent execution requirements

Current file contains 46 test functions, 88 intended parametrized cases, counted
from source, NOT collection. Prior 43 configuration cases/assertions preserved;
typed-request correction added 11 functions/30 cases; aggregate-budget follow-up
adds 9 functions/15 cases, preserving those prior 73 case assertions. Combined
focused target: original 35 + configuration 88 = 123 cases. ALL UNRUN by worker.
Every new validation path has file/provider/import/socket tripwires; a deliberate
forbidden import verifies the validation tripwire is capable of raising.

Added cases: typed four-task/bounds roundtrip (1), task order mutation (1), three
USD/lifetime mutations (4 total), missing bounds/empty tasks/unsupported task (3),
strict USD/integer primitive and Decimal subclass rejection (8), equivalent
Decimal representations under precision-one context (1), bool/int/Decimal type
tags (1), evil Path subclass zero-callback refusal at three locations (3),
oversized integer/Decimal coefficient/exponent/task string (4), nonstring task
fields (3), generic canonical integer before JSON conversion (1).

Invalid-request tests exercise BOTH freeze and validation entrypoints with
hashlib.sha256 and evidence JSON parsing patched to raise AssertionError if
reached. No such test or tripwire has been executed by worker.

Coverage: complete synthetic success/zero authority; missing policy/digest/config/
correspondence; duplicate/injected/reordered Env; entrypoint/command/WorkingDir/
User drift; history/diff-ID/manifest-layer/mount drift; unknown nested layouts;
declaration deep snapshot; request-path mutation and Path/dict or tuple/list
type-substitution refusals; self-consistent rehashed buffer
drift; policy digest/byte drift; source digest guard before parsing; NUL/unsafe
path/ambiguous history; nested duplicate JSON key; runtime observation hash
correspondence; runtime-only mount/layer injection; noncanonical rehashed policy;
explicit legacy-consistency-only behavior.

Two actual equality sites have independent ordinary-assertion test witnesses:

1. `test_effective_configuration_guard_loss_witness_ordinary_assertion`.
   Fixture changes actual Env PYTHON_VERSION only, rehashes all affected buffers,
   and freezes bindings to those buffers while retaining the original reviewed
   declaration. Normal rejection must be exactly
   `effective configuration differs from reviewed policy`.
   Parent removes ONLY `_require(_canonical(actual) ==
   _canonical(declaration["state"]), ...)`. All other checks remain satisfiable.
   Unmodified test must then raise ordinary AssertionError:
   `effective configuration equality guard lost`.

2. `test_runtime_configuration_guard_loss_witness_ordinary_assertion`.
   Fixture changes only correspondence state's Env PYTHON_VERSION, leaving actual
   OCI config and reviewed declaration matching, with consistent retained hashes.
   Normal rejection must be exactly `runtime effective correspondence drift`.
   Parent removes ONLY `_require(_canonical(observed["state"]) ==
   _canonical(actual), ...)`. Unmodified test must then raise ordinary
   AssertionError: `runtime configuration equality guard lost`.

For EACH witness, parent should capture normal result, single-guard-loss failure,
restore exactly the original guard, then rerun the UNMODIFIED named test. Restore
both guards before full focused execution/review. No test weakening, helper
monkeypatch bypass, successful mutation claim or restored-pass claim is made here.

## Remaining external proof

All authority fields remain false. Provider review is unconditionally CLOSED.
Configuration consistency cannot authenticate publisher, layers, effective file
contents, build history or runtime observations, and cannot approve build/launch.
Unchanged seven legacy missing receipts remain in nested consistency result.

Still required independently: actual retained image/config/layer provenance;
authenticated selected-provider-object/runtime binding; effective generated
layers and mounts observation; actual effective process/environment correspondence
and native inventory from that same job; independently reviewed exact policy;
synchronous exact-operation host admission; enforceable USD25 gross all-charge
ceiling including finite billing tail; one GPU, <=1800s aggregate lifetime, no
retry; native update/checkpoint/fresh-process restore witnesses. No actual image
availability or provider compatibility is established by these source changes.

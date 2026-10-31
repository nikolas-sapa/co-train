# Admitted database records on ValidatedDraw

2026-10-31. Base `2ab5a7b9a4a39c17e268b29fce9c855a06d4cb63`.
Small source prerequisite for owned SDK composition, not SDK activation.

## Test plan, before implementation

| Gate | Numeric acceptance |
| --- | --- |
| Existing denominator | Real synthetic retained artifacts still yield 8 planned, 7 eligible, 1 exclusion, unchanged order/settings/document digests. |
| Exact projection | Returned records equal every admitted `draw.identity.databases` entry, in its original order, with exactly `db_id`, `sha256`, `size_bytes`. Include databases used only by excluded planned tasks. |
| Immutability | `databases` is a tuple; every record is the exact frozen DrawDatabase type. Field/container mutation refused. No mutable artifact dictionary retained. |
| Coverage | Every planned/eligible task resolves to exactly 1 admitted record; shared DBs produce 1 record, not one per task. |
| No new work | Exactly the existing 2 fresh identity passes and 2 DB hashes per admitted database; 0 extra hashes, selection/redraw, consumer SQL/gold validation, model/native calls or publication. |
| Fidelity/refusal | Existing digest, schema, settings, path/sidecar and identity drift gates remain intact. No records are returned after refusal. |
| Sensitivity | One projected-digest substitution hits once and fails the named admitted-digest assertion. Fresh restored positive passes; source and retained input bytes unchanged. |
| Compatibility | Existing validated-draw/admission/preparation regression files pass. No persisted artifact schema, SOURCE_KEYS or expected-pin updates. |

Fixture preparation may use existing real synthetic publication/SQLite helpers;
install consumer sentries afterward, as existing tests do. No real corpus or
artifact consumption. Projection itself performs no new I/O.

## Selected API

Alongside DrawExclusion in `bench.prepare`:

```python
@dataclass(frozen=True)
class DrawDatabase:
    db_id: str
    sha256: str
    size_bytes: int
```

Add `databases: tuple[DrawDatabase, ...]` to frozen ValidatedDraw.
Build it only from the parsed, digest-admitted draw identity after both existing
current-identity comparisons succeed. Do not derive expected digests from the
second observed identity or perform another live hash. Preserve all admitted
records, including excluded-only databases.

This host-side projection introduces no persisted format or authority. A freely
constructed DrawDatabase or ValidatedDraw is not authenticated by its type.
Future configured composition must invoke load_validated_draw with independently
retained document digests and bind exact eligible task objects. Existing SqlTask
host paths remain unchanged; do not add host paths or gold to database records.

## Non-goals

No SDK/QA registration, Task/writer modification, policy/provider selection,
native/profile activation, corpus selection/downloads, SQL gold re-validation,
paired runner/baseline/estimator, new durable manifest, source repinning or gate
relaxation. Changing prepare.py naturally changes its source identity; never
refresh retained evidence to compensate.

## Implementation order

1. New projection tests and named fidelity assertion, intended RED.
2. Frozen record/result field and projection at the existing return boundary.
3. Consumer/preparation regressions, negative/restored control, Python/security
   review, documentation and verified source publication.

## Verification

Seven intended call-phase RED tests preceded the implementation, then all seven
passed. The four specified draw/admission/preparation files passed together:
**207 tests in 4.87s**. The portable
[control](spikes/reference/validated-draw-databases/) runs two fresh `-I -B`
children: exactly one substituted returned digest reaches
`PROJECTED_DB_DIGEST_NOT_ADMITTED`, while the restored original passes with
zero substitutions. Both require unchanged source/retained documents, two
corpus loads and zero consumer SQL/selection/gold/EX.

The first control attempt stopped before fixture setup because its discarded
stdout lacked pytest's required `isatty`; the corrected stream passes both
children without changing production, tests or the named fidelity gate.
No full-suite, SDK, native SQL or baseline qualification is claimed.

# Portable SQL skill SDK acceptance, offline verification

2026-10-30. Final closed-fixture helper offline acceptance: PASS. Portable-helper
native acceptance: PENDING; all three native phase invocations are NOT_EXECUTED.

## Observed scope

The final independently executed configured suite recorded 3,803 passed,
zero failed, one optional missing-Torch skip, two unchanged configured tokenizer
deselections, ten warnings and 28 passing subtests. Exit 0, 741.59s. All 3,794
previously selected IDs remained; ten new default-discovered offline guards
passed. The explicit native helper was not collected. Counts overlap earlier
runs and are not additive quality metrics.

Independent probes: 30 passed, zero failed. Real non-native SQLite/file SDK
produced source EX=0, four qualification EX=1 and one reuse EX=1, with canonical
capture, returned-object identity and final directory-fsync timing checks.
These exercise the actual SDK in process, not a native execution campaign.
Five controlled call-phase REDs covered budget, missing approval, fsync ordering,
capture-dependency binding and fixture closure. Each restored all ten guards GREEN.

## Corrected fixture/source scope

Earlier Python review found capture-only dependencies missing from controller
pins. The reviewed fix unions `capture.SOURCE_PATHS`, including `train/grpo_ptc.py`,
into `required_source_paths()`. The owned-copy dependency mutation with identical
consent/profile bytes rejects with zero dispatches; the real dependency is unchanged.

A later lifetime probe found the shared fixture factory's transaction context
did not guarantee connection closure before return without GC. The portable
helper now owns `_fixture_task(directory, label, rows, table)`, bound as
`_api().fixture_task`, using `contextlib.closing` around its transaction.
The legacy `_task`, production SDK and runtime remain unchanged. This is a
fixture-source lifetime correction, not a demonstrated old native campaign failure.

The independent seven-case real-SQLite probe disabled automatic GC and forbade
explicit GC until after assertions. Each of seven returns had raw FD delta 0
and zero live connection weakrefs; seven explicit closes occurred before GC.
Recorded FD baseline 11 remained 11. The legacy-alias control went RED at 11 to 12 FDs
before cleanup, then restored 11; GC cleanup was not used to satisfy the positive
raw criterion. Fresh final-delta Python/security reviews were reported APPROVE
by the parent, followed by the final full validation.

## Source binding and recorded evidence

At validation, base HEAD was `c1dfb85476f77e817ec57adb3b015a74b690b816`.
The working-tree bytes included the two then-uncommitted code files; no future
commit hash is asserted. All 268 bound files, including the five then-current
documents, were unchanged during the new full run and matched before this
docs-only refresh.

| Artifact | Whole-file SHA256 |
|---|---|
| `train/sql_skill_sdk_acceptance.py` | `155389a17e423845a582343bd674c38392f9be5c49d75b4937a1aad0648eaa63` |
| `train/test_sql_skill_sdk_acceptance.py` | `8367a51cae1868945447155d770b4d184ab9e3b0ca6187eae793d3b76ebc0358` |
| Canonical `validation-receipt.json` | `530e00968ac2d98f58a12b049acd6471b4c5ace210b9ec34f6faeaab602b316a` |
| `evidence-manifest.json` | `fd1fd7dcea3fff15ba387c3e64825dcc7ef031a98e4da2438fc105b1f19e479c` |

Original local bundle: `portable-sdk-closed-fixture-validation-anlaounp`, under
the caller's 2026-10-30 scratch directory, not distributed in a clone.
`manifest-verification.json` records VERIFIED for 21,505 entries (inventory,
not quality evidence). Integration reread the canonical/verification JSON and
checked canonical/manifest hashes; this does not independently rehash all entries.
Missing originals must be reported, never reconstructed.

The new receipt retains a resolved scratch preparation incident, before
collection: AST role tuples were compared with JSON-deserialized lists.
Normalizing tuples to lists fixed structural comparison. No production changes,
test bodies or full runs preceded that correction; do not call this zero incidents.

Historical pre-fixture-close evidence remains in
`portable-sdk-final-validation-alsa6hns/validation-receipt.json`
(SHA256 `adbc17e8a94af4376be20347377bdb27b0ee6de51e6e29e2ba31304091f94b1f`):
3,802 passes, 29 probes and four controls on earlier 9425fc49/56f0f087 source
bytes. It is not the latest result and is not additive to the current proof.

## Resource and integration boundaries

The independent OFFLINE validation records 678 strict fixture FD/thread checks
and 95 targeted protocols with raw and GC-settled deltas zero and no new live
threads. Those settled observations are not native CLI metrics. The portable
CLI requires exact equality of raw descriptor identity tuples/thread lists at
its phase measurement points, without forcing GC; it measures no separate
GC-settled snapshots. One-time checks found 127 recorded owned PIDs absent.
This is evidence-scoped, not host/VM/container clearance; unrecorded subprocesses
are not independently surveyed.

Audited network attempts, cache accesses and tokenizer loads were zero.
The full run permitted loopback/Unix IPC (13/1,036 recorded events); Python audit
is not arbitrary child/native telemetry or local-proxy isolation.

This documentation integration reruns no pytest, probes or native jobs.
Exactly five document hashes change from the full-proof snapshot; the other
263 bound files, including both code files, stay unchanged. The 31 controller
sources, 16 native-role files and four protected scorer/budget paths are
unchanged. The full result is not a rerun over refreshed document bytes.
Only the previously added current HANDOFF section is replaced; the complete
historical suffix remains byte-for-byte. Its pre-existing
`#current-state--2026-10-08` link remains unresolved; no new link issue is hidden.

## Native gate remains separate

| New portable-helper phase | Execution status | Prospective native jobs |
|---|---|---|
| `qualify` | NOT_EXECUTED | 11 |
| `reuse --case-index 0` | NOT_EXECUTED | 2 |
| `reuse --case-index 1` | NOT_EXECUTED | 2 |

The [usage/contract guide](../spec/sql-skill-sdk-acceptance.md) gives actual
profile APIs, closed ten-key consent/approval objects and commands. Missing
native context fails before dispatch, not SKIP. Import/help are inert; effective
Python optimization rejects early. Ten offline guards are ordinary default
collection, not native acceptance.

After integrated-commit review, a caller may separately authorize a fresh
15-job local-fixture campaign (7 PROGRAM, 8 SCORER). No new native profile,
consent, permission, claims or campaign has been created here. Already approved
source-bound profile/observer/cached image/socket must be supplied; the CLI
does not create/acquire them or start a VM. Before preparing/pinning profile or
issuing consent and again before each phase, the operator must externally
compare actual Git HEAD and required-source hashes with the reviewed commit/pins.
`reviewed_revision` is only format-checked, not Git-checked or authenticated;
profile/helper/controller file pins are checked by code.

Qualification remains UNAPPROVED; separate external fixture review/pins precede
two fresh interpreters. Baseline configuration and PREMOVE inode/mode/mtime
collection are caller-side, outside this CLI. The CLI compares container IDs/
state and DB hash/path/move evidence, not arbitrary host actors/private workloads.
Local-fixture approval is not customer permission or cryptographic authentication.

Earlier [scratch-helper native SDK proof](2026-10-29-native-sql-skill-workflow.md)
remains actual bounded 15-job happy-path evidence for its distinct helper.
The [19-job direct-evaluator trial](2026-10-29-bounded-native-acceptance.md)
is separate. Both budgets were consumed; neither validates this portable module
or authorizes replay. Fresh authorization after commit review is a remaining
gate, not a blanket ban on future native work.

No production SDK/runtime/approval/capture-schema changes, dependencies, tool
configuration or new authority are introduced. Claims/slots and best-effort STOP
do not create a crash supervisor. Two source-generation jobs are outside Timer
callbacks; timing proves callback/file-fsync scope, not baseline improvement,
model learning, paid dollar savings or human-hour benefit. Existing model,
financial, economics and traction gates remain unchanged.

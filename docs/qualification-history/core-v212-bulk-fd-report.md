# V212 report: bulk readonly FD handoff under small control records

STATUS: **SOURCEONLY UNRUN**. Nothing in this spike was executed, imported,
timed or measured. No command, no import, no test, no Git operation, no network
call, no provider call, no credential, no lock, no asset, no delegation. Every
number below is either derived by arithmetic from constants read out of the
original source, or is an explicitly labelled estimate. Parent owns execution,
review, integration and commits. This report is not approval.

Author: Core Qwen, sole author. Three files, all new:

| path | lines |
|---|---|
| `docs/core-v212-bulk-fd-plan.md` | 884 |
| `spec/spikes/core-v212-bulk-fd.py` | 1414 |
| `docs/core-v212-bulk-fd-report.md` | 526 |

All V171/V189/V194/V202/V204 paths were read only where the brief permits and
were not modified.

## 1. The unknown, and the honest answer

**Unknown.** Can a genuine fresh worker use inherited READONLY file descriptors
for the original request and a large canonical manifest, while every control
record stays at or below 8192 bytes?

**Answer as delivered: not yet answered, because nothing ran.** What is delivered
is a source-only instrument that answers it in one run, plus three findings that
change the question's shape and that are settled by arithmetic and source
reading rather than by execution.

The three settled findings:

1. **The declared worst case is infeasible.** A valid canonical manifest at the
   `10000`-member cap cannot reach `8388608` bytes. Its maximum is `5840001`.
   See section 3.
2. **The original serializer cannot carry the manifest at all.** `_WIRE_LIMIT`
   is `1048576`. Both manifest caps are roughly 8x over it. The manifest must
   travel out of band no matter what; the descriptor is not an optimisation, it
   is the only route. See section 4, blocker B2.
3. **The original request serializer is not safely usable standalone.** See
   section 4, blocker B1. The spike therefore reports the exact blocker, as the
   brief requires, and hands a genuine `QualificationRequest` across the
   descriptor in a projection envelope instead.

If the run passes, it proves the mechanism works. If it fails, the gate that
fires names the reason. Either way the run is the answer; this report is not.

## 2. What was built

One file, `spec/spikes/core-v212-bulk-fd.py`, 1414 lines, stdlib only, no
third-party import, no repository write outside a freshly created private temp
root. Two modes in one file:

- `python3 core-v212-bulk-fd.py` runs the parent: builds fixtures, spawns seven
  workers sequentially, gates every observation, prints one JSON summary, exits
  `0` on PASS and `3` on FAIL.
- `python3 core-v212-bulk-fd.py --_v212-worker <10 fields>` runs one worker:
  arms an immutable lease, validates two inherited descriptors through an
  ordered gate ladder, reads and hashes and parses both payloads in-process,
  asks for one permit, performs one exclusive marker operation, appends one
  journal line, exits.

Exactly seven `Popen` calls exist in the whole run, one per case, enforced by a
run-level gate `popen_total == 7`. There is no other spawn, no `fork`, no
`exec`, no `setsid` anywhere in worker code. `start_new_session=True` appears
only on the parent's single spawn.

## 3. The infeasible target, with the arithmetic

The brief asks for a valid canonical manifest of exactly `8388608` bytes AND
`10000` members. Those two constraints are jointly unsatisfiable.

The canonical member template, with both variable fields at their empty minimum,
is:

```
{"key":"","root":"source","sha256":"","size":1048576,"snapshot_key":""}
```

Field by field, counted from that literal:

| piece | bytes |
|---|---|
| `{` and `}` | 2 |
| `"key":""` | 8 |
| `"root":"source"` | 15 |
| `"sha256":""` | 11 |
| `"size":1048576` | 14 |
| `"snapshot_key":""` | 17 |
| four `,` separators | 4 |
| **`FIXED_MEMBER_BYTES`** | **71** |

`json.dumps` with `sort_keys=True` and default separators emits exactly that
layout, and the source recomputes it at import time and refuses to run if the
recomputed value differs from the hard-coded expectation of `71`. So the number
is checked against the real serializer, not trusted.

With `NAME_LIMIT = 256` on both `key` and `snapshot_key`, and one enclosing
manifest object costing 1 byte of braces:

$$\text{bytes} = 1 + 72M + K + S$$

where `M` is the member count, `K` the summed `key` lengths and `S` the summed
`snapshot_key` lengths. At the cap:

$$1 + 72 \times 10000 + 2560000 + 2560000 = 5840001$$

Shortfall against the declared `8388608`: **2548607 bytes**. To reach
`8388609` bytes the member count must be at least **14365**, which is `4365`
over the `10000` cap.

Two consequences, both handled:

- **C2**, the worst valid case, uses the true worst valid input: `10000`
  members, both name fields saturated at `256`, exactly `5840001` bytes. This is
  the largest manifest the declared shape can express, so it is a stronger test
  of the handoff than the declared number would have been, and it is the number
  reported in the summary as `worst_valid_manifest_bytes` alongside
  `declared_cap_shortfall`.
- **C3**, the over-cap refusal case, cannot be built at `10000` members either.
  It uses `14365` members and exactly `8388609` bytes, one byte over the cap, so
  it refuses at the byte gate for the reason the brief intends. It also exceeds
  the member cap, which is fine: the byte gate is ordered before the member gate
  so the refusal reason is the byte cap, and the case gates that ordering
  explicitly.

No unapproved padding field was added to reach an exact byte length. The fitter
solves for real `key` lengths inside the charset and the length limit, and
refuses with a hard error when the target is unreachable rather than padding.

## 4. Blockers against the original serialization, exact

The brief requires using the genuine `QualificationRequest` and the existing
first-party serializer and fixture shape where safely possible, and reporting
the exact blocker where not.

### B1: `_prepare_worker_transport` is not safely usable standalone

`train/native_qualification.py`'s `_prepare_worker_transport` is the original
serializer. Calling it requires, at minimum:

- `guards.REPO_ROOT` resolved against a real checkout layout;
- real sqlite fixture databases on disk, because it pins them with
  `_check_asset_bytes`, which does `lstat`, `S_ISREG`, `st_nlink == 1`, exact
  size, and a full read plus `sha256`;
- real repository source files at a frozen `_CONSTRUCTION_SHA`, which the
  spike cannot supply and must not fabricate;
- `native_model.verify_local_model` against a real model directory.

Every one of those is a real asset the brief forbids this spike from touching,
and none can be newly synthesised without the spike inventing repository source
pins, which would be fabrication rather than a fixture. **Blocker: the original
serializer's preconditions are original-caller assets, not synthetic fixtures.**

### B2: `_WIRE_LIMIT = 1048576` caps the original transport

The original wire format caps a single record at `1048576` bytes. The manifest
caps this spike must exercise are `8388608` and `8388609`, roughly 8x over. Even
the corrected worst valid manifest, `5840001`, is 5.6x over.

**Blocker: the manifest cannot ride the original transport at any size this
spike must exercise.** This is what makes the descriptor handoff mandatory
rather than an optimisation, and it is the single most important finding for the
unknown: the answer is not "descriptors are faster", it is "control records
cannot carry this payload at all, so the question is whether descriptors can
carry it while control stays small".

The source imports `_WIRE_LIMIT` from the original module and uses it as
`REQUEST_BYTE_CAP`, with a hard-coded fallback to `1048576` if the import is
blocked. The request payload is gated at or below that cap on both sides.

### B3: the brief's manifest record is not the original manifest record

The brief specifies a member of `{root, key, size, sha256, snapshot_key}` with a
`10000` cap. The original record shape is `{kind, key, size, sha256}` with a
`1024` cap. These are different shapes with different caps.

**Blocker: the record shape under test is this spike's own, not the original's.**
It is disclosed as a deliberate shortcut, not passed off as original. What is
genuine is the validation discipline around it: the spike calls the original
`_asset_path`, the original `_closed` exact-field-set check, the original
`_pairs` duplicate-key hook, the original `_bounds_from_wire`, the original
`_validate_bounds` and the original `_path`, all unmodified, on synthetic data.

### What is genuinely reused

Imported from the original modules and called unmodified:

| original symbol | reused for | why it is safe here |
|---|---|---|
| `QualificationRequest`, `SqlTask`, `FilePin`, `AttemptBounds` | genuine request payload | frozen dataclasses, construction only |
| `TIERS` | the original tier vocabulary; tasks are built at `TIERS[0]` and the worker refuses any reconstructed task whose `tier` is outside it | constant tuple |
| `_FIXTURES` | the four fixture names, giving the genuine 4-task and 4-database-pin shape | constant tuple of names |
| `_path` | every path this spike creates | requires absolute, non-traversing, non-symlink; touches nothing |
| `_validate_bounds`, `_bounds_from_wire` | bounds crossing the wire as Decimal text | pure validation, no filesystem |
| `_pairs`, `_closed` | duplicate-key refusal and exact field set | pure JSON hooks |
| `_asset_path` | per-member key validation | returns a `Path`, touches no filesystem |
| `_signature` | the 7-field descriptor identity tuple, verbatim | pure function of an `os.stat_result` |
| `_check_asset_bytes` | verification of every synthetic pin at fixture-build time | called only on the spike's own newly created private files |
| `_WIRE_LIMIT` | the request byte cap | constant |

Not called, and the reason is in each case B1 or B3: `_prepare_worker_transport`,
`_validate_request` as a whole, `_validate_fixture_scope`, `verify_local_model`.

The import chain was verified by reading, not by running: importing
`bench.task` pulls `bench/__init__` through `bench.loader`, `bench.score`,
`bench.shapes`, `bench.suite`, then `ptc.sqlite_safety`, `ptc.paired`,
`ptc.metrics`, `ptc/__init__`, `ptc.runtime`. All stdlib. `ptc/harness.py`,
which imports `httpx`, `pydantic` and verifiers, is imported lazily inside a
function in `ptc/__init__.py`, not at module level, so it is not pulled in.
**This is a read-based conclusion and is unverified by execution.** If it is
wrong, the run fails at import and the parent sees it immediately.

## 5. The seven cases

| case | kind | members | exact bytes | expected gate | expected reason | expected rc | markers | permits |
|---|---|---|---|---|---|---|---|---|
| C1 | exact-8193 | 40 | 8193 | none, accepted | none | 0 | 1 | 1 |
| C2 | max-valid | 10000 | 5840001 | none, accepted | none | 0 | 1 | 1 |
| C3 | over-byte | 14365 | 8388609 | `manifest_bytes` | `manifest_bytes_over_cap` | 8 | 0 | 0 |
| C4 | over-count | 10001 | 960097 | `member_count` | `member_count_over_cap` | 11 | 0 | 0 |
| C5 | wrong-sha | 24 | 2497 | `manifest_sha` | `manifest_sha_mismatch` | 9 | 0 | 0 |
| C6 | decoy-inode | 24 | 2497 | `manifest_identity` | `manifest_identity_pre_read` | 7 | 0 | 0 |
| C7 | writable-fd | 24 | 2497 | `manifest_mode` | `manifest_mode_not_readonly` | 6 | 0 | 0 |

Exit codes are distinct per rung: `0` accepted, `1` harness, `2` internal, `3`
channel, `4` protocol, `5` any request-side gate, `6` manifest mode, `7` manifest
identity, `8` manifest bytes, `9` manifest digest, `10` manifest parse, `11`
member count, `12` member record, `13` deadline, `97` lease. `97` comes from
`os._exit` in the lease timer handler, so it is observable even when the worker
is wedged inside a wait.

C1 is exactly `8193` bytes, one over the control cap, which is what makes it
proof that the payload did not squeeze through a control record. C2 is the true
worst valid input. C3 and C4 refuse before any open or operation permit. C5 uses
a genuine same-identity descriptor with a deliberately wrong expected digest. C6
passes a byte-identical, same-size, different-inode owned file and refuses at
the identity gate. C7 passes an `O_RDWR` descriptor and refuses at the mode gate.

Gate ordering inside the worker is fixed, twenty-two rungs, first failure wins,
each with its own reason string and rung exit code. `channel`, `session`, `lease`,
then the request side (`request_mode`, `request_identity`, `request_bytes`,
`request_sha`, `request_identity_after`, `request_parse`, `request_shape`), then
the manifest side (`manifest_mode`, `manifest_identity`, `manifest_bytes`,
`manifest_sha`, `manifest_identity_after`, `manifest_parse`, `member_count`,
`member_record`, which calls the original `_asset_path`), then `ready`,
`challenge`, `permit`, `marker`. Every refusal happens before the permit, which is
why every negative case gates `permit_issued == 0` and `markers == 0`.

One rung is load-bearing in a way that is easy to miss. `st_mode` in the identity
signature carries inode permissions and file type, not the open-mode access bits,
which live in the open file description. An `O_RDWR` descriptor on the same inode
has an identical signature to an `O_RDONLY` one. Only `fcntl.fcntl(fd, F_GETFL)`
distinguishes them, which is why the mode gate is separate, runs first, and is
what actually refuses C7.

The request side is gated before the manifest side, so a case that fails on the
manifest cannot be masking a request failure. C3 is the ordering case that
matters most: its manifest violates both the byte cap and the member cap, and the
byte gate runs first, so the refusal reason is `manifest_bytes_over_cap` and not
`member_count_over_cap`. That ordering is gated explicitly rather than assumed.

## 6. What the run gates

Per case, roughly 30 comparisons, all against observed values: expected refusal
gate, expected refusal reason, real `returncode`, real marker count from a real
`os.listdir` after a real reap, real marker mode from a real `stat`, real permit
count, real frame counts, real maximum frame bytes against `8192`, parent-side
and worker-side manifest bytes and member counts and digests compared against
each other rather than against constants, descriptor transfer count `== 3`,
passed copies closed, owner descriptors retained and closed, containment unused,
lease exits zero, cleanup errors empty, retained roots zero, and four real
timing measurements against their budgets.

Run level: `popen_total == 7`, elapsed strictly under `8.00`, maximum frame
bytes across all cases at or below `8192`, `markers == 2` and `permits == 2`
exactly, journal mode `0600`, exactly `7` `worker_exit` lines, exactly `7`
`case_result` lines, zero unparsable journal lines, and a clean run-root release
on PASS. Plus two startup refusals: the run refuses to start if the genuine shapes
could not be imported, and refuses to start if the recomputed
`FIXED_MEMBER_BYTES` disagrees with `71`.

Nothing asserts a hard-coded counter in place of an observation. Where an
expected value is a literal, it is compared against an observed value.

## 7. The journal, as the brief states it

Implemented, not waived. The parent creates one run-private root before any
worker exists, `mkdtemp` then `chmod 0700` then `_path` checked, and precreates
`journal.log` inside it with `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` at `0600`,
followed by `fchmod(0600)`, one `journal_precreated` line and `fsync`. The
parent is the only actor that ever passes `O_CREAT` on that path.

Every worker appends exactly one `worker_exit` line and the parent appends one
`case_result` line per case, both with `os.open(..., O_WRONLY|O_APPEND|O_NOFOLLOW)`
and **no `O_CREAT`**. Each append `fstat`s the descriptor first and refuses
unless the file is regular and `S_IMODE == 0600`, so "the parent precreated it
privately" is an observed fact in the child rather than an assumption.

The worker append sits outside the gate ladder, so every exit path including a
refusal is recorded. A worker whose append fails on an otherwise accepted run
escalates its exit code to `EXIT_PROTOCOL`, because an accepted run with no
journal line is a custody failure, not a pass.

On PASS the run root is removed. On FAIL it is retained and its path is printed
as `retained_run_root`, matching the failed-custody rule. Per-case fixture roots
follow the same rule independently.

## 8. Timing

Budget: `2.50` s per case, strictly under `8.00` s total, `2.00` s operation,
`0.50` s challenge, `1.00` s containment and kill plus reap, `10.00` s external
parent. One immutable run expiry, computed once, passed to every child, armed as
a daemon `threading.Timer` whose handler is `os._exit(97)`. No lease resets, no
epsilon. Every wait deadline is `min(case_deadline, expiry - teardown_reserve)`
and a non-positive remaining wait is refused immediately rather than clamped.

**All timing numbers are estimates. Nothing was measured.** Projected per-case:
C1 ~0.30 s, C2 ~1.10 s, C3 ~0.85 s, C4 ~0.40 s, C5-C7 ~0.30 s each. Projected
run total ~4.15 s against the `8.00` s gate.

The dominant risk is the genuine-shape import chain, paid eight times, once in
the parent and once per worker, and entirely unmeasured. At 250 ms per process
the run lands near 4.15 s. At 400 ms it lands near 5.35 s. At 700 ms C2 alone
reaches roughly 1.55 s and the run reaches roughly 7.3 s, inside the gate but
with too little margin to be comfortable. The run budget honestly includes the
parent's own import cost, because the budget starts at module load, not at
`main`.

**First measurement the parent should take, before anything else:**

```
python3 -X importtime -c "import bench.task, train.native_qualification"
```

If that exceeds roughly 300 ms, the per-case budget needs revisiting before the
spike is run, and the cheapest fix is to reduce the import surface in worker
mode rather than to loosen any timing gate.

## 9. Line count, and why it is not 400-600

The brief prefers a compact spike of roughly 400 to 600 lines. The delivered
source is **1414 lines**, 2.4x to 3.5x over the preference. That is disclosed,
not excused. Where the lines went:

| block | approximate lines | why it could not be smaller |
|---|---|---|
| docstring, imports, `sys.path` bootstrap, genuine-shape import with blocker capture | 100 | the blocker must be reported, not swallowed |
| constants, errors, lease, framed nonblocking control channel | 230 | nonblocking framed I/O with deadline slicing is not compressible |
| manifest fitter and generator | 90 | solving exact byte lengths under two length caps, with refusal when unreachable |
| request projection build and reconstruct | 130 | genuine `QualificationRequest` with genuine `SqlTask`, `FilePin`, `AttemptBounds`, Decimal-text bounds, plus pin-count validation |
| descriptor identity, mode, bounded read and hash helpers | 90 | the guards the unknown is actually about |
| journal helpers | 50 | precreate, no-`O_CREAT` append with `fstat` mode check, read-back snapshot |
| worker mode, ladder and journal wrapper | 180 | nineteen ordered gates, each with its own reason and exit code |
| parent resources, spawn, reap, containment, transfer, close | 160 | real custody accounting, not a stub |
| seven fixed cases | 50 | one dict each |
| per-case runner, gates, custody gates, parent main, dispatch | 330 | roughly 30 per-case comparisons, 8 run-level gates plus the run-root release check, each spelled out |

The honest trade: the gate count is what makes the run trustworthy, and the gate
count is what costs the lines. Cutting to 600 lines would have meant either
collapsing gates into loops over expected-value tables, which hides which gate
fired, or dropping gates, which makes a green run meaningless. Neither seemed
acceptable for a spike whose entire purpose is to distinguish seven different
refusal reasons. If the parent wants the compact version, the reduction is
mechanical: fold the per-case gate comparisons into a table-driven loop. That
would save roughly 250 lines and would cost gate-name precision in failures.

## 10. PROVES, if the run passes

1. A genuine fresh `Popen` worker consumed a `5840001`-byte, `10000`-member
   canonical manifest from an inherited readonly descriptor, hashing and parsing
   it in-process, with no path reopen and no fallback reopen.
2. The same worker reconstructed a genuine `QualificationRequest`, with genuine
   `SqlTask`, `FilePin` and `AttemptBounds` values, from a second inherited
   readonly descriptor.
3. Every control frame in every case, including the largest-manifest case, was
   at or below `8192` bytes, measured from real frames. An `8193`-byte payload
   and a `5840001`-byte payload both crossed by descriptor while control stayed
   under the cap.
4. Readonly-ness, inode identity, byte cap, digest, member count and per-record
   validity are each independently enforced, each with its own exit code, and
   each refuses before any operation permit is issued.
5. Exactly one exclusive `0600` marker was written by each positive worker after
   exactly one fresh single permit, observed after a real reap; zero markers and
   zero permits for every negative.
6. Parent custody survived: every worker reaped, every owner descriptor closed,
   every root released, no lease exit, no forced cleanup, no descendant, no exec
   or session outside the parent's single `Popen`.
7. The parent-precreated `0600` journal discipline held under real use: seven
   workers each appended exactly one line to a file they never created, each
   having `fstat`-verified it was a regular `0600` file first, and the parent
   read back exactly seven `worker_exit` and seven `case_result` lines.

## 11. SHORTCUT, deliberate and disclosed

1. The request envelope is `v212-request-projection-v1`, not the original
   `native-sql-worker-v1`, because B1 and B2 make the original serializer
   unusable and its format `1048576`-capped. The payload is a genuine
   `QualificationRequest`; the envelope name is not original.
2. The manifest record `{root, key, size, sha256, snapshot_key}` with a `10000`
   cap is this spike's shape, not the original `{kind, key, size, sha256}` with
   a `1024` cap. Per B3.
3. C2 uses `5840001` bytes, not `8388608`, because the declared target is
   arithmetically unreachable at `10000` members. C3 uses `14365` members to
   reach `8388609`, exceeding the member cap in order to hit the byte cap, with
   the gate ordering gated so the refusal reason is the byte cap.
4. The descriptor read path is the spike's own bounded read, hash and identity
   sequence rather than `_check_asset_bytes`, because `_check_asset_bytes` takes a
   path and the whole point is to work from descriptors with no reopen. It mirrors
   the original discipline exactly: `fstat`, `S_ISREG`, `st_nlink`, access-bit
   check, exact size, full read, `sha256`, and a `_signature` comparison before
   and after. `_check_asset_bytes` itself is still called, by the parent, once per
   pin at fixture-build time, on the spike's own synthetic files.
5. Pin byte verification is parent-side only. The worker reconstructs `FilePin`
   values and validates their shape, but never re-reads the pin files, because it
   holds no descriptor for them and opening them by path would break the
   no-reopen rule. A green run proves the pins were genuine at build time and
   crossed the wire intact as values.
6. All fixtures are newly created private synthetic data. No original caller asset
   is read, and the fixture database files are not sqlite databases.

## 12. MISSING, what a green run does not prove

1. **Nothing ran.** Every claim in this report is arithmetic, source reading, or
   estimate. A green run is required before any of it is evidence.
2. **The import chain conclusion is unverified.** Section 4's claim that the
   chain is stdlib-only and that `ptc/harness.py` is not pulled in was reached by
   reading. If it is wrong the run fails at import, loudly.
3. **No original serializer was exercised.** `_prepare_worker_transport`,
   `_validate_request`, `_validate_fixture_scope` and `verify_local_model` are all
   unexercised, for B1 and B3 reasons. A green run says nothing about them. The
   original validators that *are* called, `_path`, `_validate_bounds`,
   `_bounds_from_wire`, `_pairs`, `_closed`, `_asset_path`, `_signature` and
   `_check_asset_bytes`, are exercised on synthetic data only, and `_asset_path`
   only on charset-clean generated keys.
4. **Fixture-database content is not validated.** The projection's `db_path`
   values point at newly created private synthetic files that are not sqlite
   databases and contain no `readings` table.
5. **Two guards are unexercised adversarially.** The post-read identity
   comparison and the original `_asset_path` call are not attacked by any fixture
   in this set. Every generated key is charset-clean, so replacing `_asset_path`
   with a length check would not change any case outcome. A green run is not
   evidence that either guard catches anything.
6. **Concurrency is structurally excluded, not tested.** The seven workers share
   one journal path but append one at a time and none passes `O_CREAT`. The
   concurrent-first-create failure mode the brief mentions is excluded by
   construction rather than reproduced or refuted.
7. **All timing is estimated.** Every number in section 8.
8. **The 1414-line source has never been parsed by an interpreter.** It was
   reviewed by reading only. A syntax error, a name error or a bad import would
   surface on the parent's first run and not before. This is the single largest
   risk in the delivery and it is inherent to a source-only constraint.

## 13. Self-review, defects found and fixed before delivery

The source was reviewed after writing, again after the plan was corrected, and a
final pass checked all three files against each other. Thirty-one defects were
found and fixed. The ones that would have changed a run outcome:

- **Fixture subdirectories were never created.** `_pin` was called on paths
  whose parent directories did not exist. This was a real crash on the first
  case, not a style problem.
- **The digest gate was vacuous.** It compared the worker's reported digest
  against the worker's own reported digest. It now compares against a digest the
  parent computes independently, so C5 can actually fail.
- **The expected manifest identity used the decoy's signature in C6**, which
  would have made C6 pass for the wrong reason. It now always uses the original
  manifest's signature.
- **The member-count gate compared a value against itself** for the max and over
  kinds. It now has explicit branches per kind.
- **`_fit_manifest` returned a 4-tuple but the caller unpacked three**, and its
  over-cap search bound was a hard-coded `+64` that could not reach `14365` from
  `10000`. The bound is now derived: `ceil((target - 1) / (1 + 71 + 2 * 256))`,
  and C3 starts its search at the member cap.
- **`FIXED_MEMBER_BYTES` was hand-counted as 73 and the formula as
  `1 + 74M + K + S`.** Both were wrong; `"sha256"` is 8 characters and
  `"snapshot_key"` is 14. Corrected to `71` and `1 + 72M + K + S`, which changed
  every per-case target, and the plan was corrected to match. A runtime
  cross-check against the real serializer was added so this class of error
  refuses the run instead of silently mis-sizing a fixture.
- **Child sockets were not tracked**, so a spawn failure between socket creation
  and `Popen` would have leaked a descriptor and corrupted later cases' custody
  observations.
- **The run budget started after the import**, understating real elapsed time.
  It now starts at module load.

Four more came out of the final pass. Three of the four were documentation
disagreeing with source rather than source being wrong:

- **The journal helpers existed but were never called.** They are now wired into
  both entry points, the worker argv grew from 9 fields to 10 to carry the
  journal path, and run-level read-back gates were added.
- **This report's case table had the wrong exit codes** for C3, C5, C6 and C7.
  It claimed `11`, `12`, `13`, `14`; the source and the plan both say `8`, `9`,
  `7`, `6`. The report was wrong and is now corrected against the source
  constants.
- **Both docs claimed `_check_asset_bytes` was never called.** The source calls
  it, once per pin, at fixture-build time. The docs were stale and now say what
  the source does, including the honest limit: the worker never re-verifies pin
  bytes, because it holds no descriptor for them.
- **`TIERS` was claimed as reused but was not imported**, and the tier value was
  a hard-coded `"simple"`. It is now imported from `bench.task`, tasks are built
  at `TIERS[0]`, and the worker refuses any reconstructed task whose tier is
  outside `TIERS`, which also closed a gap where a corrupt tier would have
  reconstructed silently.

## 14. What the parent should do

1. Run the import-time measurement in section 8 first. If it exceeds roughly
   300 ms, revisit the per-case budget before running the spike.
2. Run `python3 spec/spikes/core-v212-bulk-fd.py` and read the single JSON
   summary. `status`, `run_failures` and `case_failures` are the first things to
   look at; `retained_run_root` and each case's `retained_roots` point at
   preserved evidence on failure.
3. If the run fails at import, that is finding 2 of section 12 and it is a real
   finding, not a spike bug: it means the genuine-shape import chain is not
   stdlib-only and the whole approach needs a narrower import.
4. If the run fails at the `FIXED_MEMBER_BYTES` startup refusal, the serializer's
   `json` formatting differs from what section 3 counted, and every byte target
   in section 5 needs recomputing from the printed derived value.
5. Only after a green run should the two unexercised guards in section 12 item 5
   be attacked, and only after that should the unknown be recorded as answered.

Nothing here was executed. Nothing here is approval.

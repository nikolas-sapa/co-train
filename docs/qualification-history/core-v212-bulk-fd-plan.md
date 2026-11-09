# V212 bulk FD handoff spike: numeric test plan

Status: SOURCEONLY UNRUN. Plan written before implementation, per brief.
Sole author: Core Qwen. Parent owns execution, review, integration, commits.

Writable paths for this assignment (only these three):

- `docs/core-v212-bulk-fd-plan.md` (this file)
- `spec/spikes/core-v212-bulk-fd.py`
- `docs/core-v212-bulk-fd-report.md`

Every V171/V189/V194/V202/V204 path is READONLY. No execution, imports, tests,
commands, Git, network, provider, delegation, SDK, config or asset access was used
to produce this plan; it is derived from file reads of own first-party source only.

## 1. The one unknown

Can a genuine fresh worker process consume, through inherited READONLY file
descriptors, both (a) the original-request payload and (b) a large canonical
manifest, while every control record crossing the socket stays `<= 8192` bytes?

Two claims must both hold for a PASS:

- **T1 (bulk by FD).** A fresh `Popen` worker reads, hashes, parses and validates
  a canonical manifest of megabyte scale from an inherited readonly descriptor,
  and reconstructs a genuine `QualificationRequest` from a second inherited
  readonly descriptor, without reopening any source path.
- **T2 (control stays small).** Every control frame actually sent or received in
  every case is `<= 8192` bytes, including the case whose manifest is the largest
  valid manifest this spike can form.

A PASS additionally requires that each negative case refuses at its exact named
gate with its exact real returncode, before any operation permit is issued.

## 2. Non-goals

- No pipeline execution, no production owner or API, no SDK, no Modal, no provider.
- No real caller asset is read, created, moved or hashed. All fixture bytes are
  newly created private synthetic data inside a per-case private root.
- No descendants. No `execve`, `setsid`, `fork` or `posix_spawn` outside the
  parent's single `subprocess.Popen` call site. Workers spawn nothing.
- No snapshot-member content validation. `snapshot_key` is validated for shape and
  canonical order only. See MISSING in section 14.
- No generic framework. Seven fixed cases, one worker mode, no plugin/registry
  layer, no case-parameterisation DSL.
- No guard-loss control is implemented as an eighth case. Section 12 plans them;
  the parent owns running them.

## 3. Original-shape reuse, and the exact serialization blocker

The brief requires genuine `QualificationRequest` and the existing first-party
serializer/fixture shape where safely possible, and requires that an unusable
serializer be reported rather than papered over. Both halves are answered here.

### 3.1 What is reused genuinely

Imported from `train/native_qualification.py` (stdlib-only at module level, no
side effects, guarded by `if __name__ == "__main__"`):

| imported object | source | use in this spike |
|---|---|---|
| `QualificationRequest` | frozen dataclass, line 79 | constructed by the parent, reconstructed by the worker |
| `FilePin` | frozen dataclass | genuine pins over newly created synthetic files |
| `AttemptBounds` | frozen dataclass | genuine bounds, `Decimal` fields |
| `_signature` | line 180 | the original 7-field FD identity tuple `(st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, st_ctime_ns)`, used verbatim for the identity gate |
| `_asset_path` | line 305 | the ORIGINAL root/key validator, called by the worker for every manifest member |
| `_pairs` | line 315 | the original duplicate-JSON-key hook |
| `_closed` | line 323 | the original exact-field-set check |
| `_path` | line 172 | the original absolute non-traversing non-symlink path check, applied to the resolved private root and every pin path |
| `_validate_bounds` | line 156 | the original bounds discipline, called by the parent on the genuine `AttemptBounds` it builds |
| `_bounds_from_wire` | line 328 | the original bounds reconstruction, called by the worker to rebuild `AttemptBounds` from FD bytes, including the `Decimal` text rule and `_validate_bounds` |
| `_check_asset_bytes` | line 185 | the original pin verification, called by the parent on every synthetic pin: `lstat`, `S_ISREG`, `st_nlink == 1`, exact size, full read and `sha256`, with `_signature` compared before, at open, during and after |
| `_WIRE_LIMIT` | line 36, `1048576` | the request FD byte cap |
| `TIERS` | `bench/task.py` line 31 | the original tier vocabulary; the parent builds tasks at `TIERS[0]` and the worker refuses any reconstructed task whose `tier` is not in `TIERS` |
| `_FIXTURES` | line 43 | the four fixture names, for the genuine 4-task shape |

`_SOURCE`, `_MODEL` and `_DATA` (lines 39-41) are deliberately **not** imported.
They are absolute `Path` objects under `/opt/qualification`, not the kind names,
so they cannot supply the `{source, model, data}` vocabulary. That vocabulary is a
literal set inside `_asset_path` (line 306) and is not exported. The spike mirrors
it as `_APPROVED_ROOTS` for one reason only: to produce a distinct
`member_root_unknown` refusal instead of folding an unknown root into
`member_key_rejected`. `_asset_path` re-validates the root itself on the very next
line of the ladder, so the mirror adds a reason string and no trust.

`_path`, `_validate_bounds`, `_bounds_from_wire` and `_check_asset_bytes` are all
pure with respect to the repository: they touch no `guards.REPO_ROOT`, no model
inventory and no caller asset, only the paths they are handed. They are therefore
safely usable on newly created private synthetic files, and using them is strictly
better than copying their logic. `_path` does require that no path component be a
symlink, so the private root is `Path(mkdtemp(...)).resolve()` before use; on macOS
that turns `/var/folders/...` into `/private/var/folders/...`, and on Linux
`resolve()` is a no-op.

Imported from `bench/task.py`:

| `SqlTask` | frozen dataclass with `__post_init__` tier checks | four genuine fixture tasks |

`bench/task.py` is reached through `bench/__init__.py`, which also imports
`bench.loader`, `bench.score`, `bench.shapes`, `bench.suite`. Those pull
`ptc.sqlite_safety`, `ptc.paired`, `ptc.metrics` and `ptc/__init__.py` ->
`ptc.runtime`. Every one of those is stdlib-only. `ptc/harness.py` (the only
module importing `httpx`, `pydantic`, `verifiers`) is imported lazily inside
`ptc/__init__.py`, not at module level, so it is never reached. The whole chain is
therefore offline and stdlib-only. Its cost is real but unmeasured: roughly ten
extra modules per process. Section 11 budgets for it and section 14 lists it as an
unverified risk. If the import fails at runtime, the spike reports
`BLOCKED original_shapes_unavailable` with the exact exception text instead of
silently substituting a replacement dataclass.

### 3.2 Blocker B1: the original serializer cannot run here

`_prepare_worker_transport` (line 382) is the only first-party function that
produces a `QualificationRequest` wire document. It cannot execute in this spike.
Its first statement after the import is `_validate_request(request)` (line 239),
which requires, in order:

1. `from train import guards, native_model`. `guards.REPO_ROOT` is
   `pathlib.Path(__file__).resolve().parents[1]`, the real repository root
   (`train/guards.py` line 42).
2. The four roots `db_root`, `model_dir`, `output_dir`, `guards.REPO_ROOT` to be
   pairwise non-overlapping. A private synthetic root under `/tmp` or `/var/tmp`
   can satisfy this, so this clause alone is not fatal.
3. `worker = request.output_dir == _OUTPUT and guards.REPO_ROOT == _SOURCE`. Since
   `guards.REPO_ROOT` is the real repository and `_SOURCE` is
   `/opt/qualification/source`, `worker` is always `False` here, so the host
   branch applies and `request.output_dir` must not already exist.
4. `_validate_fixture_scope(request.tasks, request.db_root)` (line 209): exactly
   four tasks, each byte-equal via `asdict` to a hard-coded expected `SqlTask`
   built from `_FIXTURES = (("first", 17), ("second", 29), ("third", 41),
   ("fourth", 53))`, plus four REAL sqlite databases at
   `<db_root>/<name>/<name>.sqlite` with `st_nlink == 1`, opened read-only and
   immutable, containing a `readings` table whose single column is
   `("amount", "INTEGER", 1)` and whose first row equals the fixture amount.
   Creating those would mean fabricating caller fixture databases, and reading
   real ones is forbidden. Both are out of scope.
5. `_check_asset_bytes` (line 185) on every source pin, every database pin and the
   runtime inventory: `lstat`, `S_ISREG`, `st_nlink == 1`, exact size, full read
   and `sha256`, with `_signature` compared before, at open, during and after.
   Source pins must additionally be `is_relative_to(guards.REPO_ROOT)`, i.e. real
   repository files.
6. `request.source_pins` must contain `guards.REPO_ROOT / "train/native_training.py"`
   pinned at the frozen `_CONSTRUCTION_SHA`
   `a9ed0c422adab7bc44f073c8a5fe2b83e3be7497110bfb297442f5216054ed4f`. That is a
   real repository file with a real digest, not synthetic data.
7. `_verified_model_members(request)` -> `native_model.verify_local_model`, reading
   a real registered model inventory.

Items 4, 5, 6 and 7 each independently require real caller assets or real
repository files. `_prepare_worker_transport` is therefore **not safely usable**
in a standalone synthetic spike. This is reported, not worked around.

### 3.3 Blocker B2: the original transport is 1 MiB capped, so the manifest could never ride it

`_decode_worker_transport` (line 340) opens with

```python
_require(type(payload) is bytes and len(payload) <= _WIRE_LIMIT, "worker JSON exceeds 1 MiB")
```

with `_WIRE_LIMIT = 1048576`. The brief's manifest caps are `8388608` and
`8388609` bytes, i.e. exactly 8x the original wire cap. Even the largest manifest
this spike can legally form (section 4) is `5840001` bytes, still 5.6x over.

This is the load-bearing structural finding: **the original request channel is
1 MiB capped, so a large canonical manifest cannot travel through it at all.** It
must travel out of band. This spike's out-of-band channel is an inherited readonly
descriptor, and the control socket is separately capped at 8192.

### 3.4 Blocker B3: the original asset record is not the brief's manifest record

The original wire asset record is the closed set `{kind, key, size, sha256}`
(`_decode_worker_transport`, `_closed` at line 323), with `1 <= len(assets) <= 1024`
(line 354), `key` bounded `1..256` with charset `[A-Za-z0-9_./-]`, no `""`/`.`/`..`
component and not absolute (`_asset_path`, lines 306-311), and `kind` in
`{source, model, data}`.

The brief's manifest record is `{root, key, size, sha256, snapshot_key}` with a
`10000` member cap. That is **not** the original shape: it adds `snapshot_key`,
renames `kind` to `root`, and raises the member cap by roughly 10x. It is this
spike's own manifest shape. What it borrows from the original, genuinely:

- the exact `key` rule, enforced by calling the original `_asset_path` itself;
- the closed-field-set discipline, via the original `_closed`;
- duplicate-JSON-key refusal, via the original `_pairs`;
- the size and digest shape rules from `_check_asset_bytes`
  (`0 <= size <= 2 * 1024**3`, `re.fullmatch("[0-9a-f]{64}", sha256)`);
- the `st_nlink == 1` / `S_ISREG` / `_signature` before-and-after discipline,
  applied to the inherited descriptor instead of to a named path.

`root` carries the original kind identifier (`source`, `model`, `data`), which is
exactly the key the original uses to select `_SOURCE`/`_MODEL`/`_DATA`, so
`_asset_path(root, key)` is the original root-and-key check with no adaptation.

### 3.5 Consequence for the request payload

Because B1 blocks the serializer and B2 caps the format, the request descriptor
carries a spike-local projection named `v212-request-projection-v1`. It is **not**
presented as the original `native-sql-worker-v1` document. It carries the genuine
dataclass field values of a genuine `QualificationRequest` built by the parent:

- `tasks`: four genuine `SqlTask` rows (`asdict`), fixture names from `_FIXTURES`,
  `tier="simple"`, `tier_source="derived"`, `source="fixture"`, shape fields
  matching the original fixture expectation, but `db_path` pointing at newly
  created private synthetic files rather than real sqlite fixtures.
- `db_root`, `model_dir`, `output_dir`: absolute `str` of private synthetic roots.
- `source_pins`, `database_pins`, `runtime_inventory`: genuine `FilePin` triples
  over newly created synthetic files, with real sizes and real `sha256` digests
  computed by the parent at creation.
- `image_digest`: `"sha256:" + 64 hex`, the original required shape.
- `bounds`: `asdict(AttemptBounds)`, `Decimal` rendered with `format(value, "f")`
  exactly as `_prepare_worker_transport` does, and reparsed with `Decimal(text)`
  exactly as `_bounds_from_wire` does.

The worker reparses that projection and reconstructs a genuine
`QualificationRequest` with genuine `SqlTask`, `FilePin` and `AttemptBounds`
values, then gates `type(request) is QualificationRequest`, task count and digest
shape. So the request descriptor genuinely carries and genuinely rebuilds the
original type; only the envelope name and the absence of `_validate_request` are
spike-local, and both are disclosed.

The request projection is a few kilobytes, small enough for a control frame. It is
still delivered by descriptor, because the unknown is about the descriptor path
for both payloads. That choice is stated rather than hidden.

## 4. Canonical manifest format and exact byte arithmetic

The manifest is a bare canonical JSON array of member records. There is no wrapper
object and no schema field: any wrapper would be an extra field outside the brief's
approved record set and would perturb the exact-byte arithmetic. Format:

```python
json.dumps(members, separators=(",", ":"), sort_keys=True,
           ensure_ascii=True, allow_nan=False).encode("ascii")
```

Record field set is exactly `{key, root, sha256, size, snapshot_key}`. With
`sort_keys=True` the emitted order is `key, root, sha256, size, snapshot_key`
(`"sha256" < "size"` because `h < i`; `"size" < "snapshot_key"` because `i < n`).

Per-member fixed cost is **derived in code, not hard-coded**, by measuring the
template with empty variable strings:

```python
_TEMPLATE = {"key": "", "root": "source", "sha256": "",
             "size": 1048576, "snapshot_key": ""}
```

which serialises to

```
{"key":"","root":"source","sha256":"","size":1048576,"snapshot_key":""}
```

Hand-counted length, field by field. Quoted key names are the bare name plus two
quote characters, so `"key"` is 5, `"root"` is 6, `"sha256"` is 8, `"size"` is 6,
`"snapshot_key"` is 14; each contributes a `:` and then its value:

| piece | chars |
|---|---|
| `{` | 1 |
| `"key":""` | 5+1+2 = 8 |
| `,` | 1 |
| `"root":"source"` | 6+1+8 = 15 |
| `,` | 1 |
| `"sha256":""` | 8+1+2 = 11 |
| `,` | 1 |
| `"size":1048576` | 6+1+7 = 14 |
| `,` | 1 |
| `"snapshot_key":""` | 14+1+2 = 17 |
| `}` | 1 |
| **total** | **71** |

So `FIXED_MEMBER_BYTES == 71`, and the source gates that the derived value equals
71 and refuses the run if it does not. This makes plan/source drift impossible: if
a future Python changes `json` formatting, the spike refuses rather than silently
producing wrong byte counts.

Let `M` = member count, `K` = sum of `len(key)`, `S` = sum of `len(snapshot_key)`.
Document bytes:

```
bytes = 1 ("[") + M + sum_over_members(71 + len(key) + len(snapshot_key)) + 1 ("]")
      = 1 + 72*M + K + S            (valid for M >= 1)
```

Maximum per member is `71 + 256 + 256 = 583` bytes of record plus 1 separator, so
`584` bytes per member beyond the first.

### 4.1 Feasibility of the declared caps

With `M <= 10000` (the brief's member cap) and `len(key) <= 256`,
`len(snapshot_key) <= 256` (the original `_asset_path` name limit, which the brief
directs this spike to honour):

```
max_bytes(10000) = 1 + 72*10000 + 2560000 + 2560000 = 5840001
```

**`8388608` bytes is infeasible at `10000` members.** The shortfall is
`8388608 - 5840001 = 2548607` bytes. Reaching a byte count of that order needs at
least `14365` members (section 4.2), i.e. `1.44x` the member cap, which the count
cap independently forbids.

Widening `size` does not close the gap. The largest legal size under the original
rule is `2 * 1024**3 = 2147483648`, ten digits, three more than `1048576`:

```
absolute max at 10000 members = 1 + 10000 + 10000*(71 + 3 + 256 + 256) = 5870001
```

still `2518607` bytes short. The brief forbids an unapproved padding field, so no
extra field may absorb the remainder.

**Disclosure required by the brief:** under the actual name limits, no valid
manifest with `<= 10000` members can reach exactly `8388608` bytes. Case C2
therefore uses the **true worst valid input**: `10000` members at maximum legal
width, exactly `5840001` bytes. That is the worst case the byte cap can actually
be exercised against, and it is the largest payload that ever crosses a descriptor
in this spike. The unreachable declared target is reported in the report, not
quietly redefined.

### 4.2 Exact per-case byte targets

Key prefix is `"m%05d" % index` (6 chars), snapshot prefix `"s%05d" % index`
(6 chars), filler `"x"` (inside the original charset). A fixed-width zero-padded
index prefix guarantees lexicographic order equals index order, so the canonical
sort is satisfied by construction and independently re-verified by the worker.

| case | M | sum len(key) | sum len(snapshot_key) | exact bytes |
|---|---|---|---|---|
| C1 | 40 | 4312 | 1000 | 8193 |
| C2 worst valid | 10000 | 2560000 | 2560000 | 5840001 |
| C3 | 14365 | 3676888 | 3677440 | 8388609 |
| C4 | 10001 | 100010 | 140014 | 960097 |
| C5, C6, C7 | 24 | 336 | 432 | 2497 |

Derivations:

- **C1.** `8193 = 1 + 72*40 + K + 1000` -> `K = 4312`. `4312 = 40*107 + 32`, so 32
  keys of length 108 and 8 of length 107, all `<= 256`. `len(snapshot_key) = 25`
  for all 40 (`"s%05d"` + 19 filler). Total `1 + 2880 + 4312 + 1000 = 8193`.
  `8193 = 8192 + 1`: one byte over the control cap, which is the point of the case.
- **C2.** All keys and all snapshot keys at the 256 limit.
  `1 + 720000 + 2560000 + 2560000 = 5840001`.
- **C3.** `bytes = 1 + 72*M + K + S`, and the variable width per member is at most
  `512`, so the smallest feasible `M` is the smallest `M` with
  `8388608 - 72*M <= 512*M`, i.e. `M >= ceil(8388608 / 584) = 14365`. At
  `M = 14364` the remainder is `8388608 - 72*14364 = 7354400`, but the width budget
  is `14364*512 = 7354368`: infeasible by `32` bytes. At `M = 14365` the remainder
  is `7354328` against a budget of `7354880`: feasible, and `14365` is the true
  minimum.
  The fitter fixes `S` at the maximum, `S = 256 * 14365 = 3677440`, and solves `K`
  from the remainder: `K = 7354328 - 3677440 = 3676888`.
  `3676888 = 14365*255 + 13813`, so `13813` keys of length `256` and `552` of
  length `255`, all `<= 256`. Total `1 + 1034280 + 3676888 + 3677440 = 8388609`.
  Member count `14365 > 10000`, so the count cap is also violated; the gate ladder
  in section 8 puts the byte cap first, so the observed refusal is the byte gate,
  and the reason string `manifest_bytes_over_cap` distinguishes it from a count
  refusal.
  Because hand-solving this is error-prone, the source does not hard-code `14365`:
  it starts at the derived ceiling `ceil((target - 1) / (1 + FIXED_MEMBER_BYTES +
  2*NAME_LIMIT))` and searches upward for the smallest member count whose maximum
  width reaches `MANIFEST_BYTE_CAP + 1`, bounded at `+8` members so an unreachable
  target refuses instead of hanging the run.
- **C4.** `len(key) = 10`, `len(snapshot_key) = 14`.
  `1 + 72*10001 + 100010 + 140014 = 1 + 720072 + 240024 = 960097`, far below the
  byte cap, with `M = 10001` one over the count cap.
- **C5/C6/C7.** `len(key) = 14`, `len(snapshot_key) = 18`.
  `1 + 72*24 + 336 + 432 = 2497`.

The source does not hard-code these totals. It implements one fitter that solves
key lengths from a target and one predictor from the derived `FIXED_MEMBER_BYTES`,
then asserts `predicted == len(payload) == target` before writing the file, and
records the case as a disclosed non-pass if the fit is infeasible. The table above
is the expected output of that fitter, so a mismatch between plan and source is a
loud failure rather than a silent one.

Every member carries `size = 1048576` (7 digits, uniform, inside the original
`0 <= size <= 2*1024**3`) and `sha256 = hashlib.sha256((root + ":" + key).encode()).hexdigest()`,
64 lowercase hex, distinct per member. Neither is verified against real bytes; see
MISSING.

## 5. Architecture

One file, `spec/spikes/core-v212-bulk-fd.py`, stdlib only, two modes selected by
`argv[0]`:

- `python3 core-v212-bulk-fd.py` -> parent harness.
- `python3 core-v212-bulk-fd.py --_v212-worker <argv...>` -> worker.

The parent reaches the worker mode through exactly one `subprocess.Popen` call
site, wrapped in a single function that increments `popen_calls` from the real
call. `start_new_session=True`. No `execve`, `setsid`, `fork` or `posix_spawn`
anywhere else in the file. The worker spawns nothing and calls no subprocess API.

The worker is **case-agnostic**: one code path, no case-specific branches. Cases
differ only in what the parent puts on the descriptors and in the expected facts
it sends over control. That is what makes the negative cases meaningful: the same
worker code that accepts C1 and C2 refuses C3-C7 on observed evidence.

### 5.1 Per-case lifecycle

1. Parent creates a fresh private root `mkdtemp(prefix="v212-<case>-")`, mode 0700.
2. Parent generates the request projection bytes and the manifest bytes for that
   case, computing real `len` and real `sha256`. Fixture generation time is
   measured and counted inside the case budget.
3. Parent writes both payloads with `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`, mode
   `0600`, `fchmod` re-asserted, `fsync`, close. For C6 it writes a second,
   byte-identical manifest file (different inode, same size, same digest).
4. Parent opens each file once with `os.open(path, O_RDONLY|O_NOFOLLOW)` (C7:
   `O_RDWR|O_NOFOLLOW`). Those descriptors are the retained owners, held from
   first creation until teardown.
5. Parent creates `socket.socketpair()`, keeping the parent end.
6. Parent `os.dup`s each owner descriptor to form the passed copies, and passes
   those copies plus the child's socket end through a fixed `pass_fds` tuple.
7. Immediately after `Popen` returns, the parent closes the passed copies and the
   child's socket end, retaining the owners. This satisfies "closes passed copies"
   and "retains all actual handles and FD/root owners from first creation".
   Parent and child share one open file description per descriptor; that is safe
   because the parent never reads or seeks those descriptors after spawn, so the
   child's reads always begin at offset 0.
8. Parent sends `hello`, then follows the protocol in section 7.
9. Parent reaps the worker (real `wait`), then snapshots markers, then closes
   owners, then releases the root.

Descriptor numbers are preserved across the fork by `pass_fds`, and the child is
told each number in its argv, so no fd remapping logic exists in the worker.

Worker argv after `--_v212-worker`, exactly 10 fields, index order fixed:

| index | field | why it is argv and not control |
|---|---|---|
| 0 | resolved fixture root | needed before any frame exists |
| 1 | session id | authenticates every frame |
| 2 | nonce | authenticates the single permit |
| 3 | request descriptor number | the handoff itself |
| 4 | manifest descriptor number | the handoff itself |
| 5 | control socket descriptor number | the channel itself |
| 6 | absolute expiry, `repr(float)` monotonic | the immutable lease |
| 7 | wall clock at spawn, `repr(float)` | diagnostic only, never gated |
| 8 | journal path | appended with no `O_CREAT`, section 10 |
| 9 | case name | recorded in the journal line and the marker |

A wrong field count is refused as `channel`/`argv_count` before anything is opened.
No manifest or request byte ever appears in argv.

### 5.2 FD ownership map

| descriptor | opened by | flags | passed | retained by parent | closed by parent |
|---|---|---|---|---|---|
| request file | parent, once | `O_RDONLY\|O_NOFOLLOW` | dup | owner, whole case | after reap |
| manifest file | parent, once | `O_RDONLY\|O_NOFOLLOW` (C7: `O_RDWR\|O_NOFOLLOW`) | dup | owner, whole case | after reap |
| C6 decoy manifest | parent, once | `O_RDONLY\|O_NOFOLLOW` | not passed | owner, whole case | after reap |
| socketpair parent end | parent | default | no | yes | after reap |
| socketpair child end | parent | default | yes | no | right after spawn |

No descriptor is ever opened by the worker. There is no fallback reopen of any
source path anywhere in the worker: it holds only inherited numbers and uses only
`os.fstat`, `fcntl.fcntl(F_GETFL)`, `os.read`, `os.lseek`-free sequential reads,
and `os.close`. The single exception is the marker operation, which creates a new
file inside the private root and touches no source path.

## 6. Numeric limits

| name | value | source |
|---|---|---|
| `CONTROL_MAX_FRAME` | 8192 | brief |
| `MANIFEST_BYTE_CAP` | 8388608 | brief |
| `MANIFEST_COUNT_CAP` | 10000 | brief |
| `WORST_VALID_MANIFEST_BYTES` | 5840001 | derived, section 4.1 |
| `REQUEST_BYTE_CAP` | 1048576 | original `_WIRE_LIMIT` |
| `NAME_LIMIT` | 256 | original `_asset_path` |
| `FIXED_MEMBER_BYTES` | 71 | derived, section 4 |
| `EXPECTED_FIXED_MEMBER_BYTES` | 71 | the gate value the derived one must equal, section 4 |
| `POPEN_TOTAL` | 7 | brief: at most 7 workers |
| `CASE_BUDGET_S` | 2.50 | brief, per case, fixtures included |
| `RUN_BUDGET_S` | 8.00 | brief, whole run, strict `<` |
| `EXTERNAL_PARENT_S` | 10.00 | brief, parent-imposed, informational |
| `OP_S` | 2.00 | brief, marker operation |
| `CHALLENGE_S` | 0.50 | brief, control challenge round trip |
| `STOP_S` | 1.00 | brief, containment kill+reap |
| `TERM_PROBE_S` | 0.15 | terminate-to-kill probe slice |
| `TEARDOWN_RESERVE_S` | 0.25 | subtracted from every wait deadline |
| `SELECT_SLICE_S` | 0.10 | nonblocking IO poll slice |
| `MIN_WAIT_S` | 0.02 | floor for a positive remaining wait |
| lease exit code | 97 | absolute expiry |

Returncode ladder, one code per gate rung:

| code | meaning |
|---|---|
| 0 | accepted, marker written |
| 1 | parent harness gate failure |
| 2 | internal error |
| 3 | no or invalid channel/descriptor |
| 4 | control protocol violation |
| 5 | request descriptor gate (mode, identity, bytes, sha, parse, shape) |
| 6 | `manifest_mode` |
| 7 | `manifest_identity` |
| 8 | `manifest_bytes` |
| 9 | `manifest_sha` |
| 10 | `manifest_parse` |
| 11 | `member_count` |
| 12 | `member_record` |
| 13 | deadline or permit failure |
| 97 | absolute lease expiry |

## 7. Control protocol

Framing: 4-byte big-endian length prefix, then exactly that many bytes of JSON.
Both ends use nonblocking sockets driven by `selectors`, in slices of
`SELECT_SLICE_S`, against an absolute deadline. Bounded exact IO: the declared
length is checked against `CONTROL_MAX_FRAME` **before** the body is read, and the
body length must equal the declaration exactly. Every frame carries `v` (1),
`kind`, `session` (must equal the argv session id) and `seq`, strictly increasing
per direction; a repeat, a gap or a foreign session is a protocol violation
(exit 4).

Parent -> worker:

- `hello`: `nonce`, `request_sha`, `request_bytes`, `request_identity` (the
  original 7-field `_signature` tuple), `manifest_sha`, `manifest_bytes`,
  `manifest_members`, `manifest_identity`.
- `challenge`: no payload beyond the header.
- `permit`: `nonce`. Sent at most once per worker, only after `ready`.

Worker -> parent:

- `reject`: `gate`, `reason`, `observed` (the small observed facts that caused the
  refusal, e.g. the real `fstat` size or the real access bits).
- `ready`: `pid`, `request_bytes`, `request_tasks`, `manifest_bytes`,
  `manifest_members`, `manifest_sha`, `manifest_access`, `manifest_identity_ok`.
- `alive`: `pid`, echo of the challenge.
- `done`: `pid`, `marker`, `marker_bytes`.

Largest possible frame is `hello`, roughly 400 bytes: two 64-hex digests, two
7-field integer signatures, four integers and a 32-hex nonce. Every other frame is
under 250 bytes. The observed maximum is measured from real sends and receives and
gated `<= 8192` in every case. **No manifest byte, no member record and no request
field value ever crosses control**; only digests, sizes, counts, access bits and
identity tuples do.

## 8. Worker gate ladder

Fixed order, first failure wins, each failure sends one `reject` frame then exits
with its rung code. Order matters: it is what makes each negative case refuse at
its named gate rather than at some later one.

| # | gate | check | exit | reason strings |
|---|---|---|---|---|
| 1 | `channel` | argv descriptors valid, socket usable | 3 | `channel_unavailable` |
| 2 | `session` | session id and seq discipline | 4 | `session_mismatch`, `seq_violation`, `frame_over_cap`, `frame_length_mismatch` |
| 3 | `lease` | `expiry_mono - monotonic() > 0` at boot and before every wait | 97 | `lease_expired` |
| 4 | `request_mode` | `F_GETFL` access bits `== O_RDONLY`; `S_ISREG`; `st_nlink == 1` | 5 | `request_mode_not_readonly`, `request_not_regular`, `request_hardlinked` |
| 5 | `request_identity` | pre-read `_signature(os.fstat(fd)) == expected` | 5 | `request_identity_pre_read` |
| 6 | `request_bytes` | `st_size == expected`, `<= REQUEST_BYTE_CAP`, exact bounded read of `expected + 1` cap | 5 | `request_bytes_mismatch`, `request_bytes_over_cap`, `request_read_short`, `request_read_grew` |
| 7 | `request_sha` | `sha256 == expected` | 5 | `request_sha_mismatch` |
| 8 | `request_identity_after` | post-read `_signature == pre-read` | 5 | `request_identity_post_read` |
| 9 | `request_parse` | JSON via `_pairs`; `_closed` field sets; exact types | 5 | `request_duplicate_key`, `request_fields`, `request_type` |
| 10 | `request_shape` | genuine `QualificationRequest` reconstructed; `len(tasks) == 4`; every task `tier` in the original `TIERS`; pin counts `3/4/1`; digest `sha256:[0-9a-f]{64}`; bounds through the original `_bounds_from_wire`; every `FilePin` well-typed | 5 | `request_reconstruct`, `request_task_count`, `request_tier`, `request_pin_count`, `request_digest_shape`, `request_schema`, `request_bounds` |
| 11 | `manifest_mode` | `F_GETFL` access bits `== O_RDONLY`; `S_ISREG`; `st_nlink == 1` | 6 | `manifest_mode_not_readonly`, `manifest_not_regular`, `manifest_hardlinked` |
| 12 | `manifest_identity` | pre-read `_signature == expected` | 7 | `manifest_identity_pre_read` |
| 13 | `manifest_bytes` | `st_size == expected` AND `st_size <= MANIFEST_BYTE_CAP` | 8 | `manifest_bytes_over_cap`, `manifest_bytes_mismatch` |
| 14 | `manifest_sha` | exact bounded read, `sha256 == expected` | 9 | `manifest_sha_mismatch`, `manifest_read_short`, `manifest_read_grew` |
| 15 | `manifest_identity_after` | post-read `_signature == pre-read` | 7 | `manifest_identity_post_read` |
| 16 | `manifest_parse` | JSON array via `_pairs`, `parse_constant` refuses `NaN`/`Infinity`/`-Infinity`; `_closed(member, {key, root, sha256, size, snapshot_key})`; `type(size) is int` and not `bool`; strings are `str` | 10 | `manifest_not_array`, `manifest_duplicate_key`, `manifest_nonfinite`, `member_fields`, `member_type` |
| 17 | `member_count` | `len(members) <= MANIFEST_COUNT_CAP` | 11 | `member_count_over_cap` |
| 18 | `member_record` | per member: `root` in `{source, model, data}`; original `_asset_path(root, key)` accepts; `0 <= size <= 2*1024**3`; `re.fullmatch("[0-9a-f]{64}", sha256)`; `snapshot_key` satisfies the same 1..256 / charset / no-dot-component / not-absolute rule; `(root, key)` strictly ascending; `snapshot_key` unique | 12 | `member_root_unknown`, `member_key_rejected`, `member_size_range`, `member_sha_shape`, `member_snapshot_key`, `member_order`, `member_duplicate` |
| 19 | `ready` | send `ready` | - | - |
| 20 | `challenge` | answer within `CHALLENGE_S` | 13 | `challenge_timeout` |
| 21 | `permit` | exactly one fresh `permit`, nonce matching, within deadline | 13 | `permit_absent`, `permit_nonce_mismatch`, `permit_duplicate` |
| 22 | `marker` | `os.open(root + "/v212.marker", O_WRONLY\|O_CREAT\|O_EXCL\|O_NOFOLLOW, 0o600)`, write `pid`, `case`, `nonce`, `fchmod(0o600)`, `fsync`, close, within `OP_S` | 0 | `marker_exists`, `marker_timeout` |

Note on gate 11 versus gate 12: `st_mode` in `_signature` carries inode
permissions and file type, not the open-mode access bits, which live in the open
file description. An `O_RDWR` descriptor on the same inode has an identical
`_signature` to an `O_RDONLY` one. Only `fcntl.fcntl(fd, F_GETFL)` distinguishes
them, which is why the mode gate is separate and runs first, and why it is
genuinely load-bearing in C7.

Note on gate 13 versus gate 17: the byte cap runs before parsing and before the
count cap. C3 violates both caps; the observed refusal is the byte gate, and the
reason string proves it was the cap and not a size mismatch.

## 9. The seven cases

One fresh private root and one fresh `Popen` worker each. `popen_total == 7`.

| case | manifest bytes | members | expected rc | expected gate | expected reason | markers | permits issued |
|---|---|---|---|---|---|---|---|
| C1 `exact_control_overflow` | 8193 | 40 | 0 | none | none | 1 | 1 |
| C2 `worst_valid_bulk` | 5840001 | 10000 | 0 | none | none | 1 | 1 |
| C3 `byte_cap_refusal` | 8388609 | 14365 | 8 | `manifest_bytes` | `manifest_bytes_over_cap` | 0 | 0 |
| C4 `count_cap_refusal` | 960097 | 10001 | 11 | `member_count` | `member_count_over_cap` | 0 | 0 |
| C5 `wrong_expected_sha` | 2497 | 24 | 9 | `manifest_sha` | `manifest_sha_mismatch` | 0 | 0 |
| C6 `different_inode` | 2497 | 24 | 7 | `manifest_identity` | `manifest_identity_pre_read` | 0 | 0 |
| C7 `writable_mode` | 2497 | 24 | 6 | `manifest_mode` | `manifest_mode_not_readonly` | 0 | 0 |

Case construction:

- **C1.** Valid manifest at exactly `8193 = CONTROL_MAX_FRAME + 1`. Proves the
  payload is not squeezed through control: a control frame carrying it would
  exceed the cap by one byte, yet the run passes with `control_max_frame_bytes`
  observed under 8192. The worker reports `manifest_bytes = 8193` from its own real
  `fstat`, and the parent cross-checks that against its own generated length.
- **C2.** True worst valid input: `10000` members at maximum legal name width,
  exactly `5840001` bytes. Largest payload crossing a descriptor in this spike.
  Gated `manifest_bytes == 5840001`, `manifest_members == 10000`, rc 0, one marker,
  one permit, `control_max_frame_bytes <= 8192`. This case is the primary evidence
  for T1 and T2 together.
- **C3.** Valid canonical manifest at exactly `8388609`, one byte over the byte
  cap. The parent sends the TRUE generated size as the expected size, so gate 12
  (identity) and the `st_size == expected` half of gate 13 both pass and the
  refusal is unambiguously the cap. Refuses before any read, before any parse,
  before `ready`, before any permit.
- **C4.** Valid canonical manifest, `10001` members, `960097` bytes, far below the
  byte cap. Refuses at the count cap after a successful parse, so the count gate is
  not confounded with a parse failure. Before any permit.
- **C5.** Same identity, same descriptor, same real digest, but the parent sends a
  deliberately wrong expected `sha256` over control. Refuses at the digest gate
  after a full bounded read, proving the digest comparison is real and not skipped.
  Before any permit.
- **C6.** Parent creates two byte-identical, same-size manifest files with
  different inodes. It passes the descriptor of the decoy while `hello` carries the
  identity signature of the original. Digest and size match; `st_ino` differs.
  Refuses at the identity gate, proving identity is checked independently of
  content. Before any permit.
- **C7.** Parent opens the manifest `O_RDWR|O_NOFOLLOW` and passes that descriptor.
  Inode signature, size and digest all match. Only the access bits differ. Refuses
  at the mode gate, proving readonly-ness is enforced and not inferred from the
  inode. Before any permit.

C1 and C2 are the only positives, so `challenge_ms <= 500` and `marker_ms <= 2000`
are gated there. Negatives gate `challenge_ms == 0` and `marker_ms == 0` because no
challenge and no operation ever occur.

Every case additionally gates, from real observation:

- `popen_calls == 1`, `pass_fd_transfers == 3` (request, manifest, socket), or 3
  for C6 as well since the decoy is never passed.
- `passed_copies_closed == 3`, `owner_fds_retained >= 2`, `owner_fds_closed ==
  owner_fds_retained` at teardown.
- `worker_returncode == expected rc`, from the real `wait`.
- `reject_gate`, `reject_reason` from the real `reject` frame; empty for positives.
- `markers == expected`, from a real `os.listdir` of the root **after** the reap.
- `marker_mode == 0o600` for positives, from a real `stat`.
- `control_max_frame_bytes <= 8192`, from the real maximum over all frames.
- `worker_manifest_bytes == parent_manifest_bytes` and `worker_manifest_members ==
  parent_manifest_members`: the worker's own observations agreeing with the
  parent's independent generation.
- `lease_exits == 0`, `cleanup_errors == 0`, `retained_roots == 0`.

## 10. Custody, journal and cleanup discipline

- **Reap before snapshot.** The parent waits for the real exit, then lists markers,
  then closes owners, then removes the root. No snapshot precedes a reap.
- **Journal.** Implemented as the brief states it, not waived. Before any worker
  exists, the parent creates one run-private root (`mkdtemp`, `0700`, `_path`
  checked) and precreates `journal.log` inside it with
  `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0600`, then `fchmod(0600)`, one
  `journal_precreated` line and `fsync`. The parent is the only actor that ever
  passes `O_CREAT` on that path.
  Every worker appends exactly one `worker_exit` line, and the parent appends one
  `case_result` line per case. Both use
  `os.open(path, O_WRONLY|O_APPEND|O_NOFOLLOW)` with **no `O_CREAT`**, so a child
  that finds the journal missing fails instead of first-creating a shared path.
  Each append `fstat`s the descriptor first and refuses unless the file is regular
  and `S_IMODE == 0600`, which makes "the parent precreated it privately" an
  observed fact in the child rather than an assumption.
  A worker whose append fails on an otherwise accepted run escalates its exit code
  to `EXIT_PROTOCOL`, because an accepted run with no journal line is a custody
  failure, not a pass. The append sits outside the gate ladder so every exit path,
  including a refusal, is recorded.
  Run-level gates read the journal back: mode `0600`, exactly 7 `worker_exit`
  lines, exactly 7 `case_result` lines, zero unparsable lines. On PASS the run root
  is removed; on FAIL it is retained and its path is reported, matching the
  failed-custody rule.
  Separately, inside each per-case fixture root exactly one actor writes, the
  worker, and it writes one file with `O_CREAT|O_EXCL`. That exclusive create is
  the marker operation, not a journal, and it is the operation the permit gates.
- **Accepted runs.** No forced cleanup, no lease exit, no retained owner, no
  retained root. `retained_roots == 0` and `owner_fds_closed == owner_fds_retained`
  are gated for every passing case.
- **Failed custody.** If a case fails a gate, the root is retained as a real
  directory and the `Popen` object is retained as a real object in the resource
  list, with `retained_roots` counted and reported. Owner descriptors are still
  closed, because leaking descriptors would corrupt every later case's observations.
- **Containment.** On any wait timeout the parent runs `terminate`, polls in
  `TERM_PROBE_S` slices, then `kill`, then reaps, all inside `STOP_S`. Because
  every case has a defined exit code and exits on its own, containment is expected
  to be unused; `containment_used == 0` is gated, and a nonzero value is a failure.
- **Absolute expiry.** One immutable run expiry is computed once by the parent and
  passed to every child as both a monotonic and a wall deadline. Each worker arms a
  daemon `threading.Timer` for its remaining lease at boot, whose handler is
  `os._exit(97)`. There are no lease resets, no epsilon, and no wait that continues
  past expiry: every wait deadline is `min(case_deadline, expiry_mono -
  TEARDOWN_RESERVE_S)`, and a non-positive remaining wait is refused immediately
  rather than clamped upward. A worker whose boot lease is already non-positive
  exits 97 without doing any work.
- **No descendants.** Workers call no subprocess, `fork`, `exec` or `setsid` API.
  `start_new_session=True` appears only on the parent's single `Popen`.

## 11. Timing plan

Budget arithmetic, all unmeasured and disclosed as such:

| item | estimate | basis |
|---|---|---|
| interpreter start, parent | 40 ms | one process |
| genuine-shape import chain, parent | 120-250 ms | ~10 stdlib modules incl. `sqlite3`, `ast`, `dis`, `zipfile`, `decimal` |
| interpreter start + import chain, per worker | 150-250 ms | same chain, cold, 7 times |
| C1 fixture generation | 5 ms | 8193 bytes, 40 members |
| C2 fixture generation | 200-350 ms | 5840001 bytes, 10000 members, string build plus `json.dumps` plus write |
| C2 worker read + hash + parse + record validation | 350-600 ms | `sha256` of 5840001 bytes (~10 ms), `json.loads` of 5840001 bytes with `object_pairs_hook` called 10001 times, then 10000 `_asset_path` calls each doing a `re.fullmatch` and a `PurePosixPath` |
| journal appends, whole run | < 5 ms | 15 short lines, each one `open`/`fstat`/`write`/`close` with no `O_CREAT` |
| C3 fixture generation | 300-500 ms | 8388609 bytes, 14365 members; the worker never parses it |
| C4 fixture generation + worker parse | 80-150 ms | 960097 bytes |
| C5, C6, C7 fixture generation + worker | 20-40 ms each | 2497 bytes |

Per-case totals: C1 ~0.30 s, C2 ~1.10 s, C3 ~0.85 s, C4 ~0.40 s, C5-C7 ~0.30 s
each. Sum ~3.75 s. Plus parent start and teardown ~0.40 s. Projected run total
~4.15 s against the strict `< 8.00 s` gate, leaving ~3.85 s of headroom. Worst
single case C2 at ~1.10 s against the 2.50 s per-case gate, leaving ~1.40 s.

The dominant risk is the genuine-shape import chain, which is paid eight times and
is entirely unmeasured. If it costs 400 ms per process instead of 250 ms, the run
total rises to roughly 5.35 s, still inside the gate. If it costs 700 ms per
process, C2 alone reaches ~1.55 s and the run reaches ~7.3 s, which is inside the
gate but with too little margin to be comfortable. The report states this as the
principal timing risk and names the measurement the parent should take first:
`python3 -X importtime -c "import bench.task, train.native_qualification"`.

Deadline enforcement is absolute, not estimated. Every case deadline is
`min(case_start + 2.50, expiry_mono - 0.25)`, every wait is sliced at 0.10 s, and
every timeout is a real observed failure with a real counter, never a silently
extended wait.

## 12. Minimal guard-loss and restored controls

Planned here, not implemented. The brief forbids generating unrequested control
copies, and the parent owns controls and runs. Each control names one specific
gate, states the observable that would change if that gate were removed, and states
the restored expectation. Together they establish that each gate can fail, which is
the only thing that makes the green results meaningful.

| gate | guard-loss: remove it and rerun the named case | expected changed observable | restored expectation |
|---|---|---|---|
| `manifest_bytes` (gate 13) | delete the `st_size <= MANIFEST_BYTE_CAP` comparison, rerun C3 | C3 parses 14365 members, then refuses at `member_count` (rc 11) instead of `manifest_bytes` (rc 8); if the count cap were also removed it would reach `ready`, take a permit and write 1 marker | C3 rc 8, gate `manifest_bytes`, reason `manifest_bytes_over_cap`, 0 markers, 0 permits |
| `manifest_mode` (gate 11) | delete the `F_GETFL` access-bit comparison, rerun C7 | C7 passes identity, bytes and digest, because an `O_RDWR` descriptor on the same inode has an identical `_signature`; it reaches `ready`, takes a permit, writes 1 marker, rc 0 | C7 rc 6, gate `manifest_mode`, 0 markers, 0 permits |
| `manifest_identity` (gate 12) | delete the pre-read `_signature` comparison, rerun C6 | C6 passes, because the decoy is byte-identical and same-size; 1 marker, rc 0 | C6 rc 7, gate `manifest_identity`, reason `manifest_identity_pre_read`, 0 markers |
| `manifest_sha` (gate 14) | delete the digest comparison, rerun C5 | C5 passes with a wrong expected digest; 1 marker, rc 0 | C5 rc 9, gate `manifest_sha`, 0 markers |
| `member_count` (gate 17) | delete the count comparison, rerun C4 | C4 validates 10001 records, reaches `ready`, takes a permit, 1 marker, rc 0 | C4 rc 11, gate `member_count`, 0 markers |
| `CONTROL_MAX_FRAME` (section 7) | raise the send cap and route the C2 manifest through a control frame instead of a descriptor | the send of 5840001 bytes either exceeds the declared cap and is refused as `frame_over_cap`, or, with the cap raised, proves the manifest does not fit in a control record at all | C2 passes with the manifest on a descriptor and `control_max_frame_bytes <= 8192` observed from real frames |
| `manifest_identity_after` (gate 15) | delete the post-read `_signature` comparison | no case in this set changes, because no fixture mutates a file mid-read; the guard is unexercised | unchanged; recorded as an unexercised guard, not as evidence |
| original `_asset_path` (gate 18) | replace the call with a local `len(key) <= 256` check, rerun C2 | C2 still passes, because every generated key is charset-clean; the loss would only appear on an adversarial key such as `../escape` or an empty path component | C2 rc 0 with `_asset_path` as the validator; recorded as a coverage gap |

The sixth row is the control that most directly answers the unknown: it is the only
one that shows the manifest genuinely cannot ride the control channel. The seventh
and eighth rows are recorded honestly as guards this fixture set does not
exercise, so a green run is not read as proof that they work.

## 13. Counters are observed, never constant

Every reported number comes from a real call, a real message or a real filesystem
observation. Specifically:

- `popen_calls` increments inside the single `Popen` wrapper, from the real call.
- `pass_fd_transfers` and `passed_copies_closed` count real `os.dup` and real
  `os.close` calls.
- `owner_fds_retained` and `owner_fds_closed` count real owner opens and closes.
- `permit_issued` counts real `permit` frame sends.
- `control_frames_sent`, `control_frames_recv`, `control_max_frame_bytes` come from
  real frame writes and reads.
- `manifest_bytes` and `manifest_members` on the parent side come from real
  `len(payload)` and real `len(members)` at generation.
- `worker_manifest_bytes`, `worker_manifest_members`, `worker_manifest_sha` come
  from the worker's real `fstat`, real read count and real `hashlib` digest, and
  are cross-checked against the parent's independently generated values.
- `markers` comes from a real `os.listdir` after a real reap; `marker_mode` from a
  real `stat`.
- `worker_returncode` comes from a real `wait`.
- `fixture_gen_ms`, `worker_ms`, `challenge_ms`, `marker_ms`, `elapsed_s` come from
  real `time.monotonic` differences.
- `lease_exits`, `cleanup_errors`, `containment_used`, `retained_roots` count real
  events.
- `journal_mode` and `journal_lines` come from a real `stat` and a real read-back
  of the journal after the run, not from a count of intended appends.

No case asserts a hard-coded counter. Where an expected value is a literal, it is
compared against an observed value, never substituted for one.

## 14. PROVES, SHORTCUT, MISSING

### PROVES, if the run passes

1. A genuine fresh `Popen` worker consumed a `5840001`-byte, `10000`-member
   canonical manifest from an inherited readonly descriptor, hashing and parsing it
   in-process, with no path reopen.
2. The same worker reconstructed a genuine `QualificationRequest`, with genuine
   `SqlTask`, `FilePin` and `AttemptBounds` values, from a second inherited
   readonly descriptor.
3. Every control frame in every case, including the largest-manifest case, was
   `<= 8192` bytes, measured from real frames. A `8193`-byte payload (C1) and a
   `5840001`-byte payload (C2) both crossed by descriptor while control stayed
   under the cap.
4. Readonly-ness, inode identity, byte cap, digest, member count and per-record
   validity are each independently enforced, each with its own exit code, and each
   refuses before any operation permit is issued.
5. Exactly one exclusive `0600` marker was written by each positive worker after
   exactly one fresh permit, observed after a real reap; zero markers and zero
   permits for every negative.
6. Parent custody survived: every worker was reaped, every owner descriptor closed,
   every root released, no lease exit, no forced cleanup, no descendant, no
   exec or session outside the parent's single `Popen`.
7. The parent-precreated `0600` journal discipline held under real use: 7 workers
   each appended exactly one line to a file they never created, each having
   `fstat`-verified it was a regular `0600` file first, and the parent read back
   exactly 7 `worker_exit` and 7 `case_result` lines.

### SHORTCUT, deliberate and disclosed

1. The request envelope is `v212-request-projection-v1`, not the original
   `native-sql-worker-v1`, because blockers B1 and B2 make the original serializer
   unusable and its format 1 MiB capped. The payload is a genuine
   `QualificationRequest`; the envelope name is not original.
2. The manifest record `{root, key, size, sha256, snapshot_key}` with a `10000`
   cap is this spike's shape, not the original `{kind, key, size, sha256}` with a
   `1024` cap. Only the key rule, the closed-field discipline, the duplicate-key
   hook and the size/digest shapes are borrowed, and the key rule is borrowed by
   calling the original function.
3. The manifest is a bare JSON array with no schema wrapper, to keep the exact-byte
   arithmetic clean and to avoid adding a field outside the approved record set.
4. C2 uses `5840001` bytes, not the declared `8388608`, because the declared target
   is infeasible under the actual 256-char name limit and the `10000` member cap.
   Disclosed in section 4.1 with the arithmetic and the absolute upper bound.
5. The request projection is delivered by descriptor even though it is small enough
   for a control frame, because the unknown concerns the descriptor path for both
   payloads.
6. Parent and child share one open file description per passed descriptor. Safe
   here because the parent never reads or seeks after spawn, but it is not the
   isolation a second independent `os.open` would give.

### MISSING, not demonstrated by this spike

1. **Snapshot-member content validation.** No snapshot member is read, hashed or
   compared. `snapshot_key` is validated for shape and uniqueness only. No snapshot
   directory descriptor is passed, because no snapshot content is touched. If
   snapshot members must be verified, that is a separate spike.
2. **Manifest member byte verification.** Each member's `size` and `sha256` are
   synthetic declarations. No member file exists and none is read. The spike proves
   the manifest is delivered, parsed and record-validated; it does not prove any
   member's bytes.
3. **Request pin byte verification is parent-side only.** `_check_asset_bytes` is
   called by the parent once per pin at fixture-build time, on the spike's own
   newly created synthetic files, so every pinned size and digest is real and was
   verified with the original before/at-open/during/after signature discipline.
   What is **not** done is re-verification of those pins inside the worker: the
   worker reconstructs `FilePin` values from the wire and validates their shape
   and types, but it never re-reads or re-hashes the pin files. It holds no
   descriptor for them, and opening them by path would break the no-reopen rule
   this spike exists to test. So a green run proves the pins were genuine when the
   parent built them and that they survived the wire intact as values, not that
   their bytes were still correct at worker read time.
4. **Fixture-database content.** `_validate_fixture_scope` is never called. The
   projection's `db_path` values point at newly created private synthetic files
   that are **not** sqlite databases and contain no `readings` table.
5. **`_validate_request` as a whole.** Never called, for blocker B1 reasons. Root
   overlap, image-digest registration, model inventory verification and the frozen
   construction-source pin are all unexercised.
6. **Guards 15 and 18 of section 12.** The post-read identity comparison and the
   original `_asset_path` call are not exercised adversarially by any fixture in
   this set. A green run is not evidence that they catch anything.
7. **Concurrency.** One worker per case, sequential. The seven workers do share one
   journal path, but they append to it one at a time and none of them passes
   `O_CREAT`, so the concurrent-first-create failure mode the brief mentions is
   structurally excluded rather than exercised. No two workers share a fixture root
   or a descriptor. A green run is therefore not evidence about concurrent
   first-create behaviour; it is evidence that the no-`O_CREAT` discipline holds
   when it is never put under contention.
8. **All timing.** Every number in section 11 is an estimate. Nothing was executed.

## 15. Order of work

1. This plan.
2. `spec/spikes/core-v212-bulk-fd.py`: constants, exceptions, lease, framed
   nonblocking control, manifest fitter and generator, request projection build
   and reconstruct, descriptor identity helpers, worker mode, parent resources and
   spawn, fixture builder, seven fixed cases, harness, dispatch.
3. `docs/core-v212-bulk-fd-report.md`: honest SOURCEONLY UNRUN report, restating
   blockers B1-B3, the infeasible `8388608` target, the final line count and why it
   differs from the ~400-600 line preference, and everything in section 14.

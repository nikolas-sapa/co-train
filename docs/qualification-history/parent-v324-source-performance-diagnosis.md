> Sanitized public reference. Historical acceptance applies to the private original, not these derivative bytes.

# V324 source-only performance diagnosis

Status: SOURCEONLY UNRUN. BLOCK on claiming a materially sufficient repair or implementing before the parent test plan. One bounded allocation candidate identified below. No authority for recovery, retry, bulk reads, moves, signals or another full-volume run.

## Tools and scope

Available file tools: Read, Grep, Glob, ApplyPatch. Used only file-tool orchestration. This report is the sole authorized new file. No production, C, fixture or test source edited. No commands, imports, compilation, tests, Git, network, SDK, installed interpreter, locks or asset reads.

Source root A: /qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-qwen-engineering-host

Evidence root R: /qualification-reference/scratch/cotrain-devin-continuation-2026-11-06

Current owner identity supplied by parent: 95,225 bytes, SHA256 684a5ed32b5642415aa50b7be69c255a106363100eeacdedc67050ba08eee99a. Hash not independently recomputed. Fresh source read confirms both immutable globals at A/train/qualification_isolated_owner.py:63-64 and their current uses at :1395 and :1402. Neither global is proposed again.

## Measured evidence, not a completed validation

Read R/parent-v323-full-volume-nonpass.json and R/parent-v323-timeout-journal-observation.json.

- Fresh authorized full-volume attempt timed out externally at 30s. Internal limit remains 29s; working headroom goal remains <=23s. Both recovery and execution claims are consumed, with no retry authority.
- 68 records, 9,099 journal bytes. Actual C entry and original receipt exit observed.
- Last recorded bulk-read lower bound: 8,321,499,136 bytes (7.75GiB), checkpoint-2/trainer_state.json. Journal wall/CPU spans: 28.549480084s / 20.298816s. C-observed wall/CPU spans: 28.507791792s / 20.259533s.
- The 5.5-to-5.75GiB interval took 2.049646292s wall and 0.900152s CPU. This does not identify a scheduling, storage, filesystem, hashing or instrumentation cause.
- No execution report or metrics. Progress beyond the last record, final full-content hash, validation close/seal, publication, joins and release remain UNKNOWN.
- All 8,589,934,592 bytes remain retained according to parent evidence. No retained bytes accessed here.

R/parent-v315-journal-green-volume-frozen.py:799-822 emits progress after the actual RegisteredReader.read returns, before the outer C read loop resumes. Therefore the final threshold does not itself establish the final block's C hash update. Its EOF/bulk-exit records likewise precede completion of C's subsequent final hash/identity work.

## Highest-evidence source costs

### 1. Fresh ancestor results repeatedly become temporary five-field tuples

A/train/qualification_isolated_owner.py:

- :135-146, _directory: performs live ownership/mode checks, builds a transient (0, os.getuid()) membership tuple, then returns a five-field directory identity tuple.
- :332-343, _Anchor.check: for each retained pin, independently fstats the open directory, stats its retained name when present, validates both fresh results, then compares each projected identity with the retained pin.
- :402-410, _File.check: checks the entire parent ancestry before named/open file identity.
- :1156-1165, RegisteredReader.read: executes two complete _File.check calls around each actual read.

Source-derived count, not profiling: the fixture path /qualification-reference/scratch/pc322-wsjm2kx3/volume-case/export/run/checkpoint-N has nine directory pins including /. See R/parent-v315-journal-green-volume-frozen.py:356-370 and A/train/qualification_isolated_owner.py:302-320,365-366,787-788. Each full ancestry pass evaluates nine open plus eight named results, or 17 _directory calls. Two passes give 34 calls per successful read iteration.

For 131,072 positive full-64KiB reads across exact 8GiB, that implies 4,456,448 five-field projection tuples and the same number of transient UID membership tuples. EOF, metadata, acquisition and final-sweep work add more. Short reads increase iteration count. This is the largest explicit repeated projection-allocation site identified, not a measured allocation or time attribution.

The stat_result objects, fresh stat/fstat operations, policy checks, UID queries and all retained pins are required and are not proposed for removal.

### 2. Lease-proof comparisons still package live values; path parsing is not per chunk

A/train/qualification_isolated_program.py:606-638 and A/train/qualification_isolated_owner.py:1149-1165,1198-1225 imply 22 successful active lease assertions and four yields per ordinary successful read-loop iteration. Full-sized positive reads alone imply 2,883,584 assertions.

A/train/qualification_isolated_owner.py:1396-1397 constructs a fresh two-field outcome comparison tuple per assertion. :1395 compares ChildObservation values. A/train/qualification_isolated_contract.py:354-364 declares the frozen dataclass without a custom equality method; generated equality may add intermediate packaging, but no installed interpreter/source or generated implementation was inspected. No exact allocation count or proposed DTO change follows from that hypothesis.

By contrast, _parts at owner :121-127 is reached through file/directory acquisition and inventory, not the ordinary chunk body. Optimizing path splitting or ExportEntry construction would not remove a demonstrated per-64KiB cost. Replacing proof equality with shortcuts risks altered exact-class/value/refusal behavior and is not the selected candidate.

## ONE candidate for parent test-plan evaluation

Allocation-free directory identity projection comparison at the two _Anchor.check call sites (:337 and :339-340), with an expected-pin mode in _directory.

Keep the existing _directory policy statements and their order unchanged. Existing acquisition callers still receive the original five-field tuple. Only the two existing fresh-stat comparison sites pass their already-retained expected pin and receive a boolean match instead of allocating a fresh identity tuple. In that mode:

1. Validate the fresh stat result with every existing ownership, writability and private-mode predicate, including the same live os.getuid calls.
2. Load dev, ino, mode, uid and gid from that fresh result in the original field order before comparison.
3. Compare all five fields with the existing retained pin, preserving lexicographic equality short-circuit order; construct no projection tuple.
4. Keep the existing outer require and exact error labels at their original positions.

This changes representation of a fresh observation, not observation frequency or authority. It does not cache a stat result, UID, validation result, lease fact or proof. Do not also change UID membership, DTO equality, _File identity representation, C, chunk size, checks or scheduling.

This is a candidate, not a justified speed fix. Five scalar Python comparisons and extra branching can cost more than tuple construction/equality. Removing approximately 4.46 million small tuples does not establish seconds saved, nor explain the wall-minus-CPU gap. BLOCK on claiming <=23s or even a material gain without new authorized evidence. If preserving comparison/evaluation order cannot be demonstrated, reject this candidate rather than relax a guard.

## NEW tests first, before any implementation

Use new cases with actual A/C tiny-output helpers in A/train/test_qualification_ac_valid_output.py:124-197,298-321,324-390. _install_fixture captures/restores real _ParentValidator.validate and forwards the actual C body; _release invokes actual adapter release. Do not use test_qualification_isolated_owner.install_lease_body as evidence of real C completion: it substitutes the validator body. Lifecycle observations remain synthetic and must be labeled so.

Proposed new oracles, all UNRUN and pending parent plan:

1. **test_directory_projection_no_temporary_identity_on_active_checks**: instrument and forward actual _directory calls only around active chunk ancestry checks, excluding pin creation. For N returned reader calls and actual pin depth D, require exactly 2*N*(2*D-1) directory validations and zero tuple-valued directory returns from those comparison sites after the candidate. Current code must fail the zero-tuples assertion with a positive count. Existing acquisition calls must still return exact five-field tuples.
2. **test_directory_projection_fresh_observation_order**: for each isolated chunk, record forwarded actual fstat/stat, policy validation, file checks, read, active assertions and yields. Candidate trace must match a baseline trace in count and order, normalizing only fixture FD generations and timestamps. Require 22 active assertions, four yields and two full file/ancestor checks per ordinary successful loop iteration. Each observation must call the original operation, not return a fabricated success.
3. **test_directory_projection_rejects_each_fresh_identity_field**, parameterized over open/named observations and dev/ino/mode/uid/gid: 10/10 changed fresh projections refused at the matching original check. One-field stat-result mutations are explicit fault injection after forwarding the real stat. Removing any field comparison must make its corresponding test fail. No publication.
4. **test_directory_projection_keeps_live_policy_and_postread_checks**: new cases inject fresh unsafe directory mode, changed live UID policy result, changed post-read identity and changed closed-reader final-sweep identity. Require refusal at the first applicable unchanged boundary and zero validated/publication results. Include a real tiny fixture mode/name mutation, not exclusively synthetic stat results.
5. **test_directory_projection_tiny_actual_c_publication_release**: unchanged tiny receipt/outcome validation, exactly one actual C call, two inventories, all eight reader closes and final named-pin sweep, one publication, second publication refused, actual release with no live registry resources/latch. Add new expiry/cancellation and unknown-close cases at the changed comparison boundary: cancellation still invalidates the lease; unknown close never retries or releases retained ancestry.

The allocation oracle proves a specific removed cost, not speed. Before considering volume authority, a separately approved bounded comparison must show a repeatable CPU reduction for the same real-stat/tiny-A/C workload, unchanged observation traces and zero regression failures. Parent must set its numeric performance threshold in the test plan; no timing benchmark or new test has been run here. A tiny result cannot prove full-volume headroom.

## Non-goals and next gate

No coalesced/skipped checks, removed yields, live-fact caches, bigger reads, reduced input, relaxed limits, altered C or DTO contract, recovery, retry, installed-interpreter hashing or stager work. Exact 8GiB, 64KiB reads, 29/30s limits and <=23s working goal remain unchanged.

Next action: parent reviews this single candidate and supplies a tests-first plan or rejects it. No implementation or execution implied. Source evidence alone is insufficient to promise a materially adequate repair.

VERIFY_REAL: Only permitted source/metadata inspection and this report write. No execution or new performance measurement. Publication/release and full current hashes remain UNKNOWN.

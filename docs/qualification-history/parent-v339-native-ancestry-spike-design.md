> Sanitized public reference. Internal workflow identifiers replaced; historical acceptance applies to the private original.

# V339 candidate-only native ancestry spike design
Status: DESIGN ONLY, SECURITY SOURCE REVIEW CLEAR. Nothing built, imported or executed.
User selected this design scope, not native implementation or execution.

Architect: public-review-03, source-only.
Parent-persisted design with explicit parent corrections below.
Baseline owner SHA supplied from prior verification:
684a5ed32b5642415aa50b7be69c255a106363100eeacdedc67050ba08eee99a.

## 1. Tests FIRST

Freeze executable tests before native helper implementation. All are NEW tests;
existing helper functions may be reused, not old test bodies rerun.

T1 native_boundary_binding_equivalence
- Zero differences for positional/keyword calls, missing/excess/duplicate/unknown
  arguments, bound/unbound descriptors, exception type and args.
- Thin Python wrappers keep signatures _directory(info, private), check(self).
- Preserve argument-binding name/qualname behavior, not just inspect.signature.
- Zero copied owner classes or duplicate owner-module instances.

T2 native_policy_exhaustive_equivalence
- All65536 modes x2private flags:131072 exact tuples or exception type/args.
- Genuine stat metadata, test-only fault views preserving all other fields/nanos.
- Include root/nonroot UID, writable/sticky ancestry and private700 rejection.
- Original stat.S_ISDIR, stat.S_IMODE, getuid, bool and require observations.
- ZERO mode-mask substitutions, missing policy calls or precomputed live facts.

T3 native_lookup_and_mutation_equivalence
Eight schedules, zero ordered-event/result/exception differences:
1 fstat replaces canonical _directory.
2 fstat replaces canonical require.
3 getuid replaces require and policy functions.
4 a stat-field callback replaces the applicable stat function.
5 a callback appends/deletes entries in the current pins list.
6 a callback rebinds self.pins to a different iterable.
7 a callback mutates current record/root attributes.
8 custom iteration/unpacking fails or produces malformed rows.
Rows cover lengths0..6, noniterables and exceptions while unpacking. Preserve
consumption count, not merely eventual refusal. Include deletion/builtins
fallback and truthy non-bool comparison results passed unchanged to require.

T4 native_observation_and_identity_equivalence
- Compare baseline/candidate on SAME actual open reader and pin generation.
- ZERO ordered trace differences. NO normalization of descriptor numbers,
  identity fields, ancestor timestamps, errors or ambient changes. Preserve a
  failure rather than normalizing/retrying it. Compare the original policy's
  identity fields; do not add atime to its invariant.
- Depth10 trace:22fstat,20stat,38directory,4regular,54getuid,221ownerrequire,
  6lease assertions,6monitors,12child observations,12channel checks per read.
- Five directory identity fields at open/named boundaries:10/10 refusals,
  matching first refusal, zero publication. Lifecycle observations synthetic.

T5 native_exception_and_reference_equivalence
- Every reached callback/iterator/unpack failure propagates the ORIGINAL
  exception object; zero subsequent observations after terminal failure.
- Zero double decrefs, leaked owned references or premature finalizers.
- Reentrant/destructor probes compare observable operand/temporary lifetimes.
- 10000-call stress returns tracked reference counts to baseline after teardown.
  This is a leak screen, NOT proof of memory safety.

T6 native_actual_c_lifecycle_equivalence
- Fresh actual tiny A/C entry:1validation,2inventories,8reader closes,
  24identity checks,1publication,second publication refused,actual release
  leaves0live owned resources/latch.
- Cancellation, expiry, post-read mutation and unknown close preserve exact
  refusal/custody. Unknown means retain ancestry/actual errors, no close retry,
  forged release, detached cleanup or retired-FD probe.

T7 native_negative_control
- Isolated RED omits ONLY named-ancestor identity comparison. Corresponding
  mutation case MUST fail while unchanged baseline refuses.
- Freeze tests before GREEN; retain actual nonzero RED result. No relabeling
  unexpected exceptions, selective case omission or benchmark-driven retries.

T8 native_real_entry_performance_screen
- Existing permitted tiny A/C positive reads and COMPLETE lifecycle; no new
  bulk data. Saved actual RegisteredReader.read repeated-EOF inner measurement:
  20warmups each,6alternating AB/BApairs x400reads each,all12CPU/wall samples.
- Restore all observation wrappers before timing. First timed calls reported
  separately, NOT mislabeled cold if preceded by trace calls.
- Median pairedCPU<=0.90 AND worst<=1.05; failure REJECTS without tuning/rerun.
- Full tiny-flow screen:6AB/BApairs with fresh case/owner/lease for EVERY flow,
  never reuse a consumed owner/lease. Complete setup-to-actual-release CPU/wall
  per flow; worst pairedCPU<=1.05. Freeze a source-reviewed fresh-fixture factory
  and exact case selection before these flows may execute.
- Report fresh-process build, import and first-helper-call costs separately.
  Proposed POST-HOC gates:artifact<=4MiB,import wall<=1s,first helper<=100ms.
- Not positive64KiB/8GiB throughput evidence or <=23s headroom. Passing is not
  production/GPU qualification. No automatic promotion to working reference.

## 2. Chosen implementation boundary, AFTER later approvals

Candidate-only first-party C extension implementing ONLY _directory and
_Anchor.check. Thin Python signature/descriptor wrappers install temporarily
onto the ORIGINAL canonical owner module/class in an isolated reviewed fixture.
No cloned owner class/import namespace, production file or installed package
replacement. No raw-FD or independent authority interface.

The C helper handles ordinary existing Python objects. All filesystem
observations remain calls to existing Python functions. No direct syscalls,
opens, closes, processes, timers, threads, executors or detached work.

### Exact evaluation semantics

Translate ORIGINAL expressions, not rejected inline-mask variants:
- Resolve each callable before its argument expressions, as original evaluation.
  Outer require and inner _directory are both resolved at their original sites.
  Replacement during fstat cannot change an already-resolved callable.
- Later lookup sites observe fresh replacements/deletions.
- Global name lookup must preserve original function globals AND its original
  builtins mapping, not module.__getattr__ or a new builtins snapshot.
  Namespace-container identity may mirror original function lifetime; never
  cache mutable namespace VALUES/callbacks across observation boundaries.
- Preserve short-circuit operand objects, truth conversion, rich comparison,
  original UID tuple construction and getuid calls. Do not convert comparison
  results early to bool before passing them to require.
- Preserve all labels, tuples, attribute evaluation and exception propagation.
- Read self.pins once to establish the original iterator. Existing-list mutation
  is visible; rebinding self.pins does not redirect that iterator.
- Unpack each row with Python's five-target semantics and consumption. Do not
  eagerly materialize arbitrary iterables or impose a new iteration cap.
- Read repeated root/record attributes at their original sites.

### Reference ownership, signals and cancellation

Document each borrowed/owned reference and keep operands alive exactly where
the Python evaluation stack would. Error exits retain the original exception,
release owned temporaries in compatible order and do no additional validation,
I/O or cleanup-authority operations.

Hold GIL for Python-object operations. Preserve original Python callback paths.
Async reader/checkpoint/yield/cancellation behavior stays unchanged. Signal
responsiveness and any native signal-check points require dedicated review;
extra checks can themselves change mutation/exception order. Exact nanosecond
signal timing is not promised. Unproved responsiveness/semantics BLOCKS.

No limited-API/stable-ABI claim. Exact public C interfaces/header compatibility
must be established only under separately approved read scope. If the required
semantics cannot be preserved, REJECT, do not use private ABI/trust bypass.

## 3. Approval gates

### A. Next proposed action: metadata-only preflight, NOT AUTHORIZED

One invocation of the already-approved parent stdlib runtime, one payload
process, no children/fallback/retry; external5s, cooperative collection deadline4s,
generated result<=8KiB. Internal checks cannot interrupt a blocked syscall;
serialization/write are not covered by the collection deadline. External
timeout is not universal OS/scheduling containment.

Parent CORRECTION to architect's initial sysconfig proposal: do NOT invoke
sysconfig.get_path/get_config_var/get_platform or other discovery helpers.
Avoid extra configuration/SDK/possibly executable discovery delegated to them.

Proposed metadata only:
- Builtin sys implementation/version/abiflags/cache_tag/platform/maxsize,
  executable STRING (do not resolve/stat/hash executable), prefix/base_prefix.
- Builtin _imp.extension_suffixes; no installed-module/package enumeration.
- os.uname for descriptive machine metadata, NOT native ABI/kernel proof.
- Exact path metadata/canonical resolution only for:
  /Library/Developer/CommandLineTools/usr/bin/clang
  /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk
  <reported sys.base_prefix>/include/python3.12
  that directory/Python.h and that directory/pyconfig.h.
- No config/header/binary contents or hashes. Ordinary trusted stdlib startup
  imports are the sole existing-runtime reads needed for the query.
- Canonical resolution explicitly permits component/symlink metadata traversal
  needed for nominated paths, including traversal before final-scope rejection.
  Results are non-atomic descriptive observations. Two equal lstats neither pin
  ancestry nor exclude replacement/ABA races. Final-object owner/mode checks do
  not certify ancestors or future use. No custody/execution authority results.
- Identity/size/time/maxsize fields use decimal strings; bounded version
  components remain exact small JSON integers. Trusted imports are a premise;
  the audit hook is not an import allowlist or universal sandbox.
- Use isolated/no-site/no-bytecode startup and cleared environment; no compiler,
  xcrun, shell helper, subprocess, network, ctypes or candidate native import.
- Freeze exact query source, command and output/error schema, and source-review
  them before asking for execution approval. No "approve design" inference.
- Refuse on approved-runtime/version mismatch, unknown ABI-relevant metadata,
  missing/unusable nominated paths, oversize/truncation, timeout/query error or
  need for scanning/fallback. Metadata success grants no build/header access.

No installed interpreter hash or original stager reuse: original three-hash
authority remains CONSUMED_NO_RETRY. No new approval for it is requested.

### B. Native API/build-containment plan, separately approved

After A only if useful, freeze exact narrowly named header/API read scope,
runtime/compiler/SDK compatibility evidence, compiler/link argv and sources,
process topology, authority/termination/actual-reaping ownership, artifact paths,
build/import attempts and limits. Header reads need explicit permission.

BLOCK: clang DRIVER can spawn cc1/linker descendants. External timeout or the
<=1s unrearmed birth probe proves neither descendant containment nor zero-live
cleanup. Do not assume single-process compiler behavior. Direct frontend/link
phases are future investigation only, not frozen or approved commands.
Compiler run remains CLOSED until the process plan is reviewed/approved.

### C. Source implementation and execution, separately approved

Proposed source ceilings:64KiB helper/wrappers,32KiB NEW tests. Candidate-only
newly approved directory, no dependency/install/config/model selection changes.
Build/import/test attempts and exact enforced time/file/process controls must be
set in B before execution. Proposed post-hoc size/import/performance gates are
not hard containment. No native C implementation/source is authorized now.

## 4. Non-goals / known blockers

No current compiler/SDK/header/config/binary/installed-runtime inspection,
native implementation/build/import/test, OS/provider/GPU action or snapshot/
production/stager change. Preserve every check,64KiB/exact8GiB/internal29/
external30. No new bulk generation or retained-volume access/recovery/retry.
Retained V323 hash completion/publication/release remain UNKNOWN.
Pure22pass short-lived birth-probe arithmetic does not establish build
containment or1800sGPU lifetime. GPU/native/science0/7; no speed/ETA promise.

VERIFY_REAL: design only. No native code, binary, header inspection, compiler
command or new test execution. Existing V335/V337 results remain separate.

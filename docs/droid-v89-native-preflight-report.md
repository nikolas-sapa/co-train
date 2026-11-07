# Native constructor preflight, V92 corrective source handoff

## Parent V111 source correction

Check every inspected MRO namespace key is exact str before membership/index.
Added four FakeRuntime colliding-key cases (object/str-subclass, initial/
postbaseline), armed after fixture construction, requiring zero key callbacks
and zero trainer-body entries. Intended memory target 89 cases, all new cases
UNRUN. Parent authored this follow-up; no native/child/provider authority.

Status: implementation candidate written. All new cases and both guard-loss
witnesses UNRUN. No commands, project imports, tests, Git, framework execution,
provider/network operations, builds, hydration, model/data/wheel reads,
credentials, environment inspection or delegation performed by this worker.
Base e54671bcbf2a5546ac80ff5e3e0ad356963d86e6 was supplied by parent, not
independently checked here.

## Current review follow-up

Parent reports the four-file candidate frozen as `parent-native-v92-frozen`,
two AST checks PASS, native_training/_CONSTRUCTION_SHA/_SELECTED_SOURCES exact,
and independent Python/security reviews BLOCKED. Those receipts describe the
frozen candidate, not this correction. The frozen archive was not accessed or
modified. No AST/import/test execution or source-pin recomputation occurred here.

Corrective changes address the three reported source findings:

1. Complete supported class dispatch is retained statically: class/MRO identity,
   raw descriptor/owner identity, exact default object allocation, builtin type
   call/lookup dispatch, original Python initializer/method code and globals.
   Custom metaclasses, custom allocators, proxies, unsupported descriptors and
   deferred generator/coroutine bodies are refused, never probed or repaired.
   Actual Python entry events at reviewed runtime call sites must match retained
   code, globals and bound receiver/instance class, not just live attributes.
2. Exact runtime namespace and exact Torch/module types precede lookup. Static
   metadata presence prevents module-level missing-attribute callbacks. Loaded
   source/version inspection runs before runtime class admission; static class
   admission runs before intentional device/kernel observations. No ordinary
   framework-class getattr, descriptor binding or proxy __func__/__code__ lookup
   occurs during dispatch admission.
3. Previous trace delivery retains a local callback on None, separately handles
   global None, explicit f_trace clearing/assignment and returned replacements,
   and preserves previous line/opcode preferences. Previous callbacks run first.
   Owned checks remain active even when the previous local delivery is disabled.
   Finally restores exact previous profile/global trace, plus the construction
   frame's previous callback/preferences, and clears retained frame references.

Four new named tests, **29 added parametrized cases**, all UNRUN:

| Test | Cases | Criteria |
| --- | ---: | --- |
| 52 static dispatch mutation | 6 | Trainer/config __new__, unsupported Trainer/config metaclass dispatch, model/Dataset allocation mutation; override/affected body 0 |
| 53 getter tripwires | 10 | runtime/Torch proxies, class descriptor, metaclass getter, callable proxy, with loaded inspection accepted/denied; getter and getter-triggered constructor callbacks 0 |
| 54 actual callee | 1 | different Python model callable on stack, original descriptor restored before CALL; restored-table match still yields unexpected-code refusal, override body 0 |
| 55 trace continuation | 12 | six modes times success/exception; native-versus-owned event sequence and final frame callback/preferences exactly equal, primary exception same object, exact previous profile/global trace restored |

The 23 prior preflight cases/assertions below remain, giving **52 preflight
cases total** (14 named tests). Existing historical 33 memory contracts and
science contracts remain; no current rerun or collection is claimed. The two
existing ordinary-assertion guard-loss witness plans below remain unchanged.

Test 52 custom-metaclass cases introduce an unsupported class after a supported
baseline and mutate its metaclass __call__; they do not claim an admitted mutable
custom metaclass. The only admitted metaclass is the exact immutable builtin
type. Test 55's unguarded FakeRuntime route is a CPython tracing oracle only,
not an alternate native admission path. Existing FakeRuntime/composed fixtures
now use exact ModuleType doubles with labelled fake metadata instead of
SimpleNamespace modules; no assertion was removed to accommodate admission.

## Supported grammar and exact new interfaces

Added `_runtime_namespace`, `_static_runtime_dispatch`,
`_construction_call_sites` and `_assert_construction_callee`.
Production source count: four added top-level helpers, two revised existing
top-level functions (`_check_loaded_runtime`, `_observe_construction_calls`),
one added stdlib type import. Four allowlisted files modified, no new files in
this follow-up.

- Construction runtime: exact SimpleNamespace, exact six existing loader fields,
  string-only namespace keys. Postconstruction dependency namespaces may retain
  their existing extra fields.
- Torch and present inspected modules: exact ModuleType, static plain-string
  __version__/__file__ metadata as appropriate. Missing modules still reach the
  original loaded inspector's fail-closed decision.
- Framework classes and all MRO classes: exact builtin type metaclass, no custom
  meta lookup/call; exact object.__new__ allocation. Initializers are ordinary
  Python functions (or exact object.__init__ for non-instantiated containers).
- Selected class attributes: statically resolved exact FunctionType,
  staticmethod or classmethod wrapping an ordinary synchronous FunctionType.
  No arbitrary descriptor __get__. GRPOConfig may be an admitted class or exact
  ordinary Python function; get_json_schema must be the latter. Bound receivers
  require an explicit positional receiver parameter.
- Runtime call sites: from_list, from_pretrained, get_peft_model, GRPOConfig and
  GRPOTrainer, mapped from frozen instruction source positions to CALL offsets,
  including inline cache offsets. Unknown/ambiguous representation fails closed.
  Direct Python entry checks compare code/globals/receiver before body. Direct
  profiled C dispatch at those sites is unsupported; this is not a universal C
  callable/evaluation-stack inspector or an arbitrary function-object proof.

`_check_loaded_runtime(runtime, installed, *, construction=False)` preserves the
existing default postconstruction route. The internal construction=True route
returns retained static dispatch only after loaded inspection and successful
device/kernel observations. Module identities are retained before those
observations so subsequent binding drift is refused. No fresh loader added.

## Exact interfaces and boundary

Existing source exposes `_observe_calls(trainer, observer)`, not
`_owned_observe_calls`. Its `_expected_method_codes(trainer)` requires an actual
trainer and retains its existing provenance/save/RNG/optimizer checks. Neither
interface can simply be entered before construction with a fictional trainer.

Added private leaves:

- `_candidate_host_metadata()` checks existing host/SOABI leaves plus installed
  metadata and exact selected versions without framework loading.
- `_check_loaded_runtime(runtime, installed, *, construction=False)` inspects the supplied actual
  loader return, existing selected modules/versions, runtime Torch identity,
  one visible device and existing tiny FP16 kernel. No `_observer_dependencies`
  import and no `_load_frameworks`, `_probe_runtime` or second `_load_runtime`.
- `_construction_targets()` checks unchanged frozen construction file digest,
  compiled code shape and native_training globals for the original loader and
  construction function. No expected hash update or compiled-code execution.
- `_observe_construction_calls()` uses the existing process-local profile/trace
  machinery and saved-callback/finally-restoration pattern. Construction state
  and retained identities are local to one context. It chains previous
  callbacks before decisions, tracks the original loader's direct call and
  normal return using `_normal_return`, checks that actual return once, then
  checks the caller's retained `runtime`, Torch/module identities and original
  callable/self/code identities. It never substitutes any production callee.

Only the frozen `_construct_sql_trainer` caller receives owned opcode tracing.
Existing caller line events precede evaluating constructors. Its `CALL` and
`CALL_FUNCTION_EX` opcode checks follow argument evaluation and precede the
actual call instruction, including the GRPOTrainer class call. Immediate-child
profile/trace call checks are additional guards, not invented constructor
authority. Prior local trace callbacks are chained with their own opcode-event
preference, and the exact prior global profile/trace are restored in `finally`,
including exception paths. The retained construction-frame reference is cleared.

## Actual call-site coverage

`_run_phase` wraps its existing, unchanged
`native_training._construct_sql_trainer(...)` call in the construction context,
on both phase 1 and phase 2. Cheap prerequisites and host/exact-metadata checks
precede the original loader. Loaded/device/kernel observations happen at that
loader's normal return, before its caller can execute Dataset.from_list,
FastLanguageModel.from_pretrained, get_peft_model, GRPOConfig or GRPOTrainer.
Identity decisions are repeated at the frozen caller's lines/call instructions,
without repeating kernel observations in that construction context.

The existing `_check_loaded_candidate(trainer, config)` remains the
postconstruction instance-dependent gate and reuses the extracted loaded
inspection leaf. Its existing second, postconstruction runtime observation is
retained, not counted as a second framework loader. `_expected_method_codes`,
training tracing, native save/RNG/optimizer displacement checks and cleanup
guards remain. Public controller/result/wire APIs and the ordinary public
builder are unchanged. PID/order/nonoverlap/save policies are not widened.

## Retained preflight cases, all UNRUN

Ten retained named tests, 23 parametrized memory cases:

| Test | Cases | Numeric criteria |
| --- | ---: | --- |
| 42 normal loader return | 1 | one normal return, same runtime object, loaded inspection 1, second loader/import helper 0 |
| 43 denials | 6 | host/prerequisite/version/loaded-module/device/kernel, model/trainer/dataset 0; first three loader 0, last three loader 1 |
| 44 original route | 1 | original model/trainer/loader 1 each; same function/code identities |
| 45 loader exception | 1 | exact primary exception object, loaded/device/kernel 0, model/trainer 0 |
| 46 binding drift | 7 | retained runtime, Torch, selected module, model callable, trainer callable, loader code, argument-evaluation module drift; affected constructor body 0 |
| 47 independent phases | 1 | two separate contexts labelled phase 1/2, loader/loaded/model/trainer 1 per context |
| 48 previous callbacks | 1 | previous profiler call/return 1 each, trace line/exception present, unsolicited prior opcode events 0, exact restoration after trainer exception |
| 49 loader route | 2 | missing/repeated original loader refused; model/trainer 0, loader body 0/1 |
| 50 prior trace drift | 2 | mutation at actual model/trainer call-site line, affected body 0; exact previous trace restored |
| 51 frozen source | 1 | changed in-memory source bytes refused, original hash and loader unchanged |

FakeRuntime only. Tests exercise the actual frozen construction caller except
explicit retained-runtime/missing/repeated-loader doubles. Source/module
inspection leaves are labelled doubles; `_inspect_loaded` itself is composed
with the real construction observer. Production source admission is explicitly
replaced only inside the labelled unit fixture, while test 51 separately covers
the real unchanged digest refusal using in-memory bytes. Existing assembly-only
test helper now explicitly substitutes `nullcontext` for construction tracing;
those tests still test assembly, not native evidence. Phase independence is not
fresh-process/PID evidence.

Two parent-only guard-loss witness plans, unchanged ordinary assertions:

1. Test 46 `[runtime]`: remove only the actual
   `retained native runtime binding changed` production decision. The equivalent
   namespace reaches the labelled model body, so the unchanged refusal/count
   assertions must fail. No setup failure or timeout is the intended witness.
2. Test 48: remove only construction observer's actual
   `sys.setprofile(previous)` in `finally`. The unchanged exact prior-profiler
   identity assertion must fail after the original trainer exception.

Restore each mutation before the next run. No witness executed here. Historical
native-memory 33, science 46 and source-pin passes supplied by parent remain
historical only and do not establish this candidate's correctness.

## Blockers and limits

Parent must repeat independent Python/security review, run all 52 preflight
memory cases and both guard-loss
witnesses, rerun relevant unchanged regressions, and independently verify all
source pins/integration before any admission decision. No parser/import/test
execution was permitted here, so even test collection is UNRUN. The admitted
implementation relies on the already-selected CPython 3.12 tracing/opcode API;
no cross-interpreter authority is claimed.

Supported installed runtime container/module/class/descriptor forms have not
been observed. Anything outside the grammar above is refused, not imported,
rebound, reloaded or automatically supported. The supported FakeRuntime route
does not establish that the selected native candidate has those forms. Parent
must also validate the CALL source-position mapping and CPython 3.12 trace
continuation oracle; both remain UNRUN for this corrected source.

The original loader must already load every `_EXACT` root and selected source
needed by `_inspect_loaded`. If any is only lazily imported by model/trainer
construction, this gate refuses before construction; it does not import that
module to repair the ordering. Availability of all those modules at the earlier
boundary is UNRUN and a possible compatibility blocker, not evidence of support.

This is not a hostile-thread or hostile-hook sandbox. Loaded version attributes
and selected bytes retain their existing observational limits. Framework imports,
their side effects and the tiny kernel may allocate before the model/trainer
boundary. No before-all-allocation claim. Hardware support, full native ABI,
Unsloth/vLLM compatibility, actual updates/restoration, scientific qualification,
provider containment and all-charge budget enforcement remain unproved here.
No launch, retry, provider fallback, spending increase or production authority.
The unchanged public controller/result/wire APIs, original single framework
loader, postconstruction method provenance, save/RNG/optimizer displacement,
phase PID/order/nonoverlap and cleanup guards retain their prior scope.
native_training and the two frozen digest tables were not edited. Their current
bytes and all integration pins still require parent verification.

## Written paths

- `/Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-native-preflight/train/native_qualification.py`
- `/Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-native-preflight/train/test_native_qualification.py`
- `/Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-native-preflight/docs/droid-v89-native-preflight-plan.md`
- `/Users/nikolassapalidis/scratch/cotrain-devin-continuation-2026-11-06/droid-v89-native-preflight/docs/droid-v89-native-preflight-report.md`

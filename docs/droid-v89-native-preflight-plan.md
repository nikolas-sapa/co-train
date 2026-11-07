# V89 native constructor preflight plan

## Parent V111 correction, test criteria before implementation

Validate every inspected MRO namespace key is exact str by iteration before
any namespace membership/index lookup. Refuse unsupported keys without hashing
or equality callbacks. Four FakeRuntime cases: object and str-subclass colliding
keys, each at initial admission and post-baseline trainer replacement.
Reset/arm counters after fixture construction; require zero key callbacks,
zero affected trainer-body entries and exact trace/profile restoration.
Preserve prior 85 intended memory cases; new total 89, all UNRUN. No native,
child or operation authority, changed pins or broader supported grammar.

## V92 review follow-up, test criteria before fixes

Parent froze the four-file V92 candidate separately. That archive is immutable.
The parent reports AST/source-pin checks passed but independent Python/security
review BLOCKED; no memory tests ran. The following is source-only corrective work.

1. `test_52_memory_static_dispatch_mutations`: Trainer.__new__, unsupported
   metaclass.__call__, and GRPOConfig allocation/dispatch changes after baseline
   each yield override-body count 0 and affected constructor-body count 0.
2. `test_53_memory_static_getter_tripwires`: runtime proxy, Torch proxy,
   class metaclass getter, class descriptor, and callable proxy each yield
   getter/callback count 0. Loaded inspection denial must occur before any
   runtime framework-class descriptor inspection; no constructed model/trainer.
3. `test_54_memory_actual_callee_code`: place a different Python model callable
   on the evaluation stack, restore the original class attribute before CALL.
   Actual-callee rejection precedes override body: count 0 despite matching
   current attribute table. No arbitrary C-caller guarantee.
4. `test_55_memory_trace_continuation`: compare native CPython trace delivery
   with owned chaining for local None, replacement, explicit frame.f_trace
   clearing, global None, opcode enable/disable and line preference changes.
   Event sequences must match exactly, on success and original exception routes.
   Exact prior profile/global trace restoration on both routes; exception is
   the same primary object. Callback drift is checked after the prior callback.

Retain the existing 23 cases/assertions, 33 historical memory contracts and both
ordinary-assertion guard-loss plans (retained runtime and profiler restoration).
All added/retained cases and both witnesses remain UNRUN here. FakeRuntime only,
no fixture bypass represented as native proof.

Implementation constraints: exact SimpleNamespace runtime and ModuleType Torch
before lookup; loaded inspection before runtime-class dispatch admission. Read
class MRO dictionaries through type's builtin access only after rejecting custom
metaclasses; accept only explicitly supported exact descriptor/callable forms.
Retain class allocation and metaclass dispatch identities, refuse unsupported
forms instead of probing descriptors or importing repairs. Gate actual Python
callee code/receiver/globals at the original caller's known runtime call sites.
Preserve CPython local-trace None continuation, explicit clearing/replacement and
event preferences while keeping owned checks active. No hostile-hook/thread,
arbitrary-C-caller or full-host sandbox claim. Actual installed callable types
and lazy selected-module availability remain UNKNOWN.

Follow-up inventory: test 52 has six dispatch-mutation cases, test 53 has ten
getter/loaded-refusal combinations, test 54 has one stale-evaluation-stack Python
callee case, and test 55 has twelve native-versus-owned trace cases. This adds
29 cases to the retained 23, total 52, all UNRUN. Exact supported forms and
remaining incompatibility blockers are recorded in the companion report.

## Test plan, recorded before implementation

All proposed cases are labelled FakeRuntime, memory-only, parent execution only.
No real Torch import, installation, loader execution, model, GPU or provider.

1. `test_42_memory_constructor_normal_loader_return`: one original loader normal
   return, one loaded inspection, zero fresh/preflight loader calls.
2. `test_43_memory_constructor_denials`: host, prerequisite, exact version,
   loaded module, device and kernel failures each leave model/trainer counts 0.
   Host/prerequisite/version failures also leave loader count 0.
3. `test_44_memory_constructor_original_route`: original model/trainer bodies
   each entered once, original loader identity/code unchanged.
4. `test_45_memory_constructor_loader_exception`: exact primary exception object
   preserved, loaded/device/kernel inspection counts 0.
5. `test_46_memory_constructor_binding_drift`: retained runtime, Torch module,
   model callable and trainer callable drift refused before affected constructor.
6. `test_47_memory_constructor_phase_independence`: two independent observation
   contexts, loader/inspection/model/trainer counts 1 per context.
7. `test_48_memory_constructor_previous_profile`: prior profiler receives call
   and return events; exact profiler and trace restored after constructor error.
8. `test_49_memory_constructor_late_loader`: missing or repeated original loader
   refused, no model/trainer constructor reached on missing-loader route.
9. `test_50_memory_constructor_trace_callback_drift`: previous local trace changes
   module at model/trainer call line; gate refuses before affected body.
10. `test_51_memory_constructor_frozen_source`: changed constructor source
    refused before loader, with no expected-pin refresh.

Two guard-loss witness plans, parent only, ordinary assertions unchanged:
remove the actual production retained-runtime binding decision and rerun the
runtime-drift case of test 46, which must fail its ordinary refusal/count
assertions (not timeout/setup). Remove constructor context's actual `finally`
profiler restoration and rerun test 48; exact prior-profiler identity assertion
must fail. Restore source after each witness. Neither witness has been run here.

## Implementation plan

Existing interface is `_observe_calls`, not `_owned_observe_calls`. It only
accepts an already-constructed trainer; `_expected_method_codes(trainer)` also
needs that instance. Keep their trainer/save/RNG/optimizer lifecycle intact.
Add a private construction observation context using the same saved-profile/
finally-restoration pattern. Observe the original `_load_runtime` normal return
inside the frozen `_construct_sql_trainer` frame, inspect its actual returned
runtime, then bind/check the caller's retained `runtime` and original constructor
attributes at caller lines and call events. Never replace either callee.
Also gate original caller CALL opcodes after argument evaluation, before the
callee invocation (including class allocation). Previous trace callbacks receive
only the opcode events they requested. Bound-code drift and argument-evaluation
module drift are additional test 46 parameters, separate from test 51's byte pin.
Cheap host/prerequisite/exact metadata checks run before original loader.
Retain postconstruction trainer-specific and provenance checks.

Coverage: qualification `_run_phase` phases 1 and 2 only. Public default builder,
controller, result and wire APIs unchanged. Frozen native_training source and
selected representation digests unchanged. Parent owns pin verification and
integration. New tests ALL UNRUN. Historical native memory 33/science 46 and
source-pin results are historical only, not evidence for this change.

## Non-goals

No before-all-allocation/import-side-effect claim. Loader imports and the tiny
FP16 observation may allocate. No hardware/native ABI/scientific proof, paid
execution, expanded budget, fallback provider, reload, fresh second loader,
source-pin refresh, daemon, new framework or snapshot lifecycle.

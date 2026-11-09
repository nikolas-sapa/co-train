# Native lifetime baseline, 9 Nov 2026

## Scope decision

The user explicitly excluded caller-frame locals/code/line data and traceback-frame
metadata from native-helper equivalence. This updates the undecided scope at the
[earlier header checkpoint](engineering-header-review-2026-11-09.md).
It does not exclude object lifetimes, destructor/reentrant effects, callback
order, policy/custody checks, original exception identity/type/message or handled
exception state. No native implementation or build was authorized.

## Two new Python-only cases

One separately approved RED run and one GREEN run completed, without retry, under
the unchanged isolated parent runner (internal 29/external 30 seconds each).
Each ran the same two NEW cases, outside and inside an active handled exception.

GREEN: 2 passed, 0 failures/errors/skips, exit 0. Runner elapsed 1.418 seconds.
RED: 2 intended premature-finalizer failures, 0 errors/skips, exit 1/NONPASS.
Runner elapsed 1.508 seconds. Three source pins and three import origins remained
stable for each run. No historical test bodies or compiler/GPU operations ran.

The baseline copies the frozen canonical `_directory` and `check` function bodies
without importing their production module. AST comparison matched both bodies.
All policy globals are synthetic: no actual descriptors or filesystem operations.
A one-shot iterable supplies one row of five weakly observed tagged objects:
`parent`, `name`, `record`, `pin`, `private`. It stores no row. A final root-policy
failure raises the exact injected exception.

While that exception's traceback is held, all five objects remain alive and no
finalizer occurs. After dropping the traceback and collecting, all five objects
are dead and exactly five tagged finalizers occurred. The outer handled exception
is also restored. The registry stores weakrefs and event strings, not tagged
objects. RED changes only a bridge that discards the failing call's traceback
before re-raising the same exception; both cases detect premature finalization.

This is a Python lifetime obligation and a non-vacuous detector, not evidence
that an unimplemented C helper is correct, fast, memory-safe or ABI-compatible.
It does not prove all finalizer ordering, arbitrary reentrancy or handled-state
behavior. The two-run permission is consumed and grants no retry.

## Source archives and remaining design

- [GREEN baseline](../spec/spikes/archive/native-lifetime-baseline-green-source.py.txt)
- [RED control](../spec/spikes/archive/native-lifetime-baseline-red-source.py.txt)
- [Two cases](../spec/spikes/archive/native-lifetime-baseline-tests-source.py.txt)
- [First-party source manifest](engineering-native-lifetime-manifest.json)

These archive bytes match the private sources used for the observations.
Their frozen docstrings say UNRUN because they were written before execution;
that historical source label is not a current private-run status. Text archives
are not active import roots, a runnable test package, clone acceptance or authority
to execute anything.

A thin wrapper retaining only `self` does not automatically retain the last five
locals as the original traceback does. Frame-metadata exclusion does not remove
this requirement. No state/capsule retention design is accepted yet.

Remaining witnesses cover fresh lookups and callable capture; operand identity;
tuple-membership construction/equality; temporary/call-return destruction; exact
unpack and local replacement; iterator mutation/exhaustion; broader traceback
retention; and cleanup exception state/reentrancy. Public-API selection and exact
ownership/unwind schedules remain unproved. Saving a raised error indicator alone
does not preserve handled exception state. Existing native T1-T8 correctness,
resource and performance gates are unchanged.

[Compiler-containment research](engineering-compiler-kernel-denial-2026-11-09.md)
identified a narrower historical witness, not an executable plan. Native C remains
unimplemented. No additional installed headers, interpreter hashes, retained-volume
access, native build or GPU action occurred. GPU readiness remains 0/7.

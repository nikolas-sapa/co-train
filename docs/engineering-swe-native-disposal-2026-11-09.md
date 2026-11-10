# SWE-2 continuation and directory-disposal baseline: 9 Nov 2026

This is a narrow Python semantic observation, not a native implementation,
speed result, compiler-containment plan or GPU qualification.

## Genuine workers, reviewed rather than accepted blindly

Three CLI workers used actual model `swe-2-high`, covering activation/lifetime,
expression order and compiler containment. Two were resumed with corrections.
All five agent generations reported that model; all commands completed with
exit0, and the inspected exports contained zero tool calls. This verifies model
provenance and observed tool non-use, not a general sandbox guarantee.

They returned text, not repository implementations. The parent rejected eager
policy-decision batching, unsupported temporary-retention assertions and the
first draft's passing tests that accepted broken behavior. The sources below
are parent-adapted, not verbatim worker deliverables. Private prompts, exports,
configuration and identifiers are not published.

The smaller provisional design leaves `_Anchor.check` entirely original and
considers only `_directory` for native acceleration behind its original
signature. This reduces replication work; it proves neither equivalence nor
speed. A replacement Python wrapper does not necessarily add another Python
frame. Extra references, live lookup semantics and unwind behavior still need
proof. No blanket prohibition on state-bearing designs was established.

## New witness, separate from the traceback-local baseline

The original `_directory` AST was preserved. Synthetic globals use UID0,
mode040700 and privateFalse. Synthetic policy callbacks perform no real UID,
descriptor or filesystem operations; harness source/result I/O is separate.
`getuid` still executes once even though tuple membership matches the
first element0. It returns a fresh finalizable object, observed only weakly.

Releasing the membership tuple finalizes that object, updates a bool and
replaces global `require`. Python selected the first `require` BEFORE evaluating
its arguments, so that call must still use the old callable. The second policy
must select the replacement. The exact expected event list is:

```text
getuid
del:uid
require:owned directory:uid_dead=True
replacement:unsafe writable directory
```

Both cases return `(1, 2, 0o40700, 0, 20)`, observe a dead weakref and one finalizer.
One case runs outside a handled exception; the other runs inside one. Callback
and destructor observations check handled-exception identity; the outer handler
also checks restoration. Registry/events do not retain the finalizable object.

RED's sole source change is a named-expression local retaining the membership
tuple until activation exit. RED and GREEN use identical positive test bodies:
the control is not an xfail or a passing assertion about broken behavior.

| One-shot attempt | Cases | Actual result | Errors/skips | Runner elapsed |
|---|---:|---|---|---:|
| RED retained tuple | 2 | NONPASS,2 intended ordering assertion failures,exit1 | 0/0 | 0.591354s |
| GREEN original expression | 2 | PASS,exit0 | 0/0 | 0.442586s |

Both used three stable source pins and three verified module origins. Neither
reported forbidden process/signal operations. Each had a 30-second external
limit and an unchanged 29-second internal deadline. Explicit permission covered
exactly these two attempts and is consumed, with no retry. The runner's audit
controls are not a universal OS sandbox.

## Frozen first-party text, not active modules

- [GREEN fixture](../spec/spikes/archive/directory-disposal-green-source.py.txt)
- [RED fixture](../spec/spikes/archive/directory-disposal-red-source.py.txt)
- [Identical positive tests](../spec/spikes/archive/directory-disposal-tests-source.py.txt)
- [Hashes and dated observations](engineering-swe-disposal-manifest.json)

Archives match the consumed private sources byte-for-byte. Their frozen UNRUN
docstrings describe proposal-time status; the actual attempts are recorded above.
These text files are not ordinary collection roots or execution permission.
The old [traceback-local baseline](engineering-native-lifetime-baseline-2026-11-09.md)
remains separate. Shared info in that older fixture does not prove fresh,
sole-owned info lifetime or stale evaluation-stack retention.

## Limits and next gates

This checks two success-path cases, one membership-disposal point, selected
callable order and specific handled-state observations on the selected Python
interpreter. It does not prove every temporary or callable lifetime, error
unwind, reentrancy, dynamic namespace mapping, arbitrary comparisons, tracing/
profiling callback preservation, C API/ABI compatibility, native speed or memory
safety. No actual training or full-volume validation ran.

The [compiler containment note](engineering-compiler-kernel-denial-2026-11-09.md)
remains source research, not an executable plan. Kernel birth denial is one
possible approach, not universally necessary. Install-before-exec alone does not
stop IPC delegation to pre-existing services; a build string does not establish
installed-binary/source correspondence. Filesystem-sandbox CLI help does not
prove process-birth denial.

All policy/custody checks, original exception identity/type/message, evaluation
and callback order, handled state, observable lifetimes and reentrant cleanup
remain required. The existing frame-metadata exclusion does not waive
traceback-held object lifetimes or tracing/profiling callbacks.

No native helper source/build/import, installed-header read or interpreter hash,
retained-volume access, provider deployment, GPU or science run was performed
for this checkpoint. Native GPU remains unqualified; no same-day ETA is claimed.

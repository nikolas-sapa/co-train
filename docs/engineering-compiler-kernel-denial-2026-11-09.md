# Kernel-denied compiler births: source-only investigation

Verdict: **NO_EXECUTABLE_COMPILER_CONTAINMENT_PLAN**.

A possible improvement is kernel-enforced denial of new processes before compiler
entry. A phase would have to complete in one process or fail. This would avoid
assuming that a compiler backend, assembler or linker voluntarily never forks.
A denied spawn does not guarantee exit: retry and hang behavior remain possible.

## Historical source witness

At Apple XNU commit `0a798f6738bc1db01281fc08ae024145e84df927`, `fork` and `vfork`
share `fork1`. Under `CONFIG_MACF`, the common path calls `mac_proc_check_fork`
before child construction and rejects a nonzero result. The matching
`kern_exec.c` contains `fork1(..., PROC_CREATE_SPAWN, ...)`.

- [Pinned fork source](https://github.com/apple/darwin-xnu/blob/0a798f6738bc1db01281fc08ae024145e84df927/bsd/kern/kern_fork.c)
- [Matching pinned exec/spawn source](https://github.com/apple/darwin-xnu/blob/0a798f6738bc1db01281fc08ae024145e84df927/bsd/kern/kern_exec.c)

The matching spawn call narrows an initial cross-version evidence gap. It does
not establish every branch, build configuration, Seatbelt rule mapping or current
Darwin 27 applicability. It is not the previously pinned timer witness.

## Unsupported premises remain

Historical project material names `process-fork`; that name is not an exhaustive
enforcement proof. Apple DTS describes custom SBPL profiles as undocumented for
third-party use and connects that to `sandbox-exec` deprecation. Deprecation
proves neither present availability nor removal. General sandbox inheritance
statements do not prove every rule survives each same-PID exec unchanged.
`sandbox_check` and private initialization interfaces are not supported attestation.

- [WebKit profile discussion](https://bugs.webkit.org/show_bug.cgi?id=186110)
- [Apple DTS: custom profiles/deprecation](https://developer.apple.com/forums/thread/661939)
- [Apple DTS: inheritance](https://developer.apple.com/forums/thread/770046)
- [Apple DTS: implementation-detail interfaces](https://developer.apple.com/forums/thread/759312)

Still unproved: rule-to-hook mapping and precedence; all fork/vfork/spawn routes;
non-removability; fail-closed installation before compiler/library execution;
exec persistence; and current OS correspondence. Threads, memory/CPU/FD/disk,
IPC delegation, initial birth gaps, supervisor loss, signal authority/delivery,
consuming waits and independently justified cleanup are separate obligations.

## Next possible step, not authorization

Complete source-only, version-matched enforcement/installation review before
proposing any synthetic noncompiler falsification probes. Such probes would need
their own exact process counts, custody, deadlines, cleanup and contained
allow-control. A PID census cannot prove zero transient births.
No unsandboxed fallback or automatic retry is acceptable.

The old proposed 8-total/5-live guardian probe remains unapproved. No profile was
installed, no installed runtime inspected, and no process probe/compiler/GPU ran.

# Two-header review checkpoint, 9 Nov 2026

## Outcome

The single approved read of `Python.h` and `pyconfig.h` completed with exit `0`
under an external 5-second timeout. It acquired 2,854 and 56,114 bytes respectively,
58,968 bytes total, below the 262,144-byte ceiling. It followed no includes,
computed no header/interpreter hashes, and executed no compiler, build or GPU.
The one-use permission is consumed. Neither this note nor a clone authorizes retry.

Installed header contents, identities, local paths and execution claims remain
private. The observed include names/configuration source are descriptive only:
preprocessor conditions were not evaluated, API declarations were not resolved,
and ABI compatibility was not proved. No additional installed headers were read.

## New fake-file checks

All 15 new cases passed under the unchanged isolated parent runner. No historical
test bodies ran. Two separate controls each retained NONPASS/exit `1` with exactly
one intended failure and 14 passes, zero errors/skips:

- Restore the old sentinel read: the second-file growth case detects acquisition
  beyond the per-file/aggregate ceiling.
- Omit deadline refusal: expiry-before-open detects the missing refusal.

The corrected reader bounds each acquisition by initial file size and remaining
per-file/aggregate budgets, without a sentinel byte. The capture helper creates
an exclusive no-follow, owned single-link regular output with exact mode `0600`
before any header acquisition. Existing files and live/dangling symlinks refuse.
Python and security source reviews cleared these corrections before execution.

These are new fake-file unit results and one read-only observation, not SDK,
process-control, memory-safety, full-volume or GPU qualification. Cooperative
checks and an external timeout do not prove universal OS termination, pinned
ancestry or exclusion of every concurrent-mutation/ABA case.

## First-party archives, not active modules

- [Reader](../spec/spikes/archive/two-header-reader-source.py.txt): machine path
  replaced with an authorization sentinel. This transformed archive is UNRUN.
- [Private output helper](../spec/spikes/archive/two-header-output-source.py.txt).
- [Fifteen fake cases](../spec/spikes/archive/two-header-tests-source.py.txt).

The last two archive bodies match the checked private first-party sources.
Archives are text, not import roots or a runnable test package. They do not grant
execution permission or establish acceptance for a clone. No installed header
text is included. [Archive manifest](engineering-header-review-manifest.json).

## Still blocked

Native helper semantics are not proved, including caller-frame/traceback
introspection and reference/exception lifetimes. Those requirements were not
silently excluded. Compiler descendant containment has no approved executable
plan. No native C helper exists or has been built. A check-preserving performance
fix and fresh maximum-volume validation remain open. GPU readiness stays 0/7,
with no same-day launch promise.

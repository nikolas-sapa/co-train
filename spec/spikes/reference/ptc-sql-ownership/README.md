# PTC SQL ownership reference

Throwaway reference, not a canonical runtime fix or a model baseline.

## Test plan and measured evidence

On the local Python 3.12 / SQLite build, six isolated fixture gates passed:

1. Real runtime with a 0.1s program budget and no SQL progress callbacks:
   recursive COUNT remained inside SQLite until the owned parent's 2s safety
   timeout. Parent killed its own group and drained the direct child.
2. Fixture progress callback every 1000 VM instructions: the existing Python
   runtime tracer interrupted that query in under 1s.
3. Explicit fixture-only 0.2s query deadline outside the runtime: rejection
   in under 1s.
4. Native integer, float, null and bytes rows and invalid-SQL error format
   matched the canonical Python SQLite callable.
5. Fixture worker ownership retained repeated cancellation through completion,
   allowed no late commit, and then completed a fresh program successfully.
6. A cancellation arriving during otherwise-normal fixture cleanup propagated.

Run with the project's SDK-enabled interpreter:

```text
python -I -B spec/spikes/reference/ptc-sql-ownership/ptc_sql_ownership_probe.py
python -I -B spec/spikes/reference/ptc-sql-ownership/trace_cleanup_diagnostic.py
```

The script creates only a tiny temporary SQLite database. Each child has an
owned 2s safety cap, including executor shutdown. No SDK listener, provider,
corpus or training execution is involved.

The second script injects one tracer exception at the canonical SQL callable's
connection-close line. It verifies the retained connection is still open using
connection metadata, then closes it itself. This demonstrates a cleanup edge,
not natural timing or a production fix. It must not be counted as a passing
resource-cleanup guarantee.

## PROVES

The current line tracer needs Python callbacks to regain control during a long
SQLite VM call. Progress callbacks provide that opportunity on the tested build.
The fixture shield/join pattern retains program-thread ownership on cancellation.
No alternate SQL backend or serialization format is required.

## SHORTCUTS and negative diagnostic

The `old` child deliberately suppresses progress registration through a local
connection proxy. This is an isolated negative diagnostic, not a positive test
of canonical code. It keeps the missing-progress counterexample runnable after
the canonical bug is repaired. The original pre-fix scratch run needed no such
suppression, because the canonical callable registered no progress handler.

Other children use a fixture SQL callable and fixture owned-program helper.
Scheduling gates prove ownership ordering, not physical SQLite initialization
or interruption latency. The SQLite progress callback itself confirms VM activity.
The explicit standalone query deadline is a fixture, not a new canonical default.
The parent uses private, host-created process handles, never wire PID authority.
PGID cleanup assumes cooperative children and a short-lived owned group.

## MISSING and non-goals

- Canonical SQL progress registration and canonical PTCHarness worker joining.
- Safe cleanup when the runtime tracer raises at a trusted connection-finalizer
  boundary. Progress callbacks plus joining alone do not prove this.
- Ordinary configured PTCHarness/SDK cancellation and fresh-rollout integration.
- Production runner admission, draw coverage, scoring and persisted-row checks.
- Arbitrary extension/virtual-table safety, memory containment, process-session
  escape prevention, universal blocking-I/O deadlines or an OS sandbox.
- A standalone canonical SQL timeout outside a traced program.
- Real corpus/model/baseline/training execution, policy selection or spend.

Program and SQL progress budgets remain cooperative. Joining work can extend
cancellation latency until that bounded work finishes. Trusted custom catalog
callbacks require their own bounded behavior.

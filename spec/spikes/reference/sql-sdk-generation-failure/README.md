# Original SDK generation failure after admission

Bounded COMPOSITION spike, 2026-11-01. No engineering milestone approval.
Tests/non-goals recorded before code in the parent scratch `test-plan.txt`.

## PROVES

Original registered Env, Task, Harness, SDK Agent/Rollout, evaluator and JSONL
writer run unchanged. Exact admitted `public_data[0]` identity selects an
original first-party `ScriptedClient([])` through the existing server-owned
Client seam. Its first request naturally raises the original builtin
`RuntimeError("scripted model exceeded its 0-step script (call 1)")`.
The router catches and bare-reraises that exact object. The probe checks its
identity, original `get_response.__code__`, source path and AST raise line;
the original interception record independently preserves its diagnostic.
It does NOT claim exception-object identity survives JSON serialization or HTTP.

Before generation, original scorer admission completed, its actual database
identity exists and its resource is already retained in the original scope.
While ONLY target public scorer close is event-held:

- Original Agent driver is done; actual scorer-close and Env-cleanup tasks pending.
- Scope token/live state retained; authority stopped by original failure handling.
- Target has no scoring child, result, reward or JSONL row.
- Actual PROGRAM lease close has completed; original runner closed with zero jobs.

After releasing ONLY the test-owned close gate, original cleanup completes.
All retained tasks are done and absent from `asyncio.all_tasks()`, original
scorer/PROGRAM resources are closed, tokens revoked, admission inactive.
Original writer emits seven rows: one failed target (episode AND trace false,
zero rewards), six ordinary declared-MOCK successes. All exact Data/Trace
associations are checked. Native dispatch/SQL/process/signal/external-network
guard attempt lists remain empty; no owned execution directories are staged.
Protected project hook identities and original SDK execution methods remain intact.

## SHORTCUT

Reuses guarded `_prepare` and `framework` rather than duplicating SDK plumbing.
The fixture creates only synthetic SQLite files before its SQL denial guards.
Six siblings use its explicit `OwnedSqlScorer.score_sql` ExResult MOCK.
No target score callback runs. Public scorer admit/close observers delegate
the original methods; the close gate precedes original empty-job close.
Scope state is read-only observation, never alternate authorization.
The router is a fixture Client, not a replacement Task or SDK scheduler.

## Red control and restored green

`test_generation_fault_routing_bypass_is_red` changes ONE routing edge:
the target receives the ordinary original ScriptedClient instead of the empty
one. The unchanged acceptance oracle raises `SDK_GENERATION_FAILURE_REQUIRED`.
The test verifies exact oracle code/line provenance, one bypass hit, zero
failed-client calls, and actual seven successful MOCK writer rows after
test-gate release and original cleanup. No synthetic exit codes or parked tasks.

Also measured uncaught RED: temporarily changed only the new helper's
`fault_bypass=False` default to `True`, ran
`test_original_sdk_generation_failure_after_admission`, observed exit 1,
`1 failed in 2.76s`, at `_assert_generation_fault`.
Restored that single default to `False`, then fresh full run: exit 0,
`3 passed in 4.62s`. Scenario call durations: 1.13s initial,
0.26s bypass, 0.26s fresh restored. Each scenario enforces 3s; every execution
command uses an independent 30s tool timeout. Bounds were not raised.

Exact tests:

- `test_original_sdk_generation_failure_after_admission`
- `test_generation_fault_routing_bypass_is_red`
- `test_original_sdk_generation_failure_restored`

From this repository root, with the existing qualified Python environment
activated (apply the independent 30s command watchdog):

```sh
env PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1 \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY=127.0.0.1,localhost \
  python \
  -I -B -m pytest -p no:cacheprovider \
  spec/spikes/reference/sql-sdk-generation-failure/probe.py -q
```

The same command accepts `ptc/test_owned_sql_sdk_generation_probe.py`.
Reference imports the identical tests and fixture; it does not copy execution.

## MISSING / blocked

Setup failure remains BLOCKED: no independent natural fixture failure input
was identified AFTER original successful scorer admission and BEFORE policy.
Original SDK `Task.setup` returns None and `Harness.setup` has no body;
the admitted registered pair forbids plugged hooks/toolsets/skills. Runtime
provisioning failures before Task.setup do not satisfy retained-scorer timing.
A new runtime failure injection or protected-method patch would invent the
missing seam, so none was added. A separately reviewed natural post-admission
setup fixture input is needed before claiming setup coverage.

No actual-owned actor, native invocation, ACK, SAFE, SQL accuracy, training,
external model/provider/corpus, research baseline, pending-sibling/late-race,
unknown cleanup or independent Env writer-barrier bypass qualification.
The fault-routing sensitivity control is NOT a writer-barrier mutation test.
No opaque UNIT/MOCK object or event-held empty-job close is native evidence.
Only the three new artifacts may be copied after parent review; no existing
production/core/SDK/config/hook/cap source was edited.

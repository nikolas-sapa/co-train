# Owned runner sensitivity controls

Run using the SDK-enabled test interpreter and an explicit absolute artifact
directory outside the checkout:

```text
python -I -B spec/spikes/reference/ptc-owned-program-runner/control.py --artifacts-dir /absolute/scratch/directory
```

Each mutation and restored positive uses a fresh isolated interpreter. Only
in-memory helpers change; disk source hashes must remain identical.

- **Close:** remove retained cleanup joining. Exactly one selected test must
  fail `caller returned before owned close acknowledgment`, with one bypass
  hit. Its finally releases and drains the retained fixture task.
- **Fatal:** remove infrastructure exception wrapping. Exactly one selected
  test must fail `infrastructure failure dispatched a second policy request`,
  with one bypass hit.

Receipts verify collection, call-phase assertion, bypass count, source hashes,
restored helpers and drained fixture tasks. Restored positive cases must pass.
These are unit sensitivity controls, not native-controller or SDK execution.
The actual SDK/SQLite-process composition lives in
`ptc/test_owned_program_runner_integration.py`.

## Timeout preflight

`timeout_control.py` bypasses only the optional timeout validation call.
It requires exactly one hit and the named assertion
`intended pre-model refusal dispatched a policy request`, then restores the
helper and verifies unchanged source bytes. It prints a JSON receipt, without
writing artifacts or exercising SQL/native actors.

Run this control and its restored positive in separate fresh interpreters:

```text
python -I -B spec/spikes/reference/ptc-owned-program-runner/timeout_control.py
python -B -m pytest -p no:cacheprovider -q 'ptc/test_owned_program_timeout.py::test_preflight_exception_is_fatal_not_tool_feedback[ValueError]'
```

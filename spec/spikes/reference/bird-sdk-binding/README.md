# Real-SDK SQL binding reference

This is a composition spike, not a BIRD baseline runner.

## Test and evidence

`bird_sdk_probe.py` runs one synthetic SQLite task through each arm,
sequentially. It uses the installed SDK's actual JSON loaders, `run_eval`,
episode agents, original Task hooks, scoring and JSONL writer.

Numeric acceptance:

- 2 episodes, 2 original Tasks, 4 scripted SDK policy requests.
- 1 model-facing tool in each opening request.
- Both SQL observations contain the fixture result, 42, before request 2.
- Each original Task receives setup, finalize and score exactly once.
- Both in-memory traces and persisted task-linked records contain valid
  `match` outcomes and execution-accuracy reward score/weight 1.0/1.0.
- Exact oracle SQL text is absent from all captured requests.
- Fixture teardown restores PATH and original harness identity, closes owned
  server sessions and drains owned runtime transports.

Scratch acceptance after review: **1 passed in 3.70s**. Promoted reference:
**1 passed in 3.24s**. Restored reference plus the 16 existing shared SDK
integration cases: **17 passed in 9.63s**, not the full suite.
An earlier strengthened
assertion failed because SDK JSONL stores `rewards.execution_accuracy.score`
and `weight`, not the computed `trace.reward` property. That failure remains
in scratch; the final assertion checks the actual serialized fields.

`bird_binding_control.py` substitutes only the PTC catalog's SQL callback
in memory. It returns -777 instead of querying the fixture. The negative
control must fail at `SQL result reached next request`, with exactly 1 callback
hit and pytest exit 1. The promoted control produced that exact failure
and count; the restored affected run above passed.
The receipt path is caller-supplied, absolute and create-only.

## Running the reference

From the repository, with the existing qualified SDK environment:

```sh
PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1 HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
NO_PROXY=127.0.0.1,localhost python -B -m pytest -p no:cacheprovider \
  spec/spikes/reference/bird-sdk-binding/bird_sdk_probe.py -q
```

For the intentional failure, add the reference directory to `PYTHONPATH`,
load `-p bird_binding_control`, and pass
`--bird-control-receipt /absolute/scratch/new-receipt.json`.
Never count that expected failure as a passing test.

## Shortcuts and boundaries

- Manual temporary harness assignment is a **SHORTCUT**. This does not extend
  `run_configured_ptc_qa`, whose reporting catalog remains intentionally empty.
- Taskset/module globals, a fixed database, fixed SQL and sequential execution
  are **SHORTCUTS**. No overlapping-task isolation claim.
- Scripted policy responses are predetermined. Requests, SQL execution and
  observations are real; no model reasoning or training capture is claimed.
- **MISSING:** retained-draw admission, exclusion/denominator accounting,
  complete paired coverage, shared enforced budgets, failure/cancellation
  qualification and a production launch-ownership design.
- The subprocess runtime is for this debug fixture, not a security sandbox.
  Exact oracle-text exclusion is not a confidentiality guarantee against an
  adversarial Bash process. The parent network guard does not sandbox children.
- Only bounded, ephemeral loopback fixture listeners are permitted. No external
  provider/model calls, corpus access, draws, downloads or experiments.

Current paired BIRD baseline remains **missing**, not zero. Research remains
**4 PARTIAL / 5 PARTIAL / 6 BLOCKED**.

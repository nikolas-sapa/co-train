# Project Bash QA CLI, test-first contract

2026-10-31. Base `e5f013e`, branch `feat/bash-qa-eval-cli`.
Architect APPROVE. [Usage/evidence](../docs/2026-10-31-bash-qa-eval-cli.md).

## Tests before implementation

- Isolated `-I -B` help: exit 0, zero SDK/product imports or listeners.
- Missing argument, missing file and two invalid JSON/schema cases: exit 2;
  zero wrapper calls, no raw input sentinel in stderr.
- Valid explicit JSON: actual EvalConfig narrowing, exact validated object
  passed once to the async wrapper; no changed settings.
- Wrapper exception: identical error propagates, never argparse translation.
- Three forbidden flags individually: actual wrapper refuses, zero SDK calls.
- Real `runpy` __main__: existing real framework fixture unchanged; one
  actual SDK episode, report/receipt at call 2 and exact actual JSONL QA.
  Delegation-suppression control must produce intended call-phase assertion
  RED, original/restored GREEN with immutable source hashes.

## Implementation

New root `cotrain_bash_qa_eval.py`, `main(argv=None)`. Stdlib argparse requires
`--config PATH`, JSON only. Parse/read before SDK/product imports. Catch OSError
and Pydantic ValidationError narrowly, use generic messages without raw config.
Validate using existing EvalConfig, delegate exactly once through
`asyncio.run(run_bash_qa_eval(config))`. `__main__` invokes main without passing
episodes to sys.exit. Existing SDK result/completion/scoring policy unchanged.
Reuse the existing real integration fixture and helpers, no duplicated
runtime, network, writer or listener code. A delegating asyncio.run timeout
guard is an explicit test-only outer bound, not a replacement evaluation loop.

## Non-goals

No stock vf-eval integration, YAML, implicit model/budget/output choices,
dry-run mode, new success/empty-result policy, writer, retry, normalization,
dependencies, provider/corpus/training/native campaign, public listener,
SDK edit, gate relaxation, deploy or other-worktree edits.
Trusted plugin imports and ordinary SDK logging/output are not sandboxed or
redacted by this CLI. Future real runs still need explicit authorization.

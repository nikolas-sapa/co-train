# Project Bash QA evaluation CLI

2026-10-31. Base `e5f013e`, branch `feat/bash-qa-eval-cli`.
[Test-first contract](../spec/bash-qa-eval-cli.md).

The project entry point accepts one explicit SDK EvalConfig JSON file:

```text
python -m cotrain_bash_qa_eval --config /path/to/explicit-config.json
```

Use the already qualified SDK interpreter with this repository importable.
No model, taskset, budget, output path or provider is chosen by the CLI.
All [evaluation-wrapper restrictions](2026-10-31-bash-qa-eval.md) still apply:
canonical Env/harness, explicit paired Task, fresh subprocess, finite positive
counts/turns, retries zero, edit/search false, push/resume/clean false and no
attachment, skills, compaction or custom toolset hooks.

Argument parsing and file reading precede SDK/product imports. Help imports
neither SDK nor QA plugins. Missing arguments, unreadable files and malformed
JSON/schema exit 2; file/schema errors do not print raw input. Execution errors
propagate normally, not as argparse errors. The CLI passes the exact validated
config once to the existing wrapper and ignores its returned episode list,
preserving ordinary SDK result/completion semantics. Exit 0 is not a new claim
that every episode succeeded.

This is a **project CLI**, not stock `vf-eval` support. Trusted plugin imports,
ordinary SDK config/log output and local subprocess execution are not sandboxed
or redacted. The generic input-error message is not a universal privacy boundary.
Existing SDK serialization omits execution-only resume/clean fields; tests put
forbidden flags in actual JSON input rather than relying on omitted fields.

## Actual evidence

- **125 affected tests passed in 10.66s**, including 11 new CLI cases and the
  114 existing evaluation tests.
- New cases include isolated `-I -B` help, four argument/file/input refusals,
  exact-object single delegation, unchanged execution-error propagation,
  three actual-wrapper mode refusals with zero SDK calls, and one real
  `runpy` `__main__` invocation.
- Real entry point uses the unchanged framework fixture: actual SDK evaluation,
  episode Agent, Bash child HTTP/tool gate and normal SDK-written JSONL.
  One actual report, receipt before policy call 2, exact persisted QA.
  Only a delegating `asyncio.run` test guard adds a 20s outer bound.
- Actual delegation suppression hit once and produced intended call-phase
  `CLI evaluation delegation missing` assertion RED. Baseline/restored GREEN;
  seven source/test/spec/fixture hashes unchanged.
- Python and security static reviews APPROVE. They did not execute tests.

Before this increment, user-authorized main merge `e5f013e` integrated seven
reviewed commits. Its combined affected suites passed **1,195 tests in 55.66s**;
merge tree exactly matched tested feature `5b8cabc`, and remote main was
verified. That run is separate from these 125 tests, not a full-suite claim.

Only synthetic fixtures and approved temporary loopback listeners were used.
No external provider/model/corpus, training/native campaign, install/download,
gate change, new writer, dependency, completion policy or app deployment.
Research remains 4 PARTIAL / 5 PARTIAL / 6 BLOCKED.

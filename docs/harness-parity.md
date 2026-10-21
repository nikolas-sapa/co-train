# Harness parity — the contract between the paired bash and PTC SQL arms

This file documents the contract that `ptc/sql_arms.py` and `ptc/sql_runtime.py` carry as
data and `ptc/test_sql_arms.py` executes. It is not the contract itself. Where this prose
and that code disagree, the code is right and this file is stale; the capability list, the
asymmetry list and the reasons rendered below are read out of the modules that own them, so
that a change in the code is visible as a change here.

Read it if you are deciding whether a bash-vs-PTC number from this repo means anything. The
short answer is that one earlier number did not, for a reason no test in the suite was
shaped to see, and everything here exists because of that.

---

## 1. Defect 5, which is why this exists

Run 1 (2026-10-01, taskset `ledger`, n=14, one rollout each) measured bash 0.8571 (12/14)
against PTC 0.2143 (3/14): a gap of **+64.3 pp** with disjoint CIs. The gap was instrument.
Six of this project's own defects had to be removed before the published +6.8 to +22 pp
bash-over-PTC ordering stopped reproducing (`docs/results-untrained.md`), and the fifth of
them is the one this document is about. It was found in run 2f (2026-10-02), the first
mechanically clean run, by reading what each arm actually received rather than what the rig
said it had been given. Both arms held the same three MCP tools, so the arms looked paired.
They were not. The bash arm held those tools as native tool calls and read their JSON output
with the model's own attention (its `shell-call share` was **0.0000**: it never used the
shell it was named for). The PTC arm reached the same three functions through
`ptc/runtime.py`'s sandbox, which has no `import json`, no attribute access, and a
`SAFE_BUILTINS` without `ord` or `chr`, and `_bridge` handed back `call_mcp`'s result
unparsed. So the PTC arm received a JSON *string* it owned no primitive to open: 46 of its
88 tool failures were the sandbox refusing ordinary Python (34 attribute access, 12 import),
11 more were `TypeError: string indices must be integers` (the model subscripting a JSON
string as if it were the dict the catalog's own description implied), and 17 were
`unknown name` rejections for primitives a typed catalog would have made unnecessary. On
`total-invoice` the model spent 25 calls hand-rolling a character-level JSON parser out of
`<` and `>` comparisons, discovered `.isdigit` and `ord` were both absent, and solved it
anyway: the one task PTC won and bash lost. bash's action space was a strict **superset** of
PTC's, which is not a harness comparison at all. Five of the nine harness faults in the
defect ledger (`docs/deviations.md`) penalised PTC, one penalised bash, two were symmetric,
and one is symmetric in principle but falls roughly three times harder on bash per unit of
work. **Every one of the thirty-eight was invisible to a green test suite, bar one**, and in
the thirteenth's case worse than invisible: `test_metrics.py` pinned the two failure prefixes
against drift in the strings, so the suite locked in the blindness it was meant to guard
against. (It read "every one of the thirteen" until 2026-10-13. The count was stated in a
sentence no guard parsed, so the 12 → 13 move had already passed it by; it is parsed now. The
exception is the gate tests, which a *red* suite caught and nobody had run. **The three rows
filed 2026-10-14 do not add a second exception**, checked rather than assumed: no suite saw
them at all. Two were found by reading — a log fetched six times that named the cause in one
line, and a metric's own definition against the batch size the probe ran — and the quantities
they turn on were computed nowhere in the suite, so there was nothing to go red. The third had
a green control that was telling the truth about the wrong path: twelve fenced gold queries,
never one completion shaped the way a policy writes. All three are invisible-to-green, which
is what the sentence claims.) Nothing in the suite compared what the two arms could *do*.

---

## 2. The contract

Four clauses. An arm pair that violates any of them is not hosting a comparison.

1. **Identical information.** One `TaskView` per task, one schema string read once from
   `sqlite_master` and handed to both prompts (`build_sql_arms`), one shared prompt body.
   The channel paragraph (`BASH_CHANNEL` / `PTC_CHANNEL`) is the only per-arm text. BIRD's
   `evidence` hint, where a corpus ships one, goes into the shared body, so both arms get it
   or neither does.
2. **Identical budgets.** One `Budget` struct per `ArmPair`, not one per arm: `max_turns=8`,
   `max_retries=0`, `retry_on=()`, `rollout_timeout=600.0`, `program_timeout=5.0`.
   `WRAPPER_TIMEOUT=30.0` is the bash arm's per-query deadline and is deliberately a
   different number from `program_timeout`, for the reason in §7.
3. **Identical catalog and prompt text modulo the channel.** The SQL action carries one
   name, `execute_sql`, on both arms: a catalog entry inside the program on PTC, a shell
   script of the same name on PATH on bash. An arm told its action is called something else
   is an arm reading different prompt text, which is a confound on prompt content rather
   than on channel.
4. **Neither arm holds a primitive the other lacks for the declared task class.** This is
   the clause defect 5 broke, and the only one that cannot be satisfied by reading the code,
   so it is satisfied by running it: twelve capabilities, two executable probes each, both
   run on every test invocation.

Two further invariants are structural rather than probe-shaped, and `test_sql_arms.py`
checks them where they can actually fire:

- **The PTC arm registers exactly one tool**, `run_program(code: str) -> str`
  (`docs/spec-cotrain.md`, invariant 1). TRL passes `tools=self.tools` into
  `apply_chat_template`, so every registered tool is rendered as a schema in the system
  prompt; registering a typed `execute_sql` alongside `run_program` would silently build the
  typed-tool-calling comparator instead of PTC, which is the exact axis this project
  measures.
- **The row cap lives on the channel, not on one arm's parser.** `MAX_ROWS = 200` and
  `over_cap_message` are imported by both arms rather than re-spelled. Reached bare,
  `sqlite3 <db> "<query>"` is an *uncapped* channel whose observation is truncated by a
  context limit the arm is never told about, while the PTC arm refuses at the cap: that is
  defect 5 inverted, in bash's favour, so the bash arm reaches sqlite through a generated
  wrapper that enforces the same threshold and emits the same refusal text.

---

## 3. Why `expected` is the answer, and not the channel's bytes

Each `Capability` holds one `expected` string and both arms must produce it. `expected` is
deliberately **not** the raw channel output. The bash arm reads `sqlite3 -list -header`
text; the PTC arm reads a list of dicts. Demanding byte-identical observations would be
demanding that the two channels be the same channel, which is the thing under measurement.
What a task scores on is the answer the arm reaches, so that is what the probes compare.

Two match modes:

| `match` | Rule | Used for |
|---|---|---|
| `tokens` (default) | whitespace-normalised equality: `" ".join(obs.split()) == " ".join(expected.split())` | the ten probes that *compute* an answer |
| `contains` | `expected in obs` | the two probes whose subject is a channel **message** |

Only `over_cap_refusal` and `query_error_text` use `contains`, and only because their
subject is a message both arms wrap in their own framing: sqlite's CLI prefixes `Parse error
in 5th command line argument:` while the sandbox prefixes `rejected: OperationalError:`. The
message is the information and the framing is the channel, so the probe asserts the message
arrives on both arms and declines to assert the framing matches. Whitespace normalisation is
the same concession one level down: `-list` output ends with a newline and a `print` does
not.

---

## 4. The twelve capabilities

One entry per ability the declared SQL task class needs, each with a shell line, a program,
and the answer both must produce. `why` is quoted from `ptc/sql_arms.py::CAPABILITIES`,
which owns it.

| Capability | Answer | Why the declared class needs it |
|---|---|---|
| `run_query` | `5` | "every task in the class begins by running a query and seeing its result." |
| `row_count` | `5` | "'how many X' is answerable in SQL, but checking how many rows came back is how either arm knows whether to narrow a query. An arm that cannot count its own result is an arm guessing whether it saw everything." |
| `cell_by_column_name` | `Ada` | "reading one named column of one row. The run-1 failure in one line: the catalog returned a JSON string and the sandbox owned no primitive to reach a field inside it, while bash read the same bytes with attention." |
| `iterate_rows` | `Ada Bob Cy Dee Eve` | "visiting every row of a result, which any per-row check needs." |
| `aggregate_client_side` | `495` | "summing outside SQL. Reachable in SQL too, and that is the point: an arm that can only aggregate in SQL has to get the query right first time, while the other can check its arithmetic against the rows it already has." |
| `compare_and_filter` | `Ada Cy` | "keeping the rows that satisfy a predicate the query did not express. The comparison operators are the half of this that `runtime.ALLOWED_NODES` has to carry; the filtering is the half the catalog has to." |
| `sort_client_side` | `Ada` | "ordering by a key the query did not order by. Also the probe that pins the declared `lambda` asymmetry as a SPELLING difference: the sandbox refuses `key=lambda r: r['salary']` and accepts the same key written as a def, so the capability is reachable and only the syntax differs." |
| `format_multi_value` | `Ada Cy` | "'their names separated by single spaces' is the shape four of `ledger`'s tasks already use. bash formats it with one `tr`; the sandbox needs `sql_runtime.join`, which is why that primitive exists." |
| `two_queries_one_action` | `5 3` | "combining two results without spending a turn between them. This is the axis the project measures rather than a fault, so it has to be present on BOTH arms: a bash arm that could only run one query per turn would be a comparator hobbled in PTC's favour." |
| `duplicate_column_names` | `Ada Eng` | "both columns of `SELECT e.name, d.name`, which every two-table join over similarly-named columns produces. `sqlite3 -list -header` prints `name\|name` and both values; the naive `dict(zip(columns, row))` keeps one and hands the sandbox a row of length 1. A typed channel that silently drops half a join is defect 5 in a different costume, so `dedup_columns` suffixes rather than collapses and this probe is what holds it there." |
| `over_cap_refusal` | the refusal text (`contains`) | "a result past the cap must arrive as the SAME refusal on both arms. An arm told 'add a LIMIT' while the other is silently truncated has more information about its own channel, and a model that reads part of a result and answers confidently is what the cap exists to prevent." |
| `query_error_text` | `no such table: missing` (`contains`) | "seeing WHY a query failed. Both arms get sqlite's own message, so a wrong column name costs each of them one action and the same information. Only recovery within a single action differs, and that is declared." |

The probes run against `PROBE_SCHEMA`, built by code at test time: two joinable tables, five
employees, one numeric column. It is deliberately not `bench/fixtures/schema.sql`, because
the parity contract is a property of the two arms and has to be checkable wherever `ptc`
imports. The over-cap probe's threshold is `PROBE_DB_ROWS - 1`, derived rather than written
twice, so adding a row to the fixture cannot quietly stop that probe overflowing.

### `cell_by_column_name` and `duplicate_column_names` are defect 5 written as tests

`cell_by_column_name` is the run-1 failure reduced to one assertion: reach one named field
of one row. In run 1 the bash arm did it with attention on a JSON string and the PTC arm
could not do it at all. The probe now fails loudly on either arm instead of surfacing nine
days later as a score.

`duplicate_column_names` is the same defect in the shape the fix could have taken.
`SELECT e.name, d.name FROM emp e JOIN dept d ON e.dept_id = d.id` makes
`sqlite3 -list -header` print a header of `name|name` and both values, so the bash arm sees
everything. The obvious typed translation, `dict(zip(columns, row))`, keeps one value and
hands the sandbox **a row of length 1**: half the join gone, no error, no warning, and a
program that reads `rows[0]["name"]` gets a plausible wrong answer. A typed channel that
silently drops half a join is defect 5 in a different costume, with the arms' roles
unchanged. So `dedup_columns` **suffixes rather than collapses**: repeats become `name_2`,
`name_3`, and a generated suffix is checked against the names already taken rather than
assumed free, since a column genuinely called `name_2` alongside two `name`s would otherwise
collide with the generated one. The trade is explicit: suffixing is visibly lossy in the
*name* and lossless in the *value*, which is the right direction, because the value is what
the answer is made of, and `SHARED_PROMPT` tells the model how the suffix is spelled so it is
not guessing.

### The one primitive the sandbox was given

`SQL_PRIMITIVES` holds exactly one entry. Rendered from `PRIMITIVE_REASONS`:

- **`join(sep=..., parts=...)`** — "multi-value answers are in the declared task class and
  the sandbox refuses the str method as attribute access. Reachable without it via an
  accumulator loop, so this closes a cost gap on a co-primary (completion tokens), not a
  capability gap."

The bar for entry is not "a program would be tidier with it". The value stays reachable
without it (string accumulation in a loop, measured working), the bash arm formats the same
answer with one `tr` or `paste`, and completion tokens are a pre-registered co-primary, so
leaving the accumulator loop in place would put a three-line tax on one arm's cost figure
for a step that is not the axis under measurement. The primitive is keyword-only, matching
`harness.py::_bridge` and what the system prompt tells the model: a locally registered tool
that quietly accepted positionals would teach the opposite of the prompt, which is run 1's
defect 3 (34 of 54 PTC tool failures were that one mismatch).

---

## 5. The five declared asymmetries

Gaps that are known, deliberate and not fixed. **Four of the five favour bash.** That is the
honest shape of the thing: the sandbox is a restriction, so the arm it restricts loses
affordances, and a `DECLARED_ASYMMETRIES` list that read as a clean two-two split would be
evidence that someone had been balancing the ledger rather than measuring it.
`test_sql_arms.py` asserts the direction set is exactly `{"bash", "neither"}`, so a `ptc`
direction appearing here has to be argued for rather than typed.

| Asymmetry | Favours | Probe expects | Why declared rather than denied |
|---|---|---|---|
| `try/except` | bash | `rejected` | `ast.Try` is not in `runtime.ALLOWED_NODES`, so a program cannot recover from a failed query *within one action*; bash can, with `\|\|` or `2>/dev/null`. Both arms see the failure as action output and may retry on the next turn, so this is a budget asymmetry, not an information one. Adding `Try` widens the sandbox for every program, and the escape surface it opens is not worth one retry. |
| `lambda` | bash | `rejected` | `ast.Lambda` is absent, so a `sorted()` key written as a lambda is refused. The same key written as a `def` is accepted and measured working, and the `sort_client_side` probe is what holds that: the capability is reachable and only the spelling differs. |
| `str methods` | bash | `rejected` | attribute access is refused outright, so `lower()`, `split()` and `strip()` are unavailable. The grader normalises case and whitespace on both arms (`ledger/taskset.py`'s reward lowercases and re-joins), so no answer in the declared class needs them. |
| `partial_output_before_failure` | bash | `partial_loss` | a program that prints and then issues a failing query loses the printed output: `harness.py::_loop` replaces the observation with the error text, because a program that raised did not finish and its partial output could be half a sentence. bash keeps whatever reached stdout before the failing command. Costs at most one action's partial observation, and both arms see the failure itself. Returning partial output alongside an error would teach the model that a crashed program is a successful one, which is a worse lesson than one lost print. |
| `error_message_framing` | neither | covered by the `query_error_text` capability probe | both arms receive sqlite's own message (`no such table: missing`) wrapped in their channel's framing. The information is identical and only the wrapper text differs, which is what "modulo the channel" means. Recorded so the difference is declared data rather than something a later reader finds and mistakes for an information gap. |

The reasons live in `sql_runtime.UNREACHABLE_IN_SANDBOX` (the first three) and
`sql_arms.ASYMMETRY_REASONS` (the last two), one source each, and are quoted above rather
than paraphrased. A sandbox limit that SQL work runs into and that appears in neither
`SQL_PRIMITIVES` nor `UNREACHABLE_IN_SANDBOX` is an undeclared asymmetry, which is the
defect-5 shape.

---

## 6. What the guard can detect, and what it cannot

**Detects.** An arm losing a primitive, or gaining one the other lacks, for any of the
twelve listed abilities, on either arm, without anyone remembering to update a list. A
divergence that is one-sided is also reported *as* one-sided
(`test_no_capability_is_one_sided`), because a list where every entry fails on the same arm
is a superset rather than twelve unrelated bugs, and the per-capability failure message
buries that. A `run_program`-plus-typed-tool registration. A per-arm budget. A prompt
rendered without the schema or the question.

**Cannot detect, structurally: an asymmetry nobody wrote a capability for.** The guard
measures the twelve abilities in `CAPABILITIES` and is silent on everything else. Defect 5
itself would not have been caught by a twelve-capability list that happened to omit
`cell_by_column_name`. The list is a measurement of a *declared* task class, so widening the
task class without widening the list reopens exactly the hole this guard was built to close.
Stated rather than buried: the guard converts "we believe the arms are paired" into "the arms
are paired on these twelve axes, measured on every test run", and the gap between those two
sentences is a judgement about whether the twelve are the right twelve.

**Gaps found while writing this file (2026-10-13).** Three docstrings in
`ptc/sql_arms.py` described checks that `ptc/test_sql_arms.py` did not perform. The code is
the source of truth for the contract and the test is the source of truth for what is
*enforced*; where they disagree, the enforcement is what a reader should trust, so the
disagreements were listed rather than smoothed over.

**All four were closed by `04575d4` (2026-10-13), and this list is kept as the record of
what they were.** Each now has a named test, so a reader can run it rather than trust this
paragraph:

1. **Prompt identity.** `test_the_two_prompts_differ_only_by_the_channel_paragraph` renders
   both prompts, removes the two channel strings, and fails unless the remainder is
   byte-identical. Contract clause 1 is enforced.
2. **The asymmetry probes run.** `test_every_declared_asymmetry_still_exists` is
   parameterised over every entry with a probe and executes it; a limit that quietly went
   away turns it red. `test_every_declared_asymmetry_has_a_retrievable_reason` touches
   `Asymmetry.reason`, so a name in neither reason dict fails at test time rather than at
   render time.
3. **Coverage of `UNREACHABLE_IN_SANDBOX` is asserted.**
   `test_declared_asymmetries_cover_every_sandbox_limit` imports the dict and fails on any
   limit with no declared asymmetry.
4. **The capability guard is parameterised over backends.**
   `test_the_capability_guard_runs_against_a_second_backend` drives a recording stub and
   proves both `run_bash` and `run_ptc` are reached, and that `model_tools(arm)` is called
   for real rather than merely `callable`.

Of the two smaller notes that used to follow, the tautology is gone —
`assert pair.budget is pair.budget` was replaced with the shape that would have to change
for a per-arm budget to appear — and the probes' five-row fixture scope is unchanged: right
for an action-space question, silent at corpus scale, which is what the sweep below is for.

### What the differential closes, and what it still cannot

`ptc/sql_diff.py` is the answer to the paragraph above. Instead of a thirteenth named
capability, it runs the **task class's own gold queries** through both arms' execution
channels and requires the same answer as scored by `bench/score.py` (`rows_match`,
`compare="set"`, matching BIRD's `evaluation.py`). The golds were written by BIRD before
either arm existed, so nothing in them was chosen to suit a list: a divergence is an
asymmetry nobody named, by construction.

Three comparisons, because an answer can differ at three depths:

| Comparison | What it asks | Cause vocabulary |
|---|---|---|
| delivery | did both arms return rows, both refuse at the cap, or both fail? | `one_sided_refusal`, `one_sided_error`, `one_sided_undecodable`, `refusal_text_differs`, `error_text_differs` |
| answer | do the delivered rows score as the same answer? | `rows_differ`, `trailing_empty_row` |
| render | would the two MODELS read the same thing? | `null_rendering`, `float_rendering`, `blob_rendering`, `separator_in_cell`, `newline_in_cell`, `duplicate_columns`, `control_char_rendering`, `type_rendering`, `column_count`, `row_count`, `trailing_empty_row` |

The render pass is not decoration. bash reads `sqlite3 -list -header` text; PTC reads dicts
a program must `print`, and `print` renders Python `repr`. The same rows therefore arrive as
different answers: NULL is an empty field on bash and `None` on PTC; a REAL prints
`0.33333333333333332` on the CLI and reprs as `0.3333333333333333`; a control byte prints as
caret notation (`^]`) on bash and as the raw byte on PTC; a final all-NULL row is a blank
line that the wrapper's own terminator makes unrecoverable; `|` and newlines inside a value
reshape the bash row; and two columns called `name` print `name|name` on bash against the
`name_2` suffix `SHARED_PROMPT` promises. Each is reported by name.

**Measured on the full corpus (2026-10-18, `.venv-ptc`, SQLite 3.50.4 in Python and 3.54.0
in the CLI): 1526 of 1534 BIRD dev golds agree, and every one of the 8 that do not is
characterised.** 92 of the 1526 are refused at the cap by BOTH arms — agreement, but not a
row comparison. Of the 8:

| ids | count | cause |
|---|---|---|
| `bird-0518`, `bird-0701` | 2 | the corpus's own non-terminating golds, already documented as defects in `docs/bench-taskset.md` §4.3 |
| `bird-0284`, `bird-0637`, `bird-1399`, `bird-1504` | 4 | a trailing run of all-NULL rows renders as blank lines that the wrapper's own terminator makes unrecoverable; `bird-1399` loses 13 of 14 rows this way |
| `bird-0483` | 1 | the wrapper's line-count fallback refuses early: 149 rows carrying 7 806 embedded newlines exceed the cap as LINES |
| `bird-0714` | 1 | embedded newlines split bash rows, so 118 rows arrive as 137 |

A further 25 golds agree on the answer and differ only in rendering: `null_rendering` 16
(NULL against `''`/`None`), `control_char_rendering` 4 (caret notation against the raw
byte), `duplicate_columns` 2, `newline_in_cell` 1, and `trailing_empty_row` counted on 7
(golds where the row count differs but the SET still scores equal).

**Multiset sensitivity.** The same sweep with `compare="multiset"` agrees on **1523** and
diverges on **11**: the same 8, plus `bird-0538`, `bird-0618` and `bird-0630`, whose
duplicate all-NULL rows set comparison collapses and multiset does not. That is the
trailing-row loss again, arriving a second way — and it is the only place the two BIRD
comparison conventions disagree on the differential, so neither number is reported alone.

**The check can fail, and was seen failing.** Rounding REALs to six places inside
`rows_from_cursor` — a plausible "tidy the display" regression that no capability names —
turns `test_every_fixture_gold_agrees_on_both_arms` and
`test_float_rendering_is_compared_not_assumed` red while all twelve capability probes stay
green. Switching the bash wrapper from `-list` to `-csv` turns five checks red. Both were
reverted and `ptc/sql_runtime.py` confirmed byte-identical by sha256
(`fe35aed58eca47984b4842f438680d18d7b7a220e4376b374ce84cd4225aa0b4`). The
`trailing_empty_row` and `control_char_rendering` causes were not found by design; they
were found by running the corpus's own golds, which is the point.

**What it still cannot see.** A gold returns one result set, so the differential exercises
`execute_sql` and the three outcomes above: not multi-query programs, not `join`, not the
model's own `print` formatting, not the prompt, not the budgets. It cannot detect a
divergence that only a *model-written* query triggers. And where the bash channel loses
information in a way no parser can recover — a trailing all-NULL row, a value whose
newlines outnumber the rows — the differential can only report the loss, not repair it, and
a task whose answer depends on such a row is scored differently by the two arms no matter
what this check says. That is now a known, counted property of the bash channel rather than
an unnamed hole. Two of the eight are corpus defects, so the parity defect rate among golds
that run is **6 / 1532 = 0.39 %**, all six in the bash arm's rendering of NULLs and
newlines.

Two smaller notes remain as scope, not defects: the probes still exercise the arms against a
five-row fixture, which is right for an action-space question and says nothing about corpus
scale (the sweep above is what says something about corpus scale); and the sweep is run by
hand (`bench/sql_parity_sweep.py`), not in CI, so its number describes the day it was run.

---

## 7. The swap seam

Step 6's cross-harness evaluation (H3/H4/H5) needs a policy trained on one harness to be
*evaluated* on another, so the arm pair cannot be welded to `ptc.harness.PTCHarness`.
`HarnessBackend` is the seam, a `Protocol` with six members:

| Member | What it owns |
|---|---|
| `name` | the backend's id, for provenance in results |
| `arm_ids()` | `(bash_harness_id, ptc_harness_id)` as the rig resolves them |
| `model_tools(arm)` | the tool **schemas** this arm renders into the model's context. Exactly one for the PTC arm. This is where spec invariant 1 can actually fire |
| `catalog(view, max_rows, observe)` | the PTC arm's in-program action space for one task |
| `run_ptc(program, view, max_rows)` | one PTC action, returning the observation the model would read |
| `run_bash(command, view, max_rows, bindir)` | one bash action, the same |

**What it deliberately does not abstract: the task, the schema string, the prompt body and
the budgets.** Those belong to the experiment, not to a harness, and they are identical
across harnesses by construction. A backend that could vary them could vary the comparison,
which is why `Budget` is a separate struct handed to `ArmPair` rather than a backend concern.
`Budget`'s own docstring records what happens otherwise: `PTCHarnessConfig.max_turns`
defaults to 8 and shadowed the agent-level budget entirely, so a raise to 80 applied to bash
only, 11 of 14 PTC rollouts stopped at exactly 8 programs while bash spent up to 44 turns on
the same tier, and the turn budget had become the independent variable (defect 1). `retry_on`
carries two exception names for the same reason: the two arms report the same transport fault
under different type names (`ProviderError` on PTC, which owns its HTTP client;
`HarnessError` on bash, re-wrapped by the rig around its bundled runtime's subprocess), so
retryability was being decided by which arm's code owned the socket (defect 6).

`_PtcV1Backend` is the only implementation and is thin on purpose: every method is a
one-liner over something that already existed, which is the evidence that building the seam
did not require a second harness, only that the first stop being assumed. It raises
`NotImplementedError` from `model_tools("bash")` rather than returning `[]`, because the bash
arm's schemas come from verifiers' bundled harness, and claiming ownership of an arm you do
not build is how an instrument starts asserting its own soundness.

`SECOND_HARNESS_REQUIREMENTS` is the contract a second implementation must meet, held as
data because **`HarnessBackend` is a Protocol and nothing in the type system makes a
conformant implementation a comparable one. That gap is where run 1's +64.3 pp came from.**
Verbatim:

1. `arm_ids()` returns exactly two ids, and the PTC-side id names the arm whose single
   action is a program. A harness with three arms is a different experiment.
2. `model_tools(arm)` returns EXACTLY ONE tool for the PTC arm, and that tool is the program
   entry point. Returning the SQL tool here converts the comparison into the
   typed-tool-calling comparator, which is the axis this project measures.
3. `model_tools(arm)` raises `NotImplementedError` for an arm whose schemas the backend does
   not own, rather than inventing them.
4. `catalog(db_path, max_rows, observe)` exposes the SQL action INSIDE the program, returning
   rows the program owns primitives to iterate, index, compare and format. Returning an
   unparseable string is defect 5 and invalidates the run.
5. `run_bash` / `run_ptc` deliver the same refusal text on an over-cap result and the same
   database error text, because an arm told why it failed has information the other lacks.
6. Every entry in `CAPABILITIES` passes on both of its arms.
   `test_the_capability_guard_runs_against_a_second_backend` drives this through
   `backend.run_bash` / `backend.run_ptc`, so a second implementation inherits the guard
   rather than being held to it by hand (the former §6 gap 4, closed in `04575d4`).
7. It does NOT supply the task, the schema string, the prompt body or the budgets. A backend
   that could vary those could vary the comparison.

---

## 8. Running the guard, and seeing it fail

```sh
.venv-ptc/bin/python -m pytest ptc/test_sql_arms.py -q
```

`.venv-ptc/bin/python` is not optional: `ptc/` imports `verifiers`, which the system
interpreter lacks, and the failure happens during *collection*, so a bare `pytest` reports
an error rather than a test result. Green at the state this file documents:

```
....................                                                     [100%]
20 passed in 5.80s
```

**Dated note, 2026-10-19: the count above is stale; the file now collects 28.**
`ptc/test_sql_arms.py -q` measures **28 passed** in the repo venv. The transcript is kept as
the state this document was written at on 2026-10-13; eight tests were added to the same
file since, so a reader comparing a local run against "20 passed" would think collection
had broken.

**A guard that has never gone red is not evidence.** Verified on 2026-10-13: emptying
`SQL_PRIMITIVES` in `ptc/sql_runtime.py` (`{"join": join}` to `{}`) costs the sandbox `join`,
which the bash arm has via `paste` and `tr`, and the suite goes to **3 failed, 17 passed**:
the two capabilities whose answers are multi-value (`compare_and_filter`,
`format_multi_value`) and the one-sided check that names them together.

**RE-RUN 2026-10-19: the guard still goes red, and the counts have moved with the file.**
The same mutation applied to a scratch copy turns the same three tests red --
`test_every_capability_is_reachable_on_both_arms[compare_and_filter]`,
`…[format_multi_value]` and `test_no_capability_is_one_sided` -- at **3 failed, 25 passed**
of 28 collected, and reverting every file returns **28 passed**. The failure text below is
from 2026-10-13 and is unchanged by this re-run.

```
AssertionError: format_multi_value: bash=reaches, ptc=CANNOT
    needed: 'Ada Cy' (tokens)
    bash saw: 'Ada Cy'
    ptc saw:  "rejected: unknown name 'join'; the catalog exposes ['execute_sql']"

AssertionError: action spaces diverge on: ['compare_and_filter', 'format_multi_value']
```

That is the guard doing the one thing run 1's suite could not: naming an arm that cannot
reach an answer the other can, by arm, on the axis it was lost on. The mutation was then
reverted and `ptc/sql_runtime.py` confirmed byte-identical by sha256
(`fe35aed58eca47984b4842f438680d18d7b7a220e4376b374ce84cd4225aa0b4` before and after), with
the suite back to 20 passed.

**Dated note, 2026-10-19:** "back to 20 passed" is now **28 passed**. The sha256 is still
`fe35aed58eca47984b4842f438680d18d7b7a220e4376b374ce84cd4225aa0b4` (checked in the repo
working tree today); the re-run above was done in a scratch copy and this file was not
touched by it.

The second mutation worth knowing, not re-run here because the first is sufficient and
cheaper: removing the subquery `COUNT(*)` check and the line-count guard from
`wrapper_script` makes the bash arm's channel uncapped, which `over_cap_refusal` catches as
bash failing to produce the refusal the PTC arm produces. That is defect 5 inverted, and it
is the only capability in the list whose failure favours bash.

The differential is run the same way, and has the same requirement:

```sh
.venv-ptc/bin/python -m pytest ptc/test_sql_diff.py -q          # fixture corpus, fast
.venv-ptc/bin/python -m bench.sql_parity_sweep --jobs 8 \
    --out ~/scratch/cotrain-diffparity/sweep.json               # all 1534 dev golds
```

Green at the state this file documents: `17 passed`, and the sweep's summary is the table in
§6. The sweep writes one JSON row per gold (`agreed`, both outcomes, both row counts, the
cause lists), so a divergence can be re-derived without re-running it.

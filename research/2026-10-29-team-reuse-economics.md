# Can shared agent experience save teams time?

Date: 2026-10-29.

## Answer

Moderate-to-high confidence: reusing recurring agent workflows can reduce machine
runtime and inference spend. Some regimes are slower. Confidence in saved human
team hours is low: the cited studies primarily measure agents, not teams.
None proves positive net savings for co-train after qualification, authoring,
review, maintenance and sharing.

co-train demonstrates caller-authored qualification and fresh-process reuse
mechanics. These are not evidence of automatic learning, model benefit, net cost
savings or saved team hours. No current real-pilot result supports those claims.

## Sources and method

Research used primary papers and product documentation. Agentic Plan Caching v2
and AgentSM were also directly retrieved through FetchUrl, both HTTP 200; the
other six sources were read through WebSearch-returned page text. Figures below
are source-reported, not independently reproduced experiments.

A separate SWE-2 High-assisted local static audit identified telemetry gaps.
Its source observation at 17:48:34Z, HEAD `3b41b6f`, included concurrent working
changes, not final bindings. That audit is historical measurement guidance,
not current runtime acceptance. This note does not certify the new external
timing harness; integration/final validation remains separate.

## What the evidence supports

1. [Agentic Plan Caching v2](https://arxiv.org/html/2506.14852v2), January 26,
   2026, sections 4.1–4.5, Tables 3–4: 100 random FinanceBench queries, 46% cache
   hits, entire-workload time 1,959.24 → 1,424.82 seconds versus the
   Accuracy-Optimal large-planner baseline. Timing includes extraction, lookup
   and cache generation. With a one-entry cache and 2% hits, 2,232.76 seconds
   was slower. Across several workloads, reported mean cost reduction was 50.31%,
   retaining 96.61% of baseline application performance. This is relative
   performance with some quality loss, not equal quality or 96.61% absolute
   accuracy. Cost uses token prices; quality uses a GPT-4o judge. Table 6's fuzzy
   matching raises hits to 54% and lowers latency to 1,219.73 seconds, but accuracy
   is 83% versus 85.5% for exact matching. No human team-hour study.

2. [AgentSM](https://arxiv.org/html/2601.15709v1), January 22, 2026, Tables 2–3:
   547 Spider2-Lite questions with the same Claude 4 Sonnet. CodingAgent versus
   AgentSM: EX accuracy 24.7% → 44.8%, single-execution end-to-end latency
   325.5 → 247.1 seconds, steps 18.1 → 16.4, input tokens 200K → 300K and output
   tokens 4K → 5K. Lower latency accompanies higher tokens, not automatic inference
   savings. Separate 75-question ablation, no trajectory reading versus full:
   348.6 → 252.4 seconds, accuracy 17.3% → 52.0%. Retrieval uses the same DB;
   synthetic-memory preparation is not amortized. Tables are used because the
   abstract and body disagree.

3. [ACE, revised March 29, 2026](https://arxiv.org/pdf/2510.04618), Table 4:
   offline AppWorld adaptation versus GEPA took 53,898 → 9,517 seconds and
   1,434 → 357 rollouts. Online FiNER versus Dynamic Cheatsheet took
   65,104 → 5,503 seconds and $17.70 → $2.90 token cost. These are adaptation
   comparisons, not teams or a no-memory baseline.

4. [Voyager](https://ar5iv.labs.arxiv.org/html/2305.16291), May 2023:
   executable skill library, 63 unique Minecraft items in 160 prompting iterations,
   plus fresh-world transfer. Curriculum and verification also differ; this does
   not isolate memory's effect or establish seconds saved. GPT-4 cost and
   execution errors remain relevant.

5. [MemoryArena](https://arxiv.org/pdf/2602.16313), February 2026:
   701 tasks, averaging 6.9 subtasks and 57 actions. Conversation-memory benchmark
   success does not establish agentic-task success. No savings estimate.

6. [Snowflake verified query repository](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/verified-query-repository):
   shared verified question/SQL examples retrieved by similarity. Incorrect
   verified queries can reduce accuracy. No controlled savings metric.

7. [BigQuery conversational analytics](https://docs.cloud.google.com/bigquery/docs/conversational-analytics):
   verified-query matches can use deterministic SQL with permission controls.
   No comparable controlled savings metric.

8. [Claude organization skills](https://support.claude.com/en/articles/13119606-provision-and-manage-skills-for-your-organization):
   reviewed/versioned distribution, group approval and Enterprise scanning.
   Sharing skills alone is not distinctive; no measured team-hour savings here.

## Which reuse, and which alternatives?

Answer caching assumes unchanged state. RAG/query examples still require
reasoning. Private member memory is not shared team experience. A verified
executable procedure recomputes against current data, but its assumptions can
expire. Useful repeat rate before expiry matters more than team size alone.

Closest comparisons: warehouse verified-query repositories, organization-managed
skills, and AgentSM/Agentic Plan Caching-style experience reuse. The co-train
question is whether qualification and approval buy better valid-task economics
after their costs are included. This research recommends measurement, not a new
vendor, registry or schema.

## Measurement requirements

The local static audit found partial timers, not an end-to-end savings ledger:

- Captures record outcomes, steps, refusals and aborts without timestamps.
- API `latency_ms` spans credential read, request-file handling, HTTP body and
  checks. It excludes persistence, billing, settlement and action parsing; it is
  neither provider-only time nor full end-to-end time.
- Optional prompt/completion/total tokens and reported model do not supply
  billing units or cached-token breakdowns. Actual charge requires an externally
  bound bill receipt; missing billing is unknown, not zero.
- Qualification timing excluded persistence/fsync. Model-plus-execution time
  is not full end-to-end. Planned pairs must remain visible when failures lack
  telemetry; successful latency lists alone can bias results.
- Pilot break-even scenarios counted development/proposal model charges while
  qualification compute and total economics were unavailable. Horizons
  100/1,000/10,000 were scenarios, not observed adoption or savings.

Generic capture comparison explicitly lacks billing, tokens, request latency and
approved-reuse attribution. Collect these externally, including failures, CPU/DB
compute and human review minutes. Any new timing instrumentation needs separate
final validation; adding a timer does not supply unknown billing or prove benefit.

## Minimum credible experiment, proposed only

Not performed, not authorization for paid calls or new trials. Freeze model,
budgets, tools, resources and cache policy before evaluation. Use eight SQL
procedure families: one source, four distinct qualification cases and 12 sealed
evaluations per family; three seeds give 288 evaluation runs per arm.

Five arms: from scratch, private memory, shared query examples, shared trajectory/
plan, and co-train. A team claim needs four actual participants or real member
workloads. Renaming synthetic agents is not a team study. Separate near repeats,
new compositions and held-out families. Use fresh DB names/data/distributions,
hidden multi-data SQL checks, edge cases, schema drift, stale/bad skills,
retrieval mismatches and permission failures.

Measure full end-to-end seconds (median/p95), requests, tokens, billed dollars
per valid solved task, DB compute, failures/retries and human review minutes.
Include authoring/setup, all four qualifications, failed/rejected attempts,
persistence/fsync, review, maintenance, sharing and invalidation. Preregister a
quality rule, for example at most two percentage points of regression; this is
a proposed limit, not a passed threshold.

For each unit separately:
`net savings = N × (full scratch cost − full reuse cost) − setup − qualification − maintenance`.
Count authoring/review/sharing/invalidation in full costs or overheads exactly
once. With no positive per-use savings, there is no finite break-even.
Report money and time separately. Human-hour claims require human observations,
not sums of agent wall times.

Non-goals: product/traction claims, new infrastructure, automatic approval,
new provider experiments or permission to spend. Existing native, paid and
push/deployment gates remain unchanged.

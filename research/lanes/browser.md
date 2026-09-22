# Lane: Agentic Web Access — Browser Use and Fetch

**Method note.** Bash and Write were disabled for this session, so this report was delivered as messages and concatenated by the lead. WebSearch is confirmed dead (`ValidationException: tool type 'web_search_20250305' is not supported for this model`) — every finding below comes from a direct URL fetch of a source nameable in advance: arXiv API (`export.arxiv.org`), `raw.githubusercontent.com`, `api.github.com`, `datatracker.ietf.org`, and `r.jina.ai` for pages that resist direct fetch. Semantic Scholar was not attempted (no curl). Every arXiv ID cited was verified to resolve via `id_list` before use; IDs that returned no entry are called out in Known Gaps.

Labels: **MEASURED (ind.)** = measured by someone other than the thing's authors/vendor. **MEASURED (vendor)** = the authors/vendor measured their own system. **CLAIMED** = asserted with no measurement in reach.

---

## Q1 — The SPA-shell problem: is there a shipped detector?

### Answer

**No production tool ships a content-based SPA-shell detector.** Nothing read here uses content-to-markup ratio, script-tag density, framework fingerprints, or text-node counts to decide "this page needs JS." The industry has split three ways: (a) always use a browser and never ask (Firecrawl, Jina Reader default, crawl4ai), (b) make the caller choose (Zyte, Jina `X-Engine: direct`), or (c) one genuine shipped detector — Crawlee's `AdaptivePlaywrightCrawler` — which is **not content-based at all**: it is a per-site URL-similarity logistic regression validated by differential execution. The ratio heuristics that do exist in extractors (Trafilatura, crawl4ai) are boilerplate-removal scores, not JS-detection, though Trafilatura's escalation rule is the closest thing anyone ships to a content-coverage test. **Confidence: strong** for the tools read at source; **moderate** as a claim about the whole ecosystem, since only nameable tools could be read.

### The one real detector: Crawlee `AdaptivePlaywrightCrawler` — MEASURED (n/a: mechanism, not benchmark)

Source: `raw.githubusercontent.com/apify/crawlee/master/packages/playwright-crawler/src/internals/utils/rendering-type-prediction.ts` (JS predictor), `.../internals/adaptive-playwright-crawler.ts` (the loop), and `raw.githubusercontent.com/apify/crawlee-python/master/src/crawlee/crawlers/_adaptive_playwright/_rendering_type_predictor.py` (Python port).

Mechanism, exact:

1. **Features.** URL → `[url.hostname, ...url.pathname.split('/')]`. Pairwise similarity: different hostname → `0` immediately; otherwise per-path-segment `jaroWinkler.similarity(a[i], b[i]) > 0.8 ? 1 : 0`, averaged over segments (hostname index excluded from numerator and denominator). Missing segments compare against `''`. Feature vector is 2-D: `[mean similarity to stored static URLs, mean similarity to stored clientOnly URLs]`, **scoped to the request `label`**.
2. **Model.** `ml-logistic-regression` `LogisticRegression({ numSteps: 1000, learningRate: 0.05 })` (Python: sklearn `LogisticRegression(max_iter=1000)`). Retrained from scratch on every `storeResult`. Seeded with two synthetic anchors `X = [[0,1],[1,0]]`, `Y = [0,1]`. Label convention **1 = static, 0 = clientOnly**.
3. **Prediction and the detection budget.** Cold start (`logreg.classifiers.length === 0`) → returns `clientOnly` with `detectionProbabilityRecommendation = 1`. If the two class scores are within `0.1` (`Math.abs(scores[0] - scores[1]) < 0.1`) the margin is judged too thin and the recommendation is forced to `1`. Otherwise `detectionRatio * Math.max(1, 5 - resultCount(label))` — the Python port spells the same decay as a per-label coefficient starting at `n + 2 = 5` and decrementing to a floor of 1. Default `detectionRatio` / `renderingTypeDetectionRatio = 0.1`.
4. **Verification is differential execution, not a heuristic.** On a sampled request the browser run executes **first** and commits; then the static run executes against a *copy* of the crawler state and its transaction is **never committed**. Verdict mapping: HTTP run threw ⇒ `clientOnly`; `comparisonResult === true || 'equal'` ⇒ `static`; `false`/`'different'` ⇒ `clientOnly`; `'inconclusive'` ⇒ discarded.
5. **Default comparator.** `resultChecker` defaults to `() => true` — everything passes unless you write one. `resultComparator` resolves in three steps: your comparator; else `(a,b) => resultChecker(a) && resultChecker(b)`; else a deep dataset comparison, `resultA.datasetItems.length === resultB.datasetItems.length` plus `isDeepStrictEqual` per item. Opt-in `fullResultComparator` also matches enqueued URLs and key-value store writes (note: URLs differing only by tracking params count as different).
6. **Failure path.** HTTP attempt throws → unwrapped from `RequestHandlerError`, passed to `shouldPropagateError` (default `() => false`) → logged and falls through to the browser. HTTP succeeds but checker rejects → logs `"HTTP-only request handler returned a suspicious result for"` and increments `statistics.state.renderingTypeMispredictions`. The browser attempt has **no** fallback: `throw browserRun.error`.

Other defaults: `requestHandlerTimeoutSecs = 60`, selector helpers `timeoutMs = 5000`, `enqueueLinks` defaults to `EnqueueStrategy.SameHostname`, per-attempt write policy `requestQueue: 'deferred'`, `transactionalStorage: false` is rejected outright.

**Takeaway for our design:** the shipped answer to "does this page need JS" is *learn it per host+label, and check yourself ~10% of the time by running both and diffing the output*. That is substantially better than any static heuristic, because the ground truth ("did I get the same extracted data") is directly observable and cheap to sample.

### What Firecrawl actually does — MEASURED (vendor source, no benchmark)

Source: `raw.githubusercontent.com/firecrawl/firecrawl/main/apps/api/src/scraper/scrapeURL/index.ts` and `.../scrapeURL/engines/index.ts`.

There is **no minimum character or word count anywhere**. The entire content-quality gate is:

- `const isLongEnough = checkMarkdown.trim().length > 0;`
- `isGoodStatusCode`: `(statusCode >= 200 && statusCode < 300) || statusCode === 304`
- `const hasNoPageError = engineResult.error === undefined;`
- Verdict: `isParsedImage || isLongEnough || !isGoodStatusCode`. Failure throws `EngineUnsuccessfulError(engine)` and the waterfall advances.
- `const MAX_HTML_SIZE_FOR_MARKDOWN_CHECK = 300 * 1024; // 300KB` — above this, the markdown conversion for the quality check is skipped entirely and raw trimmed HTML is used.

Firecrawl solves the SPA problem by **defaulting to a browser and refusing to degrade**. Engine `quality` weights (higher = tried first): `exchange` 2000, `x-twitter` 1500, `index` 1000 ("index should always be tried first"), `wikipedia` 500, `fire-engine;chrome-cdp` 50, `fire-engine(retry);chrome-cdp` 45, `playwright` 20, `fire-engine;tlsclient` 10, `fetch` 5; negatives are specialty: `index;documents` −1, `chrome-cdp;stealth` −2, `retry;chrome-cdp;stealth` −5, `tlsclient;stealth` −15, `pdf`/`document`/`image` −20.

The load-bearing line: when fire-engine is available and none of `useFastMode`/`atsv`/`audio`/`video` are set, `fetch` and both tlsclient variants are **spliced out of the list**, because after CDP fails, "degrading to a plain HTTP client tends to produce bot-walled or otherwise low-quality content" — the code prefers to "fail the scrape outright." Proxy escalation is the only automatic upgrade: status 401/403/429 with `proxy === "auto"` throws `AddFeatureError(["stealthProxy"])` and restarts the whole loop. Hard ceiling `meta.abort.scrapeTimeout() ?? 300000` (5 min). Downloads (pdf/document/image) are routed through the browser engines rather than direct fetch.

### Extractor thresholds that people mistake for SPA detectors

**Mozilla Readability `isProbablyReaderable`** — source: `raw.githubusercontent.com/mozilla/readability/main/Readability-readerable.js` (note: the file is `Readability-readerable.js`, lowercase "readerable"; `isProbablyReaderable.js` 404s). Defaults `minScore: 20`, `minContentLength: 140`. Candidate selector `"p, pre, article"` plus parents of `"div > br"` merged via a `Set`. Rejection: `unlikelyCandidates` regex tested against `className + " " + id` unless `okMaybeItsACandidate` also matches; `li p` skipped. Score: `score += Math.sqrt(textContentLength - options.minContentLength)`, short-circuit `true` when `score > 20`. **The arithmetic worth knowing: a single node clears the bar at >540 characters** (`sqrt(540-140) = 20`). This is the de facto shell test most downstream tools inherit, and it is a pure text-length test — a shell with a 600-char cookie banner in a `<p>` passes.

**Trafilatura** — `settings.cfg`: `MIN_EXTRACTED_SIZE = 250`, `MIN_OUTPUT_SIZE = 1`, `MIN_EXTRACTED_COMM_SIZE = 1`, `MIN_OUTPUT_COMM_SIZE = 1`, `MIN_DUPLCHECK_SIZE = 100`, `MAX_REPETITIONS = 2`, `MIN_FILE_SIZE = 10`, `MAX_FILE_SIZE = 20000000`, `MAX_TREE_SIZE` empty, `DOWNLOAD_TIMEOUT = 30`, `MAX_REDIRECTS = 2`. `settings.py` adds `MIN_DUPLICATE_LENGTH = 50`, `DEDUPE_SCAN_CAP = 200_000`, `LRU_SIZE = 4096`, `PARALLEL_CORES = min(CPU_COUNT, 16)`.

`core.py` holds **the closest thing to a shipped content-coverage test**, in `trafilatura_sequence`:

- Baseline rescue: `if len_text < options.min_extracted_size and options.focus != "precision":` then keep the baseline only `if b_len > len_text:`
- **Recall escalation (the ratio test):** triggers on `0 < len_text < ESCALATION_MAX_LENGTH` **and** `len_text < ESCALATION_PAGE_SHARE * len(html2txt(tree))`, with `ESCALATION_MAX_LENGTH = 3000` and `ESCALATION_PAGE_SHARE = 0.2`.
- Fallback arbitration: justext wins `if j_len > r_len and j_len > ESCALATION_JUSTEXT_RATIO * len_text:` (`= 2.0`); else the recall retry is accepted `elif r_len >= options.min_extracted_size and r_len > ESCALATION_ACCEPT_RATIO * len_text:` (`= 1.5`).
- Final discard in `bare_extraction`: `if len_text < options.min_output_size and len_comments < options.min_output_comm_size:` → `ValueError` → `None`.

Note precisely what `ESCALATION_PAGE_SHARE` compares: extracted text against **`html2txt(tree)`**, i.e. the *text* of the whole page, **not** the HTML source length. So it is a content-to-*page-text* ratio, not content-to-markup. Nothing in Trafilatura measures markup volume.

**crawl4ai `PruningContentFilter`** — source: `raw.githubusercontent.com/unclecode/crawl4ai/main/crawl4ai/content_filter_strategy.py`. This is the only shipped **text-to-markup ratio** found, and it is used for boilerplate pruning, not JS detection. `threshold = 0.48`, `threshold_type = "fixed"`, `min_word_threshold = None`. Metric weights summing to 1.0: `text_density: 0.4`, `link_density: 0.2`, `tag_weight: 0.2`, `class_id_weight: 0.1`, `text_length: 0.1`. Raw measures: `text_len = len(node.get_text(strip=True))`, `tag_len = len(node.encode_contents().decode("utf-8"))`, so `density = text_len / tag_len` — that *is* content-to-markup. Link density is inverted: `1 - (link_text_len / text_len)`. Length term is `math.log(text_len + 1)`. Tag weights: article 1.5, h1 1.2, h2 1.1, p/section/h3 1.0, h4 0.9, h5 0.8, h6 0.7, div/li/ul/ol 0.5, span 0.3; default lookup 0.5. Class/ID penalty −0.5 each for class or id matching `r"nav|footer|header|sidebar|ads|comment|promo|advert|social|share"`. Fixed rule `should_remove = score < self.threshold`; dynamic mode multiplies the threshold by 0.8 (tag importance > 1), 0.9 (text ratio > 0.4), 1.2 (link ratio > 0.6). Word-count short circuit approximates words as `text.count(" ") + 1` and returns `-1.0  # Guaranteed removal`. Separate BM25 filter uses `bm25_threshold = 1.0`.

**Defuddle** — `raw.githubusercontent.com/kepano/defuddle/main/src/constants.ts` contains exactly one numeric constant, `MOBILE_WIDTH = 600`. No ratios, no length floors, no score cutoffs. Two comments prove thresholds exist elsewhere: paywalled paragraphs are preserved because removing them "would trigger a low-word-count retry with partial selectors disabled" (implies a word floor + two-pass retry), and `CONTENT_ELEMENT_SELECTOR` exists to shield content "from removal by scoring, content pattern detection, and other heuristics." Structurally notable: `ENTRY_POINT_ELEMENTS` terminates in `'body'`, annotated as ensuring "there is always a match" — **Defuddle is architecturally incapable of reporting extraction failure**, which makes it a poor shell detector by construction. The actual thresholds live in the module consuming `PARTIAL_SELECTORS_REGEX` / `CONTENT_ELEMENT_SELECTOR`; that file was not located.

### The manual-choice camp

**Jina Reader** (`jina.ai/reader/` via r.jina.ai): `X-Engine` takes `direct` ("a plain HTTP fetch and is the fastest"), default ("renders the page in a headless browser so client-side JavaScript executes before extraction"), or `cf-browser-rendering` ("an experimental Cloudflare-backed renderer"). **No auto-detection is documented.** Supporting knobs: `X-Timeout`, `X-Wait-For-Selector`, `X-Respond-Timing`, `X-With-Iframe`, `X-With-Shadow-Dom`; stream mode via `Accept` is "recommended if standard mode returns incomplete content." Published average latency for `r.jina.ai` is **7.9s**; direct fetch of a simple page lands "in a few hundred milliseconds" while the browser engine "usually lands in the low seconds." 5-minute repeat-request cache.

**Zyte API** (`docs.zyte.com/zyte-api/usage/http.html`): also fully manual — `httpResponseBody: true` for plain HTTP, a separate browser request for `browserHtml`. No ML model, no "request mode", no auto-selection documented. Explicit warning that HTTP responses "do not reflect HTML content rendered by a web browser that executes JavaScript code," and that switching between the two "can break your existing parsing code" because browser HTML is HTML5-normalized. **This contradicts the folk belief that Zyte auto-picks; per their own docs it does not.**

**spider-rs** (`README.md`): claims the behavior without disclosing the heuristic — `crawl_smart()` "runs HTTP-first and launches headless Chrome only when a page needs JavaScript." The README never says what signal triggers it. **CLAIMED**; would need the Rust source to verify. (Separate, unrelated concept in the same README: `SpiderCloudMode::Smart` is proxy-then-unblocker escalation, not rendering.)

### Empty search

arXiv `all:"JavaScript rendering" AND all:crawl` returned **`totalResults = 0`**. There appears to be no arXiv literature on client-side-render detection for crawlers. A real gap in the published record, not attributable to phrasing alone (varied once, still nothing useful).

---

## Q2 — Compile-the-flow: solve once with an LLM, replay deterministically

### Answer

**Two vendors ship it today with genuinely different designs, and one 2026 paper gives the number that matters.** Skyvern compiles a solved run into reusable *code* and auto-falls-back to the agent on failure; Stagehand/Browserbase caches *results* server-side keyed on instruction+page-content+URL and falls back to full inference when the recorded selector stops resolving. LaVague, the open-source flagship for "LLM emits Selenium/Playwright code," is dormant. The academic line runs AWM → SkillWeaver → WALT → ReUseIt → AutoTailor, and **AutoTailor is the only source found that isolates the value of the fallback**: compiled-only 60.1% correctness vs compiled+LLM-fallback 90.6% vs plain LLM agent 87.5%, at 57.8% lower token cost. **Confidence: strong** on mechanisms; **moderate** on the numbers, which are single-paper and mostly vendor/author-measured.

### Shipped: Skyvern "code caching" — MEASURED (vendor), no numbers published

Source: `www.skyvern.com/docs/developers/features/code-caching` (via r.jina.ai; `docs.skyvern.com/running-tasks/caching` 404s — the domain moved).

- After a successful run Skyvern "records the actions it took and generates reusable code from them." Then: "Later runs can execute that cached code directly, skipping LLM inference and screenshot analysis entirely," making runs "faster, cheaper, and deterministic."
- Config flag is `run_with`: `"agent"` records, `"code"` replays "just the recorded action sequence replaying against the page."
- **Granularity.** Tasks cache the whole action sequence. Agents cache **per block**: "Each block that successfully executes gets its own cached script," so a partially-cached agent still benefits. Coverage accumulates — "Run 1 covers branch A, run 2 covers branch B."
- **Never cached:** "conditional evaluation blocks, wait blocks, and code blocks always run live," because they depend on runtime state. This is the right call and worth copying: the parts of a flow that branch on live state are exactly the parts a compiled script cannot safely freeze.
- **Drift handling.** "If the cached code fails because a page changed, Skyvern falls back to the agent automatically and regenerates the cache." Named triggers: layout changes, new fields, missing elements.
- **Cache key: undocumented.** Scoping is given (per run for tasks, per block for agents) but no identifier, hashing scheme, or invalidation rule beyond failure-triggered regeneration. Biggest gap in their docs for reasoning about false cache hits.

### Shipped: Stagehand / Browserbase result caching — MEASURED (vendor), no numbers published

Source: `docs.stagehand.dev/best-practices/caching` (via r.jina.ai).

Correction to a common assumption (and to the task brief): **this is a server-side result cache, not a local "observe() → persist XPath → replay" pattern.** The page states there is "nothing to install, no cache files to manage, and no state to keep in sync across machines," and never mentions `observe()` returning selectors you persist yourself.

- `cache: true` makes Browserbase cache every `act()`, `observe()`, and `extract()` server-side. **Requires a Browserbase browser** — "on a local browser the `cache` option has no effect and every call runs inference."
- **Cache key:** "Browserbase builds the cache key from the instruction, page content, and the options you pass." It "deliberately leaves out model configuration, so switching models does not invalidate your cache." "The page URL factors into the cache key."
- **Replay:** "On a cache hit, the server returns the response directly with no LLM inference and no token cost."
- **Determinism + healing, verbatim:** "Stagehand replays a cached `act()` result deterministically with self-healing turned off."
- **Drift detection, verbatim:** "If the recorded selector no longer resolves, Stagehand falls back to full inference." And "If the page content or structure changes, the action won't get a cache `HIT` and Stagehand calls the LLM." Because page content is in the key, most drift manifests as a **miss**, not a failure.
- `cache: { threshold: 2 }` — "The threshold controls how many times Browserbase must see an identical result before the cache starts serving it."
- Inspect with `result.metadata.cache.status` → `"HIT" | "MISS" | "DISABLED"`, plus `missReason`.
- Bypasses: `locator`-scoped and `ignoreLocators` calls "currently bypass the server-side result cache". `variables` travel with the request, so differing values miss — docs advise disabling cache for calls carrying credentials.
- Fail-soft: "If the cache is unreachable, Stagehand falls back to normal inference rather than failing your run."

**Caveat flagged by the lane:** only the caching docs page was read, not Stagehand's source. A client-side `selfHeal` option may exist and simply not be documented there. Verify against `github.com/browserbase/stagehand` source before relying on the absence.

### Dormant: LaVague — MEASURED (ind., repo metadata)

`api.github.com/repos/lavague-ai/LaVague`: 6,388 stars, 571 forks, 105 open issues, Apache-2.0, created 2024-02-26, **last push 2025-01-21**, `archived: false`. The `updated_at` of 2026-09-22 reflects metadata (stars) only. ~20 months without a commit. Not formally retired, but treat it as dead.

**Playwright codegen** is the non-LLM baseline for this category — record human actions, emit a script, no repair loop, no model. Labelled background knowledge, not a sourced finding.

### Published work — the lineage and the numbers

All IDs verified via `export.arxiv.org` `id_list`.

| ID | Title | Result | Label |
|---|---|---|---|
| 2409.07429 | Agent Workflow Memory | "+24.6% and 51.1% relative success rate on Mind2Web and WebArena"; online variant beats baselines by 8.9–14.0 absolute points | MEASURED (vendor) |
| 2504.07079 | SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills | relative gains "31.8% and 39.8%"; transferred APIs lift weaker agents "up to 54.3%" | MEASURED (vendor) |
| 2510.01524 | WALT: Web Agents that Learn Tools | **no numbers in abstract**, "higher success with fewer steps" | CLAIMED |
| 2510.14308 (v2) | ReUseIt: Synthesizing Reusable AI Agent Workflows for Web Automation | success **24.2% → 70.1%**, 15 tasks, 9 users, 2 baselines; DOI 10.1145/3742413.3789083 | MEASURED (vendor), n=15 tasks |
| 2609.13548 | AutoTailor: Automatic, User-Aligned Capability Selection and Adaptation for Web Agents | see below | MEASURED (vendor) |
| 2603.20340 (v3) | ContractSkill: Repairable Contract-Based Skills for Multimodal Web Agents | mechanism only | CLAIMED |
| 2607.24167 | Falsifiable Commitment Planning for Self-Correcting Web Agents | "plan-test-repair loop", scope-aware repair | CLAIMED |
| 2606.17645 | Beyond Domains: Reusing Web Skills via Transferable Interaction Patterns | cuts LLM actions 8–10% | MEASURED (vendor) |
| 2605.23939 | DRIVE: Modeling Skills at the Reasoning and Interaction Levels | 52.8% on WebArena | MEASURED (vendor) |
| 2606.04391 | Online Skill Learning for Web Agents via State-Grounded Dynamic Retrieval | "dual text-code representation" | CLAIMED |
| 2603.07024 | Enhancing Web Agents with a Hierarchical Memory Tree | stages as "reusable semantic subgoals" with pre/post-conditions | CLAIMED |
| 2604.13318 (v2) | WebXSkill: Skill Learning for Autonomous Web Agents | parameterized skills indexed in a URL graph | CLAIMED |
| 2510.10049 | ALLOY: Generating Reusable Agent Workflows from User Demonstration | manual editing rather than automated healing | CLAIMED |
| 2609.19523 | EconSkills: Skill Transfer and Retrieval for Web Agents on Live Economic Data | parameterized SOPs with "verification checks, and recovery steps" | CLAIMED |

**AutoTailor (2609.13548) is the most useful single result in this lane**, because it separates the three conditions that matter. Offline it "converts web trajectories into parameterized browser-automation programs" (exposed as MCP APIs), filtering 1,283 unrefined APIs → 87 → a final 33-API set. Measured on **106 WebArena Postmill tasks**:

- compiled APIs **with** ReAct fallback: **90.6% correctness**
- plain ReAct agent (no compiled APIs): **87.5%**
- compiled APIs **without** ReAct fallback: **60.1%**
- token cost **−57.8%**, latency **−29.4%**, request-token usage **−94.9%**

Compiling buys ~58% token reduction and ~29% latency reduction for +3.1 points of correctness — but **only if the model stays in the loop**. Strip the fallback and you lose 30.5 points, landing well below the uncompiled baseline. This is the quantitative case for "compile the flow, keep the model as the exception handler." Single paper, single site (Postmill), n=106 — directional, not settled.

### How drift is detected in practice — synthesis

1. **Selector fails to resolve** → full inference. Stagehand (shipped). Cheapest, catches hard breaks only.
2. **Cached code throws** → re-run agent, regenerate cache. Skyvern (shipped).
3. **Content-hash miss.** Stagehand puts page content in the cache key, so most drift surfaces as a `MISS` rather than a failure — *preventive* rather than reactive.
4. **Execution guards / assertions embedded in the synthesized workflow.** ReUseIt synthesizes from both successful *and failed* runs specifically to place guards so agents "detect and fix errors" and escalate; that is where 24.2% → 70.1% comes from.
5. **Pre/post-conditions and contracts.** HMT attaches pre/post-conditions to stages; ContractSkill makes the artifact "deterministically verifiable" supporting "fault localization, and minimal local repair"; FCPAgent pairs each subgoal with confirming *and falsifying* evidence.
6. **Capability-set pruning.** AutoTailor's Dynamic Reselection prunes dead APIs at runtime.

**The gap nobody covers: semantic drift.** Every mechanism above fires when a selector *breaks*. None detects the case where the selector still resolves, the click still lands, and the page has silently changed meaning (button relabeled, form reordered, currency switched, A/B variant served). Stagehand's content-hash key is the closest accidental defense. A cheap post-condition assertion on extracted *values* — not on selector existence — is the differentiating move, and it is unclaimed in both the shipped tools and the papers read.

---

## Q3 — Observation space: accessibility tree vs DOM vs screenshot vs code

### Answer

1. **Element ordering matters more than modality.** Shuffling the element list costs GPT-4V ~50% of its relative performance on VisualWebArena (74.07% → 37.04%), a larger swing than any modality substitution measured anywhere. (2409.12089)
2. **Observation "optimization" that wins is not compression.** AgentOccam tripled WebArena success (14.2% → 44.2% dev set) while *increasing* observation tokens 2210 → 2931 per step. Savings came from shrinking the **action** space, not the observation. (2410.13825)
3. **Pixels alone are not sufficient for frontier general models, and text alone is expensive.** Removing the text element list drops Gemini-1.5 from 64.20% to **3.70%**; removing the screenshot drops it to 46.30%. (2409.12089) Conversely, when pixels and the a11y tree disagree, models follow the **stale tree** on up to 0.88 of probes with self-recovery ≤0.03. (2607.04334)
4. **Code/API-mediated access nearly triples success but costs ~12x per task.** WebArena: browsing 14.8% @ $0.1/task, API 29.2% @ $1.2, hybrid 38.9% @ $1.4. (2410.16464)

**Confidence: strong** on the numbers (read from tables directly); **moderate** on generalization — nearly every ablation is single-paper, GPT-4-era, on WebArena/VWA.

### Correction to a widely repeated claim

**WebArena (2307.13854) contains no observation-modality ablation.** The paper names three possible formats — "the raw web page HTML, composed of a Document Object Model (DOM) tree," "a screenshot, a pixel-based representation," and "the accessibility tree" — then states: "We use an accessibility tree with element IDs as the observation space." Every baseline uses that one format. The only ablations are chain-of-thought and the unachievable-task hint. Table 2 (all a11y tree):

| CoT | UA hint | Model | SR | SR-AC | SR-UA |
|---|---|---|---|---|---|
| ✓ | ✓ | TEXT-BISON-001 | 5.05 | 4.00 | 27.78 |
| ✗ | ✓ | GPT-3.5 | 6.41 | 4.90 | 38.89 |
| ✓ | ✓ | GPT-3.5 | 8.75 | 6.44 | 58.33 |
| ✓ | ✓ | GPT-4 | 11.70 | 8.63 | 77.78 |
| ✗ | ✗ | GPT-3.5 | 5.10 | 4.90 | 8.33 |
| ✓ | ✗ | GPT-3.5 | 6.16 | 6.06 | 8.33 |
| ✓ | ✗ | GPT-4 | **14.41** | 13.02 | 44.44 |
| – | ✓ | Human | **78.24** | 77.30 | 100.00 |

30-step cap, temp 1.0, top-p 0.9, GPT-3.5-TURBO-16K-0613 / GPT-4-0613 / TEXT-BISON-001. No token lengths quantified anywhere; the paper only asserts a11y trees are "more compact than the DOM representation." **If a report cites WebArena for an a11y-vs-DOM-vs-screenshot comparison, that citation is wrong.** MEASURED (ind. — verified against source).

### VisualWebArena (2401.13649), Table 3 — the real modality ablation

n = 910 tasks across Classifieds / Reddit / Shopping. Success rate %:

**Text-only (accessibility tree)**
| Model | Cls | Reddit | Shop | Overall |
|---|---|---|---|---|
| LLaMA-2-70B | 0.43 | 1.43 | 1.29 | 1.10 |
| Mixtral-8x7B | 1.71 | 2.86 | 1.29 | 1.76 |
| Gemini-Pro | 0.85 | 0.95 | 3.43 | 2.20 |
| GPT-3.5 | 0.43 | 0.95 | 3.65 | 2.20 |
| GPT-4 | 5.56 | 4.76 | 9.23 | **7.25** |

**Accessibility tree + captions:** LLaMA-2-70B+BLIP-2-T5XL 0.66 · Mixtral-8x7B+BLIP-2 1.87 · GPT-3.5+LLaVA-7B 2.75 · GPT-3.5+BLIP-2 2.97 · Gemini-Pro+BLIP-2 3.85 · **GPT-4+BLIP-2 12.75**

**Image + captions + a11y tree**
| Model | Cls | Reddit | Shop | Overall |
|---|---|---|---|---|
| IDEFICS-80B-Instruct | 0.43 | 0.95 | 0.86 | 0.77 |
| CogVLM | 0.00 | 0.48 | 0.43 | 0.33 |
| Gemini-Pro | 3.42 | 4.29 | 8.15 | 6.04 |
| GPT-4V | 8.12 | 12.38 | 19.74 | **15.05** |

**Image + captions + Set-of-Marks**
| Model | Cls | Reddit | Shop | Overall |
|---|---|---|---|---|
| IDEFICS-80B-Instruct | 0.85 | 0.95 | 1.07 | 0.99 |
| CogVLM | 0.00 | 0.48 | 0.43 | 0.33 |
| Gemini-Pro | 3.42 | 3.81 | 7.73 | 5.71 |
| GPT-4V | 9.83 | 17.14 | 19.31 | **16.37** |

Human: 91.07 / 87.10 / 88.39 / **88.70**. Appendix Table 5 (later models, SoM): GPT-4o **19.78**, Gemini-Pro-1.5 11.98, Gemini-Flash-1.5 6.59; caption-augmented Llama-3-70B-Instruct 9.78.

Beyond the GPT-4-family ladder (7.25 → 12.75 → 15.05 → 16.37):
- **SoM only works for the model trained to use it.** Gemini-Pro *falls* 6.04 → 5.71 with SoM. CogVLM flat at 0.33. IDEFICS 0.77 → 0.99. Authors: "only GPT-4V demonstrates the SoM grounding ability." SoM is not a free modality upgrade.
- **Shopping regresses under SoM** (19.74 → 19.31) while visually denser sites gain (Reddit 12.38 → 17.14). Modality choice is site-dependent, not globally optimal.

### The Impact of Element Ordering (2409.12089) — the strongest causal result

**Critical condition:** the VWA results below are on a **pre-filtered subset of previously-successful "easy" tasks**, which is why absolutes far exceed the 15-16% in the VWA paper. All ordering ablations use one multimodal setting (screenshot + SoM + text list). Default ordering = "pre-order traversal of the DOM tree."

**Ordering, VisualWebArena (success rate %)**
| Ordering | Gemini 1.5 | GPT-4V | Llama3-70B |
|---|---|---|---|
| Pre-order (default) | 64.03 | **74.07** | 27.79 |
| Random | 37.04 | 37.04 | 20.37 |
| Raster | 38.88 | 53.70 | 29.63 |
| t-SNE | 44.44 | 61.11 | 24.07 |

Random ordering "decreases performance in VisualWebArena by 50% and 42% relative performance for GPT-4v and Gemini-1.5 respectively."

**Observation-type ablation, VWA, ordering held fixed**
| Screenshot | SoM | Text | Gemini 1.5 | GPT-4V |
|---|---|---|---|---|
| ✓ | ✓ | ✓ | 64.20 | 74.07 |
| ✗ | ✗ | ✓ | 46.30 | 38.89 |
| ✓ | ✗ | ✓ | 50.00 | not run |
| ✓ | ✓ | ✗ | **3.70** | 38.89 |

**Dropping the text element list costs Gemini 60.5 points (64.20 → 3.70)** while dropping the screenshot costs 17.9. For GPT-4V the two ablations are equal (38.89 either way) — it degrades gracefully to vision-only where Gemini collapses. Never assume a pixels-only observation transfers across backbones.

**OmniACT (no DOM exists, so random is the baseline; unweighted action score %)**
| Element source | Ordering | Gemini-1.5 | GPT-4v | Llama3-8B |
|---|---|---|---|---|
| Human annotations | Random | 57.29 | 61.52 | 28.67 |
| | Raster | 61.04 | **65.88** | 33.65 |
| | t-SNE | 59.17 | 62.11 | 31.99 |
| Detected (Faster-RCNN) | Random | 39.59 | 44.63 | 18.88 |
| | Raster | 45.21 | 47.38 | 21.58 |
| | t-SNE | 47.16 | **49.18** | 24.61 |

Raster wins on clean human annotations; t-SNE wins once elements are noisily detected. Detection pipeline: Faster-RCNN (detectron2, ResNet-50, 200k iters) on "67,530 interactable elements over 1468 Common Crawl webpages" + EasyOCR. Detected elements yield roughly **double** the element count of human annotations, and scores drop accordingly (Gemini t-SNE 59.17 → 47.16).

End-to-end OmniACT (action / sequence score): prior baseline GPT-4 pyautogui **11.60 / 32.75**; Gemini-1.5 code output 16.53 / 21.67; Gemini-1.5 high-level no screenshot 22.29 / 29.42; with screenshot 22.86 / 28.91; Llama-8B 18.64 / 26.22; **GPT-4v high-level + screenshot 23.34 / 30.47**. The 23.34 vs 11.60 backs "more than two times as many tasks," but bundles four simultaneous changes — **the ordering contribution alone is not isolated end-to-end.**

**Two internal inconsistencies in this paper**, reported rather than papered over: GPT-4V random ordering appears as **44.44%** in the attribute-ablation table and **37.04%** in the ordering table; the full-representation Gemini baseline appears as both **64.03%** and **64.20%**. Neither is reconciled. Treat the ±7-point band on random-ordering as real uncertainty.

### AgentOccam (2410.13825) — the token numbers, and the surprise

Observation tokens per step (GPT-2 tokenizer), full WebArena:

| Config | All | Shopping | Shop-Admin | GitLab | Map | Reddit | Multisite |
|---|---|---|---|---|---|---|---|
| Vanilla | 2210.2 | 2272.1 | 2460.2 | 2199.1 | 1883.2 | 2132.4 | 1751.0 |
| ↓Actions | **1652.0** | 1644.7 | 2133.1 | 1981.3 | 912.0 | 1081.2 | 1296.8 |
| +X Scrolling | 3376.2 | 3148.0 | 5403.7 | 3364.9 | 1378.1 | 2603.6 | 1975.5 |
| +Obs Opt. | 2891.1 | 1722.5 | 4791.7 | 2560.8 | 1476.4 | 3332.3 | 1619.4 |
| +History | 3051.3 | 1802.6 | 5140.2 | 3153.3 | 862.1 | 3156.1 | 2030.3 |
| AgentOccam | 2930.9 | 1634.2 | 4920.7 | 3126.8 | 1056.0 | 3697.8 | 1282.5 |

Success rate, 190-task dev set, GPT-4-Turbo:

| Config | All | Shopping | Shop-Admin | GitLab | Map | Reddit | Multisite |
|---|---|---|---|---|---|---|---|
| Vanilla | 14.2 | 16.7 | 12.2 | 14.6 | 17.2 | 9.5 | 10.0 |
| ↓Actions | 25.8 | 22.9 | 24.4 | 34.2 | 31.0 | 19.1 | 10.0 |
| +X Scrolling | 30.0 | 29.2 | 29.3 | 36.6 | 24.1 | 38.1 | 10.0 |
| +Obs Opt. | 34.7 | 37.5 | 34.2 | 22.0 | 41.4 | 57.1 | 10.0 |
| +History | 36.8 | 39.6 | 34.2 | 36.6 | 44.8 | 38.1 | 10.0 |
| AgentOccam | **44.2** | 45.8 | 46.3 | 48.8 | 41.4 | 47.6 | 10.0 |

Gemini-1.5-Flash ladder: 11.6 → 23.2 → 24.2 → 30.0 → 32.1 → **33.7**. Full 812-task WebArena: WebArena-replication 16.5, SteP-replication 33.3, AWM 35.5, WebPilot 37.2, **AgentOccam 43.1**, AgentOccam+SteP 41.1, **AgentOccam+Judge 45.7**. Avg steps/task: Vanilla 6.2 → AgentOccam 9.0.

**The surprise: 3.1x the success rate (14.2 → 44.2) for 1.33x the observation tokens (2210 → 2931).** The only step that *reduced* tokens was pruning the action space (2210 → 1652), and that single step also delivered the largest success jump of the ladder (+11.6 points). Everything after spends tokens to buy accuracy. **Anyone selling "compress the observation to save tokens" is optimizing the wrong axis according to the best-documented ablation available.**

What AgentOccam does to the tree: merges descriptive nodes into interactive nodes carrying the same label; converts tables/lists to Markdown so `columnheader`/`gridcell` tokens disappear; strips IDs and `[required: False]` attributes; marks "pivotal" nodes and retains only those plus "ancestor nodes... sibling nodes", collapsing the rest to "Other invisible node"; and on `branch` drops steps belonging to earlier plans (call-stack scoping).

Final action space — 8 actions: `click [id]`, `type [id] [content]`, `go_back`, `go_home`, `note [content]`, `stop [answer]`, `branch [id] [intent]`, `prune [id] [reason]`. **Removed from WebArena's original set: `noop`, `hover`, `press`, `scroll`, `tab_focus`, `new_tab`, `tab_close`, `go_forward`, `goto`.** Observed action counts: click 4720, type 1159, stop 769, go_back 339, note 197, prune 47, go_home 42, branch 34.

### Code-mediated access: Beyond Browsing (2410.16464) — MEASURED (vendor)

GPT-4o under the OpenHands framework. WebArena success rate %:

| Agent | GitLab | Map | Shopping | Shop Admin | Reddit | Multi-site | **Avg** |
|---|---|---|---|---|---|---|---|
| Browsing only | 12.8 | 20.2 | 10.2 | 22.0 | 10.4 | 10.4 | **14.8** |
| API only | 43.9 | 45.4 | 25.1 | 20.3 | 18.9‡ | 8.3 | **29.2** |
| Hybrid | 44.4 | 45.9 | 25.7 | 41.2 | 51.9‡ | 16.7 | **38.9** |

‡ Reddit uses APIs the authors added themselves. Before adding them: API-only Reddit was **9.4% with 18 endpoints** vs **18.9% with 31 endpoints** — a clean demonstration that API-agent performance is a function of **API surface, not agent capability**.

Comparison rows: WebArena baseline 12.3, AutoEval 26.9, AWM 35.5, SteP 36.5 (authors flag SteP as using WebArena-specific prompts "while other agents are task-agnostic").

**Steps and dollar cost per task (Table 7):**

| Agent | GitLab | Map | Shopping | Shop Admin | Reddit | Multi | **Avg** |
|---|---|---|---|---|---|---|---|
| Browsing steps / $ | 9.4 / 0.2 | 8.0 / 0.1 | 7.3 / 0.1 | 7.0 / 0.2 | 11.1 / 0.1 | 7.5 / 0.1 | **8.4 / 0.1** |
| API steps / $ | 7.0 / 1.7 | 6.6 / 1.1 | 8.2 / 1.0 | 8.4 / 1.1 | 8.8 / 0.6 | 7.7 / 1.6 | **7.8 / 1.2** |
| Hybrid steps / $ | 8.1 / 2.0 | 9.4 / 1.7 | 8.2 / 1.3 | 9.0 / 1.4 | 7.8 / 0.6 | 8.0 / 1.9 | **8.5 / 1.4** |

**API access costs ~12x per task in dollars while taking fewer steps.** No raw token counts are given, but the paper attributes the spend to endpoint documentation volume — for GitLab "the agent is provided with 988 available APIs, leading to much longer prompts," versus browsing needing only interface instructions and ~14 actions. Reddit, with the shortest documentation, is cheapest. Sites above 100 endpoints use two-stage retrieval via a `get_api_documentation` tool rather than inlining docs; Map (53) and Reddit (31) get full docs inline.

API availability per site as the authors rate it: GitLab 988 endpoints (good), Map 53 (good), Shopping/Shop Admin 556 shared (fair), Reddit 31 (poor).

Efficiency detail: API-solvable tasks needed on average **2.1 API calls**, but total agent steps averaged 7.8 — the rest went to documentation lookups, error recovery, and verification. Hybrid action mix: browsing-only 14.3% of tasks @ 25.0% accuracy; API-only 8.0% @ 40.0%; both 77.7% @ **42.0%**.

**Design implication:** code-mediated access is the single biggest accuracy win in this lane (+24.1 absolute over browsing), but it converts a browsing problem into a *tool-documentation retrieval* problem, and the retrieval is what costs money. The leverage is compiling a minimal API surface (cf. AutoTailor's 1,283 → 33) rather than paging full OpenAPI specs into context.

### Bandwidth/latency accounting: Sema (2604.20940) — MEASURED (vendor)

Best source found for actual transport cost of observations, framed in Shannon-Weaver Level A/B terms:

- **screenshot upload accounts for >60% of end-to-end action latency**
- a hybrid screen representation (lossless a11y-tree/OCR text + compact visual tokens) gives **130–210x screenshot uplink reduction**
- accuracy stays **within 0.7 percentage points** of the raw-screenshot baseline
- (companion audio result: voice transport sends "43-64x more data than needed")

The number to cite for "text observations are two orders of magnitude cheaper on the wire than pixels, at negligible accuracy cost" — but it is the authors' own measurement, single paper, and the 0.7pp figure is not broken out by benchmark in the abstract.

### Channel conflict: Do GUI Agents Believe Their Eyes? (2607.04334) — MEASURED (ind.)

The most decision-relevant reliability result on observation design. Formalizes "visual state reliance" and a "Perception-Fusion Gap" using **735 paired single-channel probes** across models from **4 vendors**, with **225 zero-edit divergences** (channels disagreeing without any intervention):

- when pixels and serialized structure (DOM/a11y tree) disagree, models **follow the outdated structure on up to 0.88 of probes**
- **self-recovery rate ≤ 0.03**
- the failure **triggers at the 1st step**
- a white-box ablation traces the effect to **a single copied structural value**

**Practical reading:** giving an agent both a screenshot and an a11y tree does not make it robust — it makes it confidently wrong whenever the tree is stale, which is exactly what happens on SPAs after a client-side re-render. **This connects Q1 and Q3: the SPA-shell problem does not end when the browser renders.** A tree snapshot taken before hydration completes will be *believed over the pixels*.

### Vision-only and tree-quality datapoints

- **MolmoWeb (2604.08516)** — fully open 4B/8B screenshot-only web agents "requiring no access to HTML, accessibility trees, or specialized APIs." WebVoyager **pass@1 78.2% / pass@4 94.7%**; Online-Mind2Web **pass@1 35.3% / pass@4 60.5%**. Trained on "over 100K synthetic task trajectories" + 30K+ human demonstrations. MEASURED (vendor). Cross-system comparison, not a controlled input ablation.
- **BrowserForge (2608.24848)** — 203,238 trajectories from distinct sites via parallel sandboxes; a11y tree used as a *synthesis-time* signal only, released agent "acts purely from the screenshot"; Online-Mind2Web **25.66% → 33.33%**. MEASURED (vendor).
- **Screen2AX (2507.16704)** — builds tree-structured macOS accessibility metadata from a single screenshot, **77% F1** tree reconstruction, and reports **"a 2.2x performance improvement over native accessibility representations"**. MEASURED (vendor). Uncomfortable implication: the platform-native a11y tree is often *worse* than one inferred from pixels, undercutting the assumption that a11y trees are ground truth.
- **ShowUI (2411.17465)** — UI-guided visual token selection: **75.1% zero-shot screenshot grounding, 33% fewer visual tokens, 1.4x speedup**. MEASURED (vendor).
- **UGround (2410.05243 v3)** — 10M elements over 1.3M screenshots; beats prior grounding models by up to **20% absolute** and outperforms agents that additionally consume text input, across six benchmarks. Argues directly against HTML/a11y-tree inputs on noise, incompleteness, and overhead grounds. MEASURED (vendor).
- **MAG (2607.10079 v3)** — ablates Set-of-Mark vs raw pixel coordinates; GRPO lifts a 9B agent from **6.9% to 13.2%**. MEASURED (vendor).
- **Region4Web (2605.07134)** — restructures the a11y tree into "functional regions" as a persistent PageDigest; criticizes prior work for treating "observation at the same element-level granularity as the action space." **No numbers in the abstract.** CLAIMED.

### Benchmark context for calibrating any of the above

- **WebVoyager (2401.13919)** — 59.1% task success; auto-evaluation 85.3% agreement with human raters. MEASURED (vendor).
- **OSWorld (2404.07972)** — 369 tasks; humans finish "over 72.36%", best model **12.24%**. MEASURED (vendor).
- **Mind2Web (2306.06070 v3)** — "over 2,000 open-ended tasks collected from 137 websites spanning 31 domains." No accuracy figures in the abstract.
- **An Illusion of Progress? (2504.01382 v4, COLM 2025)** — Online-Mind2Web: **300 realistic tasks across 136 websites**, LLM-as-a-Judge at ~**85% agreement** with human judgments. Thesis is that earlier reported results reflected "over-optimism" about agent competency. **Cite this whenever quoting a WebArena number as evidence of real-world capability.** MEASURED (ind.).
- **WebMall (2508.13024 v3, SIGIR 2026)** — offline four-shop benchmark from Common Crawl; eight agent configurations differing in "observation space, availability of short-term memory, and the employed LLM"; top performers stayed **under 65% completion** on the hardest categories. Possible additional modality ablation in the body; not read past the abstract. MEASURED (vendor).

### Q3 synthesis — what to act on

1. **Order the element list by DOM pre-order, always.** Free, and worth ~37 points to GPT-4V on the easy-task subset. (2409.12089)
2. **Keep a text element list in the observation even for vision-capable models.** Gemini-class models collapse to 3.70% without it.
3. **Cut the action space before touching the observation.** Fewest tokens *and* the biggest single accuracy gain in the AgentOccam ladder.
4. **Do not sell observation compression as a token-saving measure.** The winning configuration uses 33% *more* observation tokens than vanilla.
5. **Prefer API/code paths where an API surface exists, but compile a minimal surface.** 988 endpoints of docs is where the 12x cost comes from; AutoTailor's 33-API set with a model fallback got 90.6% at −57.8% tokens.
6. **Never trust a serialized tree taken before hydration settles.** Models follow the stale tree over the pixels on up to 0.88 of conflicting probes and essentially never self-correct (≤0.03).
7. **Report pass@1, not pass@4.** MolmoWeb's WebVoyager figure swings 78.2% → 94.7% on that choice alone.

---

## Q4 — Prompt injection in fetched content: what has been measured to hold

### Answer

**Exactly one defense has a measured near-zero attack success rate against a real attack corpus, and its own authors say the problem is not solved.** CaMeL drove 949 AgentDojo attacks to 0 successes on three backbones, at 7 points of utility (77% vs 84%) and ~2.8x input tokens — and the paper enumerates three side channels it does not close plus a data-flow-becomes-control-flow escalation its authors weaponize. Most instructive negative result: **Spotlighting, which its own paper reports as cutting ASR from >50% to <2%, only moves AgentDojo's targeted ASR from 47.69% to 41.65%.** **Confidence: strong.**

### AgentDojo (2406.13352) — the measurement substrate

97 realistic tasks, 629 security test cases. The results page states up front that it is **"not a leaderboard"** — not every model was tested with every attack/defense, so cross-row comparison is not apples-to-apples.

**No defense, `important_instructions` attack** — MEASURED (ind.):

| Model | Utility | Utility under attack | Targeted ASR |
|---|---|---|---|
| claude-3-7-sonnet-20250219 | **88.66%** | 77.27% | 7.31% |
| claude-3-5-sonnet-20241022 | 79.38% | 72.50% | **1.11%** |
| claude-3-5-sonnet-20240620 | 79.38% | 51.19% | 33.86% |
| claude-3-opus-20240229 | 68.04% | 52.46% | 11.29% |
| claude-3-sonnet-20240229 | 53.61% | 33.23% | 26.71% |
| claude-3-haiku-20240307 | 39.18% | 33.39% | 9.06% |
| gpt-4-0125-preview | 65.98% | 40.70% | **56.28%** |
| gpt-4-turbo-2024-04-09 | 64.95% | 54.05% | 28.62% |
| gpt-4o-mini-2024-07-18 | 68.04% | 49.92% | 27.19% |
| gpt-3.5-turbo-0125 | 35.05% | 34.66% | 10.33% |
| gemini-2.0-flash-001 | 43.30% | 39.75% | 20.83% |
| gemini-1.5-pro-002 | 61.86% | 47.06% | 17.01% |
| gemini-1.5-pro-001 | 46.39% | 28.93% | 28.62% |
| gemini-1.5-flash-002 | 38.14% | 32.43% | 3.50% |
| command-r-plus | 24.74% | 25.12% | 4.45% |
| Llama-3-70b-chat-hf | 34.02% | 18.28% | 25.60% |

Note the non-monotonicity: **claude-3-5-sonnet-20241022 at 1.11% ASR is 30x more robust than its own June predecessor at 33.86%, with identical benign utility (79.38%).** Robustness is a per-checkpoint property, not a model-family property.

**Attack-strength sweep, gpt-4o-2024-05-13, no defense** (benign utility 69.07% throughout):

| Attack | Utility under attack | Targeted ASR |
|---|---|---|
| important_instructions | 50.08% | **47.69%** |
| tool_knowledge | 57.71% | 34.50% |
| injecagent | 68.52% | 5.72% |
| ignore_previous | 66.77% | 5.41% |
| direct | 67.25% | 3.66% |

**A 13x spread in measured ASR on the same model from attack choice alone.** Any paper reporting a single ASR without naming the attack is uninterpretable.

**Defenses, gpt-4o-2024-05-13 vs `important_instructions`:**

| Defense | Utility | Utility under attack | Targeted ASR |
|---|---|---|---|
| none | 69.07% | 50.08% | 47.69% |
| repeat_user_prompt | **84.54%** | 67.25% | 27.82% |
| tool_filter | 72.16% | 56.28% | **6.84%** |
| spotlighting_with_delimiting | 72.16% | 55.64% | 41.65% |
| transformers_pi_detector | 41.24% | 21.14% | 7.95% |

`tool_filter` is the best utility/security trade. `transformers_pi_detector` buys comparable ASR by destroying utility — a classifier defense that fails closed on legitimate work. `repeat_user_prompt` is the only defense that *raised* benign utility above baseline (84.54% vs 69.07%), suggesting part of what looks like "injection vulnerability" is ordinary instruction-following drift.

### CaMeL (2503.18813 v2) — the one that measures near-zero, with its own caveats

"Defeating Prompt Injections by Design." Code: `github.com/google-research/camel-prompt-injection`.

Mechanism: derive control and data flow from the trusted user query up front so untrusted retrieved data "can never impact the program flow"; attach capabilities to data and enforce policies at tool-call time. A privileged P-LLM emits code; a quarantined Q-LLM reads untrusted content and returns symbolic values; a custom interpreter tracks provenance.

**Utility:** **77%** of AgentDojo tasks "with provable security" vs **84%** undefended. Newer backbones narrow the gap — Travel-suite utility for the Claude Sonnet line moved **25% → 55% → 75%** across 3.5, 3.7, and 4 **with no changes to CaMeL**. Claude 3.5 Haiku as Q-LLM under a Claude 4 Sonnet P-LLM cost ~1% utility while cutting median-task cost ~12%.

**Security — 949 attacks total:**
- Gemini 2.5 Pro: **300 successful attacks without CaMeL, 0 with it**
- Claude 3.5 Sonnet + CaMeL: **0**; strongest baseline (tool filter) still allowed **8**
- GPT-4o Mini: **276** successes via the native tool-calling API → **0** under CaMeL
- Residual non-zero ASR comes from two injection tasks outside the threat model.
- Policy friction is uneven: lowest on Workspace, highest on Slack and Banking.

**Overhead:** median AgentDojo task under attack runs **~2.82x input and ~2.73x output tokens** vs native tool calling, driven by re-prompting the P-LLM to fix generated code (**up to 10 repair attempts**). Spotlighting is ~1.06x input for comparison.

**What CaMeL explicitly does NOT defend (authors' own list):**
- "text-to-text attacks which have no consequences on the data flow" — a distorted summary — and injection-driven phishing.
- Trust assumptions: the user prompt is trusted and not pasted from an untrusted source; agent memory is uncompromised.
- **Data flow turning into control flow:** Claude 3.5 Sonnet, o3-mini, and o1 generated dispatch-over-all-tools code driven by email contents, which the authors weaponize into potential arbitrary execution; they expect **ROP-style composition of individually-permitted blocks**.
- No atomicity or rollback once a partially-executed plan has side effects.
- Human factors: de-classification prompts risk fatigue and rubber-stamping.

**Three side channels:** (1) indirect inference via an external resource, blocked by STRICT mode; (2) exception-based 1-bit leak — STRICT mode helps but **the authors concede an attacker may still raise exceptions by manipulating tool-visible data**; (3) timing — "not currently exploitable because the time module is not available," other timing channels not ruled out.

Authors' verdict, verbatim: **"No, prompt injection attacks are not fully solved."**

### Dual-LLM and the pattern catalogue: Design Patterns (2506.08837 v2) — CLAIMED (no measurement)

| Pattern | Mechanism | Utility cost |
|---|---|---|
| Action-Selector | LLM as a switch mapping requests to predefined tool calls, no result feedback | confined to a pre-enumerated action list |
| Plan-Then-Execute | fix the full tool-call plan *before* touching untrusted data | cannot branch on intermediate results; planned-call *parameters* can still be tampered with |
| LLM Map-Reduce | isolated tool-less LLM per untrusted item, constrained reduce | only per-item decomposable tasks with tightly constrained outputs |
| Dual LLM | privileged LLM never reads untrusted text; quarantined tool-less LLM returns symbolic variables | privileged LLM cannot inspect content it manipulates; quarantined output can still be attacker-shaped |
| Code-Then-Execute | emit an explicit program calling tools and spawning unprivileged LLMs | task must be expressible as code up front |
| Context-Minimization | strip content no longer needed before generating the answer | reply cannot draw on removed material |

**No quantitative results anywhere in the paper.** The abstract advertises "provable resistance"; the body hedges to "mitigate — if not entirely eliminate." Scope limit stated plainly: reliable guarantees are unlikely for general-purpose agents, but **"*application-specific* agents can be secured through principled system design."**

### Web/browser-specific attack measurements

**WASP (2504.18575 v3, Meta)** — MEASURED (ind.). 84 attack tasks, 37 utility tasks. Table 2:

| Model | Scaffold | Inputs | Defense | ASR-interm | ASR-e2e | Utility |
|---|---|---|---|---|---|---|
| GPT-4o-mini | VWA | axtree | — | 0.345 | 0.024 | 0.432 |
| GPT-4o-mini | Tool Calling | axtree | instr. hierarchy | 0.536 | **0.000** | 0.270 |
| GPT-4o | VWA | axtree | — | 0.321 | 0.012 | 0.595 |
| GPT-4o | VWA | axtree | system prompt | 0.167 | **0.000** | 0.459 |
| GPT-4o | VWA | axtree + SoM | — | 0.429 | 0.036 | 0.622 |
| GPT-4o | VWA | axtree + SoM | system prompt | 0.226 | 0.012 | 0.459 |
| OpenAI o1 | Tool Calling | axtree | instr. h. (system) | **0.857** | **0.167** | 0.486 |
| OpenAI o1 | Tool Calling | axtree | instr. h. (developer) | 0.583 | 0.155 | 0.459 |
| Claude Sonnet 3.5 v2 | CURI | screenshot | — | 0.583 | 0.060 | 0.081 |
| Claude Sonnet 3.7 Ext. Th. | CURI | screenshot | — | 0.536 | 0.036 | 0.486 |

Three results that should change how we build:

- **Adding Set-of-Marks to GPT-4o's axtree raises ASR-intermediate 0.321 → 0.429 and e2e 0.012 → 0.036 while raising utility 0.595 → 0.622.** A richer observation is a larger attack surface. **Direct collision between Q3 and Q4.**
- **The reasoning model with the instruction-hierarchy defense is the most hijackable configuration in the table** (o1, 0.857 interm / 0.167 e2e). Instruction hierarchy is not a browser-agent defense.
- **URL-borne injections dominate plain-text ones** (interm / e2e): GPT-4o axtree+SoM 0.619/0.071 vs 0.238/**0.000**; o1 (system) 0.976/0.095 vs 0.738/0.238; Claude-3.5 0.857/0.048 vs 0.310/0.071. **Sanitizing URLs in fetched content is a high-leverage, cheap mitigation.**
- Defensive system prompts cost utility: GPT-4o 0.595 → 0.459.

Authors' framing: hijacking "between 17-86% ASR-intermediate" against end-to-end success "of only up to 16%", attributed to agents being unable to finish multi-step malicious goals — **"security by incompetence."** The load-bearing caveat for the whole field: **the low e2e numbers are a capability artifact that disappears as agents improve.**

**Other measured web attacks:**
- **Pop-ups (2411.02391)** — adversarial pop-ups give **86% average ASR** and cut task success by **47%**. MEASURED (vendor).
- **EIA (2409.11295)** — across 177 action steps, **up to 70% ASR for stealing specific PII, 16% for the full user request**. MEASURED (vendor).
- **AdvAgent (2410.17401)** — "high success rates", **no numbers**. CLAIMED.
- **Task Shield (2412.16682)** — AgentDojo + GPT-4o: **ASR 2.07% at 69.79% utility**. MEASURED (vendor), not independently reproduced.
- **Spotlighting (2403.14720)** — authors report **>50% to <2%**. **Contradicted by AgentDojo's independent run: 41.65%.** Likely because Spotlighting was evaluated on single-turn injection, not multi-turn agentic tool use. The <2% figure should not be cited for agent settings.

### Shipped-product evidence: Brave vs Perplexity Comet — MEASURED (ind.)

Source: `brave.com/blog/comet-prompt-injection/`.

Vector: "Comet feeds a part of the webpage directly to its LLM without distinguishing between the user's instructions" and untrusted page content. Payloads can sit on attacker-owned sites (white-on-white text, HTML comments) **or in user-generated content the attacker does not control** — Reddit comments, Facebook posts. Trigger: the user asking for a summary.

Proof-of-concept chain, from a payload "hidden behind the spoiler tag" in a Reddit comment:
1. open the victim's Perplexity account details page, read their email address
2. visit a variant of the account URL where "the trailing dot creates a different domain" — "to bypass existing authentication" — and sign in with that email to trigger a one-time password
3. jump to Gmail, where the victim is already authenticated, and read the OTP
4. post the email and OTP back as a reply to the attacker's Reddit comment → account takeover

"The attack happens without any further user input." Because the agent runs with the user's own privileges across logged-in sessions, "same-origin policy (SOP) or cross-origin resource sharing (CORS) are all effectively useless."

Timeline: reported 2025-07-25; initial fix 2025-07-27; **2025-07-28 "Retesting revealed the fix was incomplete"**; disclosure 2025-08-20. **Post-publication update on the same page: "Perplexity still hasn't fully mitigated the kind of attack described here. We've re-reported this to them."**

### Q4 synthesis — what holds versus what is proposed

**Measured to hold:** CaMeL's control/data-flow separation plus capability policies — 0 of 949 attacks on three backbones — at 7 points of utility and ~2.8x tokens, with three acknowledged side channels, no defense against text-to-text manipulation or phishing, and a data-to-control-flow escalation its authors expect to be composable ROP-style. Tool filtering is the cheap 80% answer (6.84% ASR at 72.16% utility).

**Proposed but unmeasured:** the six design patterns (2506.08837) have zero quantitative evaluation. Dual-LLM quarantine is implemented inside CaMeL, so its evidence rides on CaMeL's numbers.

**Measured NOT to hold:** spotlighting/delimiting in agentic settings (41.65% vs its own paper's <2%); instruction hierarchy on browser agents (o1 the worst row in WASP); classifier-based detection at acceptable utility (41.24% benign utility).

**The framing to use:** the lethal trifecta is not a risk to be mitigated at the model layer. Every model-layer defense measured here leaks. The only thing that reaches zero constrains the *program*, and it does so by giving up the ability to plan over data the privileged model cannot see. Add the WASP result that richer observations raise ASR, and the Brave result that a patched agentic browser stayed exploitable across two fix rounds, and the honest position is: **do not give a browsing agent both private-data access and an external write channel in the same session, regardless of defense.**

---

## Q5 — The agent-web contract: standardization status vs real adoption

### Answer

**Only one of the five is a real standards effort, and it is the one with the least marketing.** Web Bot Auth has a chartered IETF working group (`webbotauth`) and an active standards-track WG draft as of 2026-09-01 — but its launch post names exactly **one** external signer (OpenAI Operator) and publishes **zero** traffic numbers. The other four are vendor or individual specs with adoption evidence ranging from thin (x402, NLWeb) to logo-count-only (AP2) to essentially unevidenced on the consumption side (llms.txt). **Confidence: strong** on standardization status; **strong** on the *absence* of adoption data, which is itself the finding.

### 1. Web Bot Auth — strongest process, thinnest adoption data

| Draft | Type | Latest | Status |
|---|---|---|---|
| `draft-meunier-web-bot-auth-architecture` | individual | -05, 2026-03-02 | Replaced, expired & archived. No WG, RFC stream `(None)` |
| `draft-meunier-webbotauth-httpsig-protocol` | individual | -02, 2026-08-19 | Expired & archived; merged architecture + directory drafts |
| **`draft-ietf-webbotauth-httpsig-protocol`** | **WG document** | **-00, 2026-09-01**, expires 2027-03-05 | **Active Internet-Draft**, WG `webbotauth`, stream IETF, IESG state "I-D Exists" |

Title: "HTTP Message Signatures for automated traffic." Authors **Thibault Meunier (Cloudflare) and Sandor Major (Google)** — cross-vendor authorship is the strongest signal here. Datatracker's intended-status reads `(None)` while the draft header says "Intended status: Standards Track"; no shepherd, responsible AD, or milestones assigned yet.

**Mechanism:** built on **HTTP Message Signatures (RFC 9421)**. Covered components `("@authority" "signature-agent")`. `Signature-Input` carries a validity window, a **Key ID that is a JWK Thumbprint (RFC 7638)**, and the tag `web-bot-auth`. A `Signature-Agent` header names the host serving the signer's JWKS directory and is itself covered by the signature. **Ed25519** demonstrated. Reference implementations at `cloudflareresearch/web-bot-auth`: Chrome extension, Workers debug server, Caddy Go plugin. A deprioritized second track is request mTLS via a proposed TLS flag (extension 65025 / `0xfe01`).

**Adoption — one data point:**
- Exactly **one external bot operator is named as signing**: "For example, OpenAI has started to sign their requests."
- `crawler.search.google.com` and `operator.openai.com` appear **only as hypothetical directory-hostname examples**. Do not read Google Search as an adopter.
- **Zero traffic or site-count numbers.** On uptake: "This is a metric we will monitor closely, and report on as adoption grows." Launch availability was a **closed beta**.

### 2. NLWeb — spec ambition high, adopters zero, and it left Microsoft's org

**Governance finding:** `api.github.com/repos/microsoft/NLWeb` **redirects to `nlweb-ai/NLWeb`**. Metadata: 6,254 stars, 699 forks, 65 open issues, MIT, Python, created 2025-04-28, last push 2026-08-11, **no releases at all**. The README still carries a Microsoft trademark notice and a microsoft.com support mailbox — the README has not caught up with the org move. (Another instance of the vendor-docs-lag pattern.)

Self-positioning, verbatim: **"NLWeb is to MCP/A2A what HTML is to HTTP."** Every deployed instance doubles as an MCP server; A2A support "forthcoming."

**Adopters: none named.** The only organizations listed are Microsoft (host/trademark) and third-party *supported integrations* (Qdrant, Snowflake, Milvus, Azure AI Search, Elasticsearch, Postgres, Cloudflare AutoRAG; OpenAI, DeepSeek, Gemini, Anthropic, HuggingFace; HubSpot, Dynamics 365, Jira) — integrations are not adopters.

**Maturity, in the project's own words:** offered "not as the definitive solution, but as proof-of-concept demonstrations showing one possible approach," and **"CI/CD pipelines are not yet included."**

### 3. llms.txt — weakest evidence base of the five

**Status: an individual/community proposal.** Not a standard, not an IETF draft. The only IETF reference is **RFC 8615 (Well-Known URIs) cited as a rejected alternative design** — the well-known-URI route was deliberately not taken. No byline on the page.

**Publisher-side adoption is real:** Mintlify, GitBook, Yoast SEO, AIOSEO, Wix auto-generate it; VitePress, Docusaurus, Drupal tooling exists; OpenAI, Anthropic, and Gemini publish llms.txt **for their own developer documentation**.

**Consumer-side adoption: no named LLM provider consumes it.** The decisive gap. The AI labs appear only as publishers. The page frames consumption as expectation, not behavior: "Agents are expected to view or search `llms.txt`." The claim that it is used for inference is asserted **without naming a consuming product**.

**Adoption statistics: essentially none.** The sole quantitative claim is "**thousands of sites publish an llms.txt file**" — no count, method, date, or source.

**Independent corroboration: none.** arXiv `all:"llms.txt"` → 2 results, neither measuring adoption:
- `2604.02544` — fingerprints nine coding agents and six assistant services against a live documentation endpoint. Finding: agent traffic "compresses multi-page navigation into a single or two requests," breaking session-depth and bounce-rate metrics. **llms.txt appears only in a recommendation list** — no per-agent fetch rate. **The paper best positioned to measure consumption did not.**
- `2603.10700` — enhanced entity page reached "+29.6% accuracy improvement for standard RAG and +29.8% for the full agentic pipeline," but **the enhanced page bundled "llms.txt-style agent instructions, breadcrumbs, and neural search" — no isolated llms.txt effect.**

### 4. x402 — active code, governance moved to a foundation, no usage data

**Governance finding:** `coinbase/x402` reports `"fork": true` — its source is **`x402-foundation/x402`**.

| | `x402-foundation/x402` (upstream) | `coinbase/x402` (fork) |
|---|---|---|
| Stars | **6,632** | 159 |
| Forks | **2,064** | 222 |
| Created | 2025-02-21 | 2026-04-02 |
| Last push | **2026-09-22** | 2026-09-21 |
| Issues/discussions | enabled | **disabled** |

**Standardization: none determinable.** No standards body, RFC, or spec version in either record. **No release object, tag, or version string.** Adoption: nothing beyond repo engagement — no transaction volumes or integration counts reachable. Referenced as the crypto rail under AP2 via `google-a2a/a2a-x402`, which AP2 calls "a production-ready solution" — **readiness language, not a deployment claim.**

### 5. AP2 — maximum logo count, zero deployment evidence

Announced 2025-09-16. A "payment-agnostic framework" targeting three gaps when an agent rather than a human clicks buy: **Authorization**, **Authenticity**, **Accountability**. Positioned as an **extension** of A2A and MCP.

Trust rests on **Mandates** — "tamper-proof, cryptographically-signed digital contracts" signed via verifiable credentials. Human-present flow captures an **Intent Mandate**, then approving the cart signs a **Cart Mandate** locking exact items and price. Delegated flow signs a detailed Intent Mandate upfront with price/timing rules. Produces a "non-repudiable audit trail" spanning intent → cart → payment.

**Standardization: none.** A Google-authored spec plus reference implementations.

**Adoption: 60+ organizations cited, 46 named, no live production deployment claimed anywhere.** Partner language is uniformly forward-looking — "looking forward to contributing," "committed to extending this support." The single "production" reference is the x402 extension.

### Q5 ranking, by evidence rather than ambition

1. **Web Bot Auth** — chartered IETF WG, active standards-track draft, Cloudflare+Google co-authors, RFC 9421 foundation. One named signer, zero telemetry.
2. **x402** — no standards process, but a foundation, 6,632 stars, commits today. Zero usage data.
3. **AP2** — vendor spec, 46 named partners, coherent VC/mandate model. Zero deployments claimed.
4. **NLWeb** — single repo that moved out of Microsoft's org, self-described proof-of-concept, no CI, no releases, no adopters.
5. **llms.txt** — individual proposal that explicitly declined the RFC 8615 route; real CMS-driven publisher adoption, **no named consumer and no measured fetch rate anywhere.**

---

## Known Gaps

**Tooling constraints that shaped this report.** WebSearch returned HTTP 400 on every call, so only URLs nameable in advance could be fetched — anything discoverable only by search is absent. Bash and Write were disabled, so the report was delivered as six messages and concatenated by the lead. Semantic Scholar was never attempted.

**Searches that came up empty:**
- arXiv `all:"JavaScript rendering" AND all:crawl` → **`totalResults = 0`**
- arXiv `all:"llms.txt"` → 2 results, neither with adoption counts or fetch measurements
- arXiv `all:"web agent" AND all:"observation space"` → 2 results; the modality literature does not use that phrasing

**404s / blocks encountered (recorded so nobody repeats them):** `mozilla/readability/main/isProbablyReaderable.js` (actual path `Readability-readerable.js`); `crawlee.dev/js/docs/guides/adaptive-playwright-crawler` and two sibling paths (read the source instead, more authoritative anyway); `ahrefs.com/blog/llms-txt`; `docs.skyvern.com/running-tasks/caching` (moved to `www.skyvern.com/docs`); `arxiv.org/html/2401.13649v3`. Content-blocked by the fetch proxy: `arxiv.org/html/2410.13825v2` and `arxiv.org/html/2409.12089v1`, both recovered via `r.jina.ai` on the PDF.

**Could not verify, would not cite without a source check:**
- **Stagehand's client-side `selfHeal` option** — only the caching docs page was read; it documents a server-side cache and never mentions `selfHeal`. Check `github.com/browserbase/stagehand` source.
- **spider-rs `crawl_smart()` heuristic** — asserted, undisclosed. Needs the Rust source.
- **Skyvern's cache-key semantics** — undocumented.
- **Firecrawl's engine-selection hit rates** and **Crawlee's adaptive-crawler measured savings** — neither vendor publishes benchmarks. "Adaptive crawling saves X%" is unsupported in both directions.
- **x402 transaction volume** and **Web Bot Auth post-beta traffic share** — neither exists in public.
- **Defuddle's actual scoring thresholds** — `constants.ts` proves they exist; the module was not located.

**Data-quality caveats on numbers reported above:**
- **2409.12089** has two unreconciled internal inconsistencies (GPT-4V random ordering 44.44% vs 37.04%; Gemini baseline 64.03% vs 64.20%), and its VWA figures are on a **pre-filtered subset of previously-successful "easy" tasks**, ~60 points above the VWA paper's own numbers. Do not mix scales.
- **AgentOccam's full 812-task ablation** was truncated in extraction; only the 190-task dev-set ablation is reported.
- **AgentDojo states it is "not a leaderboard"** — not all models were run with all attacks/defenses, and **only gpt-4o-2024-05-13 was run with defenses**. Cross-row comparison is invalid.
- **WASP n = 84**, so single-task changes move ASR by ~0.012. The 0.000 cells mean "0 of 84," not "proven safe."
- **2603.10700's +29.6%/+29.8%** bundles llms.txt-style instructions with breadcrumbs and neural search.
- Abstract-only, no numbers (labelled CLAIMED): WALT 2510.01524, Region4Web 2605.07134, ContractSkill 2603.20340, AdvAgent 2410.17401, Design Patterns 2506.08837, FCPAgent 2607.24167.
- Read abstract-only via the API, not cross-checked in body: 2606.10742, 2602.14865, 2603.07024, 2606.04391, 2404.04902, 2510.10049, 2604.13318, 2609.19523, 2608.30207, 2606.10423, 2606.17645, 2605.23939, 2604.20940, 2608.24898, 2603.04364, 2506.14866, 2607.10079, 2608.24848.

**arXiv IDs verified to resolve (via `id_list`), all confirmed present:** 2307.13854, 2401.13649, 2401.13919, 2410.16464, 2410.13825, 2409.12089, 2409.07429, 2504.07079, 2406.13352, 2504.18575, 2506.08837, 2411.02391, 2409.11295, 2410.17401, 2404.07972, 2503.18813, 2607.04334, 2604.20940, 2604.08516, 2605.07134, 2510.01524, 2510.14308, 2603.20340, 2609.13548, 2504.01382, 2306.06070, 2403.14720, 2412.16682. **No ID returned an empty entry.**

---

## Sources Consulted

**Source code** (authoritative over docs — the lesson held twice: Skyvern's and Crawlee's docs URLs both 404'd while their source was fine): mozilla/readability `Readability-readerable.js` · trafilatura `settings.cfg`, `settings.py`, `core.py` · crawl4ai `content_filter_strategy.py` · firecrawl `scrapeURL/index.ts`, `scrapeURL/engines/index.ts` · crawlee `rendering-type-prediction.ts`, `adaptive-playwright-crawler.ts` · crawlee-python `_rendering_type_predictor.py` · defuddle `constants.ts` · spider-rs README · nlweb-ai/NLWeb README

**Repo metadata:** `api.github.com/repos/nlweb-ai/NLWeb` (org move) · `api.github.com/repos/coinbase/x402` (fork-of-foundation) · `api.github.com/repos/lavague-ai/LaVague` (dormancy)

**Vendor documentation:** jina.ai/reader · docs.zyte.com/zyte-api/usage/http.html · docs.stagehand.dev/best-practices/caching · www.skyvern.com/docs/developers/features/code-caching

**Standards / protocol:** three IETF Datatracker draft pages including the active WG draft · blog.cloudflare.com/web-bot-auth · llmstxt.org · Google Cloud AP2 announcement

**Benchmarks and papers:** agentdojo.spylab.ai/results (full per-model/per-defense table) · brave.com/blog/comet-prompt-injection (exploit chain, disclosure timeline, post-publication update) · arXiv full text via r.jina.ai for 2410.13825, 2409.12089, 2401.13649, 2307.13854 · arXiv HTML for 2410.16464, 2504.18575, 2503.18813, 2506.08837 · `id_list` verification for all 28 IDs · relevance searches: `abs:"web agent" AND abs:"reusable"` (19), `abs:"accessibility tree" AND abs:"screenshot"` (12), `all:"web agent" AND all:"observation space"` (2), `all:"llms.txt"` (2), `all:"JavaScript rendering" AND all:crawl` (0)

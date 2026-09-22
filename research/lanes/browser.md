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

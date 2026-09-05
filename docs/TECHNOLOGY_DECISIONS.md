# Technology choices and trade-offs

This document describes the implemented stack, not the stack suggested in the original research. Decisions prioritize a local, reviewable hackathon solution whose repair claims can be demonstrated in a real browser. No framework comparison below claims benchmark superiority.

## Decision summary

| Concern | Chosen | Benefit for this project | Cost / alternative |
|---|---|---|---|
| Agent coordination | V1 direct pipeline; optional V2 LangGraph | Stable default plus V2 stage checkpoints | Both paths must preserve safety and evidence semantics |
| AI planning | OpenAI Responses API with Pydantic output parsing | User-selected provider and validated action contracts | Network/model dependency, variable plans and token cost |
| Browser | Playwright with Chromium | One substrate for observations, execution and repair proof | Chromium-only; limited to supported main-document actions |
| Test generation | Validated action DSL plus Python replay entry point | Model output stays data; expected results can be compared structurally | Less expressive than arbitrary Python/JavaScript tests |
| Backend | FastAPI/Uvicorn/Pydantic | Typed HTTP boundary and asynchronous browser/model calls | One local process; not a distributed job service |
| State | SQLite WAL plus per-run files | No database service; restart-persistent history and auditable snapshots | Local concurrency and retention limits |
| Dashboard | HTML/CSS/JavaScript with two-second polling | No build toolchain or external UI assets | Manual component/state management; polling cost |
| Classification | Evidence rules with heuristic scores | Auditable reasons and conservative escalation | No trained/calibrated root-cause model |
| Reports | JSON, HTML, Markdown, PNG, JUnit, ZIP | Human and machine consumption; offline inspection | Evidence can be large and requires access control |

## Why V1 has no LangGraph

This section records the retained V1 decision. V2 is now available behind
`QA_PIPELINE_VERSION=v2`; it adds explicit agent nodes and SQLite graph checkpoints
without replacing V1 or relaxing browser safety.

**LangGraph is not used.** The product is agentic because it makes bounded decisions from evidence, not because it imports an agent framework. `pipeline.py` selects reuse, planning, coverage re-plan, execution and reporting. `triage.py` records executor → retry → healer → verification → classifier/escalation transitions. The Planner uses an LLM; the Generator and Healer combine deterministic tools and constrained model assistance. These are specialized runtime roles, not independent chatting processes.

The current workflow has one active run, a ten-minute deadline, one bounded initial coverage re-plan, one unchanged failure retry and one repair proposal. Browser contexts and optional authenticated state belong to one async lifetime. A small explicit orchestrator makes those limits and cleanup paths easy to inspect.

**Example:** an unchanged scenario fails because `#old-heading` no longer exists. The executor retries once. The Healer checks an observed candidate for unique semantic identity, changes only the failed locator, and replays the entire flow. A graph framework would still need all these domain rules; it would not decide that a changed assertion is unacceptable for us.

**Trade-off:** this implementation does not provide framework-managed checkpoints, graph visualization tooling, distributed graph workers or human-interrupt persistence. SQLite events preserve what happened, but they do not resume an in-flight browser action after a crash. Interrupted runs restart as fresh runs. That avoids assuming an unknown cart mutation or submission is safe to replay.

**When to reconsider:** if the product needs multi-hour workflows, persisted approval pauses, conditional parallel branches or reliable resumable jobs, evaluate LangGraph with a durable checkpointer and idempotent node contracts. Persist serializable run/artifact IDs, not live browser objects. Browser reattachment, authentication renewal, duplicate side effects and access policy remain application responsibilities. Migration would be a separately tested change, not a dependency added to the current loop for presentation value.

## Why OpenAI structured outputs rather than free-form generated code?

The user selected OpenAI. `llm.py` calls the Responses API and parses into `Plan` or `HealProposal`. `models.py` bounds actions, lengths, steps and flow count. The backend separately validates navigation, assertions and requirement IDs. Structured shape is useful but cannot prove that a business rule or locator is correct. See [official structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs).

**Example:** `assert_text(target='[data-testid="cart-total"]', value='$18.00')` is inspectable data. A model cannot submit `eval`, shell commands or arbitrary imports because they are not actions in the contract. `generated_tests.py` is a small, fixed replay entry point; the behavior is generated in `suite.json` and interpreted by the shipped Playwright runner.

**Trade-off:** the DSL cannot express every browser test. The live PRD check exposed a model trying to assert an input placeholder with `assert_text`. The browser correctly failed it and the system retained it as `needs_review`. A future typed `assert_attribute` action could address that class of test, but it needs explicit semantics and tests. Automatically converting arbitrary failed assertions into different assertions would weaken the repair guarantee.

Model choice stays configurable instead of asserting that one model is universally best. Five logical calls and one SDK retry per call bound cost exposure; recorded tokens are measured, while dollar estimates require configured rates. No benchmark or fixed per-run cost is claimed.

## Why Playwright instead of combining several browser-agent libraries?

Reconnaissance, live validation, execution, failure snapshots and repaired-flow confirmation share the same browser implementation. CSS selectors and element fingerprints observed by the Planner can be exercised by the Executor directly. Fresh browser contexts isolate storage for each replay; [Playwright documents BrowserContext isolation](https://playwright.dev/python/docs/api/class-browsercontext).

**Example:** a product-card price locator matching multiple elements is rejected. If a preceding verified product heading provides an unambiguous container, the Healer can scope the price inside that container. It never chooses the product whose price happens to match the desired assertion.

**Trade-off:** there is no generic visual computer-use agent, OCR/canvas testing, iframe traversal or cross-browser matrix. Crawl4AI or browser-use could expand discovery, but adding them would require normalizing their observations, security policies and action traces with the existing executor. For this scope, one browser substrate reduces that integration surface; no speed claim is implied.

## Why deterministic classification with a constrained AI Healer?

Classification should explain evidence rather than produce a confident-sounding guess. A requirement-backed assertion must fail at the same step on two isolated execution attempts before receiving `likely_defect`. Inferred expectations stay unresolved. An unchanged passing retry signals intermittency; only a verified locator-only change earns `healed_ok`.

**Example:** a PRD expects "$18.00" but the app displays "$12.00" twice. The report preserves the expectation and asks for investigation. It does not “heal” the test by replacing `$18.00` with `$12.00`.

The Healer first uses unique fingerprint matching. If that fails, OpenAI may propose an observed candidate, but confidence alone is insufficient: a separate semantic-identity gate and full replay must pass. Ambiguity causes escalation.

**Trade-off:** this is not a trained ML defect classifier, and scores are not calibrated probabilities. Distinguishing an application bug from a wrong PRD still needs human confirmation. A future classifier would need labelled failures, versioned evaluation data, false-positive analysis and calibration before stronger claims.

## Why SQLite and immutable run files instead of PostgreSQL/Redis/vector storage?

The application has one trusted local user and one active job. SQLite stores run metadata, events and successful element fingerprints; individual run directories hold plans, results and screenshots. WAL supports dashboard reads while the worker updates history. Exact suite matching and structural comparisons solve the implemented reuse problem without embedding retrieval.

**Example:** run A passes; run B repairs a selector; run C loads B's completed plan. A's files are unchanged. A cancelled B is never promoted as the new suite. Changing a PRD remaps requirement links by exact text and retains expected values for review.

**Trade-off:** matching includes URL path/query/fragment, scope, engine and policy. Different entry URLs on the same domain do not automatically share a suite. Storage is not encrypted, retention is manual, and more than twelve scenarios per suite is not implemented. Events/artifacts are not a transactional distributed checkpoint. PostgreSQL plus a durable queue and object storage would be appropriate for multiple users/workers; fuzzy cross-project retrieval would require contamination and relevance evaluations before introducing embeddings.

## Why FastAPI and plain JavaScript rather than a larger application stack?

FastAPI/Pydantic validate the local REST contract; asyncio manages model calls, browser tasks and cancellation. The dashboard uses local HTML/CSS/JavaScript and system fonts with no frontend package manager or CDN dependency. A two-second poll updates persisted history; reconnect does not need replaying a separate transient socket stream.

**Example:** closing the tab does not delete a run. Reopening reads SQLite-backed history. PRD contents are returned with run details rather than every run-history poll.

**Trade-off:** plain DOM code becomes harder to maintain as interactions grow. Polling is not instantaneous, and the current UI renders a bounded latest-100 history. React could help with reusable components and richer client state; SSE could reduce polling traffic if scale or latency becomes material. Those benefits are not necessary for the current one-user demo and would add another build/runtime concern.

## Why no automatic assertion rewrite or arbitrary flow repair?

Self-healing must not turn a real regression green by changing what the test means. The repair gate compares the whole proposed flow against the original, allowing only the failed selector to differ. Verified changes are saved in the new run snapshot. Failed proposals and original screenshots remain available.

**Example:** a login journey gains MFA. Adding steps, bypassing MFA or changing success expectations is not a locator repair. The application records an uncovered or unresolved flow. Future broader repair would need approved intent contracts and independent oracles, not merely another model call.

## Why this export format?

HTML/Markdown explain the quality outcome; JSON preserves detailed evidence; PNG shows browser state; JUnit supports downstream portability; ZIP makes the bundle easy to share. The replay entry point permits rerunning without model planning calls.

**Trade-off:** reports can contain application data and large snapshots. The HTML is intentionally a portable document rather than an external hosted dashboard. It is not a signed attestation or a standalone executable environment. The [report guide](REPORT_GUIDE.md) distinguishes evidence, interpretation and prerequisites.

## Dependency policy and future decision gates

Direct package pins are listed in `../requirements.txt`; they are not a fully hashed transitive lockfile or a supply-chain certification. Existing versions were retained for this enhancement. A release for wider distribution should add a complete reproducible lock, vulnerability/licence review, supported-platform testing and a documented update process.

Adopt additional infrastructure when its failure mode or user need is demonstrated: LangGraph for durable graph workflows, a database/queue for multi-user work, a frontend framework for UI complexity, and a broader browser layer for unsupported targets. Measure reliability and maintenance effort before claiming the replacement is better.

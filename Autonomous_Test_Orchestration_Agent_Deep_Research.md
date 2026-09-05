# Autonomous Test Orchestration Agent — Deep Research & Strategy Report
**Bessemer Tech Catalyst · AI/ML Track · Prepared for hackathon team**

---

## PART 1 — PDF ANALYSIS (Authoritative Source)

### 1.1 Exact Problem Statement
> **"Autonomous Test Orchestration Agent"** — Build an autonomous test orchestration agent that takes a web application URL as input and drives the full testing lifecycle — planning, test generation, execution, and repair — without human intervention between stages.

Theme: AI/Machine Learning. Focus areas: Agentic AI, Developer Productivity, Software Quality Engineering. Organiser: Aivar Innovations (AWS Preferred Partner, backed by Bessemer Venture Partners and Sorin Investments; runs Convogent, Velogent, Kubogent platforms).

### 1.2 Problem Objective
Eliminate the **coordination burden** of testing — not the mechanical writing of tests (already partly solved by existing AI tools), but the meta-decision-making: when to plan, when to generate, when to heal, when to escalate, and how to judge if "enough" was tested. The PDF is explicit that execution is not the bottleneck; decision-making is.

### 1.3 Target Users
- **Explicit**: developers/engineering teams who currently spend disproportionate time hand-writing tests relative to feature-build time.
- **Implicit** (not named in PDF but structurally implied): QA engineers who inherit brittle suites; engineering managers who need a demo-ready quality signal; hackathon judges themselves, who are evaluators of *your* agent's decision quality.

### 1.4 Expected Outcome
"A developer provides a URL and receives a working, meaningful test suite with no manual scripting in between" — plus a synthesized test quality report.

### 1.5 Functional Requirements
**Explicitly stated (Must Have):**
1. Accept a web URL as sole required input; start autonomously.
2. Planner sub-agent explores the app, produces a human-readable test plan covering *meaningful* flows (not just happy paths).
3. Meta-agent evaluates the plan for coverage gaps (missing flows, edge cases, error states) **before** generation.
4. Generator sub-agent converts plan → executable test code, with **live selector/assertion validation** (i.e., it must actually check selectors resolve against the running app, not hallucinate them).
5. Run the suite; on failure, invoke Healer sub-agent; **distinguish broken script vs. genuine app defect**.
6. Produce a final report: scenarios covered, pass/fail, healer actions, remaining coverage gaps, untested-flow risk.

**Good to Have:** optional PRD ingestion to scope the Planner; natural-language scoping ("focus on checkout and auth"); parallel execution across flows.

**Bonus:** PRD-to-test-plan gap analysis; confident defect classification (broken test vs. real bug).

**Out of Scope (explicit):** production deployment/hosting at scale, CI/CD integration, cross-browser matrix testing, complete production coverage, any manually-written test script.

### 1.6 Non-Functional Requirements (mostly implicit — the PDF barely states these, which is itself a signal)
- **Autonomy**: zero human intervention *between* stages (explicit) — implies the meta-agent must make judgment calls a human normally makes.
- **Determinism/trust**: a "meaningful" test plan and a report a judge/developer can trust — implies explainability of every agent decision.
- **Speed**: implicit hackathon constraint — pipeline must run live, in front of judges, in minutes, not hours.
- **Cost**: LLM keys are self-funded (explicit) — implies token/cost efficiency is a real engineering constraint, not a footnote.
- **Generalization**: "should work against any web application" (explicit) — this is the hardest non-functional requirement in the whole document, because it rules out app-specific hardcoding.

### 1.7 Constraints
- Teams must bring their own LLM API keys — organiser provides none.
- Official target app(s) are only revealed on the day — teams are explicitly told not to rely on them and should bring their own target.
- Submission is a working prototype + repo + README + architecture diagram + 2–5 min demo video + deck.

### 1.8 Evaluation / Judging Criteria (with weights)
| Criterion | Weight |
|---|---|
| Functionality & completeness (full pipeline runs end-to-end, no manual steps) | 30% |
| Innovation & originality (orchestrator's handling of gaps, ambiguity, failure classification) | 20% |
| Technical implementation & code quality (agentic loop robustness, test quality, healer depth) | 20% |
| UX & demo clarity (how clearly agent decisions/output are shown) | 15% |
| Business impact & feasibility (real QA-effort reduction) | 10% |
| Presentation (live demo clarity, trade-off articulation) | 5% |

Read literally: **70% of the score is about the orchestration layer and its decisions, not the raw ability to generate a Playwright script.** Most teams will over-invest in generation and under-invest in the meta-agent's judgment logic — this is the single most important scoring insight in the document.

### 1.9 Expected Deliverables
Working prototype, source repo (GitHub/GitLab) with setup docs, README documenting architecture, an architecture diagram of sub-agent orchestration, a 2–5 min demo video, and a presentation deck covering problem/approach/trade-offs/business impact.

### 1.10 Mentioned Technologies / Terminology
- **Explicit**: "web application URL," "human-readable test plan," "executable test files," "live selector and assertion validation," "healer," "meta-agent," "PRD," "coverage gaps," "untested flow risk," "defect classification."
- **No specific framework, language, or library is named anywhere in the PDF.** This is a deliberate/implicit gap: the team must choose its own stack (Playwright vs. Selenium vs. Cypress; LangGraph vs. CrewAI vs. custom; Claude vs. GPT vs. open models).

### 1.11 Explicit vs. Inferred — Summary Table
| Requirement | Status |
|---|---|
| URL-only input | Explicit |
| 3 named sub-agents (Planner, Generator, Healer) | Explicit |
| Meta-agent coordinates + re-plans + escalates | Explicit |
| Coverage-gap evaluation before generation | Explicit |
| Live selector validation | Explicit |
| Broken-script vs. real-defect classification | Explicit (Must Have failure triage; Bonus = *confident* classification) |
| Final report with specific fields | Explicit |
| Choice of agent framework, browser driver, LLM provider | Inferred (team's choice) |
| Authentication handling for the app under test | Inferred (PDF says "username/password" are inputs per the video summary, but the formal PDF's Must-Haves only mention "URL" as the sole required input — this is a genuine ambiguity, see 1.12) |
| What counts as "meaningful" coverage | Inferred — undefined; judges will judge subjectively |
| How much autonomy is acceptable for destructive actions (e.g., form submissions that mutate real data) | Inferred — not addressed at all |

### 1.12 Ambiguities and Contradictions Found
1. **Auth input conflict**: The video summary (in the supplementary transcript) says the agent should take **URL + username + password**. The formal PDF, however, says the **sole required input is the URL** and only lists "optional PRD" and "natural language intent" as Good-to-Haves — credentials are never listed as a formal input field anywhere in the four-page PDF. Practically, almost every real app has a login wall, so the Planner cannot explore "meaningful flows" without credentials. **This is the single biggest spec gap** — teams that don't proactively design a credentials-injection mechanism (env var, config file, or secure input field) will find their agent stuck on a login screen against the organiser's surprise target app.
2. **"Meaningful, not just happy paths" vs. "Out of Scope: complete coverage"**: The PDF wants non-trivial edge-case coverage but explicitly excludes "complete test coverage of a production application." The bar is deliberately fuzzy — judges are told to reward *quality of judgment about what to skip*, not raw test count.
3. **"Live selector and assertion validation" is required for the Generator, but nothing is specified about how it should behave when validation fails** — does it silently retry, ask the Planner to re-scope, or hand off directly to the Healer? This is left to the team; it's actually the crux of the "orchestration intelligence" the judges are grading (20%).
4. **Defect classification is listed under both Must Have ("distinguishing... broken script vs genuine defect") and Bonus ("confidently distinguish")** — the difference between the Must-Have and Bonus version is *confidence/certainty*, not the capability itself. Many teams will read only one of the two mentions and miss that a shallow heuristic satisfies Must-Have but a probabilistic/evidence-backed classifier is needed for Bonus points.
5. **PRD gap analysis appears in both "Good to Have" (accept PRD to scope Planner) and "Bonus" (PRD-to-test-plan gap analysis after generation)** — these are two different mechanisms (pre-generation scoping vs. post-generation traceability) that could be built as one shared module.

---

## PART 2 — BEYOND THE PDF: EXTERNAL RESEARCH

### 2.1 Root Cause Analysis

**What's the underlying problem?** Software testing isn't slow because writing test *code* is hard — it's slow because deciding what to test, evaluating whether a failure is real, and maintaining that judgment over time requires domain expertise that doesn't scale with headcount. Industry commentary in 2026 frames this precisely as a "decision-making bottleneck," not an authoring bottleneck — mirroring the PDF's own framing almost word for word, which confirms the organiser is tracking real industry consensus rather than inventing a strawman.

**Why hasn't it been solved?** Every mainstream 2026 tool (Mabl, testRigor, Testim/Tricentis, Katalon, Functionize, Playwright's own AI test agents) has picked off *one* piece — generation, or healing, or triage — but stops short of an agent that autonomously sequences all of them end-to-end and decides *when* to escalate to a human. Reviewers of these tools explicitly describe this as a persistent gap: teams still "carry the coordination burden themselves," even with best-in-class point tools. That's precisely the gap Aivar is pointing hackathon teams at.

**Why does the gap persist technically?**
- **The oracle problem**: knowing whether a test *should* pass is fundamentally a judgment call. Academic work on LLM-generated tests (RESTestBench, 2026) explicitly names the oracle problem as unsolved even for API-level tests — it's harder for UI flows, where "correct behavior" is rarely written down anywhere machine-readable.
- **Cost of LLM-first approaches**: recent research (arXiv 2603.20358, March 2026) shows that LLM-based selector discovery/healing introduces per-run API costs that become "prohibitive at enterprise scale" — which is exactly why most production self-healing tools (Healenium, Testim) default to cheap deterministic tree/attribute matching and only escalate to an LLM as a last resort. Most hackathon teams will not know this and will call an LLM on every single locator resolution, burning their token budget and demo time.
- **Agent-generated-test volume doesn't equal value**: a February 2026 paper ("Rethinking the Value of Agent-Generated Tests") found no statistically significant relationship between how many tests an agent writes and whether it actually helps resolve the underlying task — reinforcing that the meta-agent's *judgment* about what's worth testing matters more than test count, which again maps directly onto the 20% "innovation/orchestration" judging weight.

### 2.2 Users & Stakeholders
- **Who experiences the pain**: individual contributor developers (the PDF's framing device — "3 days writing tests for 1 day of feature work"), and QA/SDET engineers who inherit and maintain the resulting suites.
- **Who pays**: engineering leadership — the ROI case is measured in $ of engineering time (see 2.4).
- **Who operates it day-to-day**: whoever is on-call for CI — flaky/red builds are frequently the QA/DevOps function's problem even though the root cause sits in dev or product.
- **Who could resist adoption**: QA engineers whose job partly *is* test authoring may see this as threatening; security/compliance teams may resist an agent that autonomously logs into a real app with real credentials and takes actions (see 2.6, hidden insight on destructive-action risk).
- **Underserved users the PDF doesn't mention**: accessibility testers (nothing in the PDF asks for a11y checks, yet the accessibility tree is the *cheapest, most robust* signal for element discovery — see 2.3); non-English-first teams (all research on test generation and healing is English-centric; multi-locale apps are an underserved edge case); teams on legacy server-rendered apps without stable `data-testid` attributes, who get the worst locator brittleness and the least attention from vendors who target modern SPA stacks.

### 2.3 Existing Solutions — Landscape Scan
| Solution | What it does | Strengths | Weaknesses / what's unsolved |
|---|---|---|---|
| **Mabl** | No-code auto-generated journeys, self-healing selectors, unified web/API/a11y checks | Fast time-to-coverage, mature | You don't own the code; limited fine-grained control |
| **testRigor** | Plain-English test authoring; generative drafting from requirements | Accessible to non-engineers, tests read as living documentation | Not a full autonomous pipeline; still largely human-directed |
| **Testim (Tricentis)** | ML-weighted attribute fingerprinting for self-healing | Proprietary ML scoring, mature enterprise product | Opaque healing decisions; no open orchestration layer |
| **Katalon Studio 11 (2026)** | Two-tier healing: classic fallback chain, then an LLM tier analyzing DOM + accessibility tree + screenshots | Configurable cost/accuracy trade-off | Still human-supervised; healing insights require manual approval |
| **Healenium** (open-source, EPAM) | Deterministic tree-comparison (Longest Common Subsequence) self-healing for Selenium, zero LLM cost | Free, auditable, framework-level, doesn't require LLM calls at all | Selenium-only historically (proxy mode now supports more); purely structural, no semantic understanding of *what* an element does |
| **Shiplight AI / "agent-native QA"** | MCP-callable, intent-based YAML tests that transpile to Playwright, self-healing surfaced as PR diffs | Coding-agent native, human-reviewable heals, real exit path (no lock-in) | Still positions the *human coding agent* (e.g., Claude Code) as the orchestrator; doesn't fully remove the human loop by itself |
| **QA Wolf and other managed-QA services** | Human engineers + AI tooling maintain your suite as a service | "Green suite," SLA-backed | Not autonomous at all — the "self-healing" is outsourced humans; no MCP surface, no autonomy |
| **Skyvern / browser-use / Stagehand / Playwright MCP** | Open-source LLM-driven browser agents (vision-based, DOM-based, or hybrid) for *exploration* and task execution | Skyvern: vision + LLM, generalizes across sites, WebVoyager SOTA-competitive; browser-use: fast, DOM-based, cheap; Stagehand: caches AI-resolved actions back to native Playwright selectors for near-zero-cost repeat runs | None of these are testing tools per se — they are the *substrate* a Planner/Generator could be built on top of, not a finished pipeline |
| **Academic prototypes** (UMTG, NAT2TESTSCR, CiRA, spec-test-generator OSS tool) | Requirements → test traceability with formal linkage | Real traceability matrices | Only work on controlled/templated NL input; fully generative LLM systems (what most hackathon teams will build) produce **no traceability artifact at all** — an open research gap you can actually close in a weekend |

**What remains unsolved across all of them**: nobody ships a single system that autonomously **sequences** planning → generation → execution → healing → reporting, makes its own re-plan/escalate decisions, and produces requirements-traceable, confidence-scored output — which is *exactly* the PDF's ask. This is a genuine, currently-open gap, not a solved problem the organiser is asking you to reinvent.

### 2.4 Research & Evidence on Scale of the Problem
- Google's internal data: flaky tests alone consume roughly **16% of developer time / test compute**, at an estimated **$1.6M/year** cost for a 50-engineer team at $200k fully loaded cost.
- A peer-reviewed 2025 arXiv study (Parry et al.) measured developers spending **1.28%** of working time specifically *repairing* flaky tests; a separate 2025 industry analysis put enterprise-team flaky-test cost at **~8% of QA time (~$120k/year for 50 engineers)**.
- Slack's engineering team publicly documented flaky **mobile** test rates as high as **56.76%**, reduced to **3.85%** after building automated flaky-test detection — saving an estimated **553 hours** of triage time.
- Bitrise's 2025 Mobile Insights report (10M+ builds, 3.5 years) found the share of teams experiencing flakiness grew from **10% (2022) to 26% (2025)** — the problem is getting worse, not better, as release velocity increases.
- A widely-cited developer survey (Eck et al.) found **58–59%** of developers deal with flaky tests **at least monthly**, and of those, **79%** rate it a moderate-to-serious problem.
- GitHub-scale data: **1 in 11 commits (9%)** had at least one red build caused specifically by a flaky test in a large sample year.
- Async/timing issues are the **#1 root cause** of flakiness (~45% of observed flakes per Luo et al., University of Illinois), followed by selector fragility, test-order/shared-state dependency, network variability, and headless-vs-headed environment differences.

**Takeaway for your pitch deck**: you don't need to invent a statistic — you can cite Google's 16%/$1.6M figure and Slack's 56.76%→3.85% case study directly as your "business impact" slide (worth 10% of the score) and as demo narrative for why the Healer's classification matters.

### 2.5 Useful Resources for the Build
| Resource | How it helps |
|---|---|
| **Playwright** (with its accessibility-tree snapshot API and codegen) | Best execution/generation substrate — accessibility-tree-based locators are the modern, standards-based (`get_by_role`) way to make Generator output robust from the start, reducing how often the Healer is even needed |
| **browser-use** (open-source Python, DOM/accessibility-tree based, Playwright-driven) | Good fit for the **Planner**'s exploration phase — cheap relative to vision-based agents, good for crawling/mapping flows |
| **Skyvern** (open-source, AGPL-3.0, vision+LLM, MCP-compatible) | Alternative/backup Planner engine if a target app is very visual or has non-standard DOM (canvas-heavy apps); note AGPL obligations if you redistribute a modified version |
| **Stagehand** | Demonstrates the "cache the AI-resolved action as a native selector" pattern — directly reusable design for your Generator+Healer cost strategy |
| **Healenium** (open-source, EPAM) | Reference implementation for **zero-LLM-cost** healing via DOM tree-comparison (LCS algorithm) — build your Healer's first-tier fallback on this pattern before ever calling an LLM |
| **arXiv 2603.20358** ("Beyond LLM-based test automation") | Directly gives you a **ten-tier priority-ranked locator hierarchy** (`get_by_role` → `data-testid` → ARIA labels → CSS fragments → visible text) — implement this almost verbatim as your Generator's selector strategy |
| **LangGraph** | Best-fit orchestration framework for the **meta-agent**: explicit state graph, conditional edges, native checkpointing/interrupts for human-in-the-loop escalation, strongest audit/observability story — matches the PDF's demand for the meta-agent to "decide when to re-plan or escalate" |
| **CrewAI** | Faster to prototype if the team is short on time — role-based crews map naturally onto Planner/Generator/Healer, at the cost of less explicit control over conditional branching than LangGraph |
| **OWASP Juice Shop / SauceDemo / ParaBank / Cypress Real World App / the-internet.herokuapp.com** | Free, stable, well-known demo apps with real login flows, checkout flows, and (Juice Shop) deliberate edge cases/bugs — ideal **bring-your-own test target** per the PDF's explicit advice, and Juice Shop in particular gives you genuine "bugs" to let your Healer correctly classify as real defects, not flaky scripts |
| **spec-test-generator** (open-source PyPI package) | Reference implementation for PRD → requirements extraction → stable-ID traceability matrix — directly reusable for the Bonus "PRD-to-test-plan gap analysis" requirement |
| **FlakeFlagger / FlaKat / NeuroFlake / Parasoft DTP write-ups** | Give you concrete, cheap **feature sets** (rerun history, static code features, keyword patterns) for a lightweight flaky-vs-real-defect classifier, without needing your own labeled dataset from scratch |
| **WebVoyager / WebArena benchmark literature** | Calibrates your expectations: even frontier agents (Claude Computer Use ~77.5%, GPT-4o computer-use agent ~58%, and only the newest specialized systems like Surfer 2 hit 90%+) do **not** reliably complete complex multi-step web tasks — budget for Planner retries and graceful partial-coverage reporting rather than assuming 100% exploration success |

---

## PART 3 — HIDDEN INSIGHT INVESTIGATION

For each: **Insight → Evidence → Why it matters → Response**

**1. The PRD says "URL only" but real apps need credentials — this is the spec's biggest hidden trap.**
Evidence: 1.12 above; nearly every non-trivial demo app has an auth wall.
Why it matters: teams that build a Planner assuming no-login apps will fail live, on the organiser's surprise target, in front of judges.
Response: design credential injection (env vars / a secure config step) from day one, even though it's not in the Must-Have input list; treat "URL + optional creds" as the real contract.

**2. LLM-first selector resolution is a cost and latency trap, not just an academic footnote.**
Evidence: arXiv 2603.20358 explicitly frames per-run LLM selector discovery as "prohibitive at enterprise scale"; every mature production healer (Healenium, Testim, Katalon's first tier) defaults to deterministic matching and only escalates to LLM calls as a last resort.
Why it matters: a naive team that calls an LLM on every element lookup will (a) blow through demo time, (b) blow through their self-funded API budget mid-hackathon, and (c) look less "engineered" to judges who know this trade-off.
Response: implement a **tiered Healer** — deterministic accessibility-tree/attribute matching first, LLM vision/semantic fallback only on total miss. This alone is a strong technical-depth talking point for the 20% "technical implementation" score.

**3. "Confident" defect classification (flaky vs. real bug) is an open research problem, not a solved one — set expectations accordingly.**
Evidence: multiple 2025–2026 papers (NeuroFlake, FlaKat, "Can We Classify Flaky Tests Using Only Test Code?") still treat this as active research; production tools like Parasoft DTP require a human-labeled training set of at least 5 instances per class before they'll even train a model.
Why it matters: judges will reward *honest, evidence-backed* confidence scoring far more than a black-box "AI says it's a bug" claim with no rationale — and will penalize overclaiming.
Response: build a rule-based/evidence-based classifier first (did the DOM structure change vs. did an assertion value change vs. did a network call fail vs. did the same test fail on 3 consecutive re-runs with different timing), and only add an LLM layer to *explain* the evidence, not invent it from nothing.

**4. Test *count* is not test *value* — recent research directly contradicts the instinct to maximize generated test volume.**
Evidence: "Rethinking the Value of Agent-Generated Tests" (Feb 2026) found no significant relationship between agent-generated test volume and actual task-resolution outcomes.
Why it matters: many teams will optimize their demo for "look how many tests we generated," which is exactly the wrong signal per both the research and the PDF's own emphasis on "meaningful" coverage over completeness.
Response: report *risk-weighted* coverage (which user flows are covered, which are missing, and why they were deprioritized) rather than a raw test count.

**5. Even state-of-the-art browser agents fail 20–40% of complex tasks — plan for partial success, not perfection.**
Evidence: WebArena human baseline is ~78% while even strong 2025-era agents scored 38–58%; the hardest current benchmarks (WebBench) top out near two-thirds success; task success drops ~31.6% moving from easy to medium difficulty tasks and a further ~15.4% moving to hard.
Why it matters: a team whose demo narrative implicitly promises "the agent explores everything perfectly" will visibly break live. A team whose meta-agent gracefully reports "I explored X of Y flows, here's what I couldn't reach and why" looks more mature and directly satisfies the PDF's explicit "untested flow risk" reporting requirement.
Response: build the escalation/graceful-degradation path as a first-class feature, not an afterthought — this is also literally one of the Must-Have behaviors (meta-agent decides "when to re-plan or escalate").

**6. Silent selector "healing" can mask real regressions — this is a known, named failure mode in the self-healing literature.**
Evidence: industry write-ups explicitly warn that the "dangerous failure mode is silent substitution — the healing engine picks a visually similar but functionally wrong element, the test passes, and a regression ships."
Why it matters: this is precisely the ambiguity the PDF leaves open (see 1.12.3) about what the Generator/Healer should do on validation failure — and it's a place a judge with QA experience will specifically probe with an adversarial question.
Response: every heal must be logged with a confidence score and a "why" (attribute similarity delta, structural distance, etc.), and any heal below a confidence threshold should be flagged as "needs review" in the final report rather than silently accepted.

**7. Non-modern / server-rendered apps are the accessibility-tree strategy's blind spot — and are exactly the kind of app a hackathon judge might bring as a surprise target.**
Evidence: the ten-tier locator hierarchy (get_by_role → data-testid → ARIA → CSS → text) degrades in effectiveness on legacy markup without semantic HTML or ARIA roles.
Why it matters: your "works against any web application" claim (an explicit PDF requirement) is at real risk if you only test against modern SPA demo apps.
Response: include at least one deliberately old-school, table-based or minimally-semantic demo target (e.g., the-internet.herokuapp.com or a plain HTML form app) in your own testing before the event, not just SauceDemo/Juice Shop.

**8. Vision-based fallback dramatically increases cost/latency but is your only real answer for canvas/WebGL-heavy or oddly-styled UIs — decide this trade-off explicitly rather than by accident.**
Evidence: benchmarking articles note the visual-vs-DOM perception trade-off directly (Skyvern = vision-first, browser-use/Playwright MCP = structured/DOM-first) and that vision-based analysis is markedly more accurate but more expensive per step.
Why it matters: if you don't decide this up front, you'll end up ad-hoc-mixing both approaches under time pressure during the actual event.
Response: pick DOM/accessibility-tree-first as your default posture (cheap, fast, matches Playwright's own native strengths) with vision as an explicit, clearly-logged last-resort fallback — and say so out loud in your architecture diagram, since judges reward stated trade-offs (5% of score is literally "ability to explain trade-offs").

---

## PART 4 — CHALLENGE THE PROBLEM STATEMENT

- **Is the stated problem the root problem, or a symptom?** It's mostly the root problem — the PDF's own framing ("not execution, but decision-making") is unusually well-aimed for a hackathon brief. The one place it under-specifies the root problem is *trust*: the real reason teams don't fully delegate testing today isn't lack of capable tools, it's lack of confidence that an autonomous agent's output is *correct* and *safe to act on*. The PDF asks for a "test quality report" but doesn't explicitly ask for confidence calibration or audit trails — building those anyway is a differentiation opportunity, not scope creep.
- **Is the stated user the most important one?** The PDF frames the developer as the user. In practice, the more underserved and arguably more important beneficiary is the **team lead/reviewer** who has to trust the agent's report enough to actually act on it (merge, block, escalate) — designing the final report for a *decision-maker*, not just a developer, is a stronger product angle.
- **Is there a simpler way to solve this?** A simpler, non-agentic way would be a checklist-driven test generator with human review gates at each stage — but that's explicitly what the PDF says is *already the status quo* ("still carry the coordination burden themselves") and is explicitly Out of Scope in spirit (no human intervention between stages is Must Have). So no — full autonomy is genuinely the differentiator being asked for, not a nice-to-have.
- **What assumptions could be wrong, and what happens if they fail?**
  - Assumption: the target app is reachable and stateless enough to be explored safely. If false (app has irreversible side effects — e.g., real payments, real emails sent), an autonomous agent could cause real-world harm; you need a safety valve (dry-run/sandbox detection, or explicit non-destructive-action allowlisting).
  - Assumption: LLM cost is not a demo-day constraint. If your architecture makes many LLM calls per step, you risk hitting rate limits or running out of budget mid-demo — validated by 2.1's cost-of-LLM-healing research.
  - Assumption: judges will value more autonomy over more transparency. Based on the scoring weights (30% functionality, 20% innovation, 20% technical quality, 15% UX/demo clarity), transparency and explainability are collectively worth at least as much as raw autonomy — don't over-index on "look, zero human touches this."
- **What would prevent adoption in the real world?** Trust and liability (an autonomous agent that can submit forms/mutate data on a real app is a genuine governance concern for any real engineering org — this is *why* Aivar's own other product, Velogent, is specifically pitched as "governed agentic process automation for regulated industries" — governance is core to their own thesis, and echoing it in your pitch signals alignment with the organiser's worldview).
- **Why haven't existing companies solved this already?** Commercial incentives favor selling a point solution (generation, or healing) as a wedge product with fast time-to-value, rather than the harder, less immediately monetizable "coordinate everything and know when to stop" layer — which is a genuinely good venture-scale insight to say out loud in your pitch, given the audience is Bessemer Venture Partners-backed.
- **What would make our solution fail in the real world?** Overfitting the Planner to the exact demo target apps you test against in practice (defeating the "works against any web application" requirement), and any silent-healing failure mode (see hidden insight #6).

**Reframed problem statement (optional, for your own clarity, not a replacement for the PDF's)**: *"Build a meta-agent that not only automates the testing lifecycle end-to-end, but produces a transparent, confidence-scored decision trail that a human reviewer can trust enough to act on without re-doing the work."* This reframing doesn't change what you build — it changes what you *emphasize* in the demo and report, directly targeting the 20%+15% of the score that rewards judgment and clarity, not just raw automation.

---

## PART 5 — FIND THE OPPORTUNITY

**Biggest pain point**: the coordination/judgment gap (root cause, 2.1).
**Most underserved user**: the human reviewer who has to trust the agent's output, not just the developer who triggers it.
**Highest-value use case**: turning a fresh, undocumented app into a trustworthy baseline test suite with zero manual scripting.
**Biggest existing gap**: no current tool couples full pipeline autonomy with requirements traceability and calibrated confidence (2.3, 2.5).
**Biggest technical opportunity**: a tiered, cost-aware Healer (deterministic-first, LLM-fallback) combined with a transparent meta-agent decision log.
**Biggest differentiation opportunity**: explainable, evidence-backed defect classification + a decision-audit trail, versus competitors who black-box the "AI decided" step.

### 5.1 Solution Directions (5–10, scored)

| # | Direction | User value | Innovation | Feasibility (hackathon) | Differentiation | Scalability | Demo potential | Impact |
|---|---|---|---|---|---|---|---|---|
| 1 | **Baseline pipeline**: LangGraph meta-agent orchestrating Planner (browser-use/Playwright)→Generator (Playwright codegen + LLM)→Healer (Healenium-style tiered healing)→Reporter | 8 | 6 | 9 | 5 | 7 | 8 | 7 |
| 2 | Direction 1 **+ explainable defect classifier** (evidence-based rules + LLM rationale, confidence scores surfaced in report) | 9 | 8 | 8 | 9 | 7 | 9 | 8 |
| 3 | Direction 2 **+ PRD-to-test-plan traceability matrix** (stable requirement IDs, coverage %, gap list) | 9 | 8 | 7 | 8 | 8 | 8 | 8 |
| 4 | **Risk-based coverage prioritization**: meta-agent ranks flows by business-criticality (auth, checkout, payment keywords) rather than exploring uniformly | 8 | 7 | 7 | 7 | 8 | 7 | 8 |
| 5 | **Human-in-the-loop escalation UX**: meta-agent pauses and asks a targeted question only when genuinely stuck (e.g., ambiguous CAPTCHA/2FA), otherwise fully autonomous | 8 | 7 | 6 | 8 | 6 | 9 | 7 |
| 6 | **Multi-target parallel run**: same pipeline run against 2+ demo apps simultaneously to prove generalization live during the demo | 6 | 5 | 6 | 6 | 6 | 9 | 5 |
| 7 | **Cost/latency dashboard**: live view of LLM calls avoided via deterministic healing vs. LLM-fallback calls made, with running $ cost estimate | 6 | 7 | 8 | 7 | 6 | 8 | 6 |
| 8 | **Regression-diff mode**: run the pipeline twice (before/after a code change) and have the meta-agent explain *what broke and why* across runs | 7 | 8 | 5 | 8 | 7 | 8 | 7 |
| 9 | Vision-fallback for canvas/legacy apps as an explicit last-resort tier | 6 | 6 | 5 | 6 | 6 | 6 | 5 |
| 10 | Fully no-code natural-language scoping UI ("focus on checkout and auth") | 7 | 5 | 7 | 5 | 7 | 7 | 6 |

**Reasoning highlights**: Direction 1 alone satisfies Must-Haves but scores only moderately on innovation/differentiation — it's table stakes. Directions 2+3 stacked on top of it are what actually move the needle on the 20% innovation and 20% technical-quality weights, and they're realistically buildable in a weekend using the open-source references in 2.5 (rather than novel research). Direction 5 (light human-in-the-loop escalation) scores high on demo potential because it's a visually compelling, judge-legible moment ("watch it correctly ask for help instead of guessing wrong") without violating the "no human intervention between stages" requirement — you're not making a human do steps *for* the agent, you're letting the agent request specific missing information (e.g., 2FA code) exactly once, which is a defensible reading of the spec, not a shortcut around it.

---

## PART 6 — THINK LIKE A HACKATHON JUDGE

**What most teams will build**: a Planner that calls an LLM to "explore," a Generator that asks an LLM to "write Playwright code," a Healer that re-asks the LLM to "fix the failing test," glued together with a simple sequential script (not a real state machine) and no coverage/confidence reasoning at all. This will demo *something* but will look like three chained prompts, not an orchestrator.

**Which approaches will feel generic**: any pipeline where the "meta-agent" is really just a for-loop calling three prompts in fixed order with no branching logic, no re-plan/escalate decision, and no visible reasoning trail.

**What judges are likely to reward**: visible, inspectable decision points (why did it re-plan? why did it call this a real bug and not a flaky failure? what confidence score, and why?); a report that reads like something a real engineering lead could act on; graceful handling of partial failure instead of a demo that silently breaks.

**What would make your project memorable**: showing the meta-agent *catch itself* — e.g., the Generator produces a test, live-selector-validation fails, the meta-agent decides to re-invoke the Planner for that one flow rather than giving up, and the report explicitly narrates that decision.

**Where you can demonstrate technical depth**: the tiered (deterministic-first, LLM-fallback) Healer design, and a defect classifier that shows its evidence rather than a bare LLM verdict.

**What creates a strong visual/demo experience**: a live dashboard (simple web UI is fine) showing the pipeline's state machine lighting up node-by-node in real time, plus the final report rendered clearly (scenarios, pass/fail, healer actions, gaps, risk).

**Measurable impact you can demonstrate**: "we generated N test cases covering M of the K flows we identified, healed X of Y failures automatically, correctly flagged Z as a real defect vs. flaky at C% confidence, in T minutes with $D of LLM spend" — a single slide with these numbers, tied back to the Google/Slack stats in 2.4 for context, is a strong business-impact close.

**Claims to avoid**: "100% autonomous, zero errors," "works on literally any website" without caveats, or any claim of defect-classification accuracy without showing your evidence — judges in this space (AWS-partner-backed, VC-backed organiser) will very likely include people who know the flaky-test literature and will probe overclaims specifically.

**Potential "wow moments"**: (1) the meta-agent visibly deciding to escalate/re-plan rather than fail silently; (2) the Healer explaining *why* it healed a locator instead of just doing it silently; (3) live PRD-gap analysis surfacing a requirement nobody wrote a test for, in real time, against a document the judges haven't seen before.

---

## PART 7 — DESIGN THE WINNING MVP

### 7.1 Must / Should / Nice / Don't Build

**Must Have (build this first, in this order):**
1. URL (+ credentials handling) input → Planner explores and outputs a structured, human-readable test plan (flows, steps, expected outcomes).
2. Meta-agent coverage-gap check on the plan (missing flows/edge cases/error states) before generation — even a simple checklist-based heuristic (login, primary CRUD action, at least one negative-path/error case per flow) satisfies this.
3. Generator converts plan → Playwright test files, validating every selector against the live DOM before finalizing a test (tiered locator strategy, 2.5).
4. Execution + tiered Healer (deterministic tree/attribute matching first, LLM fallback only on miss) + basic defect classification (rule-based signals: DOM-diff vs. timing-diff vs. assertion-value-diff).
5. Final report: scenarios covered, pass/fail, healer actions + confidence, coverage gaps, untested-flow risk — rendered as both a file and a simple UI view.

**Should Have (adds real judging-criteria value, build if Must-Have is solid by the halfway mark):**
- Optional PRD ingestion to scope the Planner and produce a basic traceability list.
- Natural-language scoping ("focus on checkout and auth").
- Parallel execution of independent flows.
- Confidence scores and a visible decision log for every meta-agent branch (re-plan/escalate/proceed).

**Nice to Have (only with real time left):**
- PRD-to-test-plan formal gap analysis with a stable-ID traceability matrix.
- Live cost/latency dashboard (LLM calls saved vs. spent).
- Multi-target parallel demo run.
- Vision-based fallback tier for non-standard UIs.

**Don't Build (impressive-sounding, wastes hackathon time):**
- Full CI/CD integration — explicitly Out of Scope.
- Cross-browser matrix testing — explicitly Out of Scope.
- A custom-trained ML flakiness classifier from scratch — the labeled-data requirement alone (Parasoft DTP needs 5+ examples per class) makes this infeasible in a weekend; use rule-based evidence + LLM rationale instead.
- A polished multi-tenant SaaS dashboard/auth system for your *own* tool — judges are grading the testing agent, not your product's login page.
- Production hosting/deployment — explicitly Out of Scope.

### 7.2 System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         META-AGENT (Orchestrator)                     │
│              LangGraph state machine — the "brain"                    │
│  State: {url, creds, prd?, plan, coverage_gaps, generated_tests,      │
│          run_results, heal_log, defect_classifications, report}       │
│                                                                        │
│   [Start] → plan → evaluate_coverage → (re-plan?) → generate →        │
│   validate_selectors → (regenerate?) → execute → heal → classify →    │
│   (escalate?) → synthesize_report → [End]                             │
└──────────────────────────────────────────────────────────────────────┘
        │                │                │                │
        ▼                ▼                ▼                ▼
┌───────────────┐ ┌────────────────┐ ┌───────────────┐ ┌───────────────┐
│  PLANNER       │ │  GENERATOR     │ │  EXECUTOR      │ │  HEALER +     │
│  sub-agent     │ │  sub-agent     │ │  (not an LLM   │ │  CLASSIFIER   │
│                │ │                │ │   agent —      │ │  sub-agent    │
│                │ │                │ │   deterministic│ │               │
│                │ │                │ │   runner)      │ │               │
└───────────────┘ └────────────────┘ └───────────────┘ └───────────────┘
```

### 7.3 Agent-by-Agent Breakdown: Tools, Inputs, LLM Usage, Tech Choices

| Agent | Purpose | Inputs | Tools / Modules | Where the LLM is used | Where it's NOT used (deterministic) | Recommended tech |
|---|---|---|---|---|---|---|
| **Meta-Agent (Orchestrator)** | Sequences the pipeline; decides re-plan/escalate/proceed; synthesizes final report | Full pipeline state (plan, coverage gaps, run results, heal log) | State graph runtime; a rules layer for coverage-gap heuristics | Judgment calls needing reasoning over ambiguous evidence (e.g., "is this coverage gap acceptable given the PDF's Out-of-Scope list?"); report narrative generation | The state transitions themselves (graph edges) are deterministic code, not LLM decisions — the LLM informs *inputs* to the decision, the graph enforces the decision *logic* | **LangGraph** (Python) — native checkpointing/interrupts give you the "escalate to human" pause for free, and step-level tracing (LangSmith or a custom log) satisfies the demo-clarity criterion directly |
| **Planner sub-agent** | Explore the live app, produce a structured, human-readable test plan of meaningful flows | URL, credentials, optional PRD text, optional NL scoping intent | Browser driver (Playwright), accessibility-tree/DOM snapshot extraction, a crawl/graph-builder to track visited states | Interpreting page structure and content to decide "what is a meaningful user flow" (e.g., recognizing a checkout form vs. a marketing footer); converting the crawl graph into human-readable plan text; incorporating PRD/NL intent into scope | Basic navigation/crawling logic (link discovery, form field enumeration) can be done without an LLM using the accessibility tree alone | **browser-use** (Python, DOM/accessibility-tree based, cheaper) as default; **Skyvern** as a vision-based fallback for canvas-heavy/legacy UIs; LLM: any strong reasoning model with tool-calling (e.g., Claude or GPT-4-class) for the "what is meaningful" judgment step |
| **Generator sub-agent** | Convert the plan into executable, validated Playwright test files | Structured plan (from Planner), live DOM access for selector validation | Playwright codegen conventions; the 10-tier locator-priority hierarchy (get_by_role → data-testid → ARIA → CSS fragment → text) from arXiv 2603.20358 | Writing the actual test code (assertions, step sequencing) from the plan's natural-language steps; deciding *which* of the 10 locator tiers is safest for a given element when multiple tiers are ambiguous | Selector *validation* itself (does this locator resolve to exactly one element right now?) is deterministic — run it against the live page, don't ask the LLM whether it thinks it'll work | Playwright (Python or TS) for execution; LLM only for code synthesis, with a deterministic post-generation validation pass (run each generated locator against the live DOM before accepting the file) |
| **Executor** | Run the generated suite | Generated test files | Playwright Test Runner | None — this should be a pure deterministic runner, no LLM involved at all | All of it | Playwright Test (native runner, parallelizable) |
| **Healer sub-agent** | On failure, repair broken locators/flows OR flag as a real defect | Failing test, stored "last-known-good" element fingerprint, current live DOM | Tier 1: deterministic tree-comparison/attribute-similarity matching (Healenium-style, LCS algorithm) against the stored fingerprint. Tier 2 (only on Tier-1 miss): LLM given DOM/accessibility-tree + screenshot to semantically re-identify the element | Tier-2 semantic re-identification only; and generating the human-readable "why I healed this" explanation | Tier-1 deterministic matching handles the majority of real-world locator drift at zero LLM cost — reserve the LLM for genuine structural rewrites | Implement your own lightweight Healenium-style LCS/attribute-fingerprint matcher (no need for the Java/Docker/Postgres original — a Python re-implementation against Playwright's accessibility tree is enough for a hackathon); LLM (vision+text) only as fallback |
| **Defect Classifier** (paired with Healer) | Decide: is this failure a broken locator/flaky test, or a genuine application bug? | Failure evidence: DOM diff, timing/retry pattern across N re-runs, whether an *assertion value* changed vs. whether an *element* went missing, network/console error logs | Rule-based evidence engine (multi-signal, inspired by FlakeFlagger/FlaKat feature sets: rerun consistency, code-change correlation, error-message pattern) | Only for producing a natural-language rationale/summary of the evidence and a calibrated confidence score — never as the sole source of the verdict | The evidence-gathering (re-run N times, diff DOM state, check if a value vs. a selector changed) is 100% deterministic and should run *before* any LLM is consulted | Simple Python rule engine to start; optionally fine-tune/prompt an LLM only to explain evidence already computed, never to invent it |
| **Reporter** | Synthesize final test-quality report | All state: plan, coverage gaps, generated tests, run results, heal log, classifications | Templating engine; optional PRD-traceability matrix builder (spec-test-generator pattern) | Turning structured data into a clear, readable narrative report for a human reviewer | Computing the actual metrics (% coverage, counts, confidence averages) is deterministic aggregation, not an LLM task | Markdown/HTML report generator; LLM only for the narrative summary paragraph, not the numbers |

### 7.4 Frontend / Backend / Data / Auth / Deployment / Monitoring / Security (hackathon-scoped)

- **Frontend**: a minimal web dashboard (single-page) showing pipeline state machine progress live + final report — build this in your usual stack (React is fine); this directly serves the 15%-weighted UX/demo-clarity criterion.
- **Backend**: a Python service hosting the LangGraph app, exposing a simple REST/WebSocket API for the frontend to stream pipeline state.
- **Database**: none required at hackathon scale — a local SQLite file or even in-memory state is enough to store the "last-known-good" element fingerprints for the Healer between runs; don't over-engineer this (Production deployment is explicitly Out of Scope).
- **APIs**: your chosen LLM provider's API (Claude/GPT/etc. — team-supplied key per the PDF's constraint); Playwright's own APIs; no other external API is required.
- **AI/ML/LLM components**: as tabulated in 7.3 — used specifically at judgment points (meaningful-flow interpretation, code synthesis, semantic locator fallback, defect rationale, report narrative), never for anything that has a deterministic, verifiable answer.
- **Data pipeline**: crawl graph (Planner) → structured plan (JSON) → generated test files → execution results (JSON) → heal log (JSON) → final report (Markdown/HTML) — keep every intermediate artifact as inspectable JSON; this is what makes your demo "explainable" rather than a black box, and it's cheap insurance for judges who ask "show me your architecture diagram" literally.
- **Authentication (of your own tool)**: none needed — this is a hackathon prototype, not a product; spend zero time here.
- **Authentication (of the app under test)**: explicit config for injecting credentials (env vars / a config field) since the formal PDF's "URL-only" input needs a practical answer for login walls (hidden insight #1).
- **Deployment**: local/dev only — explicitly Out of Scope to deploy at scale.
- **Monitoring**: a simple structured log of every meta-agent decision (re-plan/escalate/proceed) with timestamps and rationale — doubles as your audit trail and your demo narration script.
- **Security considerations**: never let the agent autonomously perform financial/destructive actions without a clearly logged, explicit allow decision; treat any form submission that looks like "delete," "pay," "send," or similar as needing an extra confirmation gate even in "full autonomy" mode — a small design touch that visibly answers the "regulated industries / governance" theme the organiser's own other products (Velogent) are built around.

**What to build vs. reuse:**
- Build yourselves: the meta-agent's graph/decision logic, the coverage-gap heuristic, the defect-classification rule engine, the report synthesis, the credential-injection handling.
- Reuse from open source: Playwright itself, browser-use/Skyvern for exploration substrate, the Healenium LCS-matching *pattern* (re-implement lightweight, don't need the full Java stack), the spec-test-generator PRD-parsing pattern, LangGraph for orchestration.

---

## PART 8 — DATA & TECHNICAL FEASIBILITY

- **What data is required**: none upfront — this system operates on a *live* target app at runtime, not a static dataset. The only "dataset" you need is a handful of demo target apps for your own testing before the event.
- **Where to get it / is it public**: yes, fully public and free — OWASP Juice Shop (self-hostable via Docker, deliberately buggy — great for defect-classification demos), SauceDemo (stable e-commerce demo, multiple login personas including a deliberately broken "problem" user), ParaBank (banking flows + APIs), Cypress Real World App, the-internet.herokuapp.com (legacy-style markup, good generalization test).
- **Dataset size / quality / licensing**: not applicable in the traditional sense; all suggested demo apps are open-source/MIT-licensed and safe to test against aggressively (note: Skyvern itself is AGPL-3.0 — fine to use as a tool, be aware of its license terms only if you redistribute a modified copy of Skyvern itself, not for using it against a target app).
- **Is synthetic data acceptable**: yes — for the PRD-ingestion feature, write your own short synthetic PRD (2–3 pages) describing the demo app's intended flows so you can show live PRD-to-test-plan gap analysis without depending on a real client document.
- **How to build a convincing demo if the organiser's surprise app misbehaves**: always have your own bring-your-own target (Juice Shop or SauceDemo) as the guaranteed-to-work fallback recording, and attempt the organiser's live app second, exactly as the PDF itself recommends ("bring your own test target... don't wait for these").

---

## PART 9 — ATTACK OUR PROPOSED SOLUTION (Adversarial Review)

| Attack vector | Failure mode | Mitigation |
|---|---|---|
| Bad inputs | Malformed URL, unreachable app, expired/wrong credentials | Fail fast with a clear error state in the report, not a silent hang; meta-agent escalates immediately rather than looping |
| Missing data | No PRD supplied (it's optional) | Planner must function fully without a PRD — never hard-depend on the Should-Have feature for Must-Have behavior |
| Incorrect AI predictions | Generator hallucinates a selector that happens to validate against the wrong element | Post-generation validation must check *uniqueness* (exactly one match) and ideally a semantic sanity check (does the element's role/text match the plan step's intent), not just "does a match exist" |
| Adversarial behavior | The target app itself has anti-bot/CAPTCHA measures (documented failure mode even for SOTA agents like Surfer 2 on WebVoyager) | Detect CAPTCHA/anti-bot patterns and escalate/report as "untestable — anti-automation measure detected" rather than retrying forever |
| Scale | Deep app with hundreds of flows | Meta-agent must risk-prioritize (auth, checkout/core-value flows first) and explicitly report what it chose not to explore, given the time budget — this is explicitly allowed since "complete coverage" is Out of Scope |
| Cost | Runaway LLM calls from the Healer's Tier-2 fallback | Hard per-run budget/step cap; Tier-1 deterministic healing must genuinely run first, always |
| Latency | Live demo takes too long | Parallelize independent flow generation/execution (a Good-to-Have anyway); pre-warm the target app; cap Planner exploration depth |
| Privacy | Credentials handled insecurely (logged in plaintext, committed to the demo repo) | Never log raw credentials; use env vars/gitignored config; redact in the decision log |
| Security | Agent submits a real payment/destructive action on a live surprise target app | Confirmation-gate for anything matching destructive-action keywords (Part 7.4); never test against production financial systems |
| User rejection | A judge/reviewer doesn't trust the "AI decided it's a real bug" verdict | Always show the underlying evidence, not just the verdict (hidden insight #3, #6) |
| Regulatory problems | N/A at hackathon scale, but worth naming in your deck given the organiser's regulated-industries thesis (Velogent) | Mention governance/audit-trail design as a forward-looking consideration in your pitch, even if not fully implemented |
| Unexpected edge cases | Multi-step flows spanning multiple tabs/windows, or apps requiring 2FA | Explicitly out of scope for a first pass — report as a known limitation rather than attempting and failing silently |

---

## PART 10 — FINAL RECOMMENDATION

1. **The Real Problem**: Existing AI testing tools have automated individual steps (generation, healing) but not the *judgment* of sequencing them, evaluating coverage, and deciding when a failure is real — that coordination and trust gap is what's actually unsolved.

2. **The Hidden Insight**: The PDF's own input contract is ambiguous about credentials, and the entire self-healing industry has already learned the hard way that LLM-first element resolution is too costly and too opaque — a tiered, evidence-first, cost-aware architecture is both cheaper to build under hackathon constraints *and* the technically correct answer.

3. **The Biggest Gap**: No existing tool — commercial or open-source — couples full pipeline autonomy with transparent, evidence-backed defect classification and requirements traceability in one system.

4. **The Winning Idea**: A LangGraph-orchestrated meta-agent coordinating Planner (browser-use/Playwright, accessibility-tree based) → Generator (Playwright codegen with a 10-tier locator strategy and live validation) → tiered Healer (deterministic-first, LLM-fallback) with an evidence-based defect classifier, closing with a transparent, confidence-scored, PRD-traceable report.

5. **Why It Can Win**: It directly targets the 70% of the rubric weighted toward orchestration intelligence, technical depth, and demo clarity — rather than competing on raw test-generation volume, which research shows doesn't even correlate with real value.

6. **Core Differentiator**: Every autonomous decision (re-plan, escalate, heal, classify) is logged with its evidence and confidence — the system is explainable by design, not a black box that happens to work.

7. **MVP**: See Part 7.1 — Must-Have list, in the stated order, is achievable in a hackathon weekend using entirely off-the-shelf open-source components.

8. **Architecture**: See Part 7.2–7.3 — LangGraph orchestrator, browser-use/Playwright-based Planner, Playwright-codegen Generator, tiered deterministic-then-LLM Healer, rule-based defect classifier, templated Reporter.

9. **Data/APIs**: No dataset needed — live target apps (Juice Shop, SauceDemo, ParaBank as bring-your-own fallback); team-supplied LLM API key; all core libraries (Playwright, LangGraph, browser-use) are free and open-source.

10. **Demo (2–3 min storyline)**: (0:00) State the coordination-gap problem with the Google/Slack stats. (0:20) Point the agent at a live URL with zero further input. (0:40) Show the dashboard lighting up: Planner discovers flows → meta-agent flags a coverage gap and re-scopes → Generator writes and validates tests live → Executor runs them → one test fails → Healer tries deterministic healing (visible, fast) → falls back to LLM semantic re-identification on a genuinely broken locator (visible, log shown) → classifier correctly identifies a seeded real bug (e.g., in Juice Shop) with its evidence shown, not just a verdict → final report renders with coverage %, healed count, flagged defect, and honest "untested flow risk" section. (2:30) Close on the business-impact slide tying back to the cited statistics.

11. **Risks**: LLM cost/latency blowup (mitigated by tiering), live demo target misbehaving (mitigated by bring-your-own fallback), overclaiming autonomy/accuracy (mitigated by always showing evidence), credential-handling ambiguity (mitigated by designing for it proactively).

12. **Next Steps for the Team, Immediately**:
    - Stand up Juice Shop and SauceDemo locally today; write your synthetic 2-page PRD for one of them.
    - Prototype the LangGraph state machine skeleton first (even with stub node functions) so the orchestration logic — the highest-weighted judging criterion — is real before the sub-agents are fully built.
    - Implement the Generator's 10-tier locator hierarchy and live-validation pass before touching the Healer — a correct Generator needs a healer far less often.
    - Build the Healer's deterministic Tier-1 matcher before writing a single LLM-based fallback prompt.
    - Design the credential-injection mechanism and the destructive-action confirmation gate now, not the night before the demo.

---

## WHAT MOST HACKATHON TEAMS WILL MISS

1. **Assumption**: "The PDF says URL-only input, so we don't need to handle login." **Reality**: nearly every real target app requires auth to reach "meaningful flows," and the video brief even mentions credentials explicitly. **Evidence**: 1.12.1. **Advantage**: your Planner reaches real flows a URL-only competitor never sees.

2. **Assumption**: "More generated tests = a better score." **Reality**: research shows agent-generated test volume has no measurable correlation with real task value, and the rubric explicitly rewards "meaningful," not "complete," coverage. **Evidence**: 2.1, "Rethinking the Value of Agent-Generated Tests" (Feb 2026). **Advantage**: a risk-prioritized, honestly-scoped test plan reads as more sophisticated than a bloated one.

3. **Assumption**: "Self-healing means calling an LLM whenever a selector breaks." **Reality**: state-of-the-art production healers (Healenium, Testim, Katalon Tier 1) default to zero-cost deterministic matching and only escalate to LLMs as a last resort, because per-run LLM-based discovery is documented as cost-prohibitive at scale. **Evidence**: 2.1, 2.5, Part 3 insight #2. **Advantage**: dramatically lower demo-day cost/latency risk, and a genuinely more "senior engineer" architecture story.

4. **Assumption**: "We should say our classifier is highly accurate at telling flaky tests from real bugs." **Reality**: this is still active academic research territory with no settled solved approach; production tools require labeled training data most teams won't have. **Evidence**: Part 2.3, Part 3 insight #3. **Advantage**: showing your evidence instead of an unfounded accuracy claim builds more judge trust and avoids an easy "prove it" gotcha question.

5. **Assumption**: "Our agent should silently fix any broken locator it finds." **Reality**: silent healing is a named, documented failure mode that can mask real regressions by substituting a visually-similar-but-wrong element. **Evidence**: Part 3 insight #6. **Advantage**: a confidence-gated "flag for review" path is both more correct and a stronger demo moment.

6. **Assumption**: "Autonomous web agents reliably explore complex apps." **Reality**: even frontier-model computer-use agents complete well under 100% of complex multi-step tasks on published benchmarks (WebArena human baseline ~78% vs. most agents well below that; task success drops steeply with task complexity). **Evidence**: Part 2.5, Part 3 insight #5. **Advantage**: designing for graceful partial coverage and honest "untested flow risk" reporting turns an inherent limitation into a Must-Have feature you're already required to build.

7. **Assumption**: "The organiser's problem statement is just about testing tools." **Reality**: the organiser's own broader product portfolio (Velogent = "governed agentic process automation for regulated industries") signals that *governance, auditability, and trust* in autonomous agents is their actual strategic lens. **Evidence**: PDF's "About Aivar Innovations" section. **Advantage**: framing your differentiator around explainability/audit trails (not just raw autonomy) directly resonates with the judging organisation's own thesis.

8. **Assumption**: "PRD ingestion and PRD-gap-analysis are two names for the same feature." **Reality**: the PDF lists them as two separate items (Good-to-Have: PRD scopes the Planner upfront; Bonus: PRD-vs-test-plan gap analysis after generation) — different mechanisms, same underlying document. **Evidence**: 1.12.5. **Advantage**: building one shared PRD-parsing module that feeds both features is more efficient than teams who treat them as unrelated asks.

9. **Assumption**: "A modern SPA demo app is representative enough to prove our agent works on any web app." **Reality**: the accessibility-tree-first locator strategy that makes modern apps easy is exactly what makes legacy/server-rendered markup harder — generalization claims need a deliberately old-school test target to be credible. **Evidence**: Part 3 insight #7. **Advantage**: testing against the-internet.herokuapp.com (or similar) before the event catches generalization failures a judge might otherwise find live.

10. **Assumption**: "Our meta-agent's internal reasoning doesn't need to be shown, just its outputs." **Reality**: 15% of the score is explicitly "how clearly does the team present the agent's decisions and output," and 5% more is "ability to explain trade-offs" — together a fifth of the total score is about *visibility into reasoning*, not the reasoning's raw correctness. **Evidence**: 1.8. **Advantage**: a visible, real-time decision log/dashboard is not a nice-to-have UI polish item — it is directly, explicitly graded.

---

### Sources Consulted
Google/flaky-test productivity data (Visdom Maturity Matrix); Functionize flaky-test cost analysis; Bug0 true-cost-of-flaky-tests report; TestDino Flaky Test Benchmark 2026; Diffie Flaky Test Report 2026; Eck et al. flaky-test developer survey (arXiv 2203.00483); testquality.com Agentic QA Architecture; Shiplight AI agent-native QA and self-healing tool comparison guides; Logic Providers and DevAssure agentic-AI-testing overviews; qatechxperts Top 10 AI Automation Testing Tools 2026; sdet.qa Self-Healing Test Automation guide; Zylos Research on AI-powered automated test generation and "Rethinking the Value of Agent-Generated Tests"; Skyvern, browser-use, Stagehand, Playwright MCP comparison articles (aimultiple, digitalapplied, menuagentic); arXiv 2603.20358 (zero-cost self-healing via accessibility-tree extraction); Healenium documentation and independent guides (qaskills.sh, crosscheck.cloud, Augment Code, GitHub self-healing-locators); LangGraph/CrewAI/AutoGen comparison articles (n-ix, dev.to, pickaxe, gurusup, buildmvpfast, cordum, presenc.ai, pecollective); testomat.io, frugaltesting, and GitHub ai-testcase-generation-engine on LLM test generation from PRDs; arXiv 2606.06563 (AI-driven test case generation survey/gaps); arXiv 2604.25862 (RESTestBench); flaky-test classification research (arXiv 2502.04471, 2605.11482, 2403.01003, 2602.05465, 2502.02715); Parasoft DTP ML root-cause analysis; automationpanda.com and BMayhew/awesome-sites-to-test-on demo-app lists; OWASP Juice Shop official docs; WebVoyager (arXiv 2401.13919), WebArena benchmark literature, Magnitude/Surfer2/WebSight benchmark reports (arXiv 2508.16987, 2510.19949), Go-Browse (arXiv 2506.03533), Online-Mind2Web (OpenReview 6jZi4HSs6o).

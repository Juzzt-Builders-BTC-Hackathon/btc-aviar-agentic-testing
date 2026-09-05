# AIVAR — Autonomous Test Orchestration Agent

**Give AIVAR a website URL. Get a reusable test suite, verified locator repairs, and a Test Quality Report with browser evidence.**

Built for the Bessemer Tech Catalyst AI/ML problem statement. AIVAR coordinates **Planner → Generator → Executor → Healer → Defect Classifier**, evaluates coverage between stages, and records why it reused, extended, retried, repaired or escalated a test.

The focus is maintaining useful tests as a website changes. Repeat runs retain scenario IDs and expected results. Locator drift can be repaired after verification; changed expected behavior remains visible as a failure requiring investigation.

## High-level architecture

The pipeline runs **nine sequential stages**. Each stage is a distinct agent decision point — Python code controls every transition; OpenAI is called only for planning and constrained locator repair.

```mermaid
flowchart TB
    User(["👤 QA Engineer / Developer\n(URL · PRD · Scope · Interaction policy)"])

    subgraph Dashboard["🖥️ Dashboard  —  HTML / CSS / Vanilla JS  (ui/)"]
        UI_Submit["Submit run\nPOST /api/runs"]
        UI_Poll["Poll every 2 s\nGET /api/runs/:id"]
        UI_Results["Results · Planner · Decision log\nPRD coverage · Defect Classifier\nChanges & repairs · Artifacts · Export ZIP"]
    end

    subgraph Backend["🐍 Python Backend  —  FastAPI + Uvicorn  ·  port 8765  (qa_agent/)"]

        subgraph Gate["Entry Gate  (server.py · safety.py · models.py)"]
            API["REST API\nserver.py"]
            Admit["Admission guard\n— one active run —"]
            Policy["Policy gate\nURL allow-list · action DSL\ndestructive/payment block"]
            Contracts["Pydantic contracts\nRunRequest · Plan · Flow · Step\nHealProposal"]
        end

        subgraph Orchestrator["Meta-Orchestrator  (pipeline.py · triage.py)"]
            direction TB

            ExploreAgent["1️⃣  Explorer Agent\nbrowser.py · crawl()\n─────────────────\nTools: Playwright page.goto\n  DOM SNAPSHOT JS (elements · text · links)\n  network route logger\n  auth_state() — storage_state\nOutputs: recon.json"]

            PlannerAgent["2️⃣  Planner Agent\nplanning.py · evolution.py · llm.py\n─────────────────\nTools: previous_suite() — SQLite history\n  remap_requirements() — PRD delta\n  merge_plan() — dedup by signature\n  llm.plan() → OpenAI Responses API\n  baseline_plan() — deterministic fallback\nOutputs: requirements.json · plan.initial.json\n         suite_evolution.json"]

            CoverageAgent["3️⃣  Coverage Checker\nplanning.py · coverage()\n─────────────────\nTools: requirement-link audit\n  ground_oracles() — quoted-literal check\n  gap detector (negative/boundary/business)\nOutputs: coverage_gaps.json · plan.json\n  ➜ triggers one bounded re-plan if fixable gaps"]

            GenAgent["4️⃣  Generator\npipeline.py · export_suite()\n─────────────────\nTools: Pydantic Plan→JSON serialiser\n  suite.json + generated_tests.py writer\nAction DSL: navigate · fill · click\n  assert_text · assert_url · assert_visible\nOutputs: suite.json · generated_tests.py"]

            ValidateAgent["5️⃣  Validator\nbrowser.py · execute_flow(attempt=validation)\n─────────────────\nTools: Playwright locator.expect × 1 per flow\n  scope_ambiguous_selector() — nth-of-type scoping\n  DOM fingerprint capture\nOutputs: validation_report.json\n  scoped_regeneration hint on selector miss"]

            ExecuteAgent["6️⃣  Executor\nbrowser.py · execute_flow(attempt=run)\n─────────────────\nTools: Playwright fresh context per flow\n  page_error · HTTP-error diagnostics listener\n  screenshot capture (masked inputs)\n  PolicyError → blocked classification\nOutputs: run_results.json · *.png screenshots"]

            TriageAgent["7️⃣  Triage / Retry Node\ntriage.py · triage_flow()\n─────────────────\nTools: execute_flow(attempt=retry) — 1 unchanged replay\n  failure_kind detector (selector · assertion · execution)\n  agent_decisions transition log\nOutputs: retry result · transitions log"]

            HealerAgent["8️⃣  Healer Agent\nhealing.py · pipeline.py · repair()\n─────────────────\nTools: store.fingerprint() — SHA-256 element key\n  deterministic_candidate() — similarity ≥ 0.85\n  semantic_match() — tag + text/name/testid guard\n  llm.heal() → OpenAI (only if deterministic fails)\n  execute_flow(attempt=healed) — full-flow confirmation\n  identity gate: repairs limited to the failed locator only\nOutputs: heal_log.json · updated suite.json"]

            ClassifyAgent["9️⃣  Defect Classifier\nhealing.py · classify() + triage.py · defect_report()\n─────────────────\nTools: outcome labels:\n  passed · healed_ok · flaky_test\n  likely_defect · needs_review\n  environment_issue · blocked\n  issue_type + next_action fields\nOutputs: classifications.json · defect_report.json"]

            Reporter["📋  Quality Reporter\nreporting.py · reports()\n─────────────────\nTools: suite_evolution.json merger\n  traceability.json (PRD→scenario→result)\n  HTML / Markdown / JUnit XML renderer\n  evidence ZIP builder (START_HERE.md)\nOutputs: report.md · report.html · junit.xml\n         decision_log.json · export.zip"]
        end

        LLMAdapter["🤖  LLM Adapter  (llm.py)\nAsyncOpenAI.responses.parse\nmodel: gpt-5.4-mini (configurable)\nmax 5 calls/run · 1 retry · 6500 output tokens\nllm.plan()  —  business-flow test plan\nllm.heal()  —  constrained locator repair"]

        Store["🗄️  Store  (store.py)\nSQLite WAL: runs · events · fingerprints\nArtifact filesystem: data/<run-id>/\nread() · artifact() · fingerprint()"]

        Runtime["⚙️  Runtime  (runtime.py · config.py)\nlaunch_browser() — readiness probe\nerror_details() — diagnostic capture\npython-dotenv .env loader"]
    end

    subgraph BrowserExec["🌐 Isolated Browser Execution  (Playwright subprocess)"]
        Chromium["Headless Chromium\n1440×1000 viewport\nservice_workers: block\naccept_downloads: false"]
        Contexts["Fresh context per flow\n5 s element timeout · 20 s nav timeout\nnetwork route logger\norigin-scoped auth storage state"]
    end

    subgraph ExtStorage["💾 Local Storage  (data/)"]
        SQLite[("SQLite WAL\nqa.sqlite3\nruns · events · fingerprints")]
        Artifacts["Per-run artifacts\nrecon.json · plan.json · suite.json\nrun_results.json · heal_log.json\nclassifications.json · defect_report.json\nreport.html · junit.xml · *.png · export.zip"]
    end

    OpenAI(["☁️  OpenAI Responses API\ngpt-5.4-mini (default)\nStructured output — Plan / HealProposal"])
    TargetApp(["🌍  Target Application\nHTTP/S — any origin admitted by QA_ALLOWED_ORIGINS"])
    Env["🔑  .env\nOPENAI_API_KEY · OPENAI_MODEL\nQA_ALLOWED_ORIGINS\nTARGET_AUTH_ORIGIN · credentials"]

    %% User → Dashboard → API
    User -->|"URL · PRD · scope\ninteraction policy"| UI_Submit
    UI_Submit -->|"POST /api/runs"| API
    API --> Admit --> Policy --> Contracts
    Contracts --> ExploreAgent

    %% Pipeline flow
    ExploreAgent -->|"recon.json"| PlannerAgent
    PlannerAgent -->|"plan.initial.json"| CoverageAgent
    CoverageAgent -->|"plan.json + gaps"| GenAgent
    GenAgent -->|"suite.json"| ValidateAgent
    ValidateAgent -->|"validation_report.json"| ExecuteAgent
    ExecuteAgent -->|"run result"| TriageAgent
    TriageAgent -->|"repeated selector failure"| HealerAgent
    HealerAgent -->|"healed result"| ClassifyAgent
    TriageAgent -->|"passed / escalate"| ClassifyAgent
    ClassifyAgent -->|"labels + defect records"| Reporter

    %% Re-plan feedback loop
    CoverageAgent -->|"fixable gaps → 1 re-plan"| LLMAdapter
    PlannerAgent -->|"llm.plan()"| LLMAdapter
    HealerAgent -->|"llm.heal() if deterministic fails"| LLMAdapter
    LLMAdapter -->|"structured Plan / HealProposal"| OpenAI
    OpenAI -->|"parsed response"| LLMAdapter

    %% Browser tools
    ExploreAgent -->|"crawl()"| Chromium
    ValidateAgent -->|"execute_flow(validation)"| Chromium
    ExecuteAgent -->|"execute_flow(run)"| Chromium
    TriageAgent -->|"execute_flow(retry)"| Chromium
    HealerAgent -->|"execute_flow(healed)"| Chromium
    Chromium --> Contexts -->|"HTTP/S"| TargetApp

    %% Storage
    ExploreAgent & PlannerAgent & CoverageAgent & GenAgent --> Store
    ValidateAgent & ExecuteAgent & HealerAgent & ClassifyAgent & Reporter --> Store
    Store --> SQLite & Artifacts

    %% Config
    Env -->|"keys · origins · credentials"| LLMAdapter & Runtime & Contexts

    %% Dashboard polling
    UI_Poll -->|"GET /api/runs/:id"| API
    API -->|"status · events · results"| UI_Results
    UI_Results -->|"view / download"| User
```

> **Key design choices:** single Python process · one active `asyncio` task · no LangGraph / Redis / Docker · all stage transitions decided by Python code · OpenAI called ≤ 5×/run (plan + optional re-plan + optional heal) · every locator repair must pass a semantic identity gate and a full-flow confirmation before the suite is updated.

## Agent roles

Each stage in the pipeline is an **autonomous decision node**. The meta-orchestrator in `pipeline.py` drives transitions; no agent calls another directly.

| # | Agent | Module(s) | What it does |
|---|---|---|---|
| 1️⃣ | **Explorer** | `browser.py · crawl()` | Launches a headless Chromium session and crawls the target URL up to the configured page budget. At each page it runs a DOM snapshot (visible elements, text, links) and records network blocks. Outputs `recon.json` used by all downstream agents. |
| 2️⃣ | **Planner** | `planning.py · evolution.py · llm.py` | Loads the previous completed suite from SQLite (if any), remaps PRD requirements to surviving flows, deduplicates by action signature, then calls `llm.plan()` to generate new scenarios grounded in the recon evidence. Falls back to `baseline_plan()` when no OpenAI key is configured. |
| 3️⃣ | **Coverage Checker** | `planning.py · coverage()` | Audits every requirement for a linked test, checks that assertions are quoted literals (`ground_oracles()`), and detects missing negative/boundary/business-flow scenarios. If fixable gaps exist it triggers **one bounded re-plan** before locking the suite. |
| 4️⃣ | **Generator** | `pipeline.py · export_suite()` | Serialises the validated `Plan` model to `suite.json` and writes `generated_tests.py` (a replay entry-point). Action DSL emitted: `navigate · fill · click · assert_text · assert_url · assert_visible`. No model-generated Python is ever evaluated — all actions stay in typed JSON. |
| 5️⃣ | **Validator** | `browser.py · execute_flow(validation)` | Replays each flow once before full execution to verify locators exist in the live page state. Ambiguous repeated selectors are automatically scoped to the nearest verified text anchor (`scope_ambiguous_selector()`). Captures DOM fingerprints for the Healer. |
| 6️⃣ | **Executor** | `browser.py · execute_flow(run)` | Runs every flow in a **fresh isolated browser context** (no shared cookies or state). Records page errors, HTTP-error responses, and a masked screenshot per flow. PolicyErrors (password fill, payment click) surface as `blocked` — not a test failure. |
| 7️⃣ | **Triage / Retry** | `triage.py · triage_flow()` | On any failure, immediately reruns the flow **unchanged once** to distinguish a transient glitch from a real failure. Detects whether the failure kind (`selector · assertion · execution`) and step index are identical across both attempts before routing to the Healer. Records every decision in `agent_decisions`. |
| 8️⃣ | **Healer** | `healing.py · pipeline.py · repair()` | Activated only on a repeated, identical selector failure. Tries a **deterministic fingerprint match** first (similarity ≥ 0.85, unique winner). Falls back to `llm.heal()` only if deterministic repair fails. A strict **semantic identity gate** ensures the repaired element has the same tag, text, name, or test-id. The full flow is then replayed with all original assertions; the suite is updated only on confirmation. |
| 9️⃣ | **Defect Classifier** | `healing.py · classify()` `triage.py · defect_report()` | Assigns one of seven outcome labels to every scenario: `passed · healed_ok · flaky_test · likely_defect · needs_review · environment_issue · blocked`. Each label includes a confidence score and a `next_action` recommendation for the engineer. |
| 📋 | **Quality Reporter** | `reporting.py · reports()` | Aggregates results, PRD traceability, suite evolution (reused / added / regressed), heal evidence and coverage gaps into `report.md`, `report.html`, `junit.xml`, and an evidence ZIP with `START_HERE.md`. |

## For the jury: start here

| Read | What it answers |
|---|---|
| [Jury and demo guide](docs/JURY_GUIDE.md) | What to demonstrate in five minutes and how to interpret the results |
| [Architecture](docs/ARCHITECTURE.md) | Components, orchestration, browser isolation and data flow |
| [Technology decisions](docs/TECHNOLOGY_DECISIONS.md) | Why this stack, why no LangGraph, examples and trade-offs |
| [Implemented features](docs/FEATURES.md) | What each feature actually does |
| [PDF alignment and self-healing](docs/SELF_HEALING_AND_PDF_ALIGNMENT.md) | Requirement mapping, reuse rules, repair gates and limitations |
| [Verification](docs/VERIFICATION.md) | Measured results, reproducible checks and unresolved observations |
| [Report guide](docs/REPORT_GUIDE.md) | How to read the ZIP, classifications and repair evidence |
| [Implementation roadmap](docs/IMPLEMENTATION_PLAN.md) | Delivered milestones and future engineering work |

## Run locally

Prerequisites: **Python 3.12** and Chromium installed through Playwright. OpenAI mode needs your own API key and network access. Baseline needs no model key. Windows is the verified environment; Linux/macOS instructions are supplied but were not acceptance-tested here.

From the repository root in PowerShell:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m playwright install chromium
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Set `OPENAI_API_KEY` privately in `.env`. `OPENAI_MODEL` is configurable; the example uses `gpt-5.4-mini`. Model access depends on your account. Keep `.env` private.

```powershell
./.venv/Scripts/python.exe run.py
```

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)** and check runtime readiness under **Configuration**. On subsequent launches, `./start.ps1` starts the application. Stop with **Ctrl+C** before starting another instance. Do not use multiple workers or Uvicorn `--reload` with this Windows browser process.

On Linux/macOS, create the environment with `python3 -m venv .venv` and use `.venv/bin/python` instead. Linux may require `.venv/bin/python -m playwright install --with-deps chromium`.

## First run

1. Click **Try a demo**, then start the baseline. It executes real Chromium checks against the included Fieldnotes shop without AI calls.
2. For business-flow planning, choose **New test run → OpenAI · Business-flow planning** and enter a test URL.
3. Optionally upload [the example Markdown PRD](examples/fieldnotes-prd.md) and enter a focus area. Enable **Allow clicks and form input** for the example cart, search and coupon scenarios.
4. Under **Execution options**, select the **Page budget** (pages explored) and **Scenario budget** (cases planned). Both support 1–12; defaults are five pages and six cases.
5. Inspect **Results**, **Planner**, **Decision log**, **PRD coverage & risks**, **Defect Classifier**, and **Changes & repairs**.
6. Choose **Export evidence**, unzip it, read **START_HERE.md**, and open **report.html**. The [report guide](docs/REPORT_GUIDE.md) explains the artifacts.
7. **Run again** preserves the URL, policy, focus and PRD. Matching scenarios are reused; new evidence or PRD gaps can trigger additions within the budget.

**Baseline checks observed content. OpenAI plans business flows.** A completed run means orchestration finished, not that every test passed. A 100% scenario pass rate does not mean full application coverage.

## What makes it agentic?

```mermaid
flowchart LR
    URL[URL + optional PRD] --> P[Planner and suite memory]
    P --> C[Coverage review]
    C --> G[Generator and live validation]
    G --> E[Executor]
    E -->|Failure| R[Unchanged retry]
    R -->|Repeated locator failure| H[Healer]
    H --> V[Verify original assertions]
    E --> D[Defect Classifier]
    R --> D
    V --> D
    D --> Q[Test Quality Report]
    Q --> M[(Reusable suite and evidence)]
    M --> P
```

The Python meta-orchestrator chooses transitions from browser evidence and coverage gaps. A repair changes only a uniquely identified failed locator, then replays the complete flow. Ambiguous repairs and changed business expectations are escalated. **LangGraph is not installed**; [Technology decisions](docs/TECHNOLOGY_DECISIONS.md) explains why and when it would become useful.

## Verified behavior

- **36 unit/API/lifecycle tests passed** on Windows.
- A controlled browser sequence verified locator repair, reuse of that repair, preservation of a content regression, and a new scenario for a newly discovered page.
- PRD upload, classifier/change tabs, mobile width and JavaScript-error checks passed.
- The final end-to-end run passed the dashboard-created baseline (2/2), generated-suite replay, local interactions, repair/classifier fixtures, authenticated SauceDemo baseline (1/1), and cancellation.
- Two live OpenAI PRD runs demonstrated **two scenarios retained and one added**. The first passed **1/2** cases; the second passed **2/3**. An unsupported placeholder-text assertion remained unresolved in both. This is a documented limitation, not an application defect claim.

See [Verification](docs/VERIFICATION.md) for exact scope and records. Generated plans can vary across runs and model versions.

## Test and replay

```powershell
./.venv/Scripts/python.exe -m pytest -q
# Start run.py before browser acceptance checks:
./.venv/Scripts/python.exe -m scripts.verify_evolution
# Optional live OpenAI check; incurs API usage:
./.venv/Scripts/python.exe -m scripts.verify_prd_ai
# Replay an exported suite from this repository without planning calls:
./.venv/Scripts/python.exe -m qa_agent.replay "path/to/extracted/suite.json"
```

Other targeted checks cover local interactions, network compatibility and authenticated SauceDemo; see [Verification](docs/VERIFICATION.md). Replay needs this project's interpreter, dependencies, browser and local authentication. The ZIP is not a standalone browser installer.

## Target access and operating limits

`QA_ALLOWED_ORIGINS=*` admits HTTP(S) targets. Authentication, CAPTCHA/MFA, cross-domain journeys, dynamic state, canvas and inaccessible content can still limit testing. Compatible loading supports external read resources; navigation remains constrained. Additional navigation origins remain an API compatibility option, not a dashboard field.

For SauceDemo, use `https://www.saucedemo.com/inventory.html`, set credentials privately in `.env`, and retain `TARGET_AUTH_ORIGIN=https://www.saucedemo.com`. The example selectors match that login. Other sites need their own login selectors or `QA_STORAGE_STATE`. No credentials are committed.

Limits: **one local user, one active run, Chromium, ten minutes, five logical model calls**. Each SDK call can retry once. A failed scenario gets one unchanged execution retry and at most one locator repair with confirmation. Interactions can repeat during validation and retry; use resettable test data. Payments, destructive actions and order completion are blocked by the current policy.

This is a working local hackathon implementation. Multi-user hosting, distributed execution, CI/CD integration, arbitrary flow repair and complete production coverage are not delivered features.

## Troubleshooting and data

| Symptom | Action |
|---|---|
| Browser missing | Run the Playwright Chromium installation command. |
| `[WinError 5] Access is denied` | Start in a normal local PowerShell terminal; check folder/browser permissions. Inspect Configuration and `runtime_error.json`. The application cannot bypass OS policy. |
| Port already in use | Stop the existing server. `scripts/restart_local.ps1` is a helper for an idle local server. |
| OpenAI key/model error | Check private `.env`, account access and connectivity, then restart. Baseline needs no key. |
| Protected page unavailable | Configure target-specific authentication; review crawl gaps. |
| Settings not reflected | Restart and refresh the dashboard. |

`data/` stores SQLite history, PRDs, screenshots and reports. It is gitignored, not encrypted. Stop the server before backing up the entire directory. Retention is manual. Optional token prices in `.env` enable estimates; unset prices remain unavailable. Timed-out calls can still incur provider charges.

## Repository map

```text
qa_agent/      API, planner, browser, Healer, persistence and reports
ui/            Dashboard HTML/CSS/JavaScript; no frontend build step
demo/          Fieldnotes test application
scripts/       Startup, readiness and acceptance checks
tests/         Unit, API, lifecycle and repair-invariant tests
examples/      Optional Markdown PRD
docs/          Jury guide, architecture, decisions, evidence and roadmap
docs/archive/  Original research, separated from implementation claims
data/          Local generated evidence and state; ignored by Git
```

The [original research](docs/archive/ORIGINAL_RESEARCH.md) is retained as provenance. Its proposed stack and numerical claims are not the specification of the running implementation.

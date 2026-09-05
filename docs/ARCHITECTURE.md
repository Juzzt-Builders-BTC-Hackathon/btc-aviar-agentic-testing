# AIVAR — architecture and technology stack

Current enhancement: [Self-healing, persistent suites, PRD uploads and PDF alignment](SELF_HEALING_AND_PDF_ALIGNMENT.md) documents the implemented agent decisions, limits, report fields and verification.
This document describes the code currently implemented in this repository. Mermaid diagrams render in GitHub and Mermaid-capable Markdown previews.

The reasons for choosing this stack and the conditions that would justify LangGraph, PostgreSQL, React or broader browser-agent tooling are documented in [Technology decisions](TECHNOLOGY_DECISIONS.md).

Runtime hardening update: startup now runs filesystem and real browser readiness probes (`runtime.py`); failed readiness blocks job admission. Compatible resource loading permits external assets/read requests, while navigation is constrained to the site, canonical redirects and per-run additional origins. The [feature guide](FEATURES.md) documents these controls and diagnostics in detail.

## 1. System architecture

```mermaid
flowchart TB
    User[QA engineer / developer]
    subgraph Machine[User workstation]
        subgraph Frontend[Dashboard — HTML / CSS / JavaScript]
            Form[URL, Markdown PRD, scope, interaction policy]
            History[Run history and metrics]
            Live[Pipeline stages and decision log]
            Evidence[Plans, results, screenshots and exports]
        end
        subgraph Backend[Python 3.12 — FastAPI / Uvicorn — loopback port 8765]
            Session[Local session cookie, trusted host and origin checks]
            API[REST API — server.py]
            Admission[One active asyncio task / cancellation]
            Policy[URL and action policy — safety.py]
            Contracts[Pydantic contracts — models.py]
            Pipeline[Meta-orchestrator — pipeline.py / triage.py]
            LLM[OpenAI adapter — llm.py]
            Browser[Browser adapter — browser.py]
            Planner[Coverage and baseline rules — planning.py]
            Healer[Fingerprint and identity rules — healing.py]
            Reporter[Test Quality Report and Defect Classifier]
            Persistence[Store — store.py]
        end
        subgraph Execution[Isolated browser execution]
            Chromium[Headless Chromium / Playwright]
            Contexts[Fresh browser context per flow]
            Auth[Origin-scoped authenticated storage state]
        end
        subgraph Storage[Local data directory]
            SQLite[(SQLite WAL database)]
            Artifacts[JSON / PNG / Markdown / HTML / JUnit / Python]
        end
        Env[Private .env configuration]
    end
    OpenAI[OpenAI Responses API]
    Target[Selected HTTP or HTTPS application]
    User --> Form
    Form --> Session --> API --> Admission --> Pipeline
    API --> History
    API --> Live
    API --> Evidence
    API --> Contracts
    API --> Policy
    Pipeline --> Planner
    Pipeline --> LLM --> OpenAI
    Pipeline --> Browser --> Chromium --> Contexts --> Target
    Auth --> Contexts
    Pipeline --> Healer
    Pipeline --> Reporter
    Pipeline --> Persistence
    Persistence --> SQLite
    Persistence --> Artifacts
    Reporter --> Artifacts
    Env --> Policy
    Env --> LLM
    Env --> Auth
```

The dashboard polls the API every two seconds. The server owns the job lifecycle and browser processes. OpenAI proposes structured plans and, when needed, constrained repair candidates. Python code decides stage transitions and test outcomes.

## 2. Technologies actually used

Versions below are the direct pins in `requirements.txt`, not claims about the newest available releases.

| Layer | Technology | Purpose in this application |
|---|---|---|
| Runtime | Python 3.12 | Backend, orchestration, browser automation, reporting and tests |
| HTTP API | FastAPI 0.135.1 | Run submission, status, configuration, cancellation and downloads |
| ASGI server | Uvicorn 0.41.0 | Single worker listening on `127.0.0.1:8765` |
| Contracts | Pydantic 2.12.5 | Strict requests, action types, plans, flow IDs and repair proposals |
| AI provider | OpenAI API | Remote planning and constrained semantic repair proposals |
| AI SDK | openai 2.26.0 | `AsyncOpenAI.responses.parse`, typed output parsing and usage accounting |
| Configured model default | `gpt-5.4-mini` | Configurable with `OPENAI_MODEL`; the backend reads the active value at startup |
| Browser automation | Playwright 1.58.0 + Chromium | Auth, crawling, DOM observations, locator validation, execution and screenshots |
| Concurrency | Python `asyncio` | One active run, asynchronous browser/API I/O, deadlines and cancellation |
| Database | Python `sqlite3`, SQLite WAL | Runs, append-only application events, fingerprints and schema version |
| Artifact storage | Local filesystem / `pathlib` | Per-run files, temporary-file replacement and screenshot evidence |
| Configuration | python-dotenv 1.2.2 | Reads `.env` without putting secrets in frontend code |
| UI | HTML5, CSS3, vanilla JavaScript | Responsive dashboard, forms, tabs, metrics and run history |
| UI transport | Browser Fetch API + JSON polling | Two-second status updates and persistent history on reconnect |
| Unit/API testing | pytest 8.3.5 | Policy, contracts, classification, API, cancellation and persistence tests |
| HTTP verification | httpx 0.28.1 | Integration scripts and FastAPI test-client dependency |
| Reports / export | Python `json`, `html`, `xml.etree`, `zipfile` | JSON, escaped HTML, Markdown, JUnit XML and evidence ZIP |
| Local launch | PowerShell and Python | Windows setup, startup and project-scoped background restart |

There is no React, Node build step, LangGraph, CrewAI, Crawl4AI, browser-use, Redis, PostgreSQL or Docker in the current runtime. Some appear in the original proposal; this implementation uses the smaller stack above. Node was used for JavaScript syntax verification during development, but is not required to run the app.

## 3. End-to-end run sequence

```mermaid
sequenceDiagram
    actor QA as QA engineer
    participant UI as Dashboard
    participant API as FastAPI
    participant O as Python orchestrator
    participant B as Playwright / Chromium
    participant AI as OpenAI Responses API
    participant DB as SQLite + artifacts
    QA->>UI: Enter URL, scope and optional Markdown PRD
    UI->>API: POST /api/runs
    API->>API: Validate session, URL, request and admission limit
    API->>DB: Create queued run
    API-->>UI: 202 Accepted + run ID
    API->>O: Start asynchronous task
    O->>B: Establish origin-scoped auth if configured
    O->>B: Crawl observed same-origin links
    B-->>O: Bounded DOM/text/element observations
    O->>DB: recon.json + events
    O->>DB: Retrieve latest matching completed suite
    O->>O: Retain existing scenarios and compare observations / PRD
    alt OpenAI planning or extension needed
        O->>AI: Observations, requirements and policy
        AI-->>O: Structured Plan + usage
    else Deterministic baseline
        O->>O: Generate observed-content assertions
    end
    O->>O: Check coverage and ground exact oracles
    opt Fixable gap and re-plan budget available
        O->>AI: Coverage feedback for one re-plan
        AI-->>O: Revised structured plan
    end
    O->>DB: Plan, gaps and executable action suite
    O->>B: Validate each flow in live page state
    O->>B: Execute flows in fresh contexts
    opt Failed execution
        O->>B: One unchanged rerun
        opt Repeatable selector failure
            O->>O: Fingerprint matching or validated anchor scoping
            opt Deterministic repair unavailable
                O->>AI: Request observed candidate selection
                AI-->>O: Candidate, confidence and rationale
                O->>O: Enforce semantic identity gate
            end
            O->>B: Confirm full flow with unchanged assertions
        end
    end
    O->>O: Classify evidence and aggregate metrics
    O->>DB: Results, screenshots, repairs and reports
    O->>B: Close contexts and browser
    O->>DB: Mark completed after resource cleanup
    loop Every 2 seconds
        UI->>API: GET /api/runs and selected run
        API->>DB: Read history and evidence
        API-->>UI: Current status, events and results
    end
    QA->>UI: Download evidence ZIP or replay suite
```

## 4. State transitions and bounded recovery

```mermaid
flowchart LR
    Q[Queued] --> R[Recon]
    R --> M[Load matching completed suite]
    M --> P[Retain or extend plan]
    P --> C[Coverage review]
    C -->|One re-plan maximum| P
    C --> G[Generate action suite]
    G --> V[Live validation]
    V --> E
    E -->|Failure| T[Unchanged rerun]
    T --> H[Conditional locator repair]
    H --> CF[Whole-flow confirmation]
    E --> CL[Classify]
    T --> CL
    CF --> CL
    CL --> RP[Report]
    RP --> CLEAN[Release browser resources]
    CLEAN --> DONE[Completed]
    Q -. Cancel .-> X[Cancelled / partial evidence retained]
    R -. Error or deadline .-> F[Failed / diagnostic retained]
    Q -. Process restart .-> I[Interrupted / fresh rerun available]
```

Cancellation and fatal errors can occur at any active stage. The diagram shows representative edges for readability. There is a ten-minute run deadline, five logical OpenAI-call maximum, one active run, and configured page/flow limits. The full repair and suite-memory diagram is in [the enhancement guide](SELF_HEALING_AND_PDF_ALIGNMENT.md). Retries are bounded; unresolved scenarios become visible review items.

## 5. Data and artifact architecture

```mermaid
flowchart TD
    Input[RunRequest] --> Runs[(runs table)]
    Stages[Stage decisions] --> Events[(events table)]
    Success[Successful element observations] --> FP[(fingerprints table)]
    Recon[recon.json] --> Initial[plan.initial.json]
    Initial --> Plan[plan.json]
    Req[requirements.json] --> Plan
    Plan --> Gaps[coverage_gaps.json]
    Plan --> Suite[suite.json + generated_tests.py]
    Suite --> Validation[validation_report.json]
    Validation --> Results[run_results.json + screenshots]
    Results --> Heals[heal_log.json]
    Results --> Labels[classifications.json]
    Results --> Defects[defect_report.json]
    Plan --> Evolution[suite_evolution.json]
    Req --> Trace[traceability.json]
    Results --> Trace
    Results --> Reports[report.md / report.html / junit.xml]
    Defects --> Reports
    Evolution --> Reports
    Heals --> Reports
    Gaps --> Reports
    Trace --> Reports
    Reports --> Zip[Evidence ZIP with START_HERE.md and decision_log.json]
```

Run artifacts live in `data/<run-id>/`. `data/qa.sqlite3` stores history and indexes. Generated Python is a fixed replay entry point; the model supplies validated JSON actions, not arbitrary Python or shell code. Replay runs the same policy-controlled Playwright executor without calling OpenAI.

## 6. Origin configuration and process boundaries

Current configuration:

```dotenv
QA_ALLOWED_ORIGINS=*
```

This admits any valid HTTP(S) **target** origin, including local applications on other ports. To restore restricted admission:

```dotenv
QA_ALLOWED_ORIGINS=https://www.saucedemo.com,http://localhost:3000
```

The following are separate boundaries:

| Boundary | Behavior |
|---|---|
| Target admission | `*` accepts any HTTP(S) target; an explicit list restricts targets |
| Browser resources | Compatible mode permits external HTTP(S) read requests; strict mode restricts origins; non-read methods require interaction permission |
| Browser navigation | Selected site, common www/HTTPS canonical redirects and explicit per-run navigation origins |
| Authentication | Credentials/storage state only apply to `TARGET_AUTH_ORIGIN` |
| Dashboard API | Loopback, trusted host, local HttpOnly cookie and origin checks; no wildcard CORS |
| Dashboard as a test target | Only its `/demo` paths are accepted |
| Generated actions | Fixed DSL, interaction opt-in, destructive/transaction click checks |
| OpenAI access | Backend-only API key; observations redacted for configured secrets |

External CDN/read-API dependencies are supported by compatible resource loading. SSO, MFA and cross-frame interaction are not automatically solved by enabling resources or navigation origins; configure an authenticated session where needed. Startup readiness validates local browser/filesystem access, not the accessibility or semantic testability of every target site.

## 7. Local deployment topology

```mermaid
flowchart LR
    Browser[User browser] -->|localhost HTTP| Server[One Uvicorn process]
    Server -->|async task| Job[One active orchestrator]
    Job -->|SDK HTTPS| OpenAI[OpenAI API]
    Job -->|Playwright subprocess| Driver[Playwright driver]
    Driver --> Chromium[Headless Chromium]
    Chromium --> Target[Selected application]
    Server --> DB[(Local SQLite)]
    Job --> Files[Local artifact files]
    Config[.env] --> Server
```

This is a local single-user topology. Shared deployment would require authentication/authorization, isolated workers, durable distributed admission, protected artifact storage, retention and operational controls described in the [implementation plan](IMPLEMENTATION_PLAN.md).

# AIVAR — implemented features and operating guide

Current enhancement: [Self-healing, persistent suites, PRD uploads and PDF alignment](SELF_HEALING_AND_PDF_ALIGNMENT.md) documents the implemented agent decisions, limits, report fields and verification.
This is a feature inventory of the working application, not a list of proposed capabilities. Source files are linked so each capability can be reviewed against implementation.

## 1. What the application does

AIVAR accepts a website URL, explores accessible pages, proposes tests, checks the plan for gaps, validates locators in a browser, executes scenarios, investigates failures, and produces reports with browser evidence. A local dashboard shows progress and retains earlier runs.

The current deployment is one user, one local server, one active run and headless Chromium. OpenAI is used for planning and a constrained repair fallback. Test execution, stage transitions, metrics and classification rules run in Python.

## 2. Run creation and website configuration

| Feature | Implemented behavior | Where to use it |
|---|---|---|
| URL input | Any HTTP(S) target with `QA_ALLOWED_ORIGINS=*`; exact allowlists remain available | New test run |
| Planner choice | OpenAI business-flow planning or deterministic observed-content baseline | Planning engine |
| Natural-language scope | Optional focus instruction included in the planner input | Focus area |
| PRD | Markdown upload up to 64 KiB, prose/list block traceability with `PRD-n` IDs; legacy API requirements remain compatible | PRD upload |
| Exact expectations | Quote expected UI strings; unsupported literal interpretations are marked inferred | PRD |
| Page budget | 1–12 pages, default 5 | Page budget |
| Scenario budget | Dashboard and API support 1–12 flows, default 6; retained suites are never truncated | Request contract |
| Interaction permission | Fills/clicks and non-read requests enabled explicitly | Interaction checkbox |
| Resource loading | Compatible mode loads external HTTP(S) assets/read requests; strict mode restricts resource origins | Website resource loading |
| Canonical redirects | Same-site `www` aliases and HTTP-to-HTTPS redirects on standard ports | Automatic |
| Additional navigation origins | Backwards-compatible API field; removed from the form | API only |
| Authenticated session | Origin-scoped environment login profile or private Playwright storage state | `.env` |

Implementation: [models.py](../qa_agent/models.py), [safety.py](../qa_agent/safety.py), [browser.py](../qa_agent/browser.py).

**Compatibility is bounded:** admitting a URL does not prove all of its functionality can be tested. Cross-origin assets are supported, but non-read HTTP methods remain blocked in read-only mode. Applications that use POST for GraphQL queries may need interaction permission on a test environment. Additional navigation origins permit navigation; they do not automatically solve SSO, MFA or configure credentials.

## 3. Runtime readiness and access-denied handling

At startup, AIVAR performs actual checks rather than inferring readiness from installed packages:

1. Create a temporary file in the configured data directory, write it and read it back.
2. Start the Playwright driver.
3. Launch the configured browser.
4. Render a small local DOM and read its heading.
5. Close the browser and report readiness.

The Configuration page displays readiness, successful checks and recovery instructions. `GET /api/readiness` returns 200 when ready and 503 when a check fails. The separate `/api/health` endpoint reports HTTP-server liveness. Jobs are rejected before creation if startup readiness failed.

Errors distinguish `ACCESS_DENIED`, `BROWSER_MISSING` and general runtime failures, with the stage recorded. Fatal run errors additionally produce `runtime_error.json` and include a remedy in the dashboard.

If the artifact directory is itself inaccessible, the error and failed artifact-write detail are still saved in SQLite when the database is writable. New run directories are created before inserting a queued record, so a denied directory does not leave a phantom queued job. Background restart waits for readiness and returns failure when probes do not pass.

For `[WinError 5]`, the code cannot grant OS privileges or override endpoint protection. Use `start.ps1` from a normal local terminal, verify write access to the data and browser-temp directories, and obtain IT approval if the driver/browser executable is blocked. The earlier sandbox failure remains in history; when that run predates a successful startup check, the UI identifies it as historical and offers a fresh rerun.

`QA_BROWSER_CHANNEL` supports bundled `chromium`, installed `chrome` or installed `msedge`. Browser temp files default to `data/runtime/browser-temp`, with `QA_BROWSER_TEMP_DIR` available as an override. Relative `QA_DATA_DIR` values resolve against the project root, regardless of the terminal's current directory.

Implementation: [runtime.py](../qa_agent/runtime.py), [server.py](../qa_agent/server.py), [run.py](../run.py).

## 4. Reconnaissance and page observations

- Uses a real browser, including JavaScript rendering.
- Follows observed permitted links breadth-first up to the page budget.
- Allows a bounded load/hydration interval before observation.
- Captures title, URL, visible text, visible element descriptions, selectors, links and HTTP status.
- Avoids capturing input values and hidden fields in the DOM digest.
- Uses test attributes, IDs, names or labels where unique; falls back to a scoped structural selector for repeated elements.
- Records blocked requests and crawl failures with their causes.
- Identifies login forms without a configured session and embedded frames as explicit limitations.
- Reports detected CAPTCHA/2FA indicators as coverage gaps.

Observations are bounded to 100 candidate elements and 7,000 visible-text characters per page. These are a planning digest, not a complete DOM archive. `recon.json` is the evidence source.

Recon follows links; it does not autonomously interact with every menu, modal or multistep wizard. Embedded frames may load, but generated assertions target the main document. Canvas/native/mobile testing and visual-regression analysis are not implemented.

## 5. OpenAI planning and coverage review

- Uses the OpenAI Responses API through the Python SDK.
- Parses strict typed plans with Pydantic.
- Supplies page observations, extracted PRD requirements, full PRD context, scope, permitted navigation origins and interaction policy.
- Treats page content as untrusted input rather than tool instructions.
- Limits each run to five logical OpenAI calls, with one SDK retry per call, a 60-second request timeout and a 6,500-token output cap.
- Sets `store=False` and records returned token usage.
- Handles missing keys, refusals and incomplete output explicitly; no silent fallback to baseline.
- Reviews missing requirement links and missing negative/boundary scenarios before generation.
- Allows one coverage-driven re-plan and retains remaining gaps.

Plans contain flow ID/name, risk, category, requirement links, oracle provenance and ordered steps. Every accepted flow must begin with navigation and contain an assertion. Invalid actions, duplicate flow IDs, unknown requirements and empty text/URL expectations are rejected.

Requirement linkage is not proof of semantic correctness. Exact quoted text/URL values can remain requirement-backed. Other exact expectations are conservatively marked inferred. Confidence values in later classification are heuristic scores, not calibrated probabilities.

Implementation: [llm.py](../qa_agent/llm.py), [planning.py](../qa_agent/planning.py), [models.py](../qa_agent/models.py).

## 6. Generation, live validation and replay

Supported actions:

| Action | Behavior |
|---|---|
| `navigate` | Navigate to a permitted page URL |
| `fill` | Fill a visible unique input with test data |
| `click` | Click a visible unique permitted control |
| `assert_visible` | Require a unique element to be visible |
| `assert_text` | Require visible inner text to contain the unchanged expected string |
| `assert_url` | Require the current URL to contain the expected value |

The generator emits `suite.json` and a fixed `generated_tests.py` replay entry point. The model does not emit executable Python or shell commands. The shipped Playwright executor interprets the validated actions.

Live validation replays steps in order, checking each locator in the page state where it is used. It checks uniqueness and visibility. Invalid selectors are not passed by arbitrarily taking the first match.

The exported suite can be replayed from the project without further OpenAI calls. Its exit code is zero only if all scenarios pass. Authentication and origin configuration still apply.

Implementation: [pipeline.py](../qa_agent/pipeline.py), [replay.py](../qa_agent/replay.py), [browser.py](../qa_agent/browser.py).

## 7. Execution and evidence

Each flow uses a fresh browser context initialized from the configured authenticated session. Local browser storage is isolated between flows; server-side test data is not automatically reset.

Evidence includes step outcomes, elapsed time, screenshots, page errors, HTTP errors, blocked-request reasons and failure-page observations. Input and textarea regions are masked in screenshots. Other sensitive visible content can still be present, so artifacts require appropriate access controls.

Validation, execution and retries can repeat interactions. Read-only runs block fills, clicks and non-read HTTP methods. Payments, destructive operations and order-completion clicks remain blocked by the action policy. This is a practical policy layer, not a proof that application GET endpoints have no side effects.

HTTP diagnostics are independent of declared UI assertions. For example, SauceDemo deep links can return HTTP 404 while rendering the SPA. The DOM assertion may pass, but the HTTP warning remains in the results and coverage gaps.

## 8. Bounded repair and failure classification

### Locator repair using validation evidence

A repeated locator can be scoped using the immediately preceding successfully verified text anchor. The rule chooses the unique matching element inside that anchor's smallest containing ancestor. It does not use the failing assertion's expected value to choose an element. The validation observation can seed the Healer after two unchanged execution failures. The repaired flow must pass a complete fresh execution.

If no safe candidate exists, the failure remains unresolved (`needs_review`). Historical runs can still contain `generation_failed` outcomes.

### Runtime repair

1. Rerun a failed scenario unchanged once.
2. For repeatable selector failures, look up a successful or observed fingerprint.
3. Try a unique deterministic semantic match: similarity at least 0.85 and a 0.10 margin over the next candidate.
4. If eligible, ask OpenAI for an observed candidate. Require confidence at least 0.90 and a separate unique semantic identity check.
5. Change only the locator and rerun the whole flow with original assertions.
6. Record the proposed change and whether confirmation passed.

### Result labels

| Label | Meaning |
|---|---|
| `passed` | Declared assertions passed |
| `blocked` | A policy prevented the scenario from executing |
| `generation_failed` | Valid executable locators could not be established |
| `flaky_test` | Unchanged flow failed once and passed on one rerun; root cause unproven |
| `healed_ok` | Runtime locator repair passed full-flow confirmation |
| `likely_defect` | The same requirement-backed assertion failed on two isolated attempts |
| `environment_issue` | Browser or execution issue needing connectivity, timing or availability investigation |
| `needs_review` | Evidence is insufficient to identify a reliable cause |

Assertions are never weakened during repair. Fingerprints are stored only after successful execution. Verified-repair counts include only confirmed locator repairs; all attempts and the original failure are retained.

Implementation: [healing.py](../qa_agent/healing.py), [pipeline.py](../qa_agent/pipeline.py).

## 9. Dashboard and reports

The responsive dashboard includes:

- Run totals, scenario pass rate, verified repairs and attention counts.
- Searchable recent-run history, target URL, mode, timestamps and status.
- Live stage indicators and persisted decision logs.
- Per-scenario results, provenance, classification, diagnostics and screenshots.
- Expandable Planner output with actions and requirement links.
- PRD coverage gaps, passing requirement links and repair audits.
- Defect Classifier details with expected/actual behavior, attempts, evidence and next action.
- Suite evolution with reused/new scenarios, regressions and bounded UI observations.
- Configuration, OpenAI-key presence, origin settings and runtime readiness.
- Cancellation, rerun and evidence export controls.

Exports include `START_HERE.md`, Markdown/escaped HTML reports, JUnit XML, JSON contracts and intermediate results, PNG screenshots, the replay suite and decision-log JSON in an evidence ZIP. The start file explains reading order, partial exports and replay prerequisites. Pass rate is explicitly distinguished from application coverage. Dollar estimates appear only when input/output token prices are configured; returned usage can exclude calls that timed out but were billed.

Implementation: [ui/](../ui/), [reporting.py](../qa_agent/reporting.py), [server.py](../qa_agent/server.py).

## 10. Persistence and local operations

- SQLite WAL with explicit transactions and closed connections.
- Run history, application event log, successful fingerprints and schema version.
- Per-run artifacts written through temporary-file replacement.
- One active task to bound local resource usage.
- Ten-minute run deadline and bounded retries.
- Cancellation with partial evidence retained.
- Startup converts unfinished runs to `interrupted`; a fresh rerun is available.
- Completed status is written after browser cleanup.
- Loopback binding, trusted host validation, HttpOnly SameSite session cookie, request-origin checks and CSP.
- API keys and test credentials are backend-only configuration and ignored by Git.

Operational checks:

```powershell
# Unit/API tests
./.venv/Scripts/python.exe -m pytest -q
# Real dashboard, replay, cancellation and browser checks; server must be running
./.venv/Scripts/python.exe -m scripts.verify_local --sauce
# Real runtime and multi-origin fixtures; optionally a billable public-site AI run
./.venv/Scripts/python.exe -m scripts.verify_compatibility
./.venv/Scripts/python.exe -m scripts.verify_compatibility --public
```

## 11. Production-readiness boundary

The implemented controls harden local use, but universal website coverage and shared-service production readiness are not established by these features. Websites can require unavailable credentials, MFA, CAPTCHA, explicit test fixtures, cross-frame interaction or unsupported widgets. Report those limitations; do not interpret a completed run as proof of complete testing.

Still required for a shared production service: user identity/RBAC, tenant isolation, hardened worker/network isolation, durable distributed queue/leases, versioned migrations, retention/encryption, load testing, supply-chain checks, incident monitoring and operational restore drills. Automatic mid-flow resume, server-data rollback, cross-browser matrices, rich Markdown semantics and document formats beyond bounded Markdown are also not implemented.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the component and deployment diagrams, and the [implementation plan](IMPLEMENTATION_PLAN.md) for release gates.

# Aviar — local autonomous QA

A locally running dashboard that explores a web application, creates a test plan with OpenAI, reviews coverage, validates and executes Playwright scenarios, attempts bounded locator repairs, and exports evidence.

## Start on Windows

Python 3.12 is required. From this directory:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m playwright install chromium
Copy-Item .env.example .env  # first setup only; do not overwrite an existing .env
```

Set `OPENAI_API_KEY` in `.env`, then:

```powershell
./.venv/Scripts/python.exe run.py
```

Open **http://127.0.0.1:8765**. On subsequent starts, `./start.ps1` also works. The server intentionally uses one worker and binds only to loopback. Do not use Uvicorn `--reload` on Windows: the browser worker needs an event loop supporting subprocesses.

For macOS/Linux use `.venv/bin/python` in the equivalent commands. Chromium may also require `python -m playwright install --with-deps chromium`.

## First run

1. Choose **Explore local demo** for a deterministic baseline without API calls, or **New test run → OpenAI** for AI-generated scenarios.
2. Use `http://127.0.0.1:8765/demo/` to test the included store. For an interactive AI run, enable form interactions and supply requirements such as:
   ```text
   Adding a notebook increases the cart count to "1 items".
   Adding one notebook updates the total to "$18.00".
   Invalid discount codes show "Invalid discount code".
   Searching for zzzunknown shows "No products found".
   ```
3. Watch the pipeline, then inspect **Results**, **Test plan**, **Decision log**, **Coverage & risks**, and **Artifacts**.
4. Export the ZIP for JSON artifacts, screenshots, Markdown/HTML reports, JUnit XML and a replayable suite.

Baseline mode runs real browsers but only tests observed page content. It is not AI planning or business coverage. AI failures do not silently fall back to baseline. Quote exact expected UI strings in requirements; assertions without exact quoted grounding are marked inferred. HTTP/browser warnings remain visible even if UI assertions pass.

## SauceDemo

The local `.env` in this workspace is configured with the supplied demo login. Credentials are not committed. On a fresh installation, fill `TARGET_USERNAME` and `TARGET_PASSWORD` yourself using the public test credentials. The selector defaults in `.env.example` match SauceDemo.

Use **https://www.saucedemo.com/inventory.html** as the run URL. Aviar logs in before recon and reuses the authenticated storage state in isolated contexts. The target origin must match `TARGET_AUTH_ORIGIN`. This configuration tests authenticated product flows; it does not claim coverage of all supplied user personas or login failures. To use another persona, change the local username and restart.

All HTTP(S) target origins are enabled with `QA_ALLOWED_ORIGINS=*`. To restrict targets again, replace `*` with comma-separated exact origins. Compatible resource loading permits external assets and read requests; strict mode is available per run. Navigation permits the selected site, common www/HTTP-to-HTTPS redirects, and any explicitly added navigation origins. Dashboard CORS remains restricted. For authenticated sites, configure login selectors or `QA_STORAGE_STATE` and `TARGET_AUTH_ORIGIN`. Storage state is an absolute path to a private Playwright JSON session file. State and credentials never enter model prompts or exported suites.

## Behavior and boundaries

- OpenAI Responses API with strict Pydantic output validation, `store=False`, configurable model, request timeout, retry limits and reported token usage.
- Deterministic orchestration: one coverage re-plan, one locator-regeneration attempt, one unchanged failure rerun, and one verified runtime repair. No arbitrary model-authored Python or shell execution.
- Compatible or strict resource policy; wildcard or explicit target admission; scoped navigation; blocked downloads and service workers; isolated contexts; transactions/destructive click intents blocked.
- Read-only mode blocks clicks, fills and non-read HTTP methods after explicit authentication. It cannot guarantee that an application’s GET endpoints have no side effects. Use test environments.
- Interactions are opt-in and may execute during validation, execution and retries. Use resettable test data. Payments, deletion and order completion remain blocked in this version.
- Assertions remain unchanged during healing. Repeated product locators can be scoped to the smallest container of the immediately preceding verified text anchor; the expected price is never used to choose the product. Classification is evidence-based and heuristic: `likely_defect` requires a repeated requirement-backed failure. Inferred expectations remain `needs_review`.
- SQLite WAL stores history and append-only application events. Interrupted runs retain evidence and can be rerun; automatic mid-flow resume is intentionally disabled because interactions may not be idempotent.
- All app assets are local; no Node build, CDN, Docker or cloud service is required except OpenAI for AI planning and the target website itself.

This is a working single-user local implementation with hardening controls, **not a certified multi-user production service**. The [implementation plan](Autonomous_Test_Orchestration_Agent_Architecture_and_Implementation_Plan.md) documents supported behavior, deviations from the source proposal, release gates and remaining deployment work.

## Tests

```powershell
./.venv/Scripts/python.exe -m pytest -q
# With run.py already running:
./.venv/Scripts/python.exe -m scripts.verify_local --sauce
# Optional live, billable OpenAI acceptance runs:
./.venv/Scripts/python.exe -m scripts.verify_ai
./.venv/Scripts/python.exe -m scripts.verify_ai --sauce
```

The integration script launches headless Chromium, creates a run through the actual UI, checks reports and responsive layouts, executes cart/negative scenarios, and verifies failure classification and selector repair. `--sauce` additionally runs a real authenticated baseline against SauceDemo. The integration tests' deliberately wrong expected price tests classifier behavior; it is not presented as a real demo-store defect.

Screenshots and a machine-readable verification record are written to `data/verification/`. These are local artifacts, not committed fixtures.

Replay a generated suite without AI calls:

```powershell
./.venv/Scripts/python.exe -m qa_agent.replay data/<run-id>/suite.json
```

The replay command returns zero only when all scenarios pass. Run it from this project with the same environment configuration and allowed target origins.

## Operations

The **Configuration** screen shows real startup readiness: writable data storage and a successful browser launch/DOM check. `/api/health` is liveness; `/api/readiness` returns 200 only when those checks pass. Jobs are rejected with recovery guidance when readiness fails.

If you see **`[WinError 5] Access is denied`**, check the run timestamp. The original restricted-sandbox failure remains in history; the current server may already be healthy. Use **Run again** after checking readiness. For a new failure, launch `./start.ps1` from a normal local PowerShell terminal, check directory permissions, and have IT approve blocked browser/driver executables when required. The app cannot override Windows permissions. `runtime_error.json` records the failing stage and guidance.

Browser temporary files default to `data/runtime/browser-temp`. Override `QA_BROWSER_TEMP_DIR` with a writable location if needed. Set `QA_BROWSER_CHANNEL=chrome` or `msedge` to use an installed browser; the default remains bundled `chromium`.

- **Stop:** Ctrl+C in the server terminal. A background instance started during setup records its launcher PID in `data/server.pid`; verify that process and its `run.py` child before stopping it.
- **Restart:** run `start.ps1`. Configuration changes require restart. A new local session cookie is issued when you reload the dashboard.
- **Backup:** stop the server and copy the entire `data/` directory to an access-controlled location. It contains database, screenshots, DOM observations, requirements and reports. Protect it as application data; `.gitignore` is not encryption.
- **Retention:** no automatic deletion. Archive or remove old run directories and matching database entries only after backup. Disk usage depends on screenshots and run count.
- **Costs:** provide `OPENAI_INPUT_PRICE` and `OPENAI_OUTPUT_PRICE` as USD per million tokens if you want estimates. No unverified pricing is hardcoded. Timeouts may be billed without usage being returned.
- **Corporate proxies:** retain normal TLS verification. Configure approved proxy/certificate settings in your environment if network access is blocked.
- **Browser missing:** run the Chromium installation command above. An executable installed by a different Playwright version may not match the pinned browser revision.

## Source documents and API references

See [Architecture and technology stack](ARCHITECTURE.md) for detailed component, execution-sequence, deployment and data-flow diagrams, plus the technologies actually used by this implementation.

See [Implemented features and operating guide](FEATURES.md) for the detailed feature inventory, configuration behavior, evidence formats and supported website boundaries.

The original [research document](Autonomous_Test_Orchestration_Agent_Deep_Research.md) is preserved. Its vendor comparisons and numerical claims were treated as proposal context, not independently established facts or instructions.

The OpenAI integration follows the official [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs). Browser session isolation follows [Playwright BrowserContext](https://playwright.dev/python/docs/api/class-browsercontext).

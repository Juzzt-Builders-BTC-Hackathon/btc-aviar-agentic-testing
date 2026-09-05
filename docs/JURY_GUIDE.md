# Jury guide — five-minute AIVAR demonstration

## The problem and the claim

Generating a test is only part of QA automation. Someone must decide whether coverage is useful, whether a failure is repeatable, whether the script or application changed, and whether a repair is trustworthy.

**AIVAR automates that coordination for bounded browser tests.** Its strongest demonstration is a repeat run that repairs a locator while retaining the original expected behavior. It also keeps a genuine content difference visible instead of making the test green by rewriting the expectation.

The implemented system is a local, single-user prototype with real OpenAI and Chromium execution. Specialized Planner, Generator and Healer roles are coordinated by explicit Python decisions. LangGraph is not used. See [Technology decisions](TECHNOLOGY_DECISIONS.md) for the rationale.

## Prepare before presenting

1. Follow [the README](../README.md), start the server, and verify **Configuration → Runtime readiness**.
2. Use the included Fieldnotes application at `http://127.0.0.1:8765/demo/`. It removes third-party availability/login uncertainty from the main demo.
3. Run `python -m scripts.verify_evolution` using the project's virtual environment. It creates controlled locator/content changes and writes evidence under `data/verification/evolution-*`. This fixture uses no model calls and can be reproduced live.
4. Optionally run `python -m scripts.verify_prd_ai`. This performs two real, billable OpenAI runs and checks PRD-driven suite extension. Keep the resulting runs available in the dashboard.
5. Have [the example PRD](../examples/fieldnotes-prd.md), [verification summary](VERIFICATION.md), and an extracted evidence ZIP ready. Do not display `.env` or private authentication state.

The fixture mutates a local test application on purpose. Label that demonstration as controlled fault injection. Do not describe it as discovering a bug in a third-party website.

## Five-minute walkthrough

| Time | Show | Explain |
|---|---|---|
| 0:00–0:35 | Dashboard and input form | “A URL is required; the PRD and focus are optional. We automate the decisions between planning, execution and repair.” |
| 0:35–1:10 | Planning engine, PRD upload and budgets | OpenAI plans business flows; baseline checks observed text. Pages explored and scenarios executed are separate limits. |
| 1:10–1:55 | A completed run's Planner, decision log and PRD coverage | Show one actual assertion, one PRD link and one uncovered risk. Explain that passing cases are not complete coverage. |
| 1:55–3:05 | Controlled repair evidence | Show the old selector, failed attempt, proposed selector and passing confirmation. The scenario ID and expected value remain the same. |
| 3:05–3:45 | Changes & repairs and repeat-run result | Show the retained suite, a new case, and a content regression that stays failed. Explain why preserving failure is useful. |
| 3:45–4:25 | Defect Classifier | Explain verified script issue versus suspected defect versus unresolved evidence. Show original reproduction and screenshot links. |
| 4:25–5:00 | Export ZIP and technology decision | Open `START_HERE.md` and `report.html`. Close with the explicit trade-off: bounded, inspectable local orchestration; wider deployment and arbitrary flow repair remain future work. |

A live model call may take longer than a presentation slot. Start it early, then explain an already recorded run with its timestamp and evidence. Clearly distinguish previously recorded results from the live run in progress.

## The repair story, with exact meaning

1. The fixture starts with a heading identified by `#heading-original`, displaying `Catalog`. A baseline scenario passes and a fingerprint is saved.
2. Only the identifier changes to `#heading-new`. The existing scenario fails and fails again unchanged.
3. The Healer finds the same semantic element, changes only the selector, and confirms the full flow. The result is `healed_ok`.
4. A third run reuses the repaired selector and passes without a new plan.
5. The heading text changes to `Unexpected replacement`. The old `Catalog` expectation is preserved and fails. A newly discovered page also receives an additional scenario.

Because this fixture uses an observed-content oracle rather than an explicit PRD-backed assertion, the content failure is a regression signal requiring review, not a confirmed application defect. That distinction is part of the demonstration.

## Measured results to cite

- 36 unit/API/lifecycle checks passed, including the export reading guide; the detailed evidence is maintained in [Verification](VERIFICATION.md).
- The real-browser repair/reuse/regression/addition sequence passed.
- Two live OpenAI PRD runs retained two cases and added one. Their outcomes were 1/2 and 2/3 passing, with an unsupported placeholder assertion left unresolved.
- No manual-hours-saved, percentage productivity uplift, universal defect accuracy or fixed run cost has been measured. These are evaluation goals, not results.

## Questions the jury may ask

| Question | Answer grounded in the implementation |
|---|---|
| Why is this agentic without LangGraph? | The meta-orchestrator branches on coverage and browser evidence, chooses reuse/extension/retry/repair/escalation and records those choices. A framework is an implementation option, not the definition of agency. |
| Can it hide a regression by healing? | Only the failed locator may change. Assertion values, other steps and scenario meaning are compared and retained. Full replay is required. Semantic matching is still conservative and can escalate. |
| Does “likely defect” mean a confirmed bug? | No. The same requirement-backed assertion failed twice; a wrong PRD can also cause it. The report asks for confirmation. |
| What happens when a generated test is wrong? | The current Healer repairs safe locator problems. Unsupported assertions/flows remain `needs_review`; they are not silently rewritten. The live placeholder case is a concrete example. |
| What persists? | Completed plan snapshots, run metadata, events, element fingerprints and evidence. Interrupted browser steps do not resume mid-action. |
| Does the same domain always share tests? | No. Matching includes the exact normalized entry URL, scope, engine and policy to avoid reusing incompatible tests. |
| Is the model call mocked? | Unit tests use mocks where appropriate; the documented OpenAI acceptance runs were real calls with token usage. The controlled repair fixture uses deterministic baseline and real Chromium. |
| Can it test every website? | HTTP(S) admission is broad; practical coverage depends on authentication, supported DOM actions, crawl bounds and target availability. |
| Is it production hosted? | No. It is a hardened local prototype. The PDF excludes hosting at scale, CI/CD and a cross-browser matrix from required scope. |

## Submission handoff

The repository includes runnable source, setup instructions, architecture diagrams, technology rationale, example PRD, evidence interpretation, verification commands and a [slide outline](PRESENTATION.md). Original research is isolated in `archive/` and labelled as proposal context.

Publishing a repository URL, recording the requested 2–5 minute video, and creating a presentation in the event's chosen slide format remain presenter submission steps. This documentation does not claim those external submissions have happened.

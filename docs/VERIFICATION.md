# Verification record

Date: **2026-09-05**. Verified environment: Windows, Python 3.12, Playwright 1.58.0 with Chromium. These are observed checks, not claims of universal compatibility.

## Current acceptance evidence

| Check | Observed result | Evidence |
|---|---|---|
| Unit/API/lifecycle suite | **36 passed** in the final test run | `python -m pytest -q`; includes export, PRD contract, suite lineage, retry and repair-invariant tests |
| Controlled locator drift | Failed old locator repaired; full flow passed with original assertion | [Browser evolution record](evidence/browser-evolution.json) |
| Repaired-suite reuse | Subsequent run reused the verified selector without planning calls | Same four-run browser fixture |
| Content regression | Changed visible text stayed failed; expected value was retained | Same fixture; observed oracle remained reviewable, not a confirmed bug |
| New-page coverage | New observed page received an additional scenario without replacing the prior case | Same fixture |
| PRD/dashboard | Markdown upload persisted; classifier, changes, coverage and plan tabs worked | Same browser check; no page JavaScript errors |
| Responsive layout | 390px viewport had no document overflow | Same browser check |
| Final end-to-end regression | Dashboard-created baseline **2/2**, replay, cart/coupon, seeded classifier, locator repair, repeated-price scoping, authenticated SauceDemo **1/1**, cancellation and no UI JavaScript errors all passed | `scripts.verify_local --sauce`; local machine record in `data/verification/verification.json` |
| Live OpenAI initial PRD | **1/2 passed**, two logical calls, 4,079 input / 727 output tokens | [Live PRD record](evidence/prd-openai.json) |
| Live OpenAI revised PRD | **2/3 passed**, two prior cases retained, one added; one logical call, 2,551 input / 252 output tokens | Same record; retained steps compared exactly |
| ZIP guide | Partial/cancelled export retains evidence and explains absent final reports | `tests/test_export.py` |

The committed JSON summaries contain run IDs and measured counts. Full screenshots and raw artifacts remain local in `data/`; they are deliberately not committed wholesale. Reproduce the fixture to obtain fresh evidence. The local original fixture directory was `data/verification/evolution-21dcbe1c/`.

## An unresolved result worth showing

The model generated a scenario named **Search input boundary visibility** using a text-content assertion for the search input's placeholder, `Try notebook`. An input placeholder is not the element's inner text, so the browser failed the assertion. The classifier returned `needs_review` and the scenario remained failed when the PRD was extended.

The system did not alter the assertion or call this an application defect. The accepted enhancement added a separate pencil-product scenario while retaining existing cases. Supporting typed placeholder/value assertions is a roadmap item. The 1/2 and 2/3 outcomes must not be presented as an all-green acceptance run.

## Reproduce the checks

From the repository root with the virtual environment installed:

```powershell
./.venv/Scripts/python.exe -m pytest -q
# Start run.py before the following browser/API checks:
./.venv/Scripts/python.exe -m scripts.verify_evolution
# Optional live OpenAI PRD planning + incremental planning; billable:
./.venv/Scripts/python.exe -m scripts.verify_prd_ai
```

Windows execution sandboxes may deny access to browser subprocesses or pytest temporary folders. These acceptance runs used ordinary user process permissions. The application does not bypass Windows restrictions.

## Additional targeted scripts

| Command after the Python executable | Purpose | External dependency |
|---|---|---|
| `-m scripts.verify_local` | Dashboard-created baseline, replay, cart/coupon cases, selector repair and cancellation | Running local server |
| `-m scripts.verify_local --sauce` | Also validates authenticated SauceDemo baseline | Target availability and private configured login |
| `-m scripts.verify_compatibility` | Controlled resource-loading/navigation fixtures | Chromium |
| `-m scripts.verify_compatibility --public` | Also exercises a public target | Network and configured API access where used |
| `-m scripts.verify_ai` | Live interactive local OpenAI acceptance | Model API; billable |
| `-m scripts.verify_ai --sauce` | Live read-only authenticated SauceDemo planning | Model API and target; billable |
| `-m scripts.verify_prd_ai` | Unique scoped PRD run and revised PRD with retained tests | Model API; billable |

The final end-to-end run repeated authenticated SauceDemo, cancellation, replay, dashboard/mobile, interaction and repair checks after the documentation/export changes. External-resource compatibility fixtures and the earlier public-site AI run remain historical evidence; they were not rerun in this final pass.

## Interpretation and limits

- Baseline verification uses real Chromium and deterministic scenarios, not mocked browser output.
- Unit tests use mocks for bounded decisions and API contracts where appropriate.
- The PRD acceptance records reflect real model calls and returned token usage. Dollar estimates were not configured.
- Heuristic confidence is not calibrated classification accuracy. No labelled production-defect benchmark was run.
- No pixel-diff, load, multi-user, cross-browser, comprehensive security or all-platform certification is claimed.
- A local server's readiness is a startup probe result, not a permanent guarantee of target reachability.

See [the jury guide](JURY_GUIDE.md) for presentation wording and [the roadmap](IMPLEMENTATION_PLAN.md) for the remaining work.

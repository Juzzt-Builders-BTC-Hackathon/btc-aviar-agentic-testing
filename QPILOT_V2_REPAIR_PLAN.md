# Qpilot V2 repair plan and verification record

## Objective
Repair the 23 audited issues while retaining V1 request compatibility, existing evidence, and the local single-user workflow. A completed run means evidence was reported, not that the application passed. Invalid tests must remain visible as generation failures or untested risk.

## Repairs and acceptance criteria
| # | Issue | Implementation / acceptance |
|---|---|---|
| 1 | Evaluator API rejection | Strict typed traceability schema; sanitized API error details and contract tests; verify a real structured response. |
| 2 | Rejected tests execute | Exhausted plan review produces a risk report; generation gates each flow and executes only valid flows. |
| 3 | Regeneration has no feedback | Supply failed steps, observed DOM, evaluation gaps and current suite; preserve approved assertions. |
| 4 | Dropdowns | Add typed select_option action and observed label/value options; update executor, safety and prompts. |
| 5 | Wrong-page locators | Page-scoped grounding, targeted bounded discovery, and live validation before execution. |
| 6 | Trivial assertions | Reject body-only visibility and negative cases without a meaningful outcome check. |
| 7 | Weakened assertions | Preserve assertion action, target and value; only the verified healer may repair assertion locators. |
| 8 | Missing plan.json | Persist initial, generated and healed plans; support dashboard and next-run reuse. |
| 9 | Reporter failure | Bounded report retry, terminal failure persistence, safe handling of storage failures. |
| 10 | Final replan context | Forward final feedback and results; retain current scenarios and original evidence. |
| 11 | Lost triage | Share classification/finalization with V1, retain validation failures and all attempts. |
| 12 | Late oracle checks | Ground assertions before validation/execution and classification. |
| 13 | Healing persistence | Save verified fingerprints, page-scope identities, restore scoped-selector repair. |
| 14 | Healer API fallback | Explicit run mode, budget reservation and caught API failures. |
| 15 | Budget starvation | Reserve final evaluator/reporter calls; expose actual budget, usage and exhaustion. |
| 16 | Hidden fallback | Persist agent health, include fallback reasons and narrative in final reports and API. |
| 17 | UI stages | Version-specific stages; publish start and per-flow progress. |
| 18 | Missing partial results | Persist each validation/execution/healing result with unique attempt evidence. |
| 19 | Repair field mismatch | Canonical new_selector, UI reads legacy candidate_selector as fallback. |
| 20 | Stale limits | API provides configured pipeline version and call budget; UI renders them. |
| 21 | Duplicate exploration | Canonicalize visited destinations; prioritize PRD links and allow bounded targeted discovery. |
| 22 | Resume absent | Explicit resume only at non-browser boundaries; preserve budget/deadline, deny unknown browser side effects. |
| 23 | Insufficient tests | Regression tests for failures, feedback, contracts, budget, artifacts, reuse, UI and real local browser actions. |

## Sequence
1. Contracts, browser actions, generation guards and API handling.
2. Runtime, routing, evidence, reporter and safe resume.
3. UI integration and regression coverage.
4. Local browser acceptance and bounded live API verification; record results below.

## Implemented flow

```text
Reconnaissance -> Previous suite -> PRD Analyst -> Planner -> Plan Evaluator
  Replan while the plan-review limit allows it.
  If still rejected: record generation failures and report untested risk.
Approved plan -> Generator(feedback + observations) -> Static/live validation -> Generation Evaluator
  Regenerate while the limit allows it.
  If still rejected: quarantine invalid flows; execute only the remaining valid flows.
Executor -> one unchanged retry for failures -> eligible Healer -> full repair verification
Final Evaluator -> one coverage replan only when the remaining call budget permits it
Suite evolution -> Reporter -> completed (or terminal failure after bounded report retry)
```

## Verification results

All 23 repair areas above are implemented. Additional import-order verification exposed
and fixed a circular import between the runtime adapter and orchestration package.

- Full regression suite: **73 passed** on this Windows workspace, including real Chromium tests.
- Dependencies: `pip check` found no broken requirements.
- Live evaluator schema verification: one logical API call, approved output, no fallback.
- Full local fixture with real agents: **2/2 tests passed**, **7/8 logical LLM calls**, **31.0 seconds**.
  PRD Analyst, Planner, both initial evaluations, Generator, final evaluation and Reporter
  all returned without fallback. The fixture covered dropdown selection and native invalid input.
- Real Chromium repair test: a missing locator was repaired, the entire flow passed with
  its original expected text, and original failure, retry, repair audit and confirmation were saved.
- Two real baseline V2 runs confirmed that `plan.json` is persisted and the second run reuses the first suite.
- Real dashboard test confirmed V2 Executor highlighting, saved-plan display, fallback warning,
  repair-selector compatibility and the configured eight-call budget.
- A real SQLite checkpoint interruption/resume test confirmed that Executor is not replayed
  when resuming Reporter and that consumed calls/tokens are restored.

Local live-AI evidence:
`data/repair-local-ai/runs/2523ddc1c8514887b656db9d4f4d1b02/`

### Regression coverage by repair

- Issues 1, 3, 5-8, 10, 12, 14-16: `tests/test_v2_repairs.py` and `scripts/verify_v2_llm.py`.
- Issues 2 and 9: `tests/test_v2_routing.py`, `tests/test_v2_graph.py`, and runtime evidence tests.
- Issues 4, 8, 13, 17, 19-21: real Chromium tests in `tests/test_v2_browser_ui.py`.
- Issues 11, 13, 17-18: `tests/test_v2_runtime_evidence.py`, triage guards, and real healing test.
- Issue 22: `tests/test_v2_resume.py` plus unsafe-boundary and expired-deadline tests.
- Issue 23: the combined regression suite and independent-import test.

### Pending external acceptance

The saved EduVale request has **not** been rerun after these repairs. Automatic approval
review rejected that operation because it would replay a ZIP-sourced request against
an external site and send its contents to the LLM without explicit approval for that rerun.
The ZIPs and original runs were preserved. On approval, use
`python scripts/verify_v2_run.py qa-run-0707b622.zip`; it saves evidence separately under
`data/repair-verification/` and does not overwrite the original reports.

Passing the local suite is evidence for the repaired behavior, not a guarantee that every
website scenario is supported or that all EduVale tests will pass. Failed generation and
untested acceptance criteria remain visible instead of being counted as application defects.

## Handoff

Restart the running Qpilot process to load these changes. Existing environment and Chromium
installation can be reused; no new dependency is needed. V1 remains available through the
existing feature flag. Public agent contracts add `select_option` and `assert_invalid` actions.

## Reference
OpenAI Structured Outputs requires closed object schemas, including nested objects: https://developers.openai.com/api/docs/guides/structured-outputs

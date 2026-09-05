# Reading an AIVAR evidence export

**Unzip the download, read `START_HERE.md`, then open `report.html` in a browser.** The ZIP contains evidence and a replayable action suite; it is not a standalone installer.

## Reading order

1. **Run status and Test Quality Report:** `completed` means orchestration finished. Review failed/blocked scenarios and gaps before drawing a quality conclusion.
2. **Defect Classifier:** distinguish verified script repairs, suspected application defects, intermittent failures and unresolved evidence.
3. **Healer audit:** compare old/proposed selectors and confirmation screenshots. A proposal is not a verified repair.
4. **Changes:** inspect retained, new, repaired, regressed and not-observed items.
5. **PRD coverage:** examine planned/passing case links and uncovered requirements.

## Artifact dictionary

| File | Purpose |
|---|---|
| `START_HERE.md` | Reading order, run ID/status and replay prerequisites |
| `report.html` / `report.md` | Human-readable Test Quality Report; HTML opens offline |
| `defect_report.json` | Classification, expected/actual evidence, original reproduction, attempt screenshots, decisions and next action |
| `run_results.json` | Detailed outcomes, all attempts, diagnostics and failure observations |
| `classifications.json` | Compact case-to-classification mapping |
| `heal_log.json` | Proposed selectors, semantic gates and `verified` status |
| `suite_evolution.json` | Source run, retained/added/deferred cases, outcome comparisons and bounded UI differences |
| `traceability.json` | PRD IDs linked to planned and passing cases |
| `requirements.json` | Extracted PRD prose/list blocks and legacy API requirements |
| `prd.md` | Uploaded PRD after configured-secret redaction; present only when supplied |
| `coverage_gaps.json` | Missing requirements, unsupported flows and untested risks |
| `plan.initial.json` / `plan.json` | Pre-review and final plans; the final plan includes verified locator repairs |
| `recon.json` | Bounded live page text, elements, URLs and crawl limitations |
| `validation_report.json` | Pre-execution replay outcomes |
| `decision_log.json` | Timestamped stage decisions exported from SQLite |
| `*.png` | Case/attempt screenshots: `validation`, `run`, `retry`, `healed` |
| `suite.json` / `generated_tests.py` | Action suite and Python replay entry point |
| `junit.xml` | Machine-readable case results; portability, not an implemented CI integration |
| `runtime_error.json` | Fatal stage failure and recovery action, when applicable |

Cancelled, interrupted and failed pipelines can export partial evidence. A final report or plan may be absent; absence does not imply a passing stage.

## Classification glossary

| Label | Interpretation |
|---|---|
| `passed` | Declared assertions passed |
| `healed_ok` | Only a locator changed and the entire flow passed confirmation |
| `likely_defect` | Same requirement-backed assertion failed on two isolated attempts; engineer confirmation is still needed |
| `flaky_test` | An unchanged replay passed after failure; original failure remains recorded |
| `blocked` | Policy prevented testing |
| `environment_issue` | Browser/execution issue needing investigation |
| `needs_review` | Evidence does not establish a reliable cause |
| `generation_failed` | Historical label for unresolved validation; current failures remain review items |

Confidence scores are heuristic, not calibrated probabilities. An incorrect requirement can cause a `likely_defect`. A repaired pass proves only that the declared flow passed after a constrained change.

## Compare and replay

`previous_run` references the latest completed matching URL/scope/engine/policy. A previously passing case now failing or blocked is a regression signal, not a root-cause verdict. DOM/text differences are bounded observations, not pixel-level visual regression. `not_observed` does not mean “deleted.” Changed PRDs can invalidate requirement links but never silently replace existing expected values.

From the repository root, with dependencies, browser and target authentication installed:

```powershell
./.venv/Scripts/python.exe -m qa_agent.replay "path/to/extracted/suite.json"
```

Replay does not regenerate a plan or call the model. It exits successfully only when every case passes. The target and original test preconditions must still be available.

PRDs, screenshots and traces can contain application data. Inspect the bundle before sharing outside a controlled demo environment.

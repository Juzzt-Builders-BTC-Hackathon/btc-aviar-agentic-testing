# Implementation status and roadmap

This is the current implementation plan. It supersedes the earlier root-level proposal. See [Architecture](ARCHITECTURE.md), [Technology decisions](TECHNOLOGY_DECISIONS.md), and [PDF mapping](SELF_HEALING_AND_PDF_ALIGNMENT.md) for design detail.

## Delivered milestones

| Milestone | Delivered behavior | Acceptance evidence |
|---|---|---|
| Local runtime | FastAPI loopback service, session checks, one job, startup browser/write probes, cancellation and interruption status | API/lifecycle tests and readiness checks |
| Planner and coverage | OpenAI structured plans, deterministic baseline, focus, Markdown PRD, requirement mapping and bounded initial re-plan | Schema/coverage tests and live OpenAI PRD runs |
| Generator and execution | Typed action suite, Python replay entry point, live selector validation, fresh Chromium contexts and artifacts | Real-browser/replay acceptance scripts |
| Healer and classifier | One unchanged retry, locator-only gate, unique semantic identity, confirmation and evidence-based escalation | Controlled drift fixture and repair-invariant tests |
| Persistent suites | Completed-run lineage, retained IDs/assertions, append-only extension, PRD link changes and observed UI/outcome diffs | Four-run fixture and two live incremental PRD runs |
| Dashboard | AIVAR styling, PRD upload, purpose text, classifier, changes, coverage and evidence export | Desktop/mobile browser verification |
| Presentation handoff | README, architecture, rationale, example PRD, jury walkthrough, slide outline and export reading guide | Documentation link audit and export checks |

“Delivered” means implemented within the documented local boundary, not universal correctness. [Verification](VERIFICATION.md) records unresolved cases.

## Next engineering increments

| Priority | Work | Concrete example | Acceptance gate |
|---|---|---|---|
| 1 | Expand typed assertion support | Distinguish input placeholder, value, selected option and inner text | Unit/browser tests reject invalid attribute assertions; evaluate observed live failure without weakening expected behavior |
| 1 | Improve oracle and PRD quality review | Exclude setup prose from candidate acceptance requirements and preserve source locations | Labelled PRD corpus; measured link accuracy and explicit unmatched content |
| 1 | Broader scenario library | Suites beyond twelve cases with selection by change/risk | Stable IDs, no silent deletion, reported selection/defer reasons and bounded execution |
| 2 | Evaluate semantic test deduplication | Similar names with identical business intent | Measured false-merge/duplicate rates; never overwrite existing assertions |
| 2 | Better change analysis | Distinguish dynamic timestamps from functional text drift | Controlled changes corpus, false-positive measurements, documented masks |
| 2 | Robust job orchestration | Persist approval pauses or multi-worker jobs | Decide whether LangGraph fits; idempotent nodes, interruption tests and safe browser lifecycle |
| 3 | Multi-user deployment | Authenticated teams with separate secrets/evidence | SSO/RBAC, isolated workers, queue, encrypted object storage, retention and restore/load tests |
| 3 | Additional target coverage | Frames, richer widgets and more browsers | Per-capability browser fixtures and honest fallback gaps |
| 3 | Broader flow repair | Changed multi-step navigation with original intent | Independent intent/oracle gates and a repair evaluation dataset before automatic acceptance |

## Release boundaries

No CI service, external hosting, autonomous arbitrary-flow rewrite, calibrated defect classifier, automatic mid-action crash resume or complete application coverage is delivered. Framework names in the archived research are options, not installed capabilities.

Before distributing beyond the local demo, produce a transitive dependency lock, dependency/licence review, supported-platform matrix, retention policy and secret/evidence handling review. Before claiming business impact, measure setup time, maintenance effort, false repairs, false defect labels and missed regressions on representative applications.

## Presenter actions

Run the quickstart on the presentation machine, prepare one controlled evidence export, record a 2–5 minute demonstration, and publish the repository/deck through the event's chosen submission process. No external publication or messaging is performed by the local application.

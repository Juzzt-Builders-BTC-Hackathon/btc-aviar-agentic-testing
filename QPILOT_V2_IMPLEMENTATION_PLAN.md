# Qpilot V2 — Agentic Orchestration Implementation Plan

## 1. Goal

Build a LangGraph-based V2 pipeline that explicitly implements the roles required by the Aivar problem statement while preserving the current working Qpilot application.

V2 must accept a URL as the only required input and autonomously perform:

```text
requirements analysis → planning → plan evaluation → generation
→ generation evaluation → execution → healing → final evaluation → reporting
```

The new agents must produce outputs compatible with Qpilot's existing models, action suite, browser executor, evidence, persistence, suite evolution, UI, and reports.

## 2. Non-breaking development policy

The current implementation remains V1:

```text
qa_agent/pipeline.py
qa_agent/planning.py
qa_agent/healing.py
qa_agent/triage.py
qa_agent/reporting.py
qa_agent/evolution.py
```

These files must not be removed or rewritten while V2 is being developed.

Pipeline selection will be explicit:

```text
QA_PIPELINE_VERSION=v1 → current pipeline
QA_PIPELINE_VERSION=v2 → LangGraph agent pipeline
```

Rules:

- Develop V2 in new folders and files.
- Reuse existing functionality through adapters.
- Preserve current API request fields and artifact meanings.
- Use additive database changes only.
- Never silently change existing test IDs, assertions, or expected values.
- V1 remains the rollback path until V2 is approved.
- Old code may be removed only in a later release after V2 produces equivalent or better outputs and removal is separately approved.

## 3. Existing Qpilot capabilities to preserve

The latest Qpilot already provides:

- FastAPI server and local dashboard.
- URL validation, origin restrictions, session checks, and interaction policy.
- Runtime and browser readiness checks.
- Playwright reconnaissance and authenticated state.
- OpenAI structured planning and deterministic baseline planning.
- Markdown PRD upload and `PRD-n` requirement identifiers.
- Initial coverage review and one bounded re-plan.
- Typed action DSL and replayable suite export.
- Live selector and assertion validation.
- Fresh browser contexts for execution.
- Unchanged failure rerun.
- Deterministic locator matching and gated semantic fallback.
- Explicit failure triage and conservative classification.
- Immutable suite snapshots, reuse, extension, and change detection.
- SQLite WAL run/event/fingerprint persistence.
- Markdown, HTML, JSON, JUnit, screenshots, and evidence ZIP.
- Cancellation, interrupted-run recovery status, and resource cleanup.

V2 must wrap and extend these features, not rebuild weaker copies.

## 4. Technology stack

### Retained

| Area | Technology |
|---|---|
| API | FastAPI and Uvicorn |
| Validation | Pydantic v2 |
| LLM | Official OpenAI SDK and Responses API |
| Browser | Playwright Python and Chromium |
| HTTP checks | httpx |
| Business persistence | Existing SQLite WAL `Store` |
| Artifact storage | Existing atomic local-file writer |
| UI | Existing HTML, CSS, and JavaScript dashboard |
| Tests | Pytest and existing verification scripts |

### Added for V2

| Area | Technology |
|---|---|
| Workflow | LangGraph `StateGraph` |
| Local graph persistence | `langgraph-checkpoint-sqlite` |
| Production graph persistence | Optional `langgraph-checkpoint-postgres` configuration |
| Observability | Structured stage events bridged into the existing Qpilot Store |
| Packaging | Docker Compose only after local V2 completion |

Do not add LangChain agents, CrewAI, AutoGen, Redis, Celery, Kubernetes, a vector database, or another browser framework during V2 implementation.

## 5. Runtime roles

### Agents using the shared LLM client

1. **PRD Analyst Agent**
   - Reads uploaded Markdown, pasted requirements, and later supported document formats.
   - Extracts requirements, acceptance criteria, edge cases, priority, and source locations.
   - Returns stable requirement IDs and confidence/evidence.

2. **Planner Agent**
   - Receives reconnaissance, requirements, focus, prior suite, and change information.
   - Reuses valid retained flows and proposes new meaningful flows.
   - Produces Qpilot-compatible `Plan` and `Flow` structures.

3. **Evaluator Agent**
   - Runs in three explicit modes:
     - `PLAN_EVALUATION`
     - `GENERATION_EVALUATION`
     - `FINAL_EVALUATION`
   - Provides semantic judgment while deterministic rules retain final routing authority.

4. **Generator Agent**
   - Converts an approved plan into Qpilot's typed action DSL.
   - Never generates arbitrary executable Python or shell commands.
   - Returns one-to-one plan-to-generated-flow mappings and generation gaps.

5. **Healer Agent**
   - Receives only failures eligible after deterministic triage.
   - Selects from observed locator candidates when deterministic matching cannot decide.
   - Cannot modify assertions, expected values, business input, or unrelated steps.

6. **Reporter Agent**
   - Produces an optional human-readable narrative from verified structured facts.
   - Cannot calculate or alter counts, classifications, pass status, coverage, or evidence.

### Deterministic components

- **LangGraph Orchestrator:** selects nodes and enforces retry limits.
- **Reconnaissance:** existing browser crawl and observations.
- **Executor:** existing Playwright action interpreter.
- **Coverage safeguards:** local checks around Evaluator decisions.
- **Triage:** existing explicit failure-transition logic.
- **Healing gate:** deterministic fingerprint and semantic identity validation.
- **Metrics and traceability:** existing reporting calculations.
- **Safety and cleanup:** existing Qpilot policies and browser lifecycle.

The Orchestrator and Executor do not use an LLM. All LLM agents share one server-side API key and one injected client. Separate prompts and schemas define their roles.

## 6. New folder structure

```text
qa_agent/
├── pipeline.py                         # Existing V1, unchanged
├── pipeline_selector.py                # V1/V2 selection
├── v2_models.py                        # Strict V2 contracts
│
├── agents_v2/
│   ├── __init__.py
│   ├── prd_analyst.py
│   ├── planner.py
│   ├── evaluator.py
│   ├── generator.py
│   ├── healer.py
│   └── reporter.py
│
├── orchestration_v2/
│   ├── __init__.py
│   ├── graph.py
│   ├── state.py
│   ├── nodes.py
│   ├── routing.py
│   ├── policies.py
│   ├── checkpoints.py
│   ├── events.py
│   └── errors.py
│
├── adapters_v2/
│   ├── __init__.py
│   ├── auth_adapter.py
│   ├── recon_adapter.py
│   ├── evolution_adapter.py
│   ├── executor_adapter.py
│   ├── triage_adapter.py
│   ├── healing_adapter.py
│   ├── reporting_adapter.py
│   └── store_adapter.py
│
└── prompts_v2/
    ├── prd_analyst.md
    ├── planner.md
    ├── evaluator_plan.md
    ├── evaluator_generation.md
    ├── evaluator_final.md
    ├── generator.md
    ├── healer.md
    └── reporter.md
```

Team-delivered files may have different names. Adapters isolate those names from LangGraph and convert their outputs into V2 contracts.

## 7. Shared V2 state

`V2PipelineState` will include:

```text
run_id
thread_id
request
pipeline_status
current_stage
started_at
deadline_at

auth_state_reference
recon_output
previous_suite
suite_evolution_input
requirements_output
planner_output
plan_evaluation
generator_output
generation_evaluation
validation_results
execution_results
active_failure
healer_actions
final_evaluation
evolution_output
report_output

planning_attempts
generation_attempts
execution_retries_by_flow
healing_attempts_by_flow
final_replan_attempts
logical_llm_calls
token_usage

events
errors
degraded_components
exhausted_limits
cancellation_requested
cleanup_completed
```

State restrictions:

- Never persist API keys, passwords, cookies, authorization headers, or chain-of-thought.
- Store references to screenshots and traces rather than binary content.
- Store only serializable values in LangGraph checkpoints.
- Never store live Playwright browser/context/page objects in checkpoints.
- Use `run_id` as the LangGraph `thread_id`.
- Qpilot Store remains authoritative for business artifacts and run history.
- LangGraph checkpoints remain authoritative only for workflow progress.

## 8. Agent response envelope

Every agent returns:

```json
{
  "status": "success | partial | failed",
  "data": {},
  "confidence": 0.0,
  "evidence": [],
  "errors": [],
  "degraded_mode": false
}
```

All responses are validated before being stored or routed. Invalid output receives one structured-output retry. A second invalid result activates the documented deterministic fallback or proceeds to final reporting.

## 9. Exact agent outputs

### PRD Analyst

```text
document_title
requirements[]:
  requirement_id
  title
  description
  acceptance_criteria[]
  edge_cases[]
  priority
  source_section
  source_excerpt
  confidence
unresolved_statements[]
```

The original redacted Markdown remains `prd.md`. Existing `PRD-n` identifiers remain compatible. Revised PRDs preserve IDs by exact normalized requirement text where possible.

### Planner

```text
plan
reused_flow_ids[]
new_flow_ids[]
deferred_candidates[]
uncovered_requirements[]
exploration_limitations[]
```

The contained plan must validate against Qpilot's existing `Plan`, `Flow`, and `Step` contracts. Existing flows and expected values cannot be silently overwritten.

### Evaluator

```text
evaluation_stage
decision
gaps[]
invalid_items[]
untested_risks[]
requirement_traceability[]
rationale
confidence
```

Allowed decisions:

```text
PLAN_EVALUATION       → APPROVE | REPLAN | INVALID
GENERATION_EVALUATION → APPROVE | REGENERATE | INVALID
FINAL_EVALUATION      → REPORT | REPLAN
```

### Generator

```text
suite
generated_flow_ids[]
ungenerated_flows[]
plan_to_suite_mapping[]
generation_gaps[]
artifact_paths[]
```

`suite` contains only Qpilot's permitted actions:

```text
navigate, fill, click, assert_visible, assert_text, assert_url
```

New assertion types may be introduced only through separate typed contracts and browser tests.

### Healer

```text
flow_id
classification
candidate_selector
confidence
rationale
proposed_locator_change
changed_fields[]
requires_confirmation
```

The deterministic healing gate rejects the proposal unless only the failed locator changed, semantic identity is unique, confidence meets policy, and full-flow confirmation passes with original assertions.

### Reporter

```text
executive_summary
important_findings[]
recommended_actions[]
```

These narrative fields are appended to deterministic Markdown/HTML/JSON/JUnit reports. Reporter cannot change structured facts.

## 10. Final LangGraph workflow

```text
START
→ initialize_run
→ authenticate
→ reconnaissance
→ load_previous_suite
→ detect_observation_and_prd_changes
→ PRD Analyst (skip when no PRD/direct requirements)
→ Planner
→ Evaluator: PLAN_EVALUATION
    ├─ REPLAN + budget available → Planner
    ├─ APPROVE → Generator
    └─ invalid/exhausted → Final Evaluator
→ Generator
→ live_validation
→ Evaluator: GENERATION_EVALUATION
    ├─ REGENERATE + budget available → Generator
    ├─ APPROVE → Executor
    └─ invalid/exhausted → Final Evaluator
→ Executor
→ unchanged_retry when required
→ deterministic_triage
    ├─ eligible repeatable locator failure → Healer
    └─ all other outcomes → Final Evaluator
→ Healer
→ deterministic_repair_gate
    ├─ accepted proposal → full_flow_confirmation
    └─ rejected/ambiguous → Final Evaluator
→ full_flow_confirmation
    ├─ passed → Final Evaluator
    └─ failed → Final Evaluator
→ Evaluator: FINAL_EVALUATION
    ├─ genuine coverage gap + budget available → Planner
    └─ otherwise → suite_evolution
→ suite_evolution
→ deterministic_reporting
→ Reporter narrative (optional)
→ persist_artifacts
→ cleanup
→ END
```

Every error, refusal, timeout, cancellation, and retry exhaustion routes to deterministic reporting, persistence, cleanup, and termination whenever those operations remain possible.

## 11. Routing rules

### Plan evaluation

- `APPROVE` → Generator.
- `REPLAN` with unused budget → Planner with gaps.
- `REPLAN` after budget → Final Evaluator with gaps preserved.
- `INVALID` → Final Evaluator.

### Generation evaluation

- `APPROVE` → Executor.
- `REGENERATE` with unused budget → Generator for affected flows only.
- `REGENERATE` after budget → Final Evaluator; affected flows become `generation_failed` or `untested`.
- `INVALID` → Final Evaluator.

### Execution and healing

- Passed flow → preserve fingerprints and continue.
- Failed flow → one unchanged isolated retry.
- Unchanged retry passes → `flaky_test`; do not heal.
- Same requirement-backed assertion fails twice → `likely_defect`; do not replan or heal assertion.
- Repeatable locator failure → deterministic matcher first.
- Deterministic unique match → verify without LLM.
- No deterministic match → Healer Agent may select only from observed candidates.
- Accepted locator-only change → full-flow confirmation.
- Rejected or failed confirmation → `needs_review`.
- Policy, auth, CAPTCHA, environment, or infrastructure problem → record and report; do not replan.

### Final evaluation

Final re-planning is permitted only for missing or incorrect coverage. It is prohibited for application defects, authentication failures, infrastructure failures, policy blocks, CAPTCHA/2FA, and unsupported browser capabilities.

Final re-planning appends valid new flows. It cannot delete or replace retained flows or expected values.

## 12. Limits

Preserve current Qpilot limits initially:

```text
Initial coverage replans:             1
Generation retries:                   1
Unchanged execution retries:          1 per flow
Healing proposals:                    1 per flow
Final coverage replans:               1
Logical OpenAI calls:                 5 by default
OpenAI SDK retries:                   1 per call
Pages and scenarios:                  maximum 12 each
Actions per flow:                     maximum 20
Run deadline:                         10 minutes
Active local runs:                    1
```

If six agents cannot operate within five logical calls, the limit must become configurable and be increased only after measuring cost and duration. Agents may be skipped when their deterministic equivalent is sufficient.

## 13. LLM failure behavior

Agent failure must never silently become success.

| Agent failure | Response |
|---|---|
| PRD Analyst | Use existing Markdown requirement blocks and mark degraded analysis |
| Planner | Use existing observed-content baseline and mark limited business coverage |
| Plan Evaluator | Use existing deterministic `coverage()` |
| Generator | Use deterministic serialization only when a valid compatible plan already exists |
| Generation Evaluator | Use live-validation facts and deterministic plan-to-suite checks |
| Healer | Preserve failure as `needs_review`; never guess a repair |
| Final Evaluator | Use deterministic traceability and triage facts |
| Reporter | Produce existing deterministic reports without narrative |

Every fallback records:

```text
failed agent
failure type
fallback used
coverage/quality impact
remaining risk
```

## 14. Suite evolution integration

The new `evolution.py` behavior is mandatory in V2:

- Find the latest compatible completed suite.
- Retain existing IDs, steps, and assertions.
- Remap revised PRD links without replacing expected values.
- Append new scenarios only when observations or requirements justify them.
- Never use failed or cancelled runs as a source suite.
- Record added, reused, deferred, changed, regressed, recovered, and repaired scenarios.
- Store a new immutable snapshot for every completed run.
- Treat an absent page as “not observed,” not automatically removed.

Planner and final re-planning must respect this append-only evolution policy.

## 15. Checkpoint and browser safety

LangGraph persistence does not make browser actions automatically safe to resume.

- Checkpoint only serializable stage state and artifact identifiers.
- Never checkpoint live Playwright objects.
- Nodes that only analyze stored data may resume normally.
- Browser-action nodes restart in a fresh context after interruption.
- Mutating actions require idempotency evidence or restart from a safe flow boundary.
- Unknown side effects prevent automatic mid-flow replay.
- Cleanup must close browser resources in success, failure, timeout, and cancellation paths.

## 16. FastAPI and UI integration

Add `pipeline_version` to stored run metadata and API responses while maintaining current request compatibility.

The existing dashboard will display:

- V1 or V2 pipeline version.
- Current LangGraph stage.
- PRD Analyst result.
- Planner plan and reused/new flows.
- Plan evaluation decision and gaps.
- Generation mapping and failed generation items.
- Test execution evidence.
- Healing proposals and verification.
- Final evaluation decision.
- Suite changes and regressions.
- Deterministic report plus optional narrative.
- Degraded-mode and exhausted-limit warnings.

Existing polling, cancellation, run history, evidence export, security headers, and session protection remain unchanged.

## 17. Implementation phases

### Phase 0 — Preserve baseline

1. Install dependencies in a Qpilot-specific virtual environment.
2. Run current Pytest and verification commands.
3. Record test counts, failures, runtime, and current artifacts.
4. Record the V1 commit and configuration.

Deliverable: reproducible V1 baseline and rollback point.

### Phase 1 — V2 contracts and stub graph

1. Add LangGraph dependencies and version flag.
2. Create V2 models, state, policies, ports, events, errors, checkpoints, nodes, and routing.
3. Create deterministic stubs matching every agent output.
4. Test all graph routes and limits without LLM or browser calls.

Deliverable: terminating checkpointed graph with no V1 modification.

### Phase 2 — Deterministic Qpilot adapters

Connect existing components through adapters:

```text
authentication
reconnaissance
suite lookup/evolution
live validation
execution
triage
deterministic healing
reporting
persistence and cleanup
```

Deliverable: V2 deterministic flow producing current Qpilot-compatible artifacts.

### Phase 3 — Agent development

Develop agents in this order:

```text
PRD Analyst
→ Planner
→ Plan Evaluator
→ Generator
→ Generation Evaluator
→ Healer
→ Final Evaluator
→ Reporter
```

The same Evaluator implementation serves all three modes. Each agent must return the exact V2 contract and remain replaceable through its port.

Deliverable: individually callable agents producing compatible outputs.

### Phase 4 — Agent connection

1. Connect one agent at a time through adapters.
2. Validate returned contracts before state updates.
3. Keep deterministic safety gates after every LLM response.
4. Record agent usage, tokens, confidence, evidence, and fallback.

Deliverable: complete agent pipeline behind `QA_PIPELINE_VERSION=v2`.

### Phase 5 — API and UI

1. Add `pipeline_selector.py`.
2. Route new V2 runs through LangGraph when selected.
3. Expose agent/evaluator stages in existing run details.
4. Extend the dashboard without removing existing V1 views.

Deliverable: selectable V1/V2 application from the current UI.

### Phase 6 — Local production hardening

1. Validate checkpoint restart behavior at safe boundaries.
2. Verify cancellation and deadline behavior.
3. Verify atomic artifacts and cleanup.
4. Confirm secrets never enter checkpoints or reports.
5. Add dependency lock and configuration documentation.
6. Add Docker Compose only after native local validation passes.

Deliverable: local production-grade V2, one infrastructure step away from cloud deployment.

## 18. Required tests

### Contract tests

- Valid and invalid response envelope.
- Every agent-domain schema.
- Stable IDs and requirement links.
- Plan-to-suite mapping.
- Immutable assertions during healing.

### Graph-path tests

```text
URL only → success
Markdown PRD → success
Plan gap → one replan → success
Generation gap → one regeneration → success
Execution failure → unchanged retry → flaky
Execution locator failure → heal → confirmation passes
Requirement assertion fails twice → likely defect
Healer ambiguity → needs review
Agent timeout → degraded deterministic output
Invalid agent response → fallback/report
Final coverage gap → append-only replan
All retry limits exhausted → report
Cancellation → cleanup and retained evidence
Process interruption → safe stage restart
```

### Regression tests

- All existing Qpilot unit and lifecycle tests.
- Existing API fields and UI behavior.
- Existing origin and interaction safety.
- Existing authentication configuration.
- Existing report and evidence export formats.
- Existing suite reuse, repair persistence, and evolution behavior.

### Live evidence tests

- Local Qpilot demo.
- Authenticated SauceDemo read-only run.
- Real OpenAI planning response.
- Real PRD Analyst extraction.
- Real generation evaluation.
- Controlled locator drift and verified healing.
- Controlled application assertion failure that remains unhealed.

Mocked results must never be presented as live evidence.

## 19. Production migration readiness

Local V2 uses SQLite checkpoints and local artifacts. Interfaces must permit later replacement:

```text
SQLite checkpointer → PostgreSQL checkpointer
Local files          → S3-compatible object storage
In-process tasks     → durable worker service
Local environment    → secret manager
One active run       → queued horizontally scaled workers
Polling              → SSE/WebSocket if required
```

These deployment components are not implemented until the local V2 pipeline is complete.

## 20. Definition of done

V2 is complete only when:

- V1 remains available and unchanged.
- V2 runs through LangGraph with durable local checkpoints.
- URL remains the only required input.
- PRD is optional and produces source-traceable requirements.
- Planner, Generator, and Healer are explicit agent roles.
- One Evaluator supports plan, generation, and final modes.
- Generated behavior uses Qpilot's safe typed action DSL.
- Live validation occurs before execution.
- Executor remains deterministic.
- Healer cannot modify assertions or business expectations.
- Suite evolution retains existing IDs and assertions.
- Final report includes results, healing, defects, gaps, untested risks, traceability, changes, and degraded modes.
- All retries are bounded and every graph path terminates.
- Cancellation, failure, and timeout paths release browser resources.
- Existing Qpilot regressions and new V2 tests pass.
- A real URL completes through V2 with browser and model evidence.

## 21. First action before implementation

Create a Qpilot-specific virtual environment, install the pinned dependencies, and record the current V1 baseline. Then implement only Phase 1—the V2 contracts and stub LangGraph—without connecting or changing existing agent/browser/runtime code.

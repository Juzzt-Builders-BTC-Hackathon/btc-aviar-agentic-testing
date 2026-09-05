import asyncio
import hashlib
import json
import time
from playwright.async_api import async_playwright
from .browser import auth_state, crawl, execute_flow
from .healing import deterministic_candidate, semantic_match
from .llm import LLM
from .models import RunRequest
from .planning import baseline_plan, coverage, requirements_list, ground_oracles, prd_requirements, unobserved_selectors
from .reporting import reports
from .safety import redact, target_url
from .runtime import launch_browser, error_details
from .evolution import previous_suite, page_changes, remap_requirements, merge_plan, outcome_changes, suite_key, should_extend_suite
from .triage import triage_flow, defect_report


def fingerprint_key(url, flow, index):
    step = flow.steps[index]
    return hashlib.sha256(f"{url}|{flow.name}|{index}|{step.intent}".encode()).hexdigest()


def remember_fingerprints(store, url, flow, result):
    """A successful step is evidence even when a later assertion fails."""
    if result.get('attempt') == 'healed' and result.get('status') != 'passed':
        return  # An unverified proposal must not update repair memory.
    for step in result.get('steps', []):
        if step.get('status') == 'passed' and step.get('fingerprint'):
            store.fingerprint(fingerprint_key(url, flow, step['index']), step['fingerprint'])


def export_suite(store, rid, request, plan):
    store.artifact(rid, "suite.json", {"request": request.model_dump(), "plan": plan.model_dump()})
    # Model data remains JSON. No model-generated Python is ever evaluated.
    store.artifact(rid, "generated_tests.py", '"""Replay from the project root: python path/to/generated_tests.py"""\nfrom pathlib import Path\nimport sys\nsys.path.insert(0, str(Path.cwd()))\nfrom qa_agent.replay import main\nif __name__ == "__main__":\n    main(Path(__file__).with_name("suite.json"))\n')


async def run_pipeline(store, rid, authentication=None):
    request = RunRequest.model_validate(store.get(rid)["request"])
    llm = LLM()
    started = time.monotonic()
    def event(stage, message):
        store.update(rid, status="running", stage=stage)
        store.event(rid, stage, redact(message))
    try:
        async with asyncio.timeout(600):
            event("recon", "Starting isolated Chromium; run deadline is 10 minutes.")
            async with async_playwright() as pw:
                browser = await launch_browser(pw)
                try:
                    state = await auth_state(browser, request.url, authentication)
                    authentication = None
                    if state: event("recon", "Authenticated session established.")
                    pages = await crawl(browser, request, state, lambda message: event("recon", message))
                    store.artifact(rid, "recon.json", pages)
                    requirements = requirements_list(request.requirements) + prd_requirements(request.prd_content)
                    if request.prd_content:
                        store.artifact(rid, "prd.md", request.prd_content)
                    previous = previous_suite(store, request)
                    changes = page_changes(previous["pages"], pages) if previous else []
                    evolution = {"suite_key": suite_key(request), "previous_run": previous["id"] if previous else None,
                                 "ui_changes": changes, "reused": [], "added": [], "deferred": [], "outcomes": []}
                    retained = remap_requirements(previous["plan"].model_copy(deep=True), previous["requirements"], requirements) if previous else None
                    if retained:
                        failed = {r['flow_id'] for r in previous['results'] if r['status'] != 'passed'}
                        invalid = {i['flow_id'] for i in unobserved_selectors(retained, previous['pages'])} & failed
                        evolution['invalidated'] = sorted(invalid)
                        if invalid:
                            retained.flows = [f for f in retained.flows if f.id not in invalid]
                            event('plan', f"Discarding {len(invalid)} previously failed generated scenarios with selectors absent from their original page evidence; regenerating coverage.")
                            if not retained.flows: retained = None
                    if retained:
                        evolution["reused"] = [f.id for f in retained.flows]
                        event("plan", f"Reusing {len(retained.flows)} existing scenarios from {previous['id'][:8]}; original assertions retained.")
                    store.artifact(rid, "requirements.json", requirements)
                    event("plan", "Generating evidence-grounded scenarios with OpenAI." if request.mode == "openai" else "Generating a deterministic baseline; no AI calls are made.")
                    limit = max(request.max_flows, len(retained.flows) if retained else 0)
                    pending = coverage(retained, pages, requirements) if retained else []
                    should_extend = should_extend_suite(request, previous, retained, changes, requirements, pending)
                    if retained and (not should_extend or len(retained.flows) >= limit):
                        plan = retained
                        if should_extend:
                            plan.gaps.append("Scenario budget reached; existing scenarios retained. Increase the scenario budget to explore additions.")
                        event("plan", "Existing suite retained without another planning call.")
                    else:
                        try:
                            proposed = await llm.plan(pages, request, requirements, existing=retained) if request.mode == "openai" else baseline_plan(pages, request.max_flows)
                            plan, evolution["added"], evolution["deferred"] = merge_plan(retained, proposed, limit)
                        except Exception as exc:
                            if retained is None: raise
                            plan = retained
                            plan.gaps.append(f"Suite enhancement unavailable ({type(exc).__name__}); existing suite will still execute.")
                    plan.gaps = list(dict.fromkeys(plan.gaps))[-30:]
                    store.artifact(rid, "suite_evolution.json", evolution)
                    store.artifact(rid, "plan.initial.json", plan.model_dump())
                    event("coverage", "Checking requirement links, assertions and missing negative paths before generation.")
                    gaps = coverage(plan, pages, requirements)
                    fixable = [g for g in gaps if "no planned test" in g or "no negative" in g or "Business journeys" in g]
                    if len(plan.flows) < request.max_flows:
                        fixable.append(f"Requested up to {request.max_flows} scenarios, but the plan contains {len(plan.flows)}. Return a complete plan with distinct supported scenarios; explain any evidence-based shortfall.")
                    if fixable and request.mode == "openai" and retained is None:
                        event("plan", "Coverage gaps triggered one bounded re-plan.")
                        plan = await llm.plan(pages, request, requirements, fixable)
                        plan.flows = plan.flows[:request.max_flows]
                        gaps = coverage(plan, pages, requirements)
                    issues = [i for i in unobserved_selectors(plan, pages) if i['flow_id'] not in evolution['reused']]
                    if issues and request.mode == 'openai' and retained is None:
                        event('plan', 'Correcting generated selectors that were not present in the observed page evidence.')
                        plan = await llm.plan(pages, request, requirements, ["Return the complete corrected plan. Copy selectors exactly from the corresponding observed page.", json.dumps(issues)])
                        plan.flows = plan.flows[:request.max_flows]
                        issues = unobserved_selectors(plan, pages)
                        gaps = coverage(plan, pages, requirements)
                    if issues:
                        store.artifact(rid, 'locator_warnings.json', issues)
                        event('validate', f"{len(issues)} generated selectors lack an exact snapshot match; browser validation will check uniqueness and visibility before use.")
                        gaps.append(f"{len(issues)} generated selectors lack exact snapshot matches. Inspect locator_warnings.json and per-step browser validation; unknown identity cannot be automatically healed.")
                    if len(plan.flows) < request.max_flows:
                        gaps.append(f"Generated {len(plan.flows)} of the requested maximum {request.max_flows} scenarios. The remaining budget was not filled with supported distinct scenarios.")
                    gaps.extend(ground_oracles(plan, requirements))
                    for flow in plan.flows:
                        for step in flow.steps:
                            if step.action == "navigate": target_url(request.url, step.target, request.navigation_origins)
                            if step.action in {"assert_text", "assert_url"} and not step.value.strip(): raise ValueError("Empty assertion rejected")
                        if flow.oracle == "requirement" and not flow.requirement_ids:
                            raise ValueError("Requirement-backed oracle must reference a supplied requirement")
                    store.artifact(rid, "plan.json", plan.model_dump())
                    store.artifact(rid, "coverage_gaps.json", gaps)
                    event("generate", f"Compiling {len(plan.flows)} scenarios into a replayable Playwright action suite.")
                    export_suite(store, rid, request, plan)
                    event("validate", "Replaying each flow to check locators in the state where they are used.")
                    validation = []
                    for flow in plan.flows:
                        result = await execute_flow(browser, request, flow, state, store.root / rid, "validation")
                        remember_fingerprints(store, request.url, flow, result)
                        validation.append(result)
                        store.artifact(rid, "validation_report.json", validation)
                        event("validate", f"{flow.name}: {result['status']}")
                    results, heals = [], []
                    event("execute", "Executing validated flows in fresh browser contexts.")
                    for flow, validated in zip(plan.flows, validation):
                        async def execute(candidate, attempt):
                            attempt_result = await execute_flow(browser, request, candidate, state, store.root / rid, attempt)
                            remember_fingerprints(store, request.url, candidate, attempt_result)
                            return attempt_result
                        async def propose(candidate, failure):
                            return await repair(store, request, candidate, failure, pages, llm)
                        result, audits = await triage_flow(flow, validated, execute, propose, event)
                        heals.extend(audits)
                        application_diagnostics = [d for d in result.get('diagnostics', []) if d.get('category') != 'telemetry']
                        if application_diagnostics:
                            gaps.append(f"{flow.name}: {len(application_diagnostics)} browser/HTTP warning(s) observed; inspect diagnostics even if UI assertions passed.")
                        if result["status"] != "passed": gaps.append(f"{flow.name}: {result['status']} — scenario not verified.")
                        results.append(result)
                        store.artifact(rid, "run_results.json", results)
                        store.artifact(rid, "heal_log.json", heals)
                        event("execute", f"{flow.name}: {result['status']} ({result['classification']['label']})")
                    event("report", "Synthesizing the Test Quality Report, Defect Classifier and suite evolution.")
                    evolution["outcomes"] = outcome_changes(previous["results"] if previous else [], results)
                    evolution["added"] = [f.id for f in plan.flows if f.id not in evolution["reused"]]
                    store.artifact(rid, "suite_evolution.json", evolution)
                    store.artifact(rid, "defect_report.json", defect_report(plan, results, heals))
                    export_suite(store, rid, request, plan)
                    store.artifact(rid, "plan.json", plan.model_dump())
                    store.artifact(rid, "coverage_gaps.json", gaps)
                    store.artifact(rid, "classifications.json", [{"flow_id": r["flow_id"], **r["classification"]} for r in results])
                    summary = reports(store, rid, request, plan, results, gaps, heals, requirements, llm.usage())
                    summary.update(requested_max_flows=request.max_flows, reused=len(evolution["reused"]), added=len(evolution["added"]),
                                   regressions=sum(c["change"] == "regression" for c in evolution["outcomes"]),
                                   ui_changes=len(changes), previous_run=evolution["previous_run"])
                finally: await browser.close()
        summary["duration_seconds"] = round(time.monotonic() - started, 1)
        store.update(rid, status="completed", stage="done", summary=summary)
        store.event(rid, "done", "Run complete. Browser resources released; review results and coverage gaps before making a release decision.")
    except asyncio.CancelledError:
        store.update(rid, status="cancelled", summary={"usage": llm.usage()})
        store.event(rid, "cancelled", "Run cancelled. Partial artifacts retained.")
        raise
    except Exception as exc:
        error = "Run exceeded its 10-minute deadline" if isinstance(exc, TimeoutError) else redact(str(exc))[:1500]
        diagnostic = error_details(exc, store.get(rid)["stage"])
        try:
            store.artifact(rid, "runtime_error.json", diagnostic)
        except OSError as artifact_error:
            diagnostic["artifact_write_error"] = redact(str(artifact_error))[:500]
        store.update(rid, status="failed", summary={"error": error, "diagnostic": diagnostic, "usage": llm.usage()})
        store.event(rid, "failed", f"{type(exc).__name__}: {error}")


async def repair(store, request, flow, result, pages, llm):
    index = result["failed_step"]
    step = flow.steps[index]
    old = store.fingerprint(fingerprint_key(request.url, flow, index))
    page_url = result.get('failure_snapshot', {}).get('url')
    if old and old.get('page_url') and page_url and old['page_url'] != page_url:
        old = None
    if not old:
        observations = [e for p in pages if p.get('url') == page_url for e in p['elements'] if e['selector'] == step.target]
        if len(observations) == 1: old = observations[0]
    audit = {"flow_id": flow.id, "step": index, "old_selector": step.target, "verified": False}
    scoped = result.get("scoped_regeneration")
    if scoped and result.get("attempt") == "validation":
        fixed = flow.model_copy(deep=True)
        fixed.steps[index].target = scoped["selector"]
        return fixed, {**audit, "tier": "scoped_regeneration", "confidence": .9, "new_selector": scoped["selector"],
            "anchor_selector": scoped["anchor"], "original_matches": scoped["original_matches"],
            "rationale": "Scoped repeated elements to the smallest container of the immediately preceding verified text anchor. Expected assertion value was not used to select the element."}
    if not old: return None, {**audit, "rationale": "No prior fingerprint; semantic identity cannot be established."}
    candidates = result.get("failure_snapshot", {}).get("elements", [])
    match = deterministic_candidate(old, candidates)
    if not match and request.mode == "openai" and llm.calls < 5:
        try:
            proposal = await llm.heal(old, candidates, step.intent)
            if proposal.confidence >= .9 and 0 <= proposal.candidate_index < len(candidates):
                candidate = candidates[proposal.candidate_index]
                eligible = [c for c in candidates if semantic_match(old, c)]
                if semantic_match(old, candidate) and len(eligible) == 1:
                    match = {"candidate": candidate, "confidence": proposal.confidence, "tier": "openai", "rationale": proposal.rationale}
        except Exception as exc:
            audit["fallback_error"] = type(exc).__name__
    if not match: return None, {**audit, "rationale": "No unique, high-confidence replacement passed the semantic identity gate."}
    fixed = flow.model_copy(deep=True)
    fixed.steps[index].target = match["candidate"]["selector"]
    return fixed, {**audit, **{k: v for k, v in match.items() if k != "candidate"}, "new_selector": fixed.steps[index].target}

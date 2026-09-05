import asyncio
import hashlib
import json
import time
from playwright.async_api import async_playwright
from .browser import auth_state, crawl, execute_flow
from .healing import deterministic_candidate, semantic_match, classify
from .llm import LLM
from .models import RunRequest
from .planning import baseline_plan, coverage, requirements_list, ground_oracles
from .reporting import reports
from .safety import redact, target_url
from .runtime import launch_browser, error_details


def fingerprint_key(url, flow, index):
    step = flow.steps[index]
    return hashlib.sha256(f"{url}|{flow.name}|{index}|{step.intent}".encode()).hexdigest()


def export_suite(store, rid, request, plan):
    store.artifact(rid, "suite.json", {"request": request.model_dump(), "plan": plan.model_dump()})
    # Model data remains JSON. No model-generated Python is ever evaluated.
    store.artifact(rid, "generated_tests.py", '"""Replay from the project root: python path/to/generated_tests.py"""\nfrom pathlib import Path\nimport sys\nsys.path.insert(0, str(Path.cwd()))\nfrom qa_agent.replay import main\nif __name__ == "__main__":\n    main(Path(__file__).with_name("suite.json"))\n')


async def run_pipeline(store, rid):
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
                    state = await auth_state(browser, request.url)
                    if state: event("recon", "Authenticated session established from local configuration.")
                    pages = await crawl(browser, request, state, lambda message: event("recon", message))
                    store.artifact(rid, "recon.json", pages)
                    requirements = requirements_list(request.requirements)
                    store.artifact(rid, "requirements.json", requirements)
                    event("plan", "Generating evidence-grounded scenarios with OpenAI." if request.mode == "openai" else "Generating a deterministic baseline; no AI calls are made.")
                    plan = await llm.plan(pages, request, requirements) if request.mode == "openai" else baseline_plan(pages, request.max_flows)
                    plan.flows = plan.flows[:request.max_flows]
                    store.artifact(rid, "plan.initial.json", plan.model_dump())
                    event("coverage", "Checking requirement links, assertions and missing negative paths before generation.")
                    gaps = coverage(plan, pages, requirements)
                    fixable = [g for g in gaps if "no planned test" in g or "no negative" in g or "Business journeys" in g]
                    if fixable and request.mode == "openai":
                        event("plan", "Coverage gaps triggered one bounded re-plan.")
                        plan = await llm.plan(pages, request, requirements, fixable)
                        plan.flows = plan.flows[:request.max_flows]
                        gaps = coverage(plan, pages, requirements)
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
                        validation.append(result)
                        store.artifact(rid, "validation_report.json", validation)
                        event("validate", f"{flow.name}: {result['status']}")
                    results, heals = [], []
                    event("execute", "Executing validated flows in fresh browser contexts.")
                    for flow, validated in zip(plan.flows, validation):
                        if validated["status"] == "blocked":
                            result = validated
                        elif validated.get("failure_kind") == "selector":
                            # Bounded regeneration uses observed semantic fingerprints only.
                            event("heal", f"Checking a single locator repair for {flow.name}.")
                            repaired, audit = await repair(store, request, flow, validated, pages, llm)
                            heals.append(audit)
                            if repaired:
                                validated = await execute_flow(browser, request, repaired, state, store.root / rid, "regenerated")
                                if validated["status"] == "passed":
                                    flow.steps = repaired.steps
                                    result = await execute_flow(browser, request, flow, state, store.root / rid, "run")
                                    audit["verified"] = result["status"] == "passed"
                                else: result = {**validated, "status": "generation_failed"}
                            else: result = {**validated, "status": "generation_failed"}
                        else:
                            result = await execute_flow(browser, request, flow, state, store.root / rid, "run")
                        retry, healed = None, False
                        if result["status"] == "failed":
                            event("triage", f"Re-running {flow.name} once without changes to check repeatability.")
                            retry = await execute_flow(browser, request, flow, state, store.root / rid, "retry")
                            if retry["status"] == "failed" and result.get("failure_kind") == "selector":
                                event("heal", "Trying deterministic fingerprint matching, then a gated semantic fallback.")
                                repaired, audit = await repair(store, request, flow, result, pages, llm)
                                heals.append(audit)
                                if repaired:
                                    confirmation = await execute_flow(browser, request, repaired, state, store.root / rid, "healed")
                                    audit["verified"] = confirmation["status"] == "passed"
                                    if audit["verified"]:
                                        result["original_failure"] = {k: v for k, v in result.items() if k != "original_failure"}
                                        result.update(status="passed", healed_attempt=confirmation)
                                        flow.steps = repaired.steps
                                        healed = True
                        result["classification"] = classify(result.get("original_failure", result), retry, healed)
                        if retry: result["retry"] = retry
                        if result.get("diagnostics"):
                            gaps.append(f"{flow.name}: {len(result['diagnostics'])} browser/HTTP warning(s) observed; inspect diagnostics even if UI assertions passed.")
                        if result["status"] == "passed":
                            for step_result in result.get("healed_attempt", result)["steps"]:
                                if step_result.get("fingerprint"):
                                    store.fingerprint(fingerprint_key(request.url, flow, step_result["index"]), step_result["fingerprint"])
                        else: gaps.append(f"{flow.name}: {result['status']} — scenario not verified.")
                        results.append(result)
                        store.artifact(rid, "run_results.json", results)
                        store.artifact(rid, "heal_log.json", heals)
                        event("execute", f"{flow.name}: {result['status']} ({result['classification']['label']})")
                    event("report", "Aggregating deterministic results, requirements traceability and uncovered risks.")
                    export_suite(store, rid, request, plan)
                    store.artifact(rid, "plan.json", plan.model_dump())
                    store.artifact(rid, "coverage_gaps.json", gaps)
                    store.artifact(rid, "classifications.json", [{"flow_id": r["flow_id"], **r["classification"]} for r in results])
                    summary = reports(store, rid, request, plan, results, gaps, heals, requirements, llm.usage())
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
    if not old:
        old = next((e for p in pages for e in p["elements"] if e["selector"] == step.target), None)
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

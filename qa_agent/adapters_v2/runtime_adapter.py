"""Real Qpilot domain operations exposed as serializable V2 stage updates."""
import os
import time
from copy import deepcopy
from playwright.async_api import async_playwright

from ..agents_v2 import (EvaluatorAgent, GeneratorAgent, HealerAgent, PlannerAgent,
                         PRDAnalystAgent, ReporterAgent)
from ..browser import auth_state, crawl, execute_flow
from ..evolution import (merge_plan, outcome_changes, page_changes, previous_suite,
                         remap_requirements, suite_key)
from ..healing import classify
from ..llm import LLM
from ..models import Plan, RunRequest
from ..pipeline import export_suite, fingerprint_key
from ..planning import ground_oracles
from ..reporting import reports
from ..runtime import launch_browser
from ..triage import defect_report
from ..v2_models import AgentEnvelope, EvaluationResult, GeneratedSuite, PRDAnalysis
from ..orchestration_v2.events import event, now
from ..orchestration_v2.policies import MAX_LLM_CALLS


class V2Runtime:
    def __init__(self, store, run_id):
        self.store, self.run_id = store, run_id
        self.llm = LLM(max_calls=MAX_LLM_CALLS)
        self.prd_agent = PRDAnalystAgent(self.llm)
        self.planner_agent = PlannerAgent(self.llm)
        self.evaluator_agent = EvaluatorAgent(self.llm)
        self.generator_agent = GeneratorAgent(self.llm)
        self.healer_agent = HealerAgent(self.llm)
        self.reporter_agent = ReporterAgent(self.llm)
        self.started = time.monotonic()

    def request(self, state): return RunRequest.model_validate(state["request"])

    def update(self, state, stage, message, **values):
        self.store.update(self.run_id, status="running", stage=stage)
        self.store.event(self.run_id, stage, message)
        values.update(current_stage=stage, pipeline_status="running",
                      events=event(state, stage, message), logical_llm_calls=self.llm.calls,
                      token_usage=self.llm.usage())
        return values

    async def initialize(self, state):
        return self.update(state, "initialize", "Qpilot V2 LangGraph run initialized.",
                           started_at=now(), deadline_at=str(time.time() + 600))

    async def reconnaissance(self, state):
        request = self.request(state)
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser, request.url)
                pages = await crawl(browser, request, session,
                                    lambda msg: self.store.event(self.run_id, "recon", msg))
            finally:
                await browser.close()
        self.store.artifact(self.run_id, "recon.json", pages)
        return self.update(state, "recon", f"Observed {len(pages)} page(s).", recon_output=pages)

    async def load_evolution(self, state):
        request = self.request(state)
        previous = previous_suite(self.store, request)
        serial = None
        changes = []
        if previous:
            changes = page_changes(previous["pages"], state["recon_output"])
            serial = {"id": previous["id"], "request": previous["request"].model_dump(),
                      "plan": previous["plan"].model_dump(), "pages": previous["pages"],
                      "requirements": previous["requirements"], "results": previous["results"]}
        return self.update(state, "evolution", "Loaded prior compatible suite and bounded UI changes.",
                           previous_suite=serial, ui_changes=changes)

    async def analyze_prd(self, state):
        request = self.request(state)
        output = await self.prd_agent.run(request, request.requirements, request.prd_content)
        parsed = AgentEnvelope.model_validate(output)
        PRDAnalysis.model_validate(parsed.data)
        if request.prd_content: self.store.artifact(self.run_id, "prd.md", request.prd_content)
        requirements = self.legacy_requirements(parsed.data)
        self.store.artifact(self.run_id, "prd_analysis.json", parsed.model_dump())
        self.store.artifact(self.run_id, "requirements.json", requirements)
        degraded = list(state.get("degraded_components", []))
        if parsed.degraded_mode: degraded.append("prd_analyst")
        return self.update(state, "prd_analyst", f"Extracted {len(requirements)} requirement(s).",
                           requirements_output=parsed.model_dump(), degraded_components=degraded)

    @staticmethod
    def legacy_requirements(data):
        return [{"id": r["requirement_id"], "text": r["description"]} for r in data.get("requirements", [])]

    async def plan(self, state):
        request = self.request(state)
        requirements = self.legacy_requirements(state["requirements_output"]["data"])
        previous = state.get("previous_suite")
        retained = None
        if previous:
            retained = remap_requirements(Plan.model_validate(previous["plan"]),
                                          previous["requirements"], requirements)
        feedback = (state.get("plan_evaluation") or {}).get("data", {}).get("gaps", [])
        output = await self.planner_agent.run(request, state["recon_output"], requirements,
                                              existing=retained, feedback=feedback)
        parsed = AgentEnvelope.model_validate(output)
        Plan.model_validate(parsed.data["plan"])
        self.store.artifact(self.run_id, "planner_output.json", parsed.model_dump())
        attempts = state.get("planning_attempts", 0) + 1
        return self.update(state, "planner", f"Planner produced {len(parsed.data['plan']['flows'])} flow(s).",
                           planner_output=parsed.model_dump(), planning_attempts=attempts)

    async def evaluate_plan(self, state):
        request = self.request(state)
        plan = Plan.model_validate(state["planner_output"]["data"]["plan"])
        requirements = self.legacy_requirements(state["requirements_output"]["data"])
        output = await self.evaluator_agent.run("PLAN_EVALUATION", request,
            pages=state["recon_output"], requirements=requirements, plan=plan)
        parsed = AgentEnvelope.model_validate(output)
        review = EvaluationResult.model_validate(parsed.data)
        self.store.artifact(self.run_id, "plan_evaluation.json", parsed.model_dump())
        return self.update(state, "plan_evaluation", f"Plan decision: {review.decision}.",
                           plan_evaluation=parsed.model_dump())

    async def generate(self, state):
        request = self.request(state)
        plan = Plan.model_validate(state["planner_output"]["data"]["plan"])
        output = await self.generator_agent.run(request, plan)
        parsed = AgentEnvelope.model_validate(output)
        suite = GeneratedSuite.model_validate(parsed.data)
        self.store.artifact(self.run_id, "generator_output.json", parsed.model_dump())
        export_suite(self.store, self.run_id, request, suite.plan)
        attempts = state.get("generation_attempts", 0) + 1
        return self.update(state, "generator", f"Generated {len(suite.generated_flow_ids)} typed flow(s).",
                           generator_output=parsed.model_dump(), generation_attempts=attempts)

    async def validate(self, state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state["generator_output"]["data"])
        validation = []
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser, request.url)
                for flow in suite.plan.flows:
                    validation.append(await execute_flow(browser, request, flow, session,
                                                         self.store.root / self.run_id, "validation"))
            finally:
                await browser.close()
        self.store.artifact(self.run_id, "validation_report.json", validation)
        return self.update(state, "validation", "Live validation completed.", validation_results=validation)

    async def evaluate_generation(self, state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state["generator_output"]["data"])
        requirements = self.legacy_requirements(state["requirements_output"]["data"])
        output = await self.evaluator_agent.run("GENERATION_EVALUATION", request,
            requirements=requirements, plan=suite.plan, generated=state["generator_output"]["data"],
            validation=state["validation_results"])
        parsed = AgentEnvelope.model_validate(output)
        review = EvaluationResult.model_validate(parsed.data)
        self.store.artifact(self.run_id, "generation_evaluation.json", parsed.model_dump())
        return self.update(state, "generation_evaluation", f"Generation decision: {review.decision}.",
                           generation_evaluation=parsed.model_dump())

    async def execute(self, state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state["generator_output"]["data"])
        validation = {r.get("flow_id"): r for r in state.get("validation_results", [])}
        results = []
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser, request.url)
                for flow in suite.plan.flows:
                    validated = validation.get(flow.id, {})
                    if validated.get("status") == "blocked":
                        original, retry = validated, None
                    else:
                        original = await execute_flow(browser, request, flow, session,
                                                      self.store.root / self.run_id, "run")
                        retry = await execute_flow(browser, request, flow, session,
                                                   self.store.root / self.run_id, "retry") if original.get("status") == "failed" else None
                    result = dict(original)
                    if retry: result["retry"] = retry
                    result["classification"] = classify(original, retry)
                    result["name"], result["risk"], result["oracle"] = flow.name, flow.risk, flow.oracle
                    result["flow_id"] = flow.id
                    result["original_flow"] = flow.model_dump()
                    result["attempts"] = [x for x in (original, retry) if x]
                    results.append(result)
            finally:
                await browser.close()
        self.store.artifact(self.run_id, "run_results.json", results)
        return self.update(state, "executor", f"Executed {len(results)} flow(s).", execution_results=results)

    async def heal(self, state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state["generator_output"]["data"])
        plan = suite.plan.model_copy(deep=True)
        results = deepcopy(state["execution_results"])
        actions = list(state.get("healer_actions", []))
        flow_by_id = {f.id: f for f in plan.flows}
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser, request.url)
                for result in results:
                    retry = result.get("retry")
                    if not (result.get("status") == "failed" and retry and retry.get("status") == "failed"
                            and result.get("failure_kind") == retry.get("failure_kind") == "selector"
                            and result.get("failed_step") == retry.get("failed_step")):
                        continue
                    flow = flow_by_id[result["flow_id"]]
                    index = result["failed_step"]
                    old = self.store.fingerprint(fingerprint_key(request.url, flow, index))
                    if not old:
                        old = next((e for p in state["recon_output"] for e in p["elements"]
                                    if e["selector"] == flow.steps[index].target), None)
                    candidates = result.get("failure_snapshot", {}).get("elements", [])
                    proposal = AgentEnvelope.model_validate(await self.healer_agent.run(old, candidates, flow.steps[index].intent))
                    audit = {"flow_id": flow.id, "step": index, "old_selector": flow.steps[index].target,
                             **proposal.data, "verified": False}
                    selector = proposal.data.get("candidate_selector")
                    if selector:
                        repaired = flow.model_copy(deep=True)
                        repaired.steps[index].target = selector
                        confirmation = await execute_flow(browser, request, repaired, session,
                                                          self.store.root / self.run_id, "healed")
                        audit["verified"] = confirmation.get("status") == "passed"
                        if audit["verified"]:
                            flow.steps = repaired.steps
                            result.update(status="passed", healed_attempt=confirmation,
                                          classification=classify(result, retry, True))
                    actions.append(audit)
            finally:
                await browser.close()
        updated = GeneratedSuite(plan=plan, generated_flow_ids=suite.generated_flow_ids,
            ungenerated_flows=suite.ungenerated_flows, plan_to_suite_mapping=suite.plan_to_suite_mapping,
            generation_gaps=suite.generation_gaps, artifact_paths=suite.artifact_paths)
        generator_output = dict(state["generator_output"]); generator_output["data"] = updated.model_dump()
        self.store.artifact(self.run_id, "run_results.json", results)
        self.store.artifact(self.run_id, "heal_log.json", actions)
        return self.update(state, "healer", f"Evaluated {len(actions)} healing proposal(s).",
                           execution_results=results, healer_actions=actions, generator_output=generator_output)

    async def evaluate_final(self, state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state["generator_output"]["data"])
        requirements = self.legacy_requirements(state["requirements_output"]["data"])
        output = await self.evaluator_agent.run("FINAL_EVALUATION", request,
            requirements=requirements, plan=suite.plan, generated=state["generator_output"]["data"],
            validation=state["validation_results"], results=state["execution_results"],
            heals=state["healer_actions"])
        parsed = AgentEnvelope.model_validate(output)
        review = EvaluationResult.model_validate(parsed.data)
        self.store.artifact(self.run_id, "final_evaluation.json", parsed.model_dump())
        replans = state.get("final_replan_attempts", 0) + (1 if review.decision == "REPLAN" else 0)
        return self.update(state, "final_evaluation", f"Final decision: {review.decision}.",
                           final_evaluation=parsed.model_dump(), final_replan_attempts=replans)

    async def evolve(self, state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state["generator_output"]["data"])
        previous = state.get("previous_suite")
        reused = (state.get("planner_output") or {}).get("data", {}).get("reused_flow_ids", [])
        evolution = {"suite_key": suite_key(request), "previous_run": previous["id"] if previous else None,
                     "ui_changes": state.get("ui_changes", []), "reused": reused,
                     "added": [f.id for f in suite.plan.flows if f.id not in reused],
                     "deferred": (state.get("planner_output") or {}).get("data", {}).get("deferred_candidates", []),
                     "outcomes": outcome_changes(previous["results"] if previous else [], state["execution_results"])}
        self.store.artifact(self.run_id, "suite_evolution.json", evolution)
        return self.update(state, "suite_evolution", "Stored immutable suite evolution evidence.", evolution_output=evolution)

    async def report(self, state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state["generator_output"]["data"])
        requirements = self.legacy_requirements(state["requirements_output"]["data"])
        gaps = list(dict.fromkeys((state["plan_evaluation"]["data"].get("gaps", [])
                    + state["generation_evaluation"]["data"].get("gaps", [])
                    + state["final_evaluation"]["data"].get("untested_risks", []))))
        gaps.extend(ground_oracles(suite.plan, requirements))
        self.store.artifact(self.run_id, "defect_report.json", defect_report(suite.plan, state["execution_results"], state["healer_actions"]))
        self.store.artifact(self.run_id, "classifications.json", [{"flow_id": r["flow_id"], **r["classification"]} for r in state["execution_results"]])
        self.store.artifact(self.run_id, "coverage_gaps.json", gaps)
        export_suite(self.store, self.run_id, request, suite.plan)
        summary = reports(self.store, self.run_id, request, suite.plan, state["execution_results"],
                          gaps, state["healer_actions"], requirements, self.llm.usage())
        narrative = await self.reporter_agent.run(request, {"summary": summary, "gaps": gaps,
            "classifications": [r["classification"] for r in state["execution_results"]]})
        self.store.artifact(self.run_id, "agent_narrative.json", narrative)
        summary.update(pipeline_version="v2", duration_seconds=round(time.monotonic() - self.started, 1),
                       previous_run=(state.get("evolution_output") or {}).get("previous_run"))
        self.store.update(self.run_id, status="completed", stage="done", summary=summary)
        self.store.event(self.run_id, "done", "Qpilot V2 run completed; review failures and coverage gaps.")
        return {"current_stage": "done", "pipeline_status": "completed", "report_output": narrative,
                "logical_llm_calls": self.llm.calls, "token_usage": self.llm.usage(),
                "events": event(state, "done", "Qpilot V2 run completed.")}

    async def fail(self, state):
        error = state.get("errors", [{}])[-1]
        self.store.artifact(self.run_id, "runtime_error.json", error)
        self.store.update(self.run_id, status="failed", stage=state.get("current_stage", "v2"),
                          summary={"error": error.get("message", "V2 pipeline failed"), "pipeline_version": "v2"})
        self.store.event(self.run_id, "failed", error.get("message", "V2 pipeline failed"))
        return {"pipeline_status": "failed", "cleanup_completed": True,
                "events": event(state, "failed", "V2 failure persisted.")}

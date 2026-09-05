from ..models import Plan
from ..v2_models import GeneratedSuite, GenerationProposal, success


SYSTEM = """Convert the approved plan into the same safe typed browser-action DSL.
Use only navigate, fill, click, assert_visible, assert_text and assert_url. Preserve flow IDs,
requirement links and assertion meaning. Never emit Python, JavaScript, shell or new origins."""


class GeneratorAgent:
    def __init__(self, llm): self.llm = llm

    async def run(self, request, approved_plan):
        plan = approved_plan.model_copy(deep=True)
        gaps = []
        if request.mode == "openai" and self.llm.calls < self.llm.max_calls:
            try:
                proposal = await self.llm.ask(GenerationProposal, SYSTEM, {
                    "approved_plan": approved_plan.model_dump(), "allowed_actions":
                    ["navigate", "fill", "click", "assert_visible", "assert_text", "assert_url"]})
                proposed = {f.id: f for f in proposal.flows}
                # IDs and assertion values are immutable across generation.
                safe = []
                for original in approved_plan.flows:
                    candidate = proposed.get(original.id)
                    if candidate and self._same_assertions(original, candidate): safe.append(candidate)
                    else:
                        safe.append(original)
                        gaps.append(f"{original.id}: generator output rejected; approved flow retained")
                plan = Plan(summary=approved_plan.summary, flows=safe, gaps=list(dict.fromkeys(approved_plan.gaps + proposal.generation_gaps + gaps)))
            except Exception as exc:
                gaps.append(f"Generator fallback: {type(exc).__name__}; approved typed plan retained")
        ids = [f.id for f in plan.flows]
        suite = GeneratedSuite(plan=plan, generated_flow_ids=ids,
            plan_to_suite_mapping=[{"flow_id": x, "suite_flow_id": x} for x in ids], generation_gaps=gaps)
        return success(suite, confidence=.9 if not gaps else .7, evidence=["approved_plan"], degraded=bool(gaps))

    @staticmethod
    def _same_assertions(original, candidate):
        before = [(s.action, s.value) for s in original.steps if s.action.startswith("assert_")]
        after = [(s.action, s.value) for s in candidate.steps if s.action.startswith("assert_")]
        return before == after and original.requirement_ids == candidate.requirement_ids

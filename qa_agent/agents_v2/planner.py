from ..evolution import merge_plan
from ..planning import baseline_plan
from ..v2_models import success
from .support import available, error_message


class PlannerAgent:
    def __init__(self, llm): self.llm = llm

    async def run(self, request, pages, requirements, existing=None, feedback=None):
        errors = []
        if request.mode == "openai" and available(self.llm):
            try:
                proposed = await self.llm.plan(pages, request, requirements, feedback, existing)
            except Exception as exc:
                errors.append(error_message(exc))
                proposed = existing.model_copy(deep=True) if existing else baseline_plan(pages, request.max_flows)
        else:
            proposed = existing.model_copy(deep=True) if existing else baseline_plan(pages, request.max_flows)
            if request.mode == 'openai': errors.append('Planner call budget reserved for final stages')
        limit = max(request.max_flows, len(existing.flows) if existing else 0)
        plan, added, deferred = merge_plan(existing, proposed, limit)
        output = success({"plan": plan.model_dump(), "reused_flow_ids": [f.id for f in existing.flows] if existing else [],
                        "new_flow_ids": added, "deferred_candidates": deferred,
                        "uncovered_requirements": [], "exploration_limitations": []}, confidence=.85,
                       evidence=[p["url"] for p in pages], degraded=bool(errors))
        output['errors'] = errors
        return output

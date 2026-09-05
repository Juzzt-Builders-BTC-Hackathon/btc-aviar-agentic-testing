from ..evolution import merge_plan
from ..planning import baseline_plan
from ..v2_models import success


class PlannerAgent:
    def __init__(self, llm): self.llm = llm

    async def run(self, request, pages, requirements, existing=None, feedback=None):
        if request.mode == "openai":
            proposed = await self.llm.plan(pages, request, requirements, feedback, existing)
        else:
            proposed = baseline_plan(pages, request.max_flows)
        limit = max(request.max_flows, len(existing.flows) if existing else 0)
        plan, added, deferred = merge_plan(existing, proposed, limit)
        return success({"plan": plan.model_dump(), "reused_flow_ids": [f.id for f in existing.flows] if existing else [],
                        "new_flow_ids": added, "deferred_candidates": deferred,
                        "uncovered_requirements": [], "exploration_limitations": []}, confidence=.85,
                       evidence=[p["url"] for p in pages])

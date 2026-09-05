from ..v2_models import ReporterNarrative, success
from .support import available, error_message


SYSTEM = """Summarize verified QA facts without changing counts, classifications or status.
Call uncertainty and untested risk out explicitly. Do not claim full application coverage."""


class ReporterAgent:
    def __init__(self, llm): self.llm = llm

    async def run(self, request, facts):
        if request.mode == "openai" and available(self.llm, 0):
            try:
                result = await self.llm.ask(ReporterNarrative, SYSTEM, facts)
                return success(result, confidence=.8, evidence=["deterministic_report_facts"])
            except Exception as exc:
                value = success({"executive_summary": "Deterministic report generated; narrative unavailable.",
                                 "important_findings": [], "recommended_actions": []}, degraded=True)
                value["errors"] = [error_message(exc)]
                return value
        results = facts.get('results',[])
        output = success({'executive_summary':f'{sum(r.get("status") == "passed" for r in results)}/{len(results)} scenarios passed. Review untested risks and failures.',
            'important_findings':facts.get('gaps',[])[:20],
            'recommended_actions':['Review generation failures separately from suspected application defects.']}, degraded=request.mode == 'openai')
        if request.mode == 'openai': output['errors'] = ['Reporter LLM call budget exhausted; deterministic narrative used']
        return output

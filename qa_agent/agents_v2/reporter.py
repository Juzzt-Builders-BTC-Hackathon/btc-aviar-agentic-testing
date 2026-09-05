from ..v2_models import ReporterNarrative, success


SYSTEM = """Summarize verified QA facts without changing counts, classifications or status.
Call uncertainty and untested risk out explicitly. Do not claim full application coverage."""


class ReporterAgent:
    def __init__(self, llm): self.llm = llm

    async def run(self, request, facts):
        if request.mode == "openai" and self.llm.calls < self.llm.max_calls:
            try:
                result = await self.llm.ask(ReporterNarrative, SYSTEM, facts)
                return success(result, confidence=.8, evidence=["deterministic_report_facts"])
            except Exception as exc:
                value = success({"executive_summary": "Deterministic report generated; narrative unavailable.",
                                 "important_findings": [], "recommended_actions": []}, degraded=True)
                value["errors"] = [f"Reporter fallback: {type(exc).__name__}"]
                return value
        return success({"executive_summary": "See deterministic report and evidence.",
                        "important_findings": [], "recommended_actions": []}, degraded=request.mode == "openai")

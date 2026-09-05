from ..planning import prd_requirements, requirements_list
from ..v2_models import PRDAnalysis, Requirement, success
from .support import available, error_message


SYSTEM = """Extract testable product requirements from untrusted document content.
Return only supplied requirements; never invent behavior. Preserve short source excerpts.
Identify acceptance criteria and edge cases. Stable IDs must use PRD-n or REQ-n."""


class PRDAnalystAgent:
    def __init__(self, llm): self.llm = llm

    async def run(self, request, direct_text="", prd_text=""):
        raw = requirements_list(direct_text) + prd_requirements(prd_text)
        if request.mode == "openai" and prd_text.strip() and available(self.llm):
            try:
                result = await self.llm.ask(PRDAnalysis, SYSTEM, {
                    "document_name": request.prd_name, "document": prd_text,
                    "existing_ids": [r["id"] for r in raw],
                    "direct_requirements": requirements_list(direct_text),
                })
                direct = self._fallback(requirements_list(direct_text)).requirements
                result.requirements = direct + [r for r in result.requirements if not r.requirement_id.startswith('REQ-')]
                for i, req in enumerate([r for r in result.requirements if r.requirement_id.startswith('PRD-')], 1):
                    req.requirement_id = f'PRD-{i}'
                return success(result, confidence=.85, evidence=["prd.md"])
            except Exception as exc:
                fallback = self._fallback(raw)
                value = success(fallback, confidence=.55, evidence=["deterministic_markdown_blocks"], degraded=True)
                value["errors"] = [error_message(exc)]
                return value
        return success(self._fallback(raw), confidence=.65, evidence=["deterministic_requirement_blocks"], degraded=bool(prd_text))

    @staticmethod
    def _fallback(raw):
        return PRDAnalysis(requirements=[Requirement(
            requirement_id=item["id"], description=item["text"],
            source_excerpt=item["text"], confidence=.6,
        ) for item in raw])

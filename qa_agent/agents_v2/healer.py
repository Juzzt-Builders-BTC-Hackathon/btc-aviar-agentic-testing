from ..healing import deterministic_candidate, semantic_match
from ..v2_models import success
from .support import available, error_message


class HealerAgent:
    def __init__(self, llm): self.llm = llm

    async def run(self, old, candidates, intent, mode='baseline'):
        match = deterministic_candidate(old, candidates) if old else None
        if match:
            return success({"classification": "broken_locator", "candidate_selector": match["candidate"]["selector"],
                            "confidence": match["confidence"], "rationale": match["rationale"],
                            "changed_fields": ["target"], "requires_confirmation": True}, confidence=match["confidence"],
                           evidence=["deterministic_fingerprint_match"])
        if old and mode == 'openai' and available(self.llm):
            try:
                proposal = await self.llm.heal(old, candidates, intent)
            except Exception as exc:
                output = success({'classification':'needs_review','candidate_selector':None,
                    'confidence':0,'rationale':'Healer API unavailable; original failure retained',
                    'changed_fields':[],'requires_confirmation':False}, degraded=True)
                output['errors'] = [error_message(exc)]
                return output
            if proposal.confidence >= .9 and 0 <= proposal.candidate_index < len(candidates):
                candidate = candidates[proposal.candidate_index]
                eligible = [c for c in candidates if semantic_match(old, c)]
                if semantic_match(old, candidate) and len(eligible) == 1:
                    return success({"classification": "broken_locator", "candidate_selector": candidate["selector"],
                                    "confidence": proposal.confidence, "rationale": proposal.rationale,
                                    "changed_fields": ["target"], "requires_confirmation": True},
                                   confidence=proposal.confidence, evidence=["gated_llm_candidate"])
        return success({"classification": "needs_review", "candidate_selector": None, "confidence": 0,
                        "rationale": "No unique identity-preserving locator candidate.",
                        "changed_fields": [], "requires_confirmation": False}, confidence=0)

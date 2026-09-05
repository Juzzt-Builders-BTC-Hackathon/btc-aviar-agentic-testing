from difflib import SequenceMatcher


def semantic_match(old, candidate):
    if old.get("tag") != candidate.get("tag") or old.get("type") != candidate.get("type"): return False
    return any(old.get(k) and old.get(k) == candidate.get(k) for k in ("text", "name", "testid"))


def similarity(old, candidate):
    if not semantic_match(old, candidate): return 0.0
    keys = {"text": .40, "name": .20, "testid": .20, "role": .10, "tag": .10}
    total = sum(w for k, w in keys.items() if old.get(k))
    return sum(w * SequenceMatcher(None, old[k], candidate.get(k, "")).ratio() for k, w in keys.items() if old.get(k)) / (total or 1)


def deterministic_candidate(old, candidates):
    ranked = sorted([(similarity(old, c), i) for i, c in enumerate(candidates)], reverse=True)
    if not ranked or ranked[0][0] < .85: return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < .10: return None
    score, index = ranked[0]
    return {"candidate": candidates[index], "confidence": round(score, 3), "tier": "deterministic", "rationale": "Unique fingerprint match with unchanged semantic identity"}


def classify(original, retry=None, healed=False):
    if original["status"] == "blocked":
        return {"label": "blocked", "confidence": 1.0, "rationale": "Run policy prevented the action; the scenario is untested."}
    if healed:
        return {"label": "healed_ok", "confidence": .85, "rationale": "Only the locator changed; the entire flow passed again with its original assertions."}
    if original["status"] == "passed":
        return {"label": "passed", "confidence": 1.0, "rationale": "All configured assertions passed in this run."}
    if retry and retry["status"] == "passed":
        return {"label": "flaky_test", "confidence": .6, "rationale": "An unchanged flow passed on one isolated rerun; this is a flakiness signal, not a proven root cause."}
    if (retry and retry.get("failure_kind") == original.get("failure_kind") == "assertion"
            and retry.get("failed_step") == original.get("failed_step") and original.get("oracle") == "requirement"):
        return {"label": "likely_defect", "confidence": .7, "rationale": "The same requirement-backed assertion failed on two isolated attempts. Review the requirement and evidence to confirm."}
    return {"label": "needs_review", "confidence": .4, "rationale": "Evidence is insufficient to distinguish an application defect from an invalid test expectation or locator."}

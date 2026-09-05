import re
from .models import Plan, Flow, Step


def ground_oracles(plan, requirements):
    """Traceability is not proof of an exact assertion. Require quoted literals."""
    lookup = {r["id"]: r["text"] for r in requirements}
    notes = []
    for flow in plan.flows:
        if flow.oracle != "requirement": continue
        literals = set()
        for rid in flow.requirement_ids:
            literals.update(re.findall(r'"([^"\n]+)"', lookup.get(rid, "")))
        assertions = [s for s in flow.steps if s.action.startswith("assert_")]
        if not all(s.action in {"assert_text", "assert_url"} and s.value in literals for s in assertions):
            flow.oracle = "inferred"
            notes.append(f"{flow.name}: exact assertion is not a quoted requirement literal; oracle marked inferred for review.")
    return notes


def requirements_list(text):
    return [{"id": f"REQ-{i+1}", "text": line.strip()} for i, line in enumerate(x for x in text.splitlines() if x.strip())]


def prd_requirements(text):
    """Extract traceable Markdown prose blocks; headings remain context, not tests."""
    blocks, paragraph = [], []
    fenced = False
    def flush():
        if paragraph:
            blocks.append(" ".join(paragraph))
            paragraph.clear()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("```", "~~~")):
            flush(); fenced = not fenced; continue
        if fenced: continue
        if not line or line.startswith("#") or re.fullmatch(r"[-*_]{3,}", line):
            flush(); continue
        if re.match(r"^(?:[-*+] |\d+[.)] )", line):
            flush()
            line = re.sub(r"^(?:[-*+] |\d+[.)] )(?:\[[ xX]\] )?", "", line)
        paragraph.append(line)
    flush()
    return [{"id": f"PRD-{i+1}", "text": block} for i, block in enumerate(dict.fromkeys(blocks))]


def baseline_plan(pages, limit):
    flows = []
    for page in pages:
        elements = [e for e in page["elements"] if e["text"] and e["tag"] in {"h1", "h2"}]
        if not elements:
            elements = [e for e in page["elements"] if e["text"] and e.get("testid") in {"title", "inventory-item-name"}]
        if not elements:
            elements = [e for e in page["elements"] if e["text"] and e["tag"] not in {"input", "textarea"}]
        if not elements and page["text"].strip():
            elements = [{"selector": "body", "text": page["text"].strip().splitlines()[0][:160]}]
        if not elements: continue
        element = elements[0]
        flows.append(Flow(id=f"smoke_{len(flows)+1}", name=f"Page baseline: {page['title'] or page['url']}",
            risk="medium", category="smoke", requirement_ids=[], oracle="observed", steps=[
                Step(action="navigate", target=page["url"], value="", intent="Open observed page"),
                Step(action="assert_text", target=element["selector"], value=element["text"], intent="Verify observed page content remains visible")]))
        if len(flows) >= limit: break
    if not flows: raise ValueError("No stable visible text found for baseline assertions")
    return Plan(summary="Deterministic page-content baseline, generated from the live browser. No AI or business-flow coverage is claimed.", flows=flows,
        gaps=["Baseline mode covers observed page content only; use OpenAI for business-flow planning."])


def coverage(plan, pages, requirements):
    linked = {rid for f in plan.flows for rid in f.requirement_ids}
    valid = {r["id"] for r in requirements}
    if linked - valid: raise ValueError("Plan references unknown requirement IDs")
    gaps = list(plan.gaps)
    for page in pages:
        gaps.extend(page.get("limitations", []))
        if page.get("network_warnings"): gaps.append(f"{page['url']}: {len(page['network_warnings'])} requests blocked by the run policy; some content may be missing.")
        if page.get("crawl_failures"): gaps.append(f"{len(page['crawl_failures'])} pages could not be explored; see recon.json for causes.")
    for req in requirements:
        if req["id"] not in linked: gaps.append(f"{req['id']}: no planned test — {req['text']}")
    has_inputs = any(e["tag"] in {"input", "select", "textarea"} for p in pages for e in p["elements"])
    if has_inputs and not any(f.category in {"negative", "boundary"} for f in plan.flows):
        gaps.append("Visible input controls have no negative or boundary scenario.")
    if all(f.category == "smoke" for f in plan.flows): gaps.append("Business journeys are not covered by the current plan.")
    if any("captcha" in p["text"].lower() or "two-factor" in p["text"].lower() for p in pages):
        gaps.append("Possible CAPTCHA/2FA: automated bypass is unsupported; supply an authenticated test session.")
    gaps.append("Coverage is bounded to discovered pages and supplied requirements; undiscovered flows remain unassessed.")
    return list(dict.fromkeys(gaps))

import html
import json
from xml.etree.ElementTree import Element, SubElement, tostring


def reports(store, rid, request, plan, results, gaps, heals, requirements, usage):
    total = len(results)
    passed = sum(r["status"] == "passed" for r in results)
    summary = {"total": total, "passed": passed, "failed": sum(r["status"] == "failed" for r in results),
        "blocked": sum(r["status"] in {"blocked", "generation_failed"} for r in results),
        "healed": sum(bool(h.get("verified")) for h in heals),
        "runtime_healed": sum(r.get("classification", {}).get("label") == "healed_ok" for r in results),
        "pass_rate": round(100 * passed / total) if total else 0, "gap_count": len(gaps), "usage": usage}
    trace = [{**req, "flows": [f.id for f in plan.flows if req["id"] in f.requirement_ids],
        "passing_flows": [r["flow_id"] for r in results if r["status"] == "passed" and req["id"] in next(f.requirement_ids for f in plan.flows if f.id == r["flow_id"])]} for req in requirements]
    store.artifact(rid, "traceability.json", trace)
    lines = ["# QA run report", "", f"Target: {request.url}", f"Mode: {request.mode}", "", plan.summary, "",
        f"{passed}/{total} scenarios passed. {summary['blocked']} blocked or generation failures. {summary['healed']} verified repairs.",
        "Pass rate is not application coverage.", "", "## Scenarios and evidence"]
    for r in results:
        lines.extend(["", f"### {r['name']}", f"Status: {r['status']} | Risk: {r['risk']} | Oracle: {r['oracle']}",
            f"Classification: {r.get('classification', {}).get('label', 'needs_review')}", r.get("classification", {}).get("rationale", ""), r.get("error", ""),
            "Browser / HTTP diagnostics: " + json.dumps(r.get("diagnostics", []))])
    lines.extend(["", "## Coverage gaps / untested risk", *[f"- {g}" for g in gaps], "", "## Healing audit", json.dumps(heals, indent=2),
        "", "## Requirements traceability", json.dumps(trace, indent=2), "", "## OpenAI usage", json.dumps(usage, indent=2),
        "Cost is unavailable unless configured token prices are supplied. Token counts reflect reported usage; timed-out requests may still be billed."])
    markdown = "\n".join(lines)
    store.artifact(rid, "report.md", markdown)
    store.artifact(rid, "report.html", '<!doctype html><html><meta charset="utf-8"><title>QA report</title><body><pre style="white-space:pre-wrap;font:15px/1.7 system-ui;max-width:1000px;margin:40px auto">' + html.escape(markdown) + '</pre></body></html>')
    suite = Element("testsuite", name="Autonomous QA", tests=str(total), failures=str(summary["failed"]), skipped=str(summary["blocked"]))
    for r in results:
        case = SubElement(suite, "testcase", name=r["name"], classname=r["flow_id"], time=str(r.get("duration_ms", 0)/1000))
        if r["status"] == "failed": SubElement(case, "failure", message=r.get("failure_kind", "failure")).text = r.get("error", "")
        elif r["status"] != "passed": SubElement(case, "skipped", message=r["status"])
    store.artifact(rid, "junit.xml", tostring(suite, encoding="unicode"))
    return summary

"""Append-only suite evolution. Previous expected outcomes never follow live text drift."""
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit
from .models import Plan, RunRequest


def canonical_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, parts.fragment))


def suite_key(request):
    # Keep different scopes, modes and interaction policies separate. A PRD revision
    # intentionally stays in the same lineage so changed requirements are visible.
    value = [canonical_url(request.url), request.scope.strip(), request.mode,
             request.allow_interactions, request.resource_policy, sorted(request.navigation_origins)]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def previous_suite(store, request):
    with store.connect() as db:
        rows = db.execute("SELECT id, request FROM runs WHERE status='completed' ORDER BY created DESC").fetchall()
    for row in rows:
        prior_request = RunRequest.model_validate(json.loads(row["request"]))
        if suite_key(prior_request) == suite_key(request):
            plan = store.read(row["id"], "plan.json")
            if plan:
                return {"id": row["id"], "request": prior_request, "plan": Plan.model_validate(plan),
                        "pages": store.read(row["id"], "recon.json", []),
                        "requirements": store.read(row["id"], "requirements.json", []),
                        "results": store.read(row["id"], "run_results.json", [])}
    return None


def should_extend_suite(request, previous, retained, changes, requirements, gaps):
    return (not retained or bool(changes) or previous['requirements'] != requirements
            or any('no planned test' in gap for gap in gaps)
            or request.max_flows > previous['request'].max_flows)


def page_changes(old, new):
    before = {canonical_url(p["url"]): p for p in old}
    after = {canonical_url(p["url"]): p for p in new}
    changes = []
    for url in sorted(after.keys() - before.keys()):
        changes.append({"kind": "new_page", "url": url, "detail": "Newly observed in this bounded crawl"})
    for url in sorted(before.keys() - after.keys()):
        changes.append({"kind": "not_observed", "url": url, "detail": "Not observed this run; may reflect crawl budget or access, not removal"})
    for url in sorted(before.keys() & after.keys()):
        a, b = before[url], after[url]
        if a.get("text") != b.get("text"):
            changes.append({"kind": "content_changed", "url": url,
                            "before": a.get("text", "")[:1500], "after": b.get("text", "")[:1500]})
        def selectors(p):
            return {e["selector"] for e in p.get("elements", [])}
        removed, added = selectors(a)-selectors(b), selectors(b)-selectors(a)
        if removed or added:
            changes.append({"kind": "locators_changed", "url": url, "removed": sorted(removed)[:30], "added": sorted(added)[:30]})
    return changes


def remap_requirements(plan, old, new):
    by_id = {r["id"]: r["text"] for r in old}
    by_text = {r["text"]: r["id"] for r in new}
    for flow in plan.flows:
        original = list(flow.requirement_ids)
        flow.requirement_ids = [by_text[by_id[r]] for r in original if by_id.get(r) in by_text]
        if len(original) != len(flow.requirement_ids):
            plan.gaps.append(f"{flow.name}: linked PRD requirement changed or was removed. Original assertions retained; review expected behavior.")
            flow.oracle = "inferred"
    plan.gaps = plan.gaps[-30:]
    return plan


def signature(flow):
    return json.dumps([(s.action, s.target, s.value) for s in flow.steps], sort_keys=True)


def merge_plan(existing, proposed, limit):
    """Never replace a retained flow. Exact actions or same name+entry URL deduplicate."""
    if existing is None:
        proposed.flows = proposed.flows[:limit]
        return proposed, [f.id for f in proposed.flows], []
    merged = existing.model_copy(deep=True)
    added, deferred = [], []
    signatures = {signature(f) for f in merged.flows}
    identities = {(f.name.casefold(), f.steps[0].target) for f in merged.flows}
    ids = {f.id for f in merged.flows}
    for candidate in proposed.flows:
        if signature(candidate) in signatures or (candidate.name.casefold(), candidate.steps[0].target) in identities:
            continue
        if len(merged.flows) >= limit:
            deferred.append(candidate.name)
            continue
        candidate = candidate.model_copy(deep=True)
        if candidate.id in ids:
            candidate.id = "case_" + hashlib.sha256(signature(candidate).encode()).hexdigest()[:16]
        merged.flows.append(candidate)
        added.append(candidate.id)
        signatures.add(signature(candidate)); ids.add(candidate.id)
        identities.add((candidate.name.casefold(), candidate.steps[0].target))
    merged.summary = "Existing scenarios retained; new evidence used to extend coverage. " + proposed.summary[:2800]
    merged.gaps = list(dict.fromkeys(existing.gaps + proposed.gaps))[-30:]
    return merged, added, deferred


def outcome_changes(previous, results):
    old = {r["flow_id"]: r for r in previous}
    changes = []
    for result in results:
        prior = old.get(result["flow_id"])
        status = "new_scenario" if not prior else "regression" if prior["status"] == "passed" and result["status"] != "passed" else "recovered" if prior["status"] != "passed" and result["status"] == "passed" else "unchanged"
        if result.get("classification", {}).get("label") == "healed_ok": status = "repaired"
        changes.append({"flow_id": result["flow_id"], "name": result["name"], "change": status,
                        "previous": prior["status"] if prior else None, "current": result["status"]})
    return changes

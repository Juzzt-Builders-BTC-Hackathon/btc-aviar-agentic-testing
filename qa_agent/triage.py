"""Bounded Healer state machine. Classifications describe evidence, not certainty."""
from .healing import classify


def enrich_classification(classification, original):
    if original.get('failure_kind') == 'execution' and classification['label'] == 'needs_review':
        script_error = any(text in original.get('error','') for text in ('Element is not an', 'requires select', 'Unknown engine'))
        classification = {'label':'needs_review' if script_error else 'environment_issue', 'confidence':.5,
            'rationale':'Invalid browser action; repair the test script.' if script_error else
                        'Browser execution failed; inspect timing, connectivity and application availability.'}
        if script_error: classification['issue_type'] = 'test_script_issue'
    classification.setdefault('issue_type', {'healed_ok':'test_script_issue','likely_defect':'application_defect_suspected',
        'flaky_test':'intermittent_failure','environment_issue':'execution_environment','blocked':'policy_block',
        'generation_failed':'test_script_issue','passed':'none'}.get(classification['label'],'undetermined'))
    classification['next_action'] = {'healed_ok':'Reuse the verified locator; retain original evidence.',
        'likely_defect':'Review the requirement and reproductions with the application owner.',
        'flaky_test':'Investigate timing; retain the original failure.', 'passed':'No action required for these assertions.',
        'blocked':'Review permissions and untested risk.', 'generation_failed':'Repair the test before executing it.'
        }.get(classification['label'],'Inspect the failed step and evidence; do not rewrite business expectations.')
    return classification


def finalize_result(flow, validated, original, retry=None, confirmation=None):
    """Common evidence semantics for the separated V2 Executor and Healer nodes."""
    healed = bool(confirmation and confirmation.get('status') == 'passed')
    result = dict(original)
    if retry: result['retry'] = retry
    if healed:
        result.update(status='passed', original_failure=original, healed_attempt=confirmation)
    if validated.get('status') == 'failed' and original['status'] == 'passed':
        result = {**validated, 'retry':original}
        classification = classify(validated, original)
    elif original['status'] == 'generation_failed':
        classification = {'label':'generation_failed','confidence':1.0,'rationale':original.get('error','Test not executable')}
    else:
        classification = classify(original, retry, healed)
    result.update(classification=enrich_classification(classification, original),
        attempts=[a for a in (validated,original,retry,confirmation) if a],
        original_flow=flow.model_dump(), name=flow.name, risk=flow.risk, oracle=flow.oracle,
        agent_decisions=[{'node':a.get('attempt','execute'),'reason':a['status']} for a in (validated,original,retry,confirmation) if a])
    return result


async def triage_flow(flow, validated, execute, propose, event):
    original_flow = flow.model_copy(deep=True)
    attempts = [validated]
    audits, transitions = [], []
    def transition(node, reason):
        transitions.append({"node": node, "reason": reason})
        event("triage" if node != "healer" else "heal", f"{flow.name}: {node} — {reason}")

    if validated["status"] == "blocked":
        original = validated
    else:
        transition("executor", "Execute in a fresh browser context")
        original = await execute(flow, "run")
        attempts.append(original)
    result = dict(original)
    retry, healed = None, False
    if original["status"] == "failed":
        transition("retry", "One unchanged replay to check repeatability")
        retry = await execute(flow, "retry")
        attempts.append(retry)
        result["retry"] = retry
        if retry["status"] == "failed" and original.get("failure_kind") == retry.get("failure_kind") == "selector" and original.get("failed_step") == retry.get("failed_step"):
            transition("healer", "Repeated locator failure; evaluate one identity-preserving repair")
            # Validation can offer a unique scoped locator for a repeated component.
            source = validated if validated.get("scoped_regeneration") and validated.get("failed_step") == original.get("failed_step") else original
            repaired, audit = await propose(flow, source)
            audits.append(audit)
            if repaired:
                allowed = flow.model_copy(deep=True)
                allowed.steps[original["failed_step"]].target = repaired.steps[original["failed_step"]].target
                if repaired != allowed:
                    audit.update(verified=False, rationale="Repair rejected: changes exceeded the failed locator.")
                    repaired = None
            if repaired:
                transition("verify", "Replay the entire repaired flow with unchanged assertions")
                confirmation = await execute(repaired, "healed")
                attempts.append(confirmation)
                audit["verified"] = confirmation["status"] == "passed"
                if audit["verified"]:
                    flow.steps = repaired.steps
                    result.update(status="passed", original_failure=original, healed_attempt=confirmation)
                    healed = True
            if not healed:
                transition("escalate", "No verified repair; preserve the failure for review")
    if validated["status"] == "failed" and original["status"] == "passed":
        # Validation is also a real replay: do not hide an intermittent first failure.
        result = {**validated, "retry": original}
        classification = classify(validated, original)
    else:
        classification = classify(original, retry, healed)
    if original.get("failure_kind") == "execution" and classification["label"] == "needs_review":
        classification = {"label": "environment_issue", "confidence": .5,
                          "rationale": "Browser or execution failure; connectivity, timing and application availability require investigation."}
    classification["issue_type"] = {"healed_ok": "test_script_issue", "likely_defect": "application_defect_suspected",
        "flaky_test": "intermittent_failure", "environment_issue": "execution_environment", "blocked": "policy_block",
        "passed": "none"}.get(classification["label"], "undetermined")
    classification["next_action"] = {"healed_ok": "Reuse the verified locator; retain the original failure evidence.",
        "likely_defect": "Review the linked PRD and reproductions; confirm with the application owner.",
        "flaky_test": "Investigate timing or environment; the first failure remains recorded.",
        "passed": "No action required for these assertions.", "blocked": "Review test permissions and the untested flow."}.get(classification["label"], "Inspect failed step, expected behavior and browser evidence; no automatic assertion rewrite.")
    if classification["label"] in {"likely_defect", "needs_review", "environment_issue"} and not any(t["node"] == "escalate" for t in transitions):
        transition("escalate", classification["next_action"])
    classification = enrich_classification(classification, original)
    result.update(classification=classification, attempts=attempts, agent_decisions=transitions, original_flow=original_flow.model_dump())
    transition("classify", classification["label"])
    return result, audits


def defect_report(plan, results, heals):
    cases = {f.id: f for f in plan.flows}
    records = []
    for result in results:
        flow = cases[result["flow_id"]]
        from .models import Flow
        flow = Flow.model_validate(result.get("original_flow", flow.model_dump()))
        original = result.get("original_failure", result)
        index = original.get("failed_step")
        step = flow.steps[index] if index is not None and index < len(flow.steps) else None
        records.append({"flow_id": flow.id, "name": flow.name, "status": result["status"],
            "risk": flow.risk, "oracle": flow.oracle, "requirement_ids": flow.requirement_ids,
            "classification": result.get("classification", {}), "failed_step": index,
            "expected": {"action": step.action, "target": step.target, "value": step.value} if step else None,
            "actual": original.get("error", "All configured assertions passed."),
            "observed_page_text": original.get("failure_snapshot", {}).get("text", "")[:2000],
            "reproduction": [s.model_dump() for s in flow.steps],
            "attempts": [{k: a.get(k) for k in ("attempt", "status", "failure_kind", "failed_step", "error", "screenshot", "duration_ms")} for a in result.get("attempts", [result])],
            "diagnostics": original.get("diagnostics", []),
            "repairs": [h for h in heals if h["flow_id"] == flow.id],
            "decisions": result.get("agent_decisions", [])})
    return records

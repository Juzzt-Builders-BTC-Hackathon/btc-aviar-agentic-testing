from .policies import MAX_FINAL_REPLANS, MAX_GENERATION_ATTEMPTS, MAX_PLAN_ATTEMPTS


def after_node(state, success_route):
    return "fail" if state.get("fatal_error") else success_route


def after_plan_evaluation(state):
    if state.get("fatal_error"):
        return "fail"
    decision = (state.get("plan_evaluation") or {}).get("data", {}).get("decision")
    if decision == "REPLAN" and state.get("planning_attempts", 0) < MAX_PLAN_ATTEMPTS:
        return "planner"
    return "generator" if decision in {"APPROVE", "REPLAN"} else "fail"


def after_generation_evaluation(state):
    if state.get("fatal_error"):
        return "fail"
    decision = (state.get("generation_evaluation") or {}).get("data", {}).get("decision")
    if decision == "REGENERATE" and state.get("generation_attempts", 0) < MAX_GENERATION_ATTEMPTS:
        return "generator"
    return "executor" if decision in {"APPROVE", "REGENERATE"} else "fail"


def after_execution(state):
    if state.get("fatal_error"):
        return "fail"
    def repeatable_selector(result):
        retry = result.get("retry") or {}
        return (result.get("status") == "failed" and retry.get("status") == "failed"
                and result.get("failure_kind") == retry.get("failure_kind") == "selector"
                and result.get("failed_step") == retry.get("failed_step"))
    return "healer" if any(repeatable_selector(r) for r in state.get("execution_results", [])) else "final_evaluator"


def after_final_evaluation(state):
    if state.get("fatal_error"):
        return "fail"
    decision = (state.get("final_evaluation") or {}).get("data", {}).get("decision")
    if decision == "REPLAN" and state.get("final_replan_attempts", 0) <= MAX_FINAL_REPLANS:
        return "planner"
    return "evolution"

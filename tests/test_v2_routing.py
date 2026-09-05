from qa_agent.orchestration_v2.routing import (after_execution, after_final_evaluation,
                                                after_generation_evaluation, after_plan_evaluation)


def envelope(decision):
    return {"data": {"decision": decision}}


def test_evaluation_routes_are_bounded():
    assert after_plan_evaluation({"plan_evaluation": envelope("REPLAN"), "planning_attempts": 1}) == "planner"
    assert after_plan_evaluation({"plan_evaluation": envelope("REPLAN"), "planning_attempts": 2}) == "generator"
    assert after_generation_evaluation({"generation_evaluation": envelope("REGENERATE"), "generation_attempts": 1}) == "generator"
    assert after_generation_evaluation({"generation_evaluation": envelope("APPROVE")}) == "executor"
    assert after_final_evaluation({"final_evaluation": envelope("REPORT")}) == "evolution"


def test_only_repeated_matching_selector_failure_routes_to_healer():
    repeated = {"status": "failed", "failure_kind": "selector", "failed_step": 1,
                "retry": {"status": "failed", "failure_kind": "selector", "failed_step": 1}}
    assertion = {"status": "failed", "failure_kind": "assertion", "failed_step": 1,
                 "retry": {"status": "failed", "failure_kind": "assertion", "failed_step": 1}}
    assert after_execution({"execution_results": [repeated]}) == "healer"
    assert after_execution({"execution_results": [assertion]}) == "final_evaluator"

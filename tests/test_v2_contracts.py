import pytest
from pydantic import ValidationError
from qa_agent.v2_models import AgentEnvelope, EvaluationResult, Requirement


def test_agent_envelope_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AgentEnvelope(status="success", surprise=True)


def test_requirement_requires_stable_identifier():
    with pytest.raises(ValidationError):
        Requirement(requirement_id="bad", description="Login works")


def test_evaluator_contract_supports_all_three_stages():
    for stage in ("PLAN_EVALUATION", "GENERATION_EVALUATION", "FINAL_EVALUATION"):
        assert EvaluationResult(evaluation_stage=stage, decision="REPORT").evaluation_stage == stage

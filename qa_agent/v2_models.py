"""Strict contracts shared by Qpilot V2 agents and orchestration."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from .models import Flow, Plan


class V2Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Requirement(V2Model):
    requirement_id: str = Field(pattern=r"^(?:REQ|PRD)-[A-Za-z0-9_-]+$")
    title: str = Field(default="", max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=20)
    edge_cases: list[str] = Field(default_factory=list, max_length=20)
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    source_section: str = Field(default="", max_length=300)
    source_excerpt: str = Field(default="", max_length=2000)
    confidence: float = Field(default=0.5, ge=0, le=1)


class PRDAnalysis(V2Model):
    document_title: str = Field(default="Product requirements", max_length=300)
    requirements: list[Requirement] = Field(default_factory=list, max_length=100)
    unresolved_statements: list[str] = Field(default_factory=list, max_length=50)


class RequirementTrace(V2Model):
    requirement_id: str
    flow_ids: list[str] = Field(default_factory=list)
    status: Literal["covered", "partial", "uncovered"] = "uncovered"
    rationale: str = ""


class EvaluationResult(V2Model):
    evaluation_stage: Literal["PLAN_EVALUATION", "GENERATION_EVALUATION", "FINAL_EVALUATION"]
    decision: Literal["APPROVE", "REPLAN", "REGENERATE", "INVALID", "REPORT"]
    gaps: list[str] = Field(default_factory=list, max_length=50)
    invalid_items: list[str] = Field(default_factory=list, max_length=50)
    untested_risks: list[str] = Field(default_factory=list, max_length=50)
    requirement_traceability: list[RequirementTrace] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=3000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason_type: Literal["none", "coverage_gap", "generation_gap", "defect", "environment", "policy"] = "none"


class GenerationProposal(V2Model):
    flows: list[Flow] = Field(default_factory=list, max_length=12)
    generation_gaps: list[str] = Field(default_factory=list, max_length=30)


class GeneratedSuite(V2Model):
    plan: Plan
    generated_flow_ids: list[str]
    ungenerated_flows: list[dict[str, str]] = Field(default_factory=list)
    plan_to_suite_mapping: list[dict[str, str]] = Field(default_factory=list)
    generation_gaps: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)


class ReporterNarrative(V2Model):
    executive_summary: str = Field(max_length=3000)
    important_findings: list[str] = Field(default_factory=list, max_length=20)
    recommended_actions: list[str] = Field(default_factory=list, max_length=20)


class AgentEnvelope(V2Model):
    status: Literal["success", "partial", "failed"]
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[Any] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    degraded_mode: bool = False


def success(data: BaseModel | dict, *, confidence: float | None = None,
            evidence: list[Any] | None = None, degraded: bool = False) -> dict:
    payload = data.model_dump() if isinstance(data, BaseModel) else data
    return AgentEnvelope(status="success", data=payload, confidence=confidence,
                         evidence=evidence or [], degraded_mode=degraded).model_dump()

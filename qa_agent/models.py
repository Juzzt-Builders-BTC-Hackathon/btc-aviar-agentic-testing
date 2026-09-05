from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(StrictModel):
    url: str = Field(min_length=8, max_length=2000)
    scope: str = Field(default="", max_length=2000)
    requirements: str = Field(default="", max_length=12000)
    mode: Literal["openai", "baseline"] = "openai"
    allow_interactions: bool = False
    max_pages: int = Field(default=5, ge=1, le=12)
    max_flows: int = Field(default=6, ge=1, le=12)


class Step(StrictModel):
    action: Literal["navigate", "fill", "click", "assert_visible", "assert_text", "assert_url"]
    target: str = Field(max_length=2000)
    value: str = Field(max_length=2000)
    intent: str = Field(min_length=1, max_length=500)


class Flow(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    name: str = Field(min_length=1, max_length=200)
    risk: Literal["critical", "high", "medium", "low"]
    category: Literal["smoke", "happy_path", "negative", "boundary"]
    requirement_ids: list[str] = Field(max_length=30)
    oracle: Literal["requirement", "observed", "inferred"]
    steps: list[Step] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def meaningful(self):
        if self.steps[0].action != "navigate":
            raise ValueError("Every flow must start with navigation")
        if not any(s.action.startswith("assert_") for s in self.steps):
            raise ValueError("Every flow needs an assertion")
        return self


class Plan(StrictModel):
    summary: str = Field(max_length=3000)
    flows: list[Flow] = Field(min_length=1, max_length=12)
    gaps: list[str] = Field(max_length=30)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({f.id for f in self.flows}) != len(self.flows):
            raise ValueError("Duplicate flow IDs")
        return self


class HealProposal(StrictModel):
    candidate_index: int
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=1000)

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(StrictModel):
    url: str = Field(min_length=8, max_length=2000)
    scope: str = Field(default="", max_length=2000)
    requirements: str = Field(default="", max_length=12000)
    prd_name: str = Field(default="", max_length=200)
    prd_content: str = Field(default="", max_length=65536)
    mode: Literal["openai", "baseline"] = "openai"
    allow_interactions: bool = False
    max_pages: int = Field(default=5, ge=1, le=12)
    max_flows: int = Field(default=6, ge=1, le=12)
    resource_policy: Literal["compatible", "same_origin"] = "compatible"
    navigation_origins: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_navigation_origins(self):
        from .safety import origin
        if self.prd_content:
            if not self.prd_name.lower().endswith((".md", ".markdown")):
                raise ValueError("PRD must be a Markdown (.md or .markdown) document")
            if len(self.prd_content.encode("utf-8")) > 65536 or "\x00" in self.prd_content:
                raise ValueError("PRD must be UTF-8 text, at most 64 KiB, without NUL bytes")
            if not self.prd_content.strip():
                raise ValueError("PRD is empty")
        if self.prd_name and not self.prd_content:
            raise ValueError("PRD content is required when a filename is supplied")
        self.prd_name = self.prd_name.replace("\\", "/").rsplit("/", 1)[-1]
        self.navigation_origins = list(dict.fromkeys(origin(value) for value in self.navigation_origins))
        return self


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

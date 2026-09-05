from typing import Any, TypedDict


class V2PipelineState(TypedDict, total=False):
    run_id: str
    thread_id: str
    request: dict[str, Any]
    pipeline_status: str
    current_stage: str
    started_at: str
    deadline_at: str
    recon_output: list[dict[str, Any]]
    previous_suite: dict[str, Any] | None
    ui_changes: list[dict[str, Any]]
    requirements_output: dict[str, Any] | None
    planner_output: dict[str, Any] | None
    plan_evaluation: dict[str, Any] | None
    generator_output: dict[str, Any] | None
    generation_evaluation: dict[str, Any] | None
    validation_results: list[dict[str, Any]]
    execution_results: list[dict[str, Any]]
    healer_actions: list[dict[str, Any]]
    final_evaluation: dict[str, Any] | None
    evolution_output: dict[str, Any] | None
    report_output: dict[str, Any] | None
    planning_attempts: int
    generation_attempts: int
    final_replan_attempts: int
    logical_llm_calls: int
    token_usage: dict[str, Any]
    events: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    degraded_components: list[str]
    exhausted_limits: list[str]
    cancellation_requested: bool
    cleanup_completed: bool
    fatal_error: bool
    quarantined_flow_ids: list[str]
    schema_version: int


def initial_state(run_id, request):
    return V2PipelineState(run_id=run_id, thread_id=run_id, request=request,
        pipeline_status="queued", current_stage="queued", recon_output=[], previous_suite=None,
        ui_changes=[], requirements_output=None, planner_output=None, plan_evaluation=None,
        generator_output=None, generation_evaluation=None, validation_results=[], execution_results=[],
        healer_actions=[], final_evaluation=None, evolution_output=None, report_output=None,
        planning_attempts=0, generation_attempts=0, final_replan_attempts=0,
        logical_llm_calls=0, token_usage={}, events=[], errors=[], degraded_components=[],
        exhausted_limits=[], cancellation_requested=False, cleanup_completed=False, fatal_error=False,
        quarantined_flow_ids=[], schema_version=2)

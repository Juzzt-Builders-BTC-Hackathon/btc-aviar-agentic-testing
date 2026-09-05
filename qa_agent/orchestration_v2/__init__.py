"""LangGraph-based Qpilot V2 orchestration."""
async def run_pipeline_v2(store, run_id, resume=False):
    # Keep adapter imports independent of the package import order.
    from .runner import run_pipeline_v2 as run
    return await run(store, run_id, resume=resume)

__all__ = ["run_pipeline_v2"]

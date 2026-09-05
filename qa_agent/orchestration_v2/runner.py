import asyncio
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from ..adapters_v2 import V2Runtime
from .checkpoints import checkpoint_path, graph_config
from .graph import build_graph
from .state import initial_state


async def run_pipeline_v2(store, run_id):
    record = store.get(run_id)
    if not record:
        return
    runtime = V2Runtime(store, run_id)
    try:
        async with asyncio.timeout(600):
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path())) as checkpointer:
                graph = build_graph(runtime, checkpointer)
                await graph.ainvoke(initial_state(run_id, record["request"]), graph_config(run_id))
    except asyncio.CancelledError:
        store.update(run_id, status="cancelled", stage="cancelled", summary={"pipeline_version": "v2"})
        store.event(run_id, "cancelled", "Qpilot V2 run cancelled.")
        raise
    except Exception as exc:
        state = initial_state(run_id, record["request"])
        state["errors"] = [{"stage": "runner", "type": type(exc).__name__, "message": str(exc)}]
        await runtime.fail(state)

import asyncio
import time
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from ..adapters_v2 import V2Runtime
from ..safety import redact
from .checkpoints import checkpoint_path, graph_config
from .graph import build_graph
from .state import initial_state

SAFE_NODES = {'prd_analyst','plan_evaluator','generator','generation_evaluator','final_evaluator','evolution','reporter'}


def resume_guard(record, snapshot, marker):
    if record['status'] not in {'interrupted','cancelled','failed'}:
        return False,'Only an interrupted or failed run can resume'
    if not snapshot or snapshot.values.get('schema_version') != 2 or not snapshot.next:
        return False,'No compatible pending checkpoint; start a new run'
    if float(snapshot.values.get('deadline_at',0)) <= time.time():
        return False,'Original run deadline expired; start a new run'
    if marker.get('phase') == 'started' and marker.get('browser'):
        return False,'A browser action may have occurred; start a new run with known preconditions'
    if not set(snapshot.next).issubset(SAFE_NODES):
        return False,'Next checkpoint is a browser boundary; start a new run'
    return True,'Resume from saved non-browser stage; original call budget and deadline apply'


async def resume_status(store, run_id):
    record = store.get(run_id)
    if not record or record['status'] not in {'interrupted','cancelled','failed'}:
        return {'allowed':False,'reason':'No interrupted run'}
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path())) as saver:
        graph = build_graph(V2Runtime(store,run_id),saver)
        snapshot = await graph.aget_state(graph_config(run_id))
        allowed,reason = resume_guard(record,snapshot,store.read(run_id,'active_stage.json',{}))
        return {'allowed':allowed,'reason':reason}


async def run_pipeline_v2(store, run_id, resume=False):
    record = store.get(run_id)
    if not record: return
    runtime = V2Runtime(store,run_id)
    try:
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path())) as checkpointer:
            graph = build_graph(runtime,checkpointer)
            state = initial_state(run_id,record['request'])
            timeout = 600
            if resume:
                snapshot = await graph.aget_state(graph_config(run_id))
                # The API marks this job queued only after checking eligibility.
                prior = {**record,'status':'interrupted'} if record['status'] == 'queued' else record
                allowed,reason = resume_guard(prior,snapshot,store.read(run_id,'active_stage.json',{}))
                if not allowed: raise ValueError(reason)
                state = snapshot.values
                runtime.last_state = dict(state)
                runtime.llm.restore_usage(store.read(run_id,'llm_usage.json',state.get('token_usage',{})))
                timeout = max(.01,float(state['deadline_at'])-time.time())
                store.event(run_id,'resume',reason)
            async with asyncio.timeout(timeout):
                result = await graph.ainvoke(None if resume else state,graph_config(run_id))
                if result.get('pipeline_status') == 'failed' and store.get(run_id)['status'] != 'failed':
                    await runtime.fail(result)
    except asyncio.CancelledError:
        store.update(run_id,status='cancelled',summary={'pipeline_version':'v2','usage':runtime.llm.usage()})
        store.event(run_id,'cancelled','Cancelled; partial evidence saved. Resume requires a safe checkpoint.')
        raise
    except Exception as exc:
        state = runtime.last_state or initial_state(run_id,record['request'])
        state['errors'] = list(state.get('errors',[]))+[{'stage':store.get(run_id)['stage'],
            'type':type(exc).__name__,'message':'Run exceeded its original 10-minute deadline' if isinstance(exc,TimeoutError)
                    else redact(str(exc))[:1500]}]
        await runtime.fail(state)

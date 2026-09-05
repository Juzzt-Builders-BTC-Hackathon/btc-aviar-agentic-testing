import asyncio
import time
import runpy
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from qa_agent.models import RunRequest
from qa_agent.store import Store
from qa_agent.llm import LLM
from qa_agent.orchestration_v2 import runner
from qa_agent.orchestration_v2.graph import build_graph
from qa_agent.orchestration_v2.state import initial_state
from qa_agent.orchestration_v2.checkpoints import graph_config


def test_real_checkpoint_resume_does_not_repeat_executor_and_restores_budget(tmp_path,monkeypatch):
    FakeRuntime=runpy.run_path('tests/test_v2_graph.py')['FakeRuntime']
    path=tmp_path/'graph.sqlite3';monkeypatch.setenv('QA_V2_CHECKPOINT_DB',str(path))
    store=Store(tmp_path/'runs');rid=store.create(RunRequest(url='https://example.com',mode='baseline').model_dump())
    resumed=[]
    class ResumedRuntime(FakeRuntime):
        def __init__(self,store,rid):
            super().__init__();self.llm=LLM(max_calls=8);self.last_state={};resumed.append(self)
        async def report(self,state):
            store.update(rid,status='completed',stage='done')
            return await super().report(state)
    monkeypatch.setattr(runner,'V2Runtime',ResumedRuntime)
    async def exercise():
        entered=asyncio.Event()
        class PausedRuntime(FakeRuntime):
            async def report(self,state):
                entered.set();await asyncio.Event().wait()
        original=PausedRuntime()
        async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
            graph=build_graph(original,saver)
            state=initial_state(rid,store.get(rid)['request']);state['deadline_at']=str(time.time()+600)
            task=asyncio.create_task(graph.ainvoke(state,graph_config(rid)))
            await entered.wait();task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        store.update(rid,status='interrupted')
        store.artifact(rid,'active_stage.json',{'phase':'started','browser':False,'method':'report'})
        store.artifact(rid,'llm_usage.json',{'calls':4,'input_tokens':12,'output_tokens':5})
        assert (await runner.resume_status(store,rid))['allowed']
        await runner.run_pipeline_v2(store,rid,resume=True)
        assert original.visited.count('executor')==1
    asyncio.run(exercise())
    assert store.get(rid)['status']=='completed'
    assert resumed[-1].visited==['reporter']
    assert resumed[-1].llm.calls==4 and resumed[-1].llm.input_tokens==12

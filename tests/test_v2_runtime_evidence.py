import asyncio
from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from qa_agent.adapters_v2 import runtime_adapter as adapter
from qa_agent.models import Flow,Plan,Step,RunRequest
from qa_agent.v2_models import GeneratedSuite,success
from qa_agent.store import Store
from qa_agent.orchestration_v2.state import initial_state


class PlaywrightContext:
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass


def setup_runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(adapter,'async_playwright',PlaywrightContext)
    monkeypatch.setattr(adapter,'launch_browser',AsyncMock(return_value=SimpleNamespace(close=AsyncMock())))
    monkeypatch.setattr(adapter,'auth_state',AsyncMock(return_value=None))
    request = RunRequest(url='https://example.com',mode='baseline')
    store=Store(tmp_path);rid=store.create(request.model_dump())
    runtime=adapter.V2Runtime(store,rid);state=initial_state(rid,request.model_dump())
    flows=[Flow(id=f'f{i}',name=f'Flow {i}',risk='medium',category='smoke',oracle='observed',requirement_ids=[],steps=[
        Step(action='navigate',target=request.url,value='',intent='Open'),Step(action='assert_text',target='h1',value='Hello',intent='Check')]) for i in (1,2)]
    state['generator_output']=success(GeneratedSuite(plan=Plan(summary='',flows=flows,gaps=[]),generated_flow_ids=['f1','f2']))
    state['validation_results']=[{'flow_id':f.id,'status':'passed','attempt':'validation'} for f in flows]
    return runtime,state


def test_cancel_preserves_completed_flow(tmp_path,monkeypatch):
    runtime,state=setup_runtime(tmp_path,monkeypatch)
    async def execute(browser,request,flow,*args):
        if flow.id=='f2': raise asyncio.CancelledError()
        return {'flow_id':flow.id,'status':'passed','steps':[],'attempt':'run','duration_ms':1}
    monkeypatch.setattr(adapter,'execute_flow',execute)
    with pytest.raises(asyncio.CancelledError): asyncio.run(runtime.execute(state))
    assert runtime.store.read(runtime.run_id,'run_results.json')[0]['flow_id']=='f1'


def test_quarantined_flow_never_reaches_browser_executor(tmp_path,monkeypatch):
    runtime,state=setup_runtime(tmp_path,monkeypatch)
    state['quarantined_flow_ids']=['f1','f2']
    execute=AsyncMock();monkeypatch.setattr(adapter,'execute_flow',execute)
    output=asyncio.run(runtime.execute(state))
    assert not execute.called
    assert all(r['status']=='generation_failed' for r in output['execution_results'])


def test_begin_publishes_stage_before_work(tmp_path,monkeypatch):
    runtime,state=setup_runtime(tmp_path,monkeypatch)
    runtime.begin(state,'execute')
    assert runtime.store.get(runtime.run_id)['stage']=='executor'
    assert runtime.store.read(runtime.run_id,'active_stage.json')['phase']=='started'


def test_verified_fingerprints_are_saved(tmp_path,monkeypatch):
    runtime,state=setup_runtime(tmp_path,monkeypatch)
    flow=GeneratedSuite.model_validate(state['generator_output']['data']).plan.flows[0]
    fingerprint={'selector':'h1','tag':'h1','text':'Hello'}
    runtime.persist_fingerprints(runtime.request(state),flow,{'status':'passed','steps':[{'index':1,'fingerprint':fingerprint}]})
    assert runtime.store.fingerprint(adapter.fingerprint_key(runtime.request(state).url,flow,1))==fingerprint

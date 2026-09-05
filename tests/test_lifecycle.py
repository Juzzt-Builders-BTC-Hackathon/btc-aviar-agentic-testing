import asyncio
import shutil
import pytest
from qa_agent import config, pipeline
from qa_agent.models import RunRequest
from qa_agent.store import Store
from qa_agent.llm import LLM


def test_cancellation_retains_terminal_state(tmp_path,monkeypatch):
    class PausedBrowser:
        async def __aenter__(self):
            await asyncio.Event().wait()
        async def __aexit__(self,*args): pass
    monkeypatch.setattr(pipeline,'async_playwright',PausedBrowser)
    store=Store(tmp_path)
    rid=store.create(RunRequest(url=config.DEMO_ORIGIN+'/demo/',mode='baseline').model_dump())
    async def exercise():
        task=asyncio.create_task(pipeline.run_pipeline(store,rid))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(exercise())
    assert store.get(rid)['status']=='cancelled'
    assert store.events(rid)[-1]['stage']=='cancelled'


def test_call_budget_prevents_unbounded_spend():
    llm=LLM();llm.calls=5
    with pytest.raises(ValueError,match='budget exhausted'):
        asyncio.run(llm.ask(None,'',{}))


def test_stopped_database_backup_restores_artifacts(tmp_path):
    source=tmp_path/'source';store=Store(source)
    rid=store.create({'url':'test'})
    store.artifact(rid,'evidence.json',{'observed':True})
    store.update(rid,status='completed',summary={'passed':1})
    shutil.copytree(source,tmp_path/'restore')
    restored=Store(tmp_path/'restore')
    assert restored.get(rid)['summary']['passed']==1
    assert restored.read(rid,'evidence.json')=={'observed':True}

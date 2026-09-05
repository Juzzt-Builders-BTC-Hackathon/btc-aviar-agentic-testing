import asyncio
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from qa_agent import config, runtime, server
from qa_agent.safety import request_block_reason, target_url, PolicyError
from qa_agent.store import Store
import pytest


def test_compatible_assets_and_explicit_navigation(monkeypatch):
    monkeypatch.setattr(config,'ALLOWED',{'*'})
    base='https://example.com/'
    assert request_block_reason(base,'https://cdn.example.net/app.js','GET',False,False) is None
    assert request_block_reason(base,'https://api.example.net/query','POST',False,False)
    assert request_block_reason(base,'https://api.example.net/query','POST',False,True) is None
    assert request_block_reason(base,'https://cdn.example.net/app.js','GET',False,False,'same_origin')
    assert request_block_reason(base,'https://elsewhere.net/','GET',True,False)
    assert request_block_reason(base,'https://elsewhere.net/','GET',True,False,extra=['https://elsewhere.net']) is None
    assert request_block_reason(base,config.DEMO_ORIGIN+'/api/config','GET',False,False)


def test_canonical_redirects_are_bounded(monkeypatch):
    monkeypatch.setattr(config,'ALLOWED',{'*'})
    assert target_url('http://example.com/','https://www.example.com/home')
    with pytest.raises(PolicyError):target_url('https://example.com/','http://example.com/')
    with pytest.raises(PolicyError):target_url('https://example.com/','https://example.com.evil.test/')
    with pytest.raises(PolicyError):target_url('http://localhost:3000/','http://localhost:4000/')


def test_permission_failure_is_actionable_and_does_not_claim_ready(tmp_path,monkeypatch):
    class Denied:
        async def __aenter__(self):raise PermissionError(13,'Access is denied')
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(runtime,'async_playwright',Denied)
    result=asyncio.run(runtime.preflight())
    assert result['ready'] is False
    assert result['errors'][0]['code']=='ACCESS_DENIED'
    assert result['errors'][0]['stage']=='playwright_driver'
    assert 'start.ps1' in result['errors'][0]['remedy']


def test_readiness_blocks_admission_before_a_failed_job_is_created(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'store',Store(tmp_path))
    monkeypatch.setattr(server,'preflight',AsyncMock(return_value={'ready':False,'checks':[], 'errors':[{'code':'ACCESS_DENIED','stage':'browser_launch','message':'Denied','remedy':'Use a normal terminal'}]}))
    with TestClient(server.app) as client:
        client.get('/')
        assert client.get('/api/readiness').status_code==503
        response=client.post('/api/runs',json={'url':config.DEMO_ORIGIN+'/demo/','mode':'baseline'})
        assert response.status_code==503
        assert 'ACCESS_DENIED' in response.json()['detail']
        assert client.get('/api/runs').json()==[]


def test_failed_error_artifact_still_records_failure_in_database(tmp_path,monkeypatch):
    from qa_agent import pipeline
    from qa_agent.models import RunRequest
    class Denied:
        async def __aenter__(self):raise PermissionError(13,'Access is denied')
        async def __aexit__(self,*args):pass
    store=Store(tmp_path)
    rid=store.create(RunRequest(url=config.DEMO_ORIGIN+'/demo/',mode='baseline').model_dump())
    def fail_artifact(*args):raise PermissionError('Artifact directory denied')
    monkeypatch.setattr(store,'artifact',fail_artifact)
    monkeypatch.setattr(pipeline,'async_playwright',Denied)
    asyncio.run(pipeline.run_pipeline(store,rid))
    run=store.get(rid)
    assert run['status']=='failed'
    assert run['summary']['diagnostic']['code']=='ACCESS_DENIED'
    assert 'artifact_write_error' in run['summary']['diagnostic']

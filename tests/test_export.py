import io
import zipfile
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from qa_agent.store import Store


def test_partial_export_explains_status_and_preserves_evidence(tmp_path,monkeypatch):
    from qa_agent import server
    store=Store(tmp_path)
    monkeypatch.setattr(server,'store',store)
    monkeypatch.setattr(server,'preflight',AsyncMock(return_value={'ready':True,'checks':[],'errors':[]}))
    with TestClient(server.app) as client:
        rid=store.create({'url':'https://example.com/'})
        store.update(rid,status='cancelled')
        store.artifact(rid,'recon.json',{'observation':'retained'})
        store.event(rid,'cancelled','Cancelled with partial evidence')
        client.get('/')
        response=client.get(f'/api/runs/{rid}/export')
        assert response.status_code==200
        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            guide=bundle.read('START_HERE.md').decode()
            assert rid in guide and 'Status at export: cancelled' in guide
            assert 'Partial exports' in guide and 'not a standalone installer' in guide
            assert 'recon.json' in bundle.namelist() and 'decision_log.json' in bundle.namelist()

"""Replay a QA request through V2 into a separate verification store (at most 8 LLM calls)."""
import asyncio
import json
import os
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_agent import config
from qa_agent.models import RunRequest
from qa_agent.store import Store
from qa_agent.orchestration_v2.runner import run_pipeline_v2


async def main():
    if len(sys.argv)!=2: raise SystemExit('Usage: python scripts/verify_v2_run.py path/to/qa-run.zip')
    with zipfile.ZipFile(sys.argv[1]) as archive:
        request=RunRequest.model_validate(json.loads(archive.read('suite.json'))['request'])
    root=ROOT/'data'/'repair-verification'
    os.environ['QA_V2_CHECKPOINT_DB']=str(root/'graph.sqlite3')
    store=Store(root/'runs');rid=store.create(request.model_dump())
    print('Verification run:',rid,flush=True)
    print('Evidence:',store.root/rid,flush=True)
    task=asyncio.create_task(run_pipeline_v2(store,rid))
    last=None
    while not task.done():
        current=store.get(rid)
        if current['stage']!=last:
            print('Stage:',current['stage'],flush=True);last=current['stage']
        await asyncio.wait({task},timeout=2)
    await task
    record=store.get(rid)
    print('Status:',record['status'],flush=True)
    print('Summary:',json.dumps(record['summary']),flush=True)
    for result in store.read(rid,'run_results.json',[]):
        print(result['flow_id'],result['status'],result.get('classification',{}).get('label'),flush=True)
    health=store.read(rid,'agent_health.json',{})
    for role,data in health.items():
        print('Agent:',role,'fallback='+str(data['degraded_mode']),data['errors'],flush=True)
    return 0 if record['status']=='completed' else 1


if __name__=='__main__': raise SystemExit(asyncio.run(main()))

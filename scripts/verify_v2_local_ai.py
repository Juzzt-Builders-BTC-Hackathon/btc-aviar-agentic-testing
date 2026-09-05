"""Known local fixture + real LLM agents; at most eight logical calls, no external target."""
import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_agent import config
from qa_agent.models import RunRequest
from qa_agent.store import Store
from qa_agent.orchestration_v2.runner import run_pipeline_v2

HTML='''<!doctype html><h1>Local prediction test</h1><input id="rank" type="number" min="1" required>
<select id="category" required><option value="">Choose</option><option value="BCB">BC-B</option></select>
<button id="predict" onclick="document.getElementById('result').textContent='Selected '+document.getElementById('category').value">Predict</button>
<p id="result">Waiting</p>'''
PRD='''# Local fixture requirements
## Valid category selection
Enter rank 15000 in #rank, select category BC-B (option value BCB) in #category,
and click #predict. The #result paragraph must then contain "Selected BCB".
## Invalid rank
Enter -500 in the rank input. The input must have native HTML validity false because min=1.
Use the native validity assertion; no inline custom error message is required.
'''


async def main():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            data=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        url=f'http://127.0.0.1:{server.server_port}/'
        config.ALLOWED.add(url.rstrip('/'))
        root=ROOT/'data'/'repair-local-ai';os.environ['QA_V2_CHECKPOINT_DB']=str(root/'graph.sqlite3')
        store=Store(root/'runs');request=RunRequest(url=url,mode='openai',prd_name='local-fixture.md',prd_content=PRD,
            allow_interactions=True,max_pages=1,max_flows=2)
        rid=store.create(request.model_dump());print('Run:',rid,flush=True)
        task=asyncio.create_task(run_pipeline_v2(store,rid));last=None
        while not task.done():
            stage=store.get(rid)['stage']
            if stage!=last: print('Stage:',stage,flush=True);last=stage
            await asyncio.wait({task},timeout=2)
        await task
        record=store.get(rid);print('Status:',record['status'],flush=True);print('Summary:',json.dumps(record['summary']),flush=True)
        for role,health in store.read(rid,'agent_health.json',{}).items():
            print(role,'fallback='+str(health['degraded_mode']),health['errors'],flush=True)
        print('Evidence:',store.root/rid,flush=True)
        return 0 if record['status']=='completed' else 1
    finally: server.shutdown();server.server_close();worker.join(timeout=5)


if __name__=='__main__': raise SystemExit(asyncio.run(main()))

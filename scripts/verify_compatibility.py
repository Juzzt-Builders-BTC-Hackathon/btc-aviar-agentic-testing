"""Real-browser compatibility fixtures and optional live public-site run."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.async_api import async_playwright
import httpx
from qa_agent import config
from qa_agent.browser import execute_flow
from qa_agent.models import RunRequest, Flow, Step
from qa_agent.runtime import preflight
import sys


class AssetHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/app.js':
            content=b'document.querySelector("#loaded").textContent="External script loaded";'
            mime='application/javascript'
        else:
            content=b'<h1>Asset host</h1>';mime='text/html'
        self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(content)
    def log_message(self,*args):pass


async def main():
    asset=ThreadingHTTPServer(('127.0.0.1',0),AssetHandler)
    asset_origin=f'http://127.0.0.1:{asset.server_port}'
    class PageHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(f'<h1>Compatibility fixture</h1><p id="loaded">Waiting</p><script src="{asset_origin}/app.js"></script>'.encode())
        def log_message(self,*args):pass
    site=ThreadingHTTPServer(('127.0.0.1',0),PageHandler)
    for server in (asset,site):threading.Thread(target=server.serve_forever,daemon=True).start()
    records=[]
    try:
        ready=await preflight();assert ready['ready'],ready
        records.append({'check':'real runtime preflight','result':ready})
        url=f'http://127.0.0.1:{site.server_port}/'
        req=RunRequest(url=url,mode='baseline')
        flow=Flow(id='cdn',name='External script loads',risk='high',category='smoke',oracle='observed',requirement_ids=[],steps=[
            Step(action='navigate',target=url,value='',intent='Open fixture'),
            Step(action='assert_text',target='#loaded',value='External script loaded',intent='Verify actual script execution')])
        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            try:
                passed=await execute_flow(browser,req,flow,None)
                assert passed['status']=='passed',passed
                strict=req.model_copy(update={'resource_policy':'same_origin'})
                blocked=await execute_flow(browser,strict,flow,None)
                assert blocked['status']=='failed'
                assert any(d['type']=='blocked_request' for d in blocked['diagnostics'])
                records.append({'check':'external JavaScript executes in compatible mode and is diagnosed in strict mode','passed':True})
                navigation=req.model_copy(update={'navigation_origins':[asset_origin]})
                across=flow.model_copy(deep=True)
                across.steps[0].target=asset_origin
                across.steps[1].target='h1';across.steps[1].value='Asset host'
                assert (await execute_flow(browser,navigation,across,None))['status']=='passed'
                assert (await execute_flow(browser,req,across,None))['status']=='blocked'
                records.append({'check':'explicit additional navigation origin is enforced','passed':True})
            finally:await browser.close()
    finally:
        for server in (site,asset):server.shutdown();server.server_close()
    async with httpx.AsyncClient(base_url=config.DEMO_ORIGIN,timeout=30) as client:
        await client.get('/')
        readiness=await client.get('/api/readiness');assert readiness.status_code==200,readiness.text
        if '--public' in sys.argv:
            created=await client.post('/api/runs',json={'url':'https://eduvale.in','mode':'openai','max_pages':3,'max_flows':4,'scope':'Read-only analysis of the public website: navigation and visible page content. State any blocked or unavailable content.'})
            created.raise_for_status();rid=created.json()['id'];print('Public-site AI run:',rid,flush=True)
            last=''
            for _ in range(620):
                run=(await client.get(f'/api/runs/{rid}')).json()
                if run['stage']!=last: print('Stage:',run['stage'],flush=True);last=run['stage']
                if run['status'] not in {'queued','running'}:break
                await asyncio.sleep(1)
            assert run['status']=='completed',run['summary']
            records.append({'check':'live public website AI analysis','run_id':rid,'target':run['request']['url'],'summary':run['summary']})
    folder=config.DATA/'verification';folder.mkdir(exist_ok=True)
    (folder/'compatibility.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps(records,indent=2))


if __name__=='__main__':asyncio.run(main())

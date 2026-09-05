import asyncio
import json
import threading
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import pytest
from playwright.async_api import async_playwright
from qa_agent import config
from qa_agent.browser import execute_flow,crawl
from qa_agent.models import Step,Flow,RunRequest
from qa_agent.store import Store
from qa_agent.orchestration_v2.runner import run_pipeline_v2
from qa_agent.evolution import previous_suite

HTML = '''<!doctype html><h1 id="title">Hello</h1>
<input id="rank" type="number" min="1" required>
<select id="category" required><option value="">Choose</option><option value="BCB">BC-B</option></select>
<button id="predict" onclick="document.getElementById('result').textContent='Selected '+document.getElementById('category').value">Predict</button>
<p id="result">Waiting</p><a href="/">Home</a><a href="/redirect">Alias</a><a href="/form">Form</a>'''


@pytest.fixture
def local_site(monkeypatch):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(config.ROOT),**kwargs)
        def log_message(self,*args): pass
        def do_GET(self):
            if self.path == '/redirect':
                self.send_response(302);self.send_header('Location','/');self.end_headers();return
            if self.path in {'/','/form'}:
                data=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html')
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            if self.path.startswith('/assets/'): self.path='/ui/'+self.path[len('/assets/'):]
            return super().do_GET()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(config,'ALLOWED',{'*'})
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown();server.server_close();thread.join(timeout=5)


def test_real_dropdown_and_negative_validation(local_site,tmp_path):
    async def exercise():
        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            try:
                request=RunRequest(url=local_site,mode='baseline',allow_interactions=True)
                flow=Flow(id='dropdown',name='Dropdown',category='happy_path',risk='medium',oracle='observed',requirement_ids=[],steps=[
                    Step(action='navigate',target=local_site,value='',intent='Open'),
                    Step(action='select_option',target='#category',value='BC-B',intent='Choose category by label'),
                    Step(action='click',target='#predict',value='',intent='Predict'),
                    Step(action='assert_text',target='#result',value='Selected BCB',intent='Check selection')])
                result=await execute_flow(browser,request,flow,None,tmp_path,'test')
                assert result['status']=='passed',result.get('error')
                flow.steps[1].value='BCB'
                assert (await execute_flow(browser,request,flow,None))['status']=='passed'
                flow.steps=[flow.steps[0],Step(action='fill',target='#rank',value='-500',intent='Invalid rank'),
                    Step(action='assert_invalid',target='#rank',value='',intent='Check native invalidity')]
                assert (await execute_flow(browser,request,flow,None))['status']=='passed'
            finally: await browser.close()
    asyncio.run(exercise())


def test_crawl_deduplicates_redirect_destinations(local_site):
    async def exercise():
        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            try:
                pages=await crawl(browser,RunRequest(url=local_site,mode='baseline',max_pages=3),None,lambda message:None)
                assert len(pages)==2
                assert len({p['url'] for p in pages})==2
                category=next(e for e in pages[0]['elements'] if e['selector']=='#category')
                assert {'label':'BC-B','value':'BCB'} in category['options']
            finally: await browser.close()
    asyncio.run(exercise())


def test_real_v2_run_reports_and_reuses_suite(local_site,tmp_path,monkeypatch):
    monkeypatch.setenv('QA_V2_CHECKPOINT_DB',str(tmp_path/'graph.sqlite3'))
    store=Store(tmp_path/'runs');request=RunRequest(url=local_site,mode='baseline',max_pages=1,max_flows=1)
    rid=store.create(request.model_dump())
    asyncio.run(run_pipeline_v2(store,rid))
    record=store.get(rid)
    assert record['status']=='completed',record
    assert record['summary']['passed']==1 and record['summary']['usage']['calls']==0
    assert store.read(rid,'plan.json') and store.read(rid,'agent_health.json')
    assert previous_suite(store,request)['id']==rid
    second=store.create(request.model_dump());asyncio.run(run_pipeline_v2(store,second))
    assert store.get(second)['status']=='completed'
    assert store.read(second,'suite_evolution.json')['previous_run']==rid
    assert store.read(second,'suite_evolution.json')['reused']


def test_real_v2_healer_preserves_expected_outcome(local_site,tmp_path):
    from qa_agent.adapters_v2.runtime_adapter import V2Runtime
    from qa_agent.orchestration_v2.state import initial_state
    from qa_agent.v2_models import GeneratedSuite,success
    from qa_agent.models import Plan
    from qa_agent.pipeline import fingerprint_key
    request=RunRequest(url=local_site,mode='baseline')
    store=Store(tmp_path/'runs');rid=store.create(request.model_dump());runtime=V2Runtime(store,rid)
    flow=Flow(id='drift',name='Locator drift',risk='medium',category='smoke',oracle='observed',requirement_ids=[],steps=[
        Step(action='navigate',target=local_site,value='',intent='Open'),
        Step(action='assert_visible',target='#old-predict',value='',intent='Prediction control visible'),
        Step(action='assert_text',target='#title',value='Hello',intent='Title unchanged')])
    store.fingerprint(fingerprint_key(local_site,flow,1),{'selector':'#old-predict','tag':'button','type':'','text':'Predict'})
    state=initial_state(rid,request.model_dump());state['generator_output']=success(GeneratedSuite(
        plan=Plan(summary='',flows=[flow],gaps=[]),generated_flow_ids=['drift']))
    state['validation_results']=[{'flow_id':'drift','status':'passed','attempt':'validation'}]
    async def exercise():
        state.update(await runtime.execute(state))
        assert state['execution_results'][0]['status']=='failed'
        state.update(await runtime.heal(state))
    asyncio.run(exercise())
    result=state['execution_results'][0]
    assert result['status']=='passed' and result['classification']['label']=='healed_ok'
    assert len(result['attempts'])==4 and result['original_failure']['status']=='failed'
    assert state['healer_actions'][0]['new_selector']=='#predict'
    assert store.read(rid,'plan.json')['flows'][0]['steps'][2]['value']=='Hello'


def test_real_ui_v2_stage_plan_fallback_and_config(local_site):
    async def exercise():
        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            try:
                page=await browser.new_page();errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
                run={'id':'test','created':'2026-09-05T10:00:00Z','updated':'2026-09-05T10:00:01Z',
                     'status':'running','stage':'executor','summary':{'pipeline_version':'v2'},
                     'request':{'url':local_site,'mode':'baseline'},'events':[{'stage':'executor','message':'Starting executor','at':'2026-09-05T10:00:01Z'}],
                     'results':[],'plan':{'summary':'Saved V2 plan','flows':[]},'gaps':[],
                     'heals':[{'flow_id':'test','verified':True,'old_selector':'#old','candidate_selector':'#new','rationale':'Verified'}],'traceability':[],
                     'defects':[],'evolution':{},'artifacts':['plan.json','pipeline_metadata.json'],
                     'agent_health':{'plan_evaluation':{'degraded_mode':True,'errors':['Diagnostic retained']}},'resume':{'allowed':False}}
                async def route(request):
                    path=request.request.url.split('/api',1)[1]
                    if path=='/config': data={'openai_configured':False,'model':'test','pipeline_version':'v2','max_llm_calls':8,
                        'runtime':{'ready':True,'checks':[],'errors':[]},'allowed_origins':['*'],'allow_all_origins':True,'demo_url':local_site}
                    elif path=='/runs': data=[run]
                    else: data=run
                    await request.fulfill(content_type='application/json',body=json.dumps(data))
                await page.route('**/api/**',route)
                await page.goto(local_site+'/ui/index.html')
                await page.locator('.pipeline-step.current').wait_for()
                assert 'Executor' in await page.locator('.pipeline-step.current').inner_text()
                assert 'Diagnostic retained' in await page.locator('#detail-content').inner_text()
                await page.locator('[data-tab="plan"]').click()
                assert 'Saved V2 plan' in await page.locator('#detail-content').inner_text()
                await page.locator('[data-tab="coverage"]').click()
                assert '#new' in await page.locator('#detail-content').inner_text()
                await page.locator('[data-nav="settings"]').click()
                assert '8 OpenAI calls maximum' in await page.locator('#settings-content').inner_text()
                assert not errors,errors
            finally: await browser.close()
    asyncio.run(exercise())

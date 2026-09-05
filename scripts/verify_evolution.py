"""Real-browser suite lifecycle check on a controlled local fixture; no AI calls."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
import httpx
from playwright.async_api import async_playwright, expect
from qa_agent import config
from qa_agent.models import RunRequest
from qa_agent.pipeline import run_pipeline
from qa_agent.store import Store


class Fixture(BaseHTTPRequestHandler):
    locator = 'heading-original'
    text = 'Catalog'
    extra = False
    def log_message(self, *args): pass
    def do_GET(self):
        extra = '<a href="/new">New page</a>' if self.extra and self.path != '/new' else ''
        body = f'<!doctype html><title>Catalog</title><h1 id="{self.locator}">{self.text if self.path != "/new" else "New page"}</h1>{extra}'.encode()
        self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body)


async def main():
    root = config.DATA / 'verification' / ('evolution-' + uuid4().hex[:8])
    store = Store(root)
    server = ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    worker = threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    config.ALLOWED.add(base)
    request = RunRequest(url=base+'/',mode='baseline',max_pages=2,max_flows=3,
                         prd_name='catalog.md',prd_content='# Catalog\n\n- The page shows "Catalog".')
    async def run():
        rid = store.create(request.model_dump())
        await run_pipeline(store,rid)
        assert store.get(rid)['status']=='completed',store.get(rid)['summary']
        return rid,store.read(rid,'plan.json'),store.read(rid,'run_results.json'),store.read(rid,'suite_evolution.json')
    try:
        first,original,_,_=await run()
        Fixture.locator='heading-new'
        second,repaired,results,evolution=await run()
        assert results[0]['classification']['label']=='healed_ok',results[0]['classification']
        assert original['flows'][0]['id']==repaired['flows'][0]['id']
        assert original['flows'][0]['steps'][-1]['value']==repaired['flows'][0]['steps'][-1]['value']
        assert repaired['flows'][0]['steps'][-1]['target']=='#heading-new'
        assert evolution['previous_run']==first and evolution['outcomes'][0]['change']=='repaired'
        third,stable,results,evolution=await run()
        assert stable['flows']==repaired['flows'] and results[0]['status']=='passed'
        assert store.get(third)['summary']['usage']['calls']==0
        Fixture.text='Unexpected replacement';Fixture.extra=True
        fourth,changed,results,evolution=await run()
        assert results[0]['status']=='failed' and evolution['outcomes'][0]['change']=='regression'
        assert changed['flows'][0]['steps'][-1]['value']=='Catalog'
        assert len(changed['flows'])==2 and evolution['added']
        assert any(c['kind']=='new_page' for c in evolution['ui_changes'])
        report=store.read(fourth,'defect_report.json')
        assert len(report[0]['attempts'])==3 and report[0]['classification']['label']=='needs_review'

        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            page=await browser.new_page(viewport={'width':1440,'height':1050})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto(config.DEMO_ORIGIN)
            await expect(page.locator('#connection-label')).to_have_text('Connected')
            await page.locator('#try-demo').click()
            assert await page.locator('#navigation-origins').count()==0
            await page.locator('#prd-file').set_input_files({'name':'catalog.md','mimeType':'text/markdown','buffer':b'# Demo\n\n- Show "Aviar Demo Store".'})
            await expect(page.locator('#prd-status')).to_contain_text('catalog.md')
            await page.screenshot(path=str(root/'prd-dialog.png'))
            async with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
                await page.locator('#launch-run').click()
            response=await created.value
            assert response.status==202,await response.text()
            rid=(await response.json())['id']
            async with httpx.AsyncClient(base_url=config.DEMO_ORIGIN) as client:
                await client.get('/')
                for _ in range(180):
                    live=(await client.get('/api/runs/'+rid)).json()
                    if live['status'] not in {'running','queued'}:break
                    await asyncio.sleep(.5)
                assert live['status']=='completed',live['summary']
                assert live['request']['prd_name']=='catalog.md' and live['defects']
                assert 'prd.md' in live['artifacts']
            await expect(page.locator('#detail-id')).to_contain_text('COMPLETED',timeout=10000)
            for tab in ('defects','evolution','coverage','plan','activity'):
                await page.locator(f'[data-tab={tab}]').click()
                assert await page.locator('#detail-content').inner_text()
            await page.locator('[data-tab=defects]').click()
            await page.locator('#detail-content details').first.locator('summary').click()
            await page.screenshot(path=str(root/'defect-classifier.png'),full_page=True)
            await page.set_viewport_size({'width':390,'height':844})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(root/'mobile.png'),full_page=True)
            assert not errors,errors
            await browser.close()
        checks={'fixture_runs':[first,second,third,fourth],'ui_run':rid,
                'checks':['locator drift repaired','original assertions preserved','verified repair reused','content regression retained',
                          'new page scenario appended','PRD upload and traceability','classifier and change tabs','mobile layout','no JS errors']}
        (root/'verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
        print(json.dumps({'status':'passed','evidence':str(root),**checks},indent=2))
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__': asyncio.run(main())

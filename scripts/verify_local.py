"""Integration check against a running local server; includes real Chromium execution.
Run from the project root: python -m scripts.verify_local [--sauce]
"""
import asyncio
import json
import sys
from pathlib import Path
import httpx
from playwright.async_api import async_playwright, expect
from qa_agent import config
from qa_agent.browser import execute_flow, snapshot, new_context
from qa_agent.healing import classify
from qa_agent.models import Flow, Step, RunRequest
from qa_agent.pipeline import repair, fingerprint_key
from qa_agent.llm import LLM
from qa_agent.store import Store


async def wait_run(client, rid):
    for _ in range(240):
        run=(await client.get(f"/api/runs/{rid}")).json()
        if run['status'] not in {'queued','running'}: return run
        await asyncio.sleep(.5)
    raise AssertionError('Run did not finish within 120 seconds')


async def main():
    root=config.DATA/'verification';root.mkdir(parents=True,exist_ok=True)
    checks=[]
    async with httpx.AsyncClient(base_url=config.DEMO_ORIGIN,timeout=20) as client:
        await client.get('/')
        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            try:
                page=await browser.new_page(viewport={'width':1512,'height':1100})
                errors=[]
                page.on('pageerror',lambda err:errors.append(str(err)))
                await page.goto(config.DEMO_ORIGIN)
                await page.get_by_role('button',name='Explore local demo').click()
                await expect(page.locator('#run-mode')).to_have_value('baseline')
                async with page.expect_response(lambda response: response.url.endswith('/api/runs') and response.request.method=='POST') as created:
                    await page.get_by_role('button',name='Start test run').click()
                created_response=await created.value
                assert created_response.status==202,await created_response.text()
                await expect(page.locator('#run-detail')).to_be_visible()
                run=await wait_run(client,(await created_response.json())['id'])
                assert run['status']=='completed',run['summary']
                assert run['summary']['passed']>=2,run['summary']
                assert all(r['screenshot'] for r in run['results'])
                assert 'junit.xml' in run['artifacts'] and 'generated_tests.py' in run['artifacts']
                checks.append({'check':'dashboard-created local baseline','run_id':run['id'],'summary':run['summary']})
                exported=config.DATA/run['id']/'generated_tests.py'
                replay_process=await asyncio.create_subprocess_exec(sys.executable,str(exported),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                output,error=await asyncio.wait_for(replay_process.communicate(),timeout=60)
                assert replay_process.returncode==0,error.decode(errors='replace')
                replay_results=json.loads(output)
                assert all(r['status']=='passed' for r in replay_results)
                checks.append({'check':'generated Python suite replay without OpenAI','passed':True})
                await page.reload();await page.wait_for_timeout(1000)
                await page.screenshot(path=str(root/'dashboard-desktop.png'),full_page=True)
                await page.get_by_role('tab',name='Coverage & risks').click()
                assert await page.get_by_text('Passing tests do not prove full coverage.',exact=False).count()==1
                await page.get_by_role('button',name='Configuration',exact=False).click()
                assert await page.get_by_text('OpenAI Responses API',exact=False).count()==1
                await page.get_by_role('button',name='Overview',exact=False).click()
                await page.set_viewport_size({'width':390,'height':844})
                await page.screenshot(path=str(root/'dashboard-mobile.png'),full_page=True)
                assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                assert not errors,errors
                checks.append({'check':'desktop/mobile dashboard, tabs, navigation, no JS errors','passed':True})

                req=RunRequest(url=config.DEMO_ORIGIN+'/demo/',mode='baseline',allow_interactions=True)
                f=Flow(id='cart',name='Demo cart arithmetic',risk='high',category='happy_path',oracle='requirement',requirement_ids=['REQ-1'],steps=[
                    Step(action='navigate',target=req.url,value='',intent='Open demo store'),
                    Step(action='click',target='[data-testid="add-notebook"]',value='',intent='Add a notebook'),
                    Step(action='assert_text',target='[data-testid="cart-count"]',value='1 items',intent='Cart count increases'),
                    Step(action='assert_text',target='[data-testid="cart-total"]',value='$18.00',intent='Verify exact item price')])
                result=await execute_flow(browser,req,f,None,root,'integration')
                assert result['status']=='passed',result
                checks.append({'check':'real cart click and total assertions','passed':True})
                negative=f.model_copy(deep=True);negative.id='negative';negative.steps=[negative.steps[0],
                    Step(action='fill',target='[data-testid="coupon"]',value='BAD-CODE',intent='Enter invalid coupon'),
                    Step(action='click',target='[data-testid="apply-coupon"]',value='',intent='Apply invalid coupon'),
                    Step(action='assert_text',target='[data-testid="coupon-message"]',value='Invalid discount code',intent='Verify rejection')]
                assert (await execute_flow(browser,req,negative,None,root,'integration'))['status']=='passed'
                checks.append({'check':'negative form scenario','passed':True})
                broken=f.model_copy(deep=True);broken.id='assertion_failure';broken.steps[-1].value='$999.00'
                first=await execute_flow(browser,req,broken,None,root,'first')
                second=await execute_flow(browser,req,broken,None,root,'retry')
                assert classify(first,second)['label']=='likely_defect'
                assert first['failure_kind']=='assertion'
                checks.append({'check':'seeded wrong requirement yields repeatable likely-defect signal','passed':True})

                healed=f.model_copy(deep=True);healed.id='locator_drift';healed.steps[1].target='#old-notebook-button'
                failed=await execute_flow(browser,req,healed,None,root,'before-repair')
                fingerprint=next(e for e in failed['failure_snapshot']['elements'] if e['selector']=='[data-testid="add-notebook"]')
                memory=Store(root/'repair-store')
                memory.fingerprint(fingerprint_key(req.url,healed,1),{**fingerprint,'selector':'#old-notebook-button'})
                fixed,audit=await repair(memory,req,healed,failed,[],LLM())
                assert fixed and audit['tier']=='deterministic'
                assert fixed.steps[-1]==healed.steps[-1]
                confirmed=await execute_flow(browser,req,fixed,None,root,'after-repair')
                assert confirmed['status']=='passed'
                checks.append({'check':'selector drift repair with unchanged assertions, real browser confirmation','passed':True})
                ambiguous=Flow(id='repeated_price',name='Price belongs to the named product',risk='high',category='happy_path',oracle='observed',requirement_ids=[],steps=[
                    Step(action='navigate',target=req.url,value='',intent='Open demo store'),
                    Step(action='assert_text',target='[data-testid="notebook-card"] h2',value='Everyday Notebook',intent='Identify the notebook card'),
                    Step(action='assert_text',target='.products strong',value='$18.00',intent='Verify that product price')])
                invalid=await execute_flow(browser,req,ambiguous,None,root,'validation')
                assert invalid['failure_kind']=='selector'
                scoped,audit=await repair(memory,req,ambiguous,invalid,[],LLM())
                assert scoped and audit['tier']=='scoped_regeneration'
                assert scoped.steps[-1].value=='$18.00'
                assert (await execute_flow(browser,req,scoped,None,root,'scoped'))['status']=='passed'
                scoped.steps[-1].value='$12.00'  # Other product's price must not be selected.
                assert (await execute_flow(browser,req,scoped,None,root,'wrong-price'))['status']=='failed'
                checks.append({'check':'repeated-price scoping preserves product identity and rejects another product price','passed':True})
            finally: await browser.close()

        if '--sauce' in sys.argv:
            response=await client.post('/api/runs',json={'url':'https://www.saucedemo.com/inventory.html','mode':'baseline','max_pages':3,'max_flows':3})
            response.raise_for_status()
            sauce=await wait_run(client,response.json()['id'])
            assert sauce['status']=='completed',sauce['summary']
            assert sauce['summary']['passed']>0,sauce['summary']
            checks.append({'check':'authenticated SauceDemo baseline','run_id':sauce['id'],'summary':sauce['summary']})
        cancellation=await client.post('/api/runs',json={'url':config.DEMO_ORIGIN+'/demo/','mode':'baseline'})
        cancellation.raise_for_status()
        cancel_id=cancellation.json()['id']
        cancelled=await client.post(f'/api/runs/{cancel_id}/cancel')
        assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
        checks.append({'check':'API cancellation reaches terminal cancelled state','passed':True})
    (root/'verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks,indent=2))


if __name__=='__main__': asyncio.run(main())

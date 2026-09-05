"""Live, billable OpenAI acceptance run against the local demo or read-only SauceDemo."""
import asyncio
import json
import sys
import httpx
from qa_agent import config


async def main():
    sauce='--sauce' in sys.argv
    request={
        'url':'https://www.saucedemo.com/inventory.html' if sauce else config.DEMO_ORIGIN+'/demo/',
        'mode':'openai','max_pages':3,'max_flows':4,'allow_interactions':not sauce,
        'scope':'Verify visible products, prices and product navigation without modifying data.' if sauce else 'Cart arithmetic, product search, and invalid discount handling. Use separate flows.',
        'requirements':'The inventory page displays "Products".\nThe inventory displays "Sauce Labs Backpack".' if sauce else
            'Adding a notebook increases the cart count to "1 items".\nAdding one notebook makes the total "$18.00".\nInvalid discount codes show "Invalid discount code".\nSearching for zzzunknown shows "No products found".'}
    async with httpx.AsyncClient(base_url=config.DEMO_ORIGIN,timeout=30) as client:
        await client.get('/')
        response=await client.post('/api/runs',json=request)
        response.raise_for_status()
        rid=response.json()['id'];print('Live OpenAI run:',rid,flush=True)
        previous=''
        for _ in range(620):
            r=(await client.get(f'/api/runs/{rid}')).json()
            if r['stage']!=previous: print('Stage:',r['stage'],flush=True);previous=r['stage']
            if r['status'] not in {'queued','running'}:
                record={'id':rid,'status':r['status'],'summary':r['summary'],'flows':[{'name':f['name'],'status':f['status'],'classification':f['classification']} for f in r['results']],'gaps':r['gaps']}
                folder=config.DATA/'verification';folder.mkdir(exist_ok=True)
                (folder/('openai-sauce.json' if sauce else 'openai-local.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
                print(json.dumps(record,indent=2),flush=True)
                assert r['status']=='completed',r['summary']
                assert r['summary']['usage']['input_tokens']>0
                assert r['summary']['passed']>0
                return
            await asyncio.sleep(1)
        raise AssertionError('Live run exceeded deadline')


if __name__=='__main__':asyncio.run(main())

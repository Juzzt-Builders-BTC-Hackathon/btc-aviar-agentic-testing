"""Two live OpenAI runs: PRD planning, then append-only suite enhancement."""
import asyncio
import json
from uuid import uuid4
import httpx
from qa_agent import config


async def main():
    async with httpx.AsyncClient(base_url=config.DEMO_ORIGIN,timeout=30) as client:
        await client.get('/')
        request={'url':config.DEMO_ORIGIN+'/demo/','mode':'openai','max_pages':1,'max_flows':2,
                 'scope':'Read-only PRD acceptance verification '+uuid4().hex[:8],
                 'prd_name':'store.md','prd_content':'# Store\n\n- The page heading displays "Make room for good ideas.".\n- A product called "Everyday Notebook" is visible.'}
        async def run():
            response=await client.post('/api/runs',json=request);response.raise_for_status()
            rid=response.json()['id'];print('Run:',rid,flush=True)
            for _ in range(610):
                r=(await client.get('/api/runs/'+rid)).json()
                if r['status'] not in {'queued','running'}:
                    assert r['status']=='completed',r['summary']
                    assert r['summary']['passed']>0,r['summary']
                    return r
                await asyncio.sleep(1)
            raise AssertionError('Run did not finish')
        first=await run()
        assert first['summary']['usage']['input_tokens']>0
        assert first['traceability'] and first['defects']
        request['max_flows']=4
        request['prd_content']+='\n- A product called "Studio Pencil Set" is visible.'
        second=await run()
        assert second['evolution']['previous_run']==first['id']
        current={f['id']:f for f in second['plan']['flows']}
        for old in first['plan']['flows']:
            assert current[old['id']]['steps']==old['steps']
        assert second['summary']['usage']['input_tokens']>0
        record={'first':{'id':first['id'],'summary':first['summary']},
                'second':{'id':second['id'],'summary':second['summary'],'evolution':second['evolution']},
                'checks':['live PRD planning','PRD traceability','existing assertions retained','live incremental planning']}
        path=config.DATA/'verification'/'prd-openai.json'
        path.write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps(record,indent=2))


if __name__=='__main__':asyncio.run(main())

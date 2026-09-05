import asyncio
from qa_agent.models import Flow, Step
from qa_agent.triage import triage_flow


def test_proposed_assertion_rewrite_is_rejected_before_replay():
    flow=Flow(id='case',name='Case',risk='high',category='smoke',oracle='observed',requirement_ids=[],steps=[
        Step(action='navigate',target='https://example.com/',value='',intent='Open'),
        Step(action='assert_text',target='#old',value='Expected',intent='Verify')])
    calls=[]
    def failure(attempt):
        return {'status':'failed','failure_kind':'selector','failed_step':1,'oracle':'observed','attempt':attempt}
    async def execute(candidate,attempt):
        calls.append(attempt);return failure(attempt)
    async def propose(candidate,result):
        altered=candidate.model_copy(deep=True)
        altered.steps[-1].target='#new';altered.steps[-1].value='Whatever the app shows'
        return altered,{'flow_id':'case','verified':False}
    result,audits=asyncio.run(triage_flow(flow,failure('validation'),execute,propose,lambda *a:None))
    assert calls==['run','retry']
    assert result['status']=='failed' and not audits[0]['verified']
    assert flow.steps[-1].value=='Expected'


def test_failed_validation_followed_by_passing_execution_stays_flaky():
    flow=Flow(id='case',name='Case',risk='low',category='smoke',oracle='observed',requirement_ids=[],steps=[
        Step(action='navigate',target='https://example.com/',value='',intent='Open'),
        Step(action='assert_text',target='h1',value='Expected',intent='Verify')])
    async def execute(*args): return {'status':'passed','attempt':'run'}
    async def propose(*args): raise AssertionError('A passing execution must not be repaired')
    result,_=asyncio.run(triage_flow(flow,{'status':'failed','attempt':'validation'},execute,propose,lambda *a:None))
    assert result['status']=='failed' and result['classification']['label']=='flaky_test'

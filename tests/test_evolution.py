import asyncio
import pytest
from pydantic import ValidationError
from qa_agent.models import RunRequest, Plan, Flow, Step
from qa_agent.evolution import merge_plan, remap_requirements, previous_suite, page_changes, outcome_changes
from qa_agent.planning import prd_requirements
from qa_agent.store import Store
from qa_agent.evolution import should_extend_suite
from qa_agent.triage import triage_flow, defect_report


def scenario():
    return Flow(id="original", name="Cart", risk="high", category="happy_path", oracle="requirement",
        requirement_ids=["PRD-1"], steps=[Step(action="navigate", target="https://example.com/", value="", intent="Open"),
        Step(action="assert_text", target="#old", value="Cart", intent="Check title")])


def test_increased_budget_extends_unchanged_suite():
    request = RunRequest(url='https://example.com/', max_flows=6)
    previous = {'request': request.model_copy(update={'max_flows': 1}), 'requirements': []}
    retained = Plan(summary='', flows=[scenario()], gaps=[])
    assert should_extend_suite(request, previous, retained, [], [], [])
    previous['request'] = request
    assert not should_extend_suite(request, previous, retained, [], [], [])
    assert should_extend_suite(request, None, None, [], [], [])


def test_planner_receives_remaining_budget_and_complete_replan_instruction():
    from unittest.mock import AsyncMock
    from qa_agent.llm import LLM
    request = RunRequest(url='https://example.com/', max_flows=6)
    retained = Plan(summary='', flows=[scenario()], gaps=[])
    llm = LLM()
    llm.ask = AsyncMock(return_value=retained)
    asyncio.run(llm.plan([], request, [], existing=retained))
    assert llm.ask.call_args.args[2]['max_flows'] == 5
    asyncio.run(llm.plan([], request, [], feedback=['Coverage gap']))
    assert llm.ask.call_args.args[2]['max_flows'] == 6
    assert 'COMPLETE plan' in llm.ask.call_args.args[1]


def test_markdown_contract_and_block_traceability():
    content='# Cart\n\n- Show "Cart".\n- Adding an item\n  updates the count.\n\n```js\nignore()\n```'
    assert [r['text'] for r in prd_requirements(content)] == ['Show "Cart".', 'Adding an item updates the count.']
    assert RunRequest(url='https://example.com',prd_name='../cart.md',prd_content=content).prd_name=='cart.md'
    for name, text in [('bad.pdf','text'),('ok.md','\x00'),('ok.md','é'*40000),('ok.md','   ')]:
        with pytest.raises(ValidationError): RunRequest(url='https://example.com',prd_name=name,prd_content=text)


def test_evolution_never_overwrites_expected_values_and_tracks_deferred():
    old=Plan(summary='',flows=[scenario()],gaps=[])
    changed=scenario();changed.steps[-1].value='Changed app text'
    new=scenario();new.id='new';new.name='New flow';new.steps[0].target='https://example.com/new'
    proposed=Plan(summary='',flows=[changed,new],gaps=[])
    merged,added,deferred=merge_plan(old,proposed,2)
    assert merged.flows[0]==old.flows[0] and added==['new'] and not deferred
    assert merge_plan(old,proposed,1)[2]==['New flow']
    remapped=remap_requirements(old,[{'id':'PRD-1','text':'Old rule'}],[{'id':'PRD-1','text':'New rule'}])
    assert remapped.flows[0].oracle=='inferred' and remapped.flows[0].steps[-1].value=='Cart'
    assert not remapped.flows[0].requirement_ids


def test_suite_history_survives_restart_and_ignores_incomplete_run(tmp_path):
    store=Store(tmp_path);request=RunRequest(url='https://example.com/',mode='baseline')
    rid=store.create(request.model_dump());store.artifact(rid,'plan.json',Plan(summary='',flows=[scenario()],gaps=[]).model_dump())
    store.update(rid,status='completed')
    store.create(request.model_dump())
    assert previous_suite(Store(tmp_path),request)['id']==rid
    request.scope='different scope'
    assert previous_suite(store,request) is None


def test_diff_does_not_claim_missing_page_is_deleted():
    changes=page_changes([{'url':'https://example.com/a'}],[{'url':'https://example.com/b'}])
    assert {c['kind'] for c in changes}=={'new_page','not_observed'}
    assert outcome_changes([{'flow_id':'x','status':'passed'}],[{'flow_id':'x','name':'X','status':'failed'}])[0]['change']=='regression'


def result(status='failed',kind='selector',attempt='validation'):
    return {'flow_id':'original','name':'Cart','risk':'high','oracle':'requirement','status':status,
            'failure_kind':kind,'failed_step':1,'steps':[],'attempt':attempt,'error':'missing'}


def test_healer_bounded_replay_preserves_original_reproduction():
    flow=scenario();calls=[]
    async def execute(f,attempt):
        calls.append(attempt)
        return result('passed' if attempt=='healed' else 'failed',attempt=attempt)
    async def propose(f,r):
        fixed=f.model_copy(deep=True);fixed.steps[-1].target='#new'
        return fixed,{'flow_id':f.id,'old_selector':'#old','new_selector':'#new','verified':False}
    actual,audits=asyncio.run(triage_flow(flow,result(),execute,propose,lambda *a:None))
    assert calls==['run','retry','healed']
    assert actual['classification']['issue_type']=='test_script_issue' and audits[0]['verified']
    assert flow.steps[-1].target=='#new' and flow.steps[-1].value=='Cart'
    report=defect_report(Plan(summary='',flows=[flow],gaps=[]),[actual],audits)[0]
    assert report['expected']['target']=='#old'
    assert len(report['attempts'])==4


@pytest.mark.parametrize('kind,oracle,label',[('assertion','requirement','likely_defect'),('assertion','inferred','needs_review'),('execution','observed','environment_issue')])
def test_non_locator_failures_are_not_rewritten(kind,oracle,label):
    flow=scenario();flow.oracle=oracle
    async def execute(f,attempt):
        r=result(kind=kind,attempt=attempt);r['oracle']=oracle;return r
    async def propose(*args): raise AssertionError('Must not heal an assertion or environment failure')
    actual,audits=asyncio.run(triage_flow(flow,result(kind=kind),execute,propose,lambda *a:None))
    assert actual['classification']['label']==label and not audits


def test_flaky_failure_is_retained_and_failed_repair_not_promoted():
    flow=scenario()
    async def execute(f,attempt): return result('passed' if attempt=='retry' else 'failed',attempt=attempt)
    async def propose(*args): raise AssertionError('Do not repair a passing retry')
    actual,_=asyncio.run(triage_flow(flow,result(),execute,propose,lambda *a:None))
    assert actual['status']=='failed' and actual['classification']['label']=='flaky_test'

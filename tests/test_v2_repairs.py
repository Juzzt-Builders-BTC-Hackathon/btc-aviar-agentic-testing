import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from qa_agent import config
from qa_agent.models import Flow, Step, Plan, RunRequest
from qa_agent.v2_models import EvaluationResult, GeneratedSuite, GenerationProposal, success
from qa_agent.llm import LLM
from qa_agent.agents_v2.evaluator import EvaluatorAgent
from qa_agent.agents_v2.generator import GeneratorAgent
from qa_agent.agents_v2.healer import HealerAgent
from qa_agent.agents_v2.validation import plan_issues
from qa_agent.agents_v2.support import error_message
from qa_agent.adapters_v2.runtime_adapter import V2Runtime
from qa_agent.orchestration_v2.state import initial_state
from qa_agent.orchestration_v2.graph import build_graph
from qa_agent.orchestration_v2.runner import resume_guard
from qa_agent.evolution import previous_suite
from qa_agent.triage import finalize_result
from qa_agent.store import Store


def make_flow():
    return Flow(id='test',name='Page title',category='smoke',risk='medium',oracle='observed',requirement_ids=[],steps=[
        Step(action='navigate',target='https://example.com/',value='',intent='Open page'),
        Step(action='assert_text',target='h1',value='Hello',intent='Verify title')])


def make_plan(): return Plan(summary='Test plan',flows=[make_flow()],gaps=[])


def test_adapter_import_does_not_depend_on_orchestrator_import_order():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-c','from qa_agent.adapters_v2 import V2Runtime'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


@pytest.fixture
def runtime_state(tmp_path):
    request = RunRequest(url='https://example.com/',mode='baseline')
    store = Store(tmp_path)
    rid = store.create(request.model_dump())
    runtime = V2Runtime(store,rid)
    state = initial_state(rid,request.model_dump())
    state.update(deadline_at=str(time.time()+600),planner_output=success({'plan':make_plan().model_dump()}),
        requirements_output=success({'requirements':[]}),
        recon_output=[{'url':'https://example.com/','text':'Hello','elements':[{'selector':'h1','tag':'h1','text':'Hello'}]}])
    state['generator_output'] = success(GeneratedSuite(plan=make_plan(),generated_flow_ids=['test']))
    state['plan_evaluation'] = success(EvaluationResult(evaluation_stage='PLAN_EVALUATION',decision='APPROVE'))
    state['generation_evaluation'] = success(EvaluationResult(evaluation_stage='GENERATION_EVALUATION',decision='APPROVE'))
    return runtime,state


def test_all_api_output_schemas_have_closed_nested_objects():
    from openai.lib._pydantic import to_strict_json_schema
    from qa_agent.v2_models import PRDAnalysis,ReporterNarrative
    from qa_agent.models import HealProposal
    def check(node):
        if isinstance(node,dict):
            if node.get('type') == 'object': assert node.get('additionalProperties') is False
            for value in node.values(): check(value)
        elif isinstance(node,list):
            for value in node: check(value)
    for model in (EvaluationResult,PRDAnalysis,GenerationProposal,ReporterNarrative,Plan,HealProposal):
        check(to_strict_json_schema(model))


def test_error_keeps_diagnostics_but_redacts_key(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','secret-value')
    message = error_message(ValueError('Invalid schema secret-value'))
    assert 'Invalid schema' in message and 'secret-value' not in message


def test_generator_cannot_weaken_assertion():
    original = make_flow(); original.steps[1] = Step(action='assert_visible',target='#results',value='',intent='Results')
    changed = original.model_copy(deep=True); changed.steps[1].target = 'body'
    assert not GeneratorAgent._same_assertions(original,changed)


def test_wrong_page_selector_and_body_only_assertions_are_rejected():
    flow = make_flow(); flow.steps[1].target = '#other'
    pages = [{'url':'https://example.com/','elements':[]},
             {'url':'https://example.com/other','elements':[{'selector':'#other','tag':'h1'}]}]
    assert 'another page' in str(plan_issues(Plan(summary='',flows=[flow],gaps=[]),pages))
    flow.steps[1] = Step(action='assert_visible',target='body',value='',intent='Check validation')
    assert 'body visibility' in str(plan_issues(Plan(summary='',flows=[flow],gaps=[]),[]))


def test_generator_receives_feedback_and_keeps_failed_items():
    model = LLM(max_calls=8)
    model.ask = AsyncMock(return_value=GenerationProposal(flows=[make_flow()]))
    request = RunRequest(url='https://example.com',mode='openai')
    validation = [{'flow_id':'test','status':'failed','error':'missing locator','failure_snapshot':{'url':request.url,'elements':[]}}]
    asyncio.run(GeneratorAgent(model).run(request,make_plan(),feedback={'gaps':['repair locator']},validation=validation))
    payload = model.ask.call_args.args[2]
    assert payload['feedback']['gaps'] == ['repair locator']
    assert payload['validation'][0]['error'] == 'missing locator'


def test_evaluator_reserves_reporter_call_and_early_stages_reserve_two():
    model = LLM(max_calls=8); model.calls = 6
    model.ask = AsyncMock(return_value=EvaluationResult(evaluation_stage='FINAL_EVALUATION',decision='REPORT'))
    agent = EvaluatorAgent(model)
    request = RunRequest(url='https://example.com',mode='openai')
    asyncio.run(agent.run('PLAN_EVALUATION',request,plan=make_plan()))
    assert not model.ask.called
    asyncio.run(agent.run('FINAL_EVALUATION',request,plan=make_plan()))
    assert model.ask.call_count == 1


def test_healer_baseline_and_api_failure_are_safe():
    model = LLM(); model.heal = AsyncMock(side_effect=ValueError('API unavailable'))
    old = {'tag':'button','type':'','text':'Submit'}
    baseline = asyncio.run(HealerAgent(model).run(old,[],'Submit',mode='baseline'))
    assert not model.heal.called and baseline['data']['candidate_selector'] is None
    fallback = asyncio.run(HealerAgent(model).run(old,[],'Submit',mode='openai'))
    assert fallback['degraded_mode'] and 'API unavailable' in fallback['errors'][0]


def test_validation_failure_is_preserved_as_flaky():
    failed = {'flow_id':'test','status':'failed','failure_kind':'assertion','attempt':'validation'}
    passed = {'flow_id':'test','status':'passed','attempt':'run'}
    result = finalize_result(make_flow(),failed,passed)
    assert result['status'] == 'failed' and result['classification']['label'] == 'flaky_test'
    assert result['classification']['next_action'] and len(result['attempts']) == 2


def test_plan_artifact_supports_suite_reuse(runtime_state):
    runtime,state = runtime_state
    runtime.save_suite(runtime.request(state),GeneratedSuite.model_validate(state['generator_output']['data']))
    runtime.store.update(runtime.run_id,status='completed')
    assert previous_suite(runtime.store,runtime.request(state))['id'] == runtime.run_id


def test_rejected_plan_produces_visible_generation_failures(runtime_state):
    runtime,state = runtime_state
    update = asyncio.run(runtime.reject_plan(state))
    assert update['execution_results'][0]['status'] == 'generation_failed'
    assert runtime.store.read(runtime.run_id,'run_results.json')[0]['classification']['next_action']


def test_final_feedback_reaches_planner(runtime_state):
    runtime,state = runtime_state
    state['final_evaluation'] = success({'gaps':['Missing rank boundary'],'decision':'REPLAN'})
    state['final_replan_attempts'] = 1
    runtime.planner_agent.run = AsyncMock(return_value=state['planner_output'])
    asyncio.run(runtime.plan(state))
    feedback = runtime.planner_agent.run.call_args.kwargs['feedback']
    assert feedback['final_review']['gaps'] == ['Missing rank boundary']
    assert runtime.planner_agent.run.call_args.kwargs['existing'] is not None


def test_oracle_is_grounded_before_validation(runtime_state):
    runtime,state = runtime_state
    plan=make_plan();plan.flows[0].oracle='requirement';plan.flows[0].requirement_ids=['REQ-1']
    state['requirements_output']=success({'requirements':[{'requirement_id':'REQ-1','description':'The title must be visible'}]})
    runtime.planner_agent.run=AsyncMock(return_value=success({'plan':plan.model_dump()}))
    updated=asyncio.run(runtime.plan(state))
    assert updated['planner_output']['data']['plan']['flows'][0]['oracle']=='inferred'
    assert runtime.store.read(runtime.run_id,'plan.json')['flows'][0]['oracle']=='inferred'


def test_failure_persisted_even_when_artifacts_cannot_be_written(runtime_state,monkeypatch):
    runtime,state = runtime_state
    monkeypatch.setattr(runtime.store,'artifact',lambda *args:(_ for _ in ()).throw(OSError('disk full')))
    asyncio.run(runtime.fail({**state,'errors':[{'message':'report failed'}]}))
    assert runtime.store.get(runtime.run_id)['status'] == 'failed'


@pytest.mark.parametrize('browser,deadline,node,expected',[(False,100,'reporter',True),(True,100,'reporter',False),
    (False,-1,'reporter',False),(False,100,'executor',False)])
def test_resume_only_at_safe_boundaries(browser,deadline,node,expected):
    snap = SimpleNamespace(values={'schema_version':2,'deadline_at':str(time.time()+deadline)},next=(node,))
    assert resume_guard({'status':'interrupted'},snap,{'phase':'started','browser':browser})[0] is expected


def test_report_contains_narrative_fallback_and_usage(runtime_state):
    runtime,state = runtime_state
    state['execution_results'] = [finalize_result(make_flow(),{}, {'flow_id':'test','status':'passed','steps':[],'duration_ms':0})]
    state['final_evaluation'] = success(EvaluationResult(evaluation_stage='FINAL_EVALUATION',decision='REPORT'))
    runtime.record('plan_evaluation',{'status':'success','data':{},'degraded_mode':True,'errors':['Schema rejected']})
    asyncio.run(runtime.report(state))
    text = (runtime.store.root/runtime.run_id/'report.md').read_text(encoding='utf-8')
    assert 'Reporter narrative' in text and 'Schema rejected' in text
    assert runtime.store.get(runtime.run_id)['status'] == 'completed'

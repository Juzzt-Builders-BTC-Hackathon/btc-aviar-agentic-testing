"""Qpilot V2 stages: durable evidence, bounded decisions and isolated browser work."""
import time
from copy import deepcopy
from playwright.async_api import async_playwright
from ..agents_v2 import EvaluatorAgent, GeneratorAgent, HealerAgent, PlannerAgent, PRDAnalystAgent, ReporterAgent
from ..agents_v2.validation import plan_issues, compact_results
from ..browser import auth_state, crawl, execute_flow
from ..evolution import canonical_url, outcome_changes, page_changes, previous_suite, remap_requirements, suite_key
from ..llm import LLM
from ..models import Plan, RunRequest, Flow
from ..pipeline import export_suite, fingerprint_key
from ..planning import ground_oracles
from ..reporting import reports
from ..runtime import launch_browser
from ..safety import redact
from ..triage import defect_report, finalize_result
from ..v2_models import AgentEnvelope, EvaluationResult, GeneratedSuite, PRDAnalysis, success
from ..orchestration_v2.events import event, now
from ..orchestration_v2.policies import MAX_LLM_CALLS

STAGES = {'analyze_prd':'prd_analyst','plan':'planner','evaluate_plan':'plan_evaluator',
          'generate':'generator','validate':'validator','evaluate_generation':'generation_evaluator',
          'execute':'executor','heal':'healer','evaluate_final':'final_evaluator',
          'evolve':'evolution','report':'reporter','reconnaissance':'recon'}
BROWSER_STAGES = {'reconnaissance','plan','validate','execute','heal'}


class V2Runtime:
    def __init__(self, store, run_id):
        self.store, self.run_id = store, run_id
        self.llm = LLM(max_calls=MAX_LLM_CALLS)
        self.llm.on_usage = lambda usage:self.store.artifact(run_id,'llm_usage.json',usage)
        self.prd_agent, self.planner_agent = PRDAnalystAgent(self.llm), PlannerAgent(self.llm)
        self.evaluator_agent, self.generator_agent = EvaluatorAgent(self.llm), GeneratorAgent(self.llm)
        self.healer_agent, self.reporter_agent = HealerAgent(self.llm), ReporterAgent(self.llm)
        self.started = time.monotonic()
        self.last_state = {}
        self.narrative = None

    def request(self, state): return RunRequest.model_validate(state['request'])

    def progress(self, stage, message):
        self.store.update(self.run_id,status='running',stage=stage)
        self.store.event(self.run_id,stage,redact(message))

    def begin(self, state, method):
        self.last_state = deepcopy(state)
        stage = STAGES.get(method,method)
        self.store.artifact(self.run_id,'active_stage.json',{'method':method,'phase':'started',
                            'browser':method in BROWSER_STAGES,'schema_version':2})
        self.progress(stage,f'Starting {stage}')

    def finish(self, method):
        self.store.artifact(self.run_id,'active_stage.json',{'method':method,'phase':'completed',
                            'browser':method in BROWSER_STAGES,'schema_version':2})

    def update(self, state, stage, message, **values):
        self.progress(stage,message)
        health = self.store.read(self.run_id,'agent_health.json',{})
        values.update(current_stage=stage,pipeline_status='running',events=event(state,stage,message),
                      logical_llm_calls=self.llm.calls,token_usage=self.llm.usage(),
                      degraded_components=[k for k,v in health.items() if v['degraded_mode']])
        self.last_state = {**state,**values}
        return values

    def record(self, role, output):
        parsed = AgentEnvelope.model_validate(output)
        self.store.artifact(self.run_id,role+'.json',parsed.model_dump())
        health = self.store.read(self.run_id,'agent_health.json',{})
        old = health.get(role,{})
        health[role] = {'status':parsed.status,'degraded_mode':parsed.degraded_mode or old.get('degraded_mode',False),
            'errors':list(dict.fromkeys(old.get('errors',[]) + parsed.errors)),
            'attempts':old.get('attempts',0)+1}
        self.store.artifact(self.run_id,'agent_health.json',health)
        self.store.artifact(self.run_id,f'{role}.attempt-{health[role]["attempts"]}.json',parsed.model_dump())
        if parsed.degraded_mode: self.progress(self.store.get(self.run_id)['stage'],f'{role}: fallback used; inspect agent health')
        return parsed

    def save_suite(self, request, suite):
        self.store.artifact(self.run_id,'plan.json',suite.plan.model_dump())
        export_suite(self.store,self.run_id,request,suite.plan)

    @staticmethod
    def legacy_requirements(data):
        return [{'id':r['requirement_id'],'text':r['description'],
                 'acceptance_criteria':r.get('acceptance_criteria',[]),'edge_cases':r.get('edge_cases',[])}
                for r in data.get('requirements',[])]

    async def initialize(self, state):
        self.store.artifact(self.run_id,'pipeline_metadata.json',{'pipeline_version':'v2','schema_version':2,
                             'max_llm_calls':self.llm.max_calls})
        return self.update(state,'initialize','V2 run initialized',started_at=now(),
                           deadline_at=str(time.time()+600))

    async def reconnaissance(self, state):
        request = self.request(state)
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser,request.url)
                pages = await crawl(browser,request,session,lambda msg:self.progress('recon',msg))
            finally: await browser.close()
        self.store.artifact(self.run_id,'recon.json',pages)
        return self.update(state,'recon',f'Observed {len(pages)} distinct pages',recon_output=pages)

    async def load_evolution(self,state):
        previous = previous_suite(self.store,self.request(state))
        serial,changes = None,[]
        if previous:
            changes = page_changes(previous['pages'],state['recon_output'])
            serial = {**previous,'request':previous['request'].model_dump(),'plan':previous['plan'].model_dump()}
        return self.update(state,'load_evolution','Loaded compatible suite',previous_suite=serial,ui_changes=changes)

    async def analyze_prd(self,state):
        request = self.request(state)
        parsed = self.record('prd_analysis',await self.prd_agent.run(request,request.requirements,request.prd_content))
        PRDAnalysis.model_validate(parsed.data)
        if request.prd_content: self.store.artifact(self.run_id,'prd.md',request.prd_content)
        self.store.artifact(self.run_id,'requirements.json',self.legacy_requirements(parsed.data))
        return self.update(state,'prd_analyst','Requirements extracted',requirements_output=parsed.model_dump())

    async def plan(self,state):
        request = self.request(state)
        requirements = self.legacy_requirements(state['requirements_output']['data'])
        retained = None
        if state.get('final_replan_attempts') and state.get('generator_output'):
            retained = Plan.model_validate(state['generator_output']['data']['plan'])
        elif state.get('previous_suite'):
            prev = state['previous_suite']
            retained = remap_requirements(Plan.model_validate(prev['plan']),prev['requirements'],requirements)
        feedback = {'plan_review':(state.get('plan_evaluation') or {}).get('data',{}),
                    'final_review':(state.get('final_evaluation') or {}).get('data',{}),
                    'previous_attempt':(state.get('planner_output') or {}).get('data',{}),
                    'results':compact_results(state.get('execution_results',[]))}
        parsed = self.record('planner_output',await self.planner_agent.run(request,state['recon_output'],requirements,
                             existing=retained,feedback=feedback))
        plan = Plan.model_validate(parsed.data['plan'])
        plan.gaps = list(dict.fromkeys(plan.gaps+ground_oracles(plan,requirements)))[:30]
        parsed.data['plan'] = plan.model_dump()
        pages = list(state['recon_output'])
        # Bounded supplementary discovery of actual planned entry pages.
        missing = [f.steps[0].target for f in plan.flows if canonical_url(f.steps[0].target) not in
                   {canonical_url(p['url']) for p in pages}]
        for url in list(dict.fromkeys(missing))[:max(0,min(12,request.max_pages+3)-len(pages))]:
            from ..safety import target_url
            try:
                url = target_url(request.url,url,request.navigation_origins)
                async with async_playwright() as pw:
                    browser = await launch_browser(pw)
                    try:
                        session = await auth_state(browser,request.url)
                        extra = await crawl(browser,request.model_copy(update={'url':url,'max_pages':1}),session,
                                            lambda msg:self.progress('planner',msg))
                    finally: await browser.close()
                known = {canonical_url(p['url']) for p in pages}
                pages.extend(p for p in extra if canonical_url(p['url']) not in known)
            except Exception as exc:
                plan.gaps = (plan.gaps+[redact(f'Could not observe {url}: {exc}')[:500]])[-30:]
        parsed.data['plan'] = plan.model_dump()
        self.store.artifact(self.run_id,'plan.json',plan.model_dump())
        self.store.artifact(self.run_id,'planner_output.json',parsed.model_dump())
        if not state.get('planning_attempts'): self.store.artifact(self.run_id,'plan.initial.json',plan.model_dump())
        self.store.artifact(self.run_id,'recon.json',pages)
        return self.update(state,'planner',f'Planned {len(plan.flows)} flows',planner_output=parsed.model_dump(),
                           recon_output=pages,planning_attempts=state.get('planning_attempts',0)+1,
                           generation_attempts=0,generation_evaluation=None,quarantined_flow_ids=[])

    async def evaluate_plan(self,state):
        parsed = self.record('plan_evaluation',await self.evaluator_agent.run('PLAN_EVALUATION',self.request(state),
            pages=state['recon_output'],requirements=self.legacy_requirements(state['requirements_output']['data']),
            plan=Plan.model_validate(state['planner_output']['data']['plan'])))
        return self.update(state,'plan_evaluator',f'Plan decision: {parsed.data["decision"]}',plan_evaluation=parsed.model_dump())

    async def generate(self,state):
        request = self.request(state)
        parsed = self.record('generator_output',await self.generator_agent.run(request,
            Plan.model_validate(state['planner_output']['data']['plan']),pages=state['recon_output'],
            feedback=(state.get('generation_evaluation') or {}).get('data',{}),validation=state.get('validation_results',[])))
        suite = GeneratedSuite.model_validate(parsed.data)
        self.save_suite(request,suite)
        return self.update(state,'generator',f'Generated {len(suite.generated_flow_ids)} candidate flows',
                           generator_output=parsed.model_dump(),generation_attempts=state.get('generation_attempts',0)+1)

    def invalid_result(self,flow,reason,status='generation_failed'):
        return {'flow_id':flow.id,'name':flow.name,'risk':flow.risk,'oracle':flow.oracle,'status':status,
                'failure_kind':'policy' if status == 'blocked' else 'generation','error':reason,
                'steps':[],'diagnostics':[],'duration_ms':0,'attempt':'generation_gate'}

    def attempt_name(self,state,name):
        return f'p{state.get("planning_attempts",0)}-g{state.get("generation_attempts",0)}-{name}'

    async def validate(self,state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state['generator_output']['data'])
        invalid = plan_issues(suite.plan,state['recon_output'],request)
        validation = []
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser,request.url)
                for flow in suite.plan.flows:
                    if flow.id in invalid: result = self.invalid_result(flow,'; '.join(invalid[flow.id]))
                    else: result = await execute_flow(browser,request,flow,session,self.store.root/self.run_id,
                                                       self.attempt_name(state,'validation'))
                    validation.append(result)
                    self.store.artifact(self.run_id,'validation_report.json',validation)
                    self.progress('validator',f'{flow.name}: {result["status"]} ({len(validation)}/{len(suite.plan.flows)})')
            finally: await browser.close()
        self.store.artifact(self.run_id,self.attempt_name(state,'validation')+'.json',validation)
        return self.update(state,'validator','Validation finished',validation_results=validation)

    async def evaluate_generation(self,state):
        parsed = self.record('generation_evaluation',await self.evaluator_agent.run('GENERATION_EVALUATION',
            self.request(state),pages=state['recon_output'],requirements=self.legacy_requirements(state['requirements_output']['data']),
            plan=Plan.model_validate(state['planner_output']['data']['plan']),generated=state['generator_output']['data'],
            validation=state['validation_results']))
        return self.update(state,'generation_evaluator',f'Generation decision: {parsed.data["decision"]}',
                           generation_evaluation=parsed.model_dump())

    async def reject_plan(self,state):
        plan = Plan.model_validate(state['planner_output']['data']['plan'])
        suite = GeneratedSuite(plan=plan,generated_flow_ids=[],generation_gaps=state['plan_evaluation']['data'].get('gaps',[]))
        results = [finalize_result(f,{},self.invalid_result(f,'Plan review was not approved; scenario untested')) for f in plan.flows]
        self.save_suite(self.request(state),suite)
        self.store.artifact(self.run_id,'run_results.json',results)
        return self.update(state,'plan_evaluator','Plan rejected; reporting untested scenarios',
            generator_output=success(suite),generation_evaluation=success(EvaluationResult(evaluation_stage='GENERATION_EVALUATION',
                decision='INVALID',gaps=['Generation skipped because plan was not approved'])),
            execution_results=results,exhausted_limits=state.get('exhausted_limits',[])+['plan_review'])

    async def quarantine(self,state):
        review = state['generation_evaluation']['data']
        ids = review.get('invalid_items',[])
        if not ids: ids = [f['id'] for f in state['generator_output']['data']['plan']['flows']]
        return self.update(state,'generation_evaluator','Rejected flows excluded from execution; retained as untested risk',
                           quarantined_flow_ids=ids,exhausted_limits=state.get('exhausted_limits',[])+['generation_review'])

    async def execute(self,state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state['generator_output']['data'])
        validation = {r['flow_id']:r for r in state['validation_results']}
        results = []
        self.store.artifact(self.run_id,'run_results.json',results)
        if all(f.id in state.get('quarantined_flow_ids',[]) for f in suite.plan.flows):
            for flow in suite.plan.flows:
                validated = validation.get(flow.id,{})
                original = self.invalid_result(flow,'Generation validation rejected this flow: '+validated.get('error','review gaps'),
                                               'blocked' if validated.get('status') == 'blocked' else 'generation_failed')
                results.append(finalize_result(flow,validated,original))
            self.store.artifact(self.run_id,'run_results.json',results)
            return self.update(state,'executor','No approved executable flows; reporting untested risk',execution_results=results)
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser,request.url)
                for flow in suite.plan.flows:
                    validated = validation.get(flow.id,{})
                    retry = None
                    if flow.id in state.get('quarantined_flow_ids',[]):
                        original = self.invalid_result(flow,'Generation validation rejected this flow: '+validated.get('error','review gaps'),
                                                       'blocked' if validated.get('status') == 'blocked' else 'generation_failed')
                    elif validated.get('status') == 'blocked': original = validated
                    else:
                        original = await execute_flow(browser,request,flow,session,self.store.root/self.run_id,self.attempt_name(state,'run'))
                        if original['status'] == 'failed':
                            self.store.artifact(self.run_id,'run_results.json',results+[finalize_result(flow,validated,original)])
                            self.progress('executor',f'{flow.name}: retrying unchanged failure once')
                            retry = await execute_flow(browser,request,flow,session,self.store.root/self.run_id,self.attempt_name(state,'retry'))
                    result = finalize_result(flow,validated,original,retry)
                    results.append(result)
                    self.persist_fingerprints(request,flow,result)
                    self.store.artifact(self.run_id,'run_results.json',results)
                    self.progress('executor',f'{flow.name}: {result["status"]} ({len(results)}/{len(suite.plan.flows)})')
            finally: await browser.close()
        self.store.artifact(self.run_id,self.attempt_name(state,'execution')+'.json',results)
        return self.update(state,'executor','Execution complete',execution_results=results)

    def persist_fingerprints(self,request,flow,result):
        if result['status'] != 'passed': return
        for step in result.get('healed_attempt',result).get('steps',[]):
            if step.get('fingerprint'): self.store.fingerprint(fingerprint_key(request.url,flow,step['index']),step['fingerprint'])

    async def heal(self,state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state['generator_output']['data'])
        results,actions = deepcopy(state['execution_results']),list(state.get('healer_actions',[]))
        validation = {r['flow_id']:r for r in state['validation_results']}
        async with async_playwright() as pw:
            browser = await launch_browser(pw)
            try:
                session = await auth_state(browser,request.url)
                for result in results:
                    retry = result.get('retry') or {}
                    if not (result['status'] == retry.get('status') == 'failed'
                            and result.get('failure_kind') == retry.get('failure_kind') == 'selector'
                            and result.get('failed_step') == retry.get('failed_step')): continue
                    flow = next(f for f in suite.plan.flows if f.id == result['flow_id'])
                    original_flow = flow.model_copy(deep=True)
                    index = result['failed_step']
                    old = self.store.fingerprint(fingerprint_key(request.url,flow,index))
                    page_url = result.get('failure_snapshot',{}).get('url',flow.steps[0].target)
                    if not old:
                        old = next((e for p in state['recon_output'] if canonical_url(p['url']) == canonical_url(page_url)
                                    for e in p['elements'] if e['selector'] == flow.steps[index].target),None)
                    validated = validation.get(flow.id,{})
                    scoped = result.get('scoped_regeneration')
                    if not scoped and validated.get('failed_step') == index:
                        scoped = validated.get('scoped_regeneration')
                    if scoped:
                        proposal = success({'candidate_selector':scoped['selector'],'rationale':'Unique selector scoped by verified preceding text anchor',
                                            'tier':'scoped_regeneration'})
                    else:
                        proposal = await self.healer_agent.run(old,result.get('failure_snapshot',{}).get('elements',[]),
                                                              flow.steps[index].intent,mode=request.mode)
                    parsed = self.record('healer_output',proposal)
                    selector = parsed.data.get('candidate_selector')
                    audit = {'flow_id':flow.id,'step':index,'old_selector':flow.steps[index].target,
                             **parsed.data,'new_selector':selector,'verified':False}
                    if selector:
                        repaired = flow.model_copy(deep=True)
                        repaired.steps[index].target = selector
                        confirmation = await execute_flow(browser,request,repaired,session,self.store.root/self.run_id,self.attempt_name(state,'healed'))
                        audit['verified'] = confirmation['status'] == 'passed'
                        original = next((a for a in result['attempts'] if a.get('attempt','').endswith('-run')), result)
                        updated = finalize_result(original_flow,validated,original,retry,confirmation)
                        result.clear(); result.update(updated)
                        if audit['verified']:
                            flow.steps = repaired.steps
                            self.persist_fingerprints(request,flow,result)
                    actions.append(audit)
                    self.store.artifact(self.run_id,'run_results.json',results)
                    self.store.artifact(self.run_id,'heal_log.json',actions)
                    self.save_suite(request,suite)
                    self.progress('healer',f'{flow.name}: repair '+('verified' if audit['verified'] else 'not verified'))
            finally: await browser.close()
        output = dict(state['generator_output']); output['data'] = suite.model_dump()
        self.store.artifact(self.run_id,'generator_output.json',output)
        return self.update(state,'healer','Healing complete',execution_results=results,healer_actions=actions,generator_output=output)

    async def evaluate_final(self,state):
        suite = GeneratedSuite.model_validate(state['generator_output']['data'])
        parsed = self.record('final_evaluation',await self.evaluator_agent.run('FINAL_EVALUATION',self.request(state),
            pages=state['recon_output'],requirements=self.legacy_requirements(state['requirements_output']['data']),
            plan=suite.plan,generated=state['generator_output']['data'],validation=state.get('validation_results',[]),
            results=state['execution_results'],heals=state.get('healer_actions',[])))
        # No replan without budget for planning plus final evaluation and report.
        if parsed.data['decision'] == 'REPLAN' and not self.llm.can_call(3):
            parsed.data['decision'] = 'REPORT'
            parsed.data['untested_risks'].append('Replan budget exhausted; coverage omissions remain untested')
            self.store.artifact(self.run_id,'final_evaluation.json',parsed.model_dump())
        return self.update(state,'final_evaluator',f'Final decision: {parsed.data["decision"]}',
            final_evaluation=parsed.model_dump(),
            final_replan_attempts=state.get('final_replan_attempts',0)+(parsed.data['decision'] == 'REPLAN'))

    async def evolve(self,state):
        suite = GeneratedSuite.model_validate(state['generator_output']['data'])
        previous = state.get('previous_suite')
        reused = (state.get('planner_output') or {}).get('data',{}).get('reused_flow_ids',[])
        evolution = {'suite_key':suite_key(self.request(state)),'previous_run':previous['id'] if previous else None,
            'ui_changes':state.get('ui_changes',[]),'reused':reused,
            'added':[f.id for f in suite.plan.flows if f.id not in reused],
            'deferred':state['planner_output']['data'].get('deferred_candidates',[]),
            'outcomes':outcome_changes(previous['results'] if previous else [],state['execution_results'])}
        self.store.artifact(self.run_id,'suite_evolution.json',evolution)
        return self.update(state,'evolution','Suite evolution saved',evolution_output=evolution)

    async def report(self,state):
        request = self.request(state)
        suite = GeneratedSuite.model_validate(state['generator_output']['data'])
        gaps = list(suite.plan.gaps)+suite.generation_gaps
        for key in ('plan_evaluation','generation_evaluation','final_evaluation'):
            review = (state.get(key) or {}).get('data',{})
            gaps.extend(review.get('gaps',[])+review.get('untested_risks',[]))
        gaps.extend(f'{r["name"]}: browser warnings require review' for r in state['execution_results'] if r.get('diagnostics'))
        gaps = list(dict.fromkeys(gaps))
        health = self.store.read(self.run_id,'agent_health.json',{})
        if self.narrative is None:
            self.narrative = await self.reporter_agent.run(request,{'results':compact_results(state['execution_results']),
                'gaps':gaps,'agent_health':health,'heals':state.get('healer_actions',[])})
        narrative = self.record('agent_narrative',self.narrative).model_dump()
        health = self.store.read(self.run_id,'agent_health.json',{})
        self.store.artifact(self.run_id,'defect_report.json',defect_report(suite.plan,state['execution_results'],state.get('healer_actions',[])))
        self.store.artifact(self.run_id,'classifications.json',[{'flow_id':r['flow_id'],**r['classification']} for r in state['execution_results']])
        self.store.artifact(self.run_id,'coverage_gaps.json',gaps)
        self.save_suite(request,suite)
        summary = reports(self.store,self.run_id,request,suite.plan,state['execution_results'],gaps,state.get('healer_actions',[]),
            self.legacy_requirements(state['requirements_output']['data']),self.llm.usage(),
            narrative=narrative,agent_health=health)
        summary.update(pipeline_version='v2',duration_seconds=round(time.time()-float(state['deadline_at'])+600,1),
            previous_run=(state.get('evolution_output') or {}).get('previous_run'),max_llm_calls=self.llm.max_calls,
            exhausted_limits=state.get('exhausted_limits',[]),degraded_components=[k for k,v in health.items() if v['degraded_mode']])
        self.store.update(self.run_id,status='completed',stage='done',summary=summary)
        self.store.event(self.run_id,'done','Run completed. Review failures and untested coverage.')
        return {'pipeline_status':'completed','current_stage':'done','report_output':narrative,'cleanup_completed':True,
                'logical_llm_calls':self.llm.calls,'token_usage':self.llm.usage()}

    async def fail(self,state):
        error = (state.get('errors') or [{'message':'Pipeline failed; inspect last stage'}])[-1]
        message = redact(error.get('message') or 'Run exceeded deadline or encountered an error')[:1500]
        # Persist terminal status even when the filesystem artifact write fails.
        self.store.update(self.run_id,status='failed',stage=error.get('stage',state.get('current_stage','v2')),
                          summary={'error':message,'pipeline_version':'v2','usage':self.llm.usage()})
        try: self.store.artifact(self.run_id,'runtime_error.json',error)
        except OSError: pass
        self.store.event(self.run_id,'failed',message)
        return {'pipeline_status':'failed','cleanup_completed':True}

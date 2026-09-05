"""One bounded live evaluator call; no browser interactions or secret output."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qa_agent.llm import LLM
from qa_agent.models import RunRequest,Plan,Flow,Step
from qa_agent.agents_v2.evaluator import EvaluatorAgent


async def main():
    llm=LLM(max_calls=3)  # Reserve two; this verification makes at most one logical API call.
    flow=Flow(id='schema_check',name='Title smoke',category='smoke',risk='low',oracle='observed',requirement_ids=[],steps=[
        Step(action='navigate',target='https://example.com/',value='',intent='Open'),
        Step(action='assert_text',target='h1',value='Example',intent='Verify title')])
    result=await EvaluatorAgent(llm).run('GENERATION_EVALUATION',RunRequest(url='https://example.com/',mode='openai'),
        plan=Plan(summary='Schema check',flows=[flow],gaps=[]),generated={'generated_flow_ids':['schema_check']},
        validation=[{'flow_id':'schema_check','status':'passed'}])
    print('Live evaluator:', 'PASS' if not result['degraded_mode'] else 'FAIL')
    print('Decision:',result['data']['decision'])
    print('Calls:',llm.calls)
    for error in result['errors']: print(error)
    return 1 if result['degraded_mode'] else 0


if __name__=='__main__': raise SystemExit(asyncio.run(main()))

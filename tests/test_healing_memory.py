import asyncio
from qa_agent.models import Flow, Step, RunRequest
from qa_agent.pipeline import remember_fingerprints, fingerprint_key, repair
from qa_agent.llm import LLM


class Memory:
    def __init__(self): self.values = {}
    def fingerprint(self, key, value=None):
        if value is not None: self.values[key] = value
        return self.values.get(key)


def scenario():
    return Flow(id='case', name='Workspace', risk='low', category='smoke', oracle='observed', requirement_ids=[], steps=[
        Step(action='navigate', target='https://example.com/a', value='', intent='Open'),
        Step(action='assert_text', target='#old', value='Workspace', intent='Verify heading')])


def test_successful_step_survives_later_failure_but_failed_heal_does_not():
    memory = Memory(); flow = scenario()
    fingerprint = {'selector': '#old', 'text': 'Workspace'}
    result = {'status': 'failed', 'attempt': 'validation', 'steps': [
        {'index': 1, 'status': 'passed', 'fingerprint': fingerprint}]}
    remember_fingerprints(memory, 'https://example.com/a', flow, result)
    key = fingerprint_key('https://example.com/a', flow, 1)
    assert memory.values[key] == fingerprint
    result['attempt'] = 'healed'
    result['steps'][0]['fingerprint'] = {'selector': '#unverified'}
    remember_fingerprints(memory, 'https://example.com/a', flow, result)
    assert memory.values[key] == fingerprint


def test_repair_does_not_borrow_identity_from_another_page():
    flow = scenario(); memory = Memory()
    request = RunRequest(url='https://example.com/a', mode='baseline')
    old = {'selector': '#old', 'tag': 'h1', 'type': '', 'text': 'Workspace', 'page_url': 'https://example.com/b'}
    memory.fingerprint(fingerprint_key(request.url, flow, 1), old)
    failure = {'failed_step': 1, 'failure_snapshot': {'url': request.url, 'elements': [{**old, 'selector': '#new'}]}}
    pages = [{'url': 'https://example.com/b', 'elements': [old]}]
    fixed, audit = asyncio.run(repair(memory, request, flow, failure, pages, LLM()))
    assert fixed is None and not audit['verified']

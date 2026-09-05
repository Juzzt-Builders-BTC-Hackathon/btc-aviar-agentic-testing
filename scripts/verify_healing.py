"""Offline real-browser healer verification; no external sites, credentials or model calls."""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch
from playwright.async_api import async_playwright
from qa_agent import browser as module, config
from qa_agent.models import Flow, Step, RunRequest
from qa_agent.pipeline import repair, remember_fingerprints, fingerprint_key
from qa_agent.llm import LLM
from qa_agent.runtime import launch_browser
from qa_agent.store import Store
from qa_agent.triage import triage_flow


async def main():
    base = 'https://healing-fixture.test/'
    request = RunRequest(url=base, mode='baseline')
    html = '<h1 id="old" data-testid="heading">Workspace</h1><p id="status">Ready</p>'
    flow = Flow(id='drift', name='Workspace heading', risk='medium', category='smoke', oracle='observed', requirement_ids=[], steps=[
        Step(action='navigate', target=base, value='', intent='Open workspace'),
        Step(action='assert_text', target='#old', value='Workspace', intent='Verify heading'),
        Step(action='assert_text', target='#status', value='Ready', intent='Verify readiness')])
    original_context = module.new_context

    async def fixture_context(*args, **kwargs):
        context = await original_context(*args, **kwargs)
        async def serve(route):
            await route.fulfill(content_type='text/html', body=html)
        await context.route('**/*', serve)
        return context

    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        try:
            with tempfile.TemporaryDirectory(dir=config.DATA / 'runtime') as folder, patch.object(config, 'ALLOWED', {'*'}), patch.object(module, 'new_context', fixture_context):
                store = Store(Path(folder))
                async def execute(candidate, attempt):
                    result = await module.execute_flow(browser, request, candidate, None, attempt=attempt)
                    remember_fingerprints(store, base, candidate, result)
                    return result
                async def propose(candidate, failure):
                    return await repair(store, request, candidate, failure, [], LLM())

                original = await execute(flow, 'validation')
                assert original['status'] == 'passed'
                # Snapshot prefers data-testid; actual execution used an id alias.
                assert store.fingerprint(fingerprint_key(base, flow, 1))['selector'] == '#old'
                html = '<section><h1 id="new" data-testid="new-heading">Workspace</h1></section><p id="status">Ready</p>'
                validated = await execute(flow, 'validation')
                result, audits = await triage_flow(flow, validated, execute, propose, lambda *a: None)
                assert result['classification']['label'] == 'healed_ok'
                assert audits[0]['verified']
                assert flow.steps[1].value == 'Workspace'
                assert (await execute(flow, 'reuse'))['status'] == 'passed'
                print('Locator alias fingerprint, drift repair, full replay and reuse: PASS', flush=True)

                # Changed application text must not be healed into the expected value.
                html = html.replace('Workspace', 'Unexpected content')
                wrong = await execute(flow, 'validation')
                assert wrong['failure_kind'] == 'assertion'
                result, audits = await triage_flow(flow, wrong, execute, propose, lambda *a: None)
                assert result['status'] == 'failed' and not audits
                print('Changed assertion remains failed; no repair attempted: PASS', flush=True)

                # Two indistinguishable replacement controls must not be guessed.
                html = '<h1 id="a">Workspace</h1><h1 id="b">Workspace</h1><p id="status">Ready</p>'
                missing = await execute(flow, 'validation')
                fixed, audit = await propose(flow, missing)
                assert fixed is None and not audit['verified']
                print('Ambiguous replacement rejected: PASS', flush=True)

                # No source fingerprint: never derive identity from expected text.
                unknown = flow.model_copy(deep=True)
                unknown.name = 'Unobserved generated selector'
                fixed, audit = await propose(unknown, missing)
                assert fixed is None and 'No prior fingerprint' in audit['rationale']
                print('Missing prior identity rejected: PASS', flush=True)
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())

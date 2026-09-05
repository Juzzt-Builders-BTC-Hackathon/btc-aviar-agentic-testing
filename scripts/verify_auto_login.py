"""Offline browser regression checks for automatic authentication; no real credentials."""
import asyncio
from unittest.mock import patch
from playwright.async_api import async_playwright
from qa_agent import browser as module, config
from qa_agent.authentication import LoginError, controls
from qa_agent.models import LoginCredentials
from qa_agent.runtime import launch_browser


async def main():
    base = 'https://login-fixture.test'
    credentials = LoginCredentials(username='fixture-user', password='fixture-pass')
    settings = dict.fromkeys(('username_selector', 'password_selector'), '')
    form = '''<form onsubmit="event.preventDefault();localStorage.setItem('session','fixture');location.href='/private'">
      <label>Email<input type="email" autocomplete="username"></label>
      <label>Password<input type="password"></label>
      <button type="button" aria-label="Show password">Show password</button><button>Sign in</button></form>'''
    # Use a text username because the fixture credentials are not email addresses.
    form = form.replace('type="email"', 'type="text"')
    original = module.new_context

    async def fixture_context(*args, **kwargs):
        context = await original(*args, **kwargs)
        async def serve(route):
            path = route.request.url.removeprefix(base)
            if path == '/':
                html = '<h1>Welcome</h1><a href="/login">Log in</a>'
            elif path == '/private':
                html = "<script>if(!localStorage.getItem('session'))location.href='/login'</script><h1>Private workspace</h1>"
            elif path == '/sequential':
                import json
                from html import escape
                handler = escape('document.body.innerHTML=' + json.dumps(form), quote=True)
                html = '<label>Username<input autocomplete="username"></label><button onclick="'+handler+'">Continue</button>'
            else:
                html = form
            await route.fulfill(content_type='text/html', body=html)
        await context.route('**/*', serve)
        return context

    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        try:
            with patch.object(config, 'ALLOWED', {'*'}), patch.object(module, 'new_context', fixture_context):
                for path in ('/', '/login', '/private', '/sequential'):
                    state = await module.auth_state(browser, base + path, credentials)
                    assert state['origins'][0]['localStorage'] == [{'name': 'session', 'value': 'fixture'}]
                    if path == '/login':
                        from qa_agent.models import RunRequest
                        pages = await module.crawl(browser, RunRequest(url=base + path, max_pages=1), state, lambda _: None)
                        assert pages[0]['url'] == base + '/private'
                    print(path + ': PASS')
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<nav>' + '<button>Navigation</button>' * 180 + '</nav><main><div><h1>Workspace</h1><input placeholder="Search items"></div></main>')
                observation = await module.snapshot(page)
                assert observation['elements'][0]['selector'] == 'h1'
                assert any(e['selector'] == 'input[placeholder="Search items"]' for e in observation['elements'])
                await page.evaluate("document.querySelector('main').innerHTML='<section><h1>Workspace</h1></section>'")
                assert await page.locator(observation['elements'][0]['selector']).inner_text() == 'Workspace'
                await page.set_content('<input type="text"><input type="text"><input type="password">')
                try:
                    await controls(page, settings)
                    raise AssertionError('Ambiguous username fields must fail')
                except LoginError:
                    pass
                await context.close()
                # Rejected credentials keep the login form and never create a session.
                form = form.replace("localStorage.setItem('session','fixture');location.href='/private'", "document.querySelector('h1').textContent='Invalid credentials'")
                form = '<h1>Sign in</h1>' + form
                try:
                    await module.auth_state(browser, base + '/login', credentials)
                    raise AssertionError('Rejected credentials must not be accepted')
                except LoginError as exc:
                    assert 'confirming signed-in session' in str(exc)
                    assert credentials.password.get_secret_value() not in str(exc)
                print('Ambiguous controls and rejected credentials: PASS')
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())

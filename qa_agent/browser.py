import os
import time
from urllib.parse import urlsplit
from playwright.async_api import expect
from .safety import PolicyError, origin, target_url, check_action, redact, request_block_reason

# Input values and hidden fields are deliberately excluded from the observation.
SNAPSHOT = r"""() => {
 const nodes = [...document.querySelectorAll('a,button,input,select,textarea,h1,h2,h3,[role="alert"],[data-testid],[data-test]')];
 const elements = nodes.filter(e => e.getClientRects().length).slice(0,100).map(e => {
   const attr = k => e.getAttribute(k) || '';
   const q = s => JSON.stringify(s);
   let selector = attr('data-testid') ? '[data-testid='+q(attr('data-testid'))+']' :
     attr('data-test') ? '[data-test='+q(attr('data-test'))+']' : e.id ? '#'+CSS.escape(e.id) :
     attr('name') ? e.tagName.toLowerCase()+'[name='+q(attr('name'))+']' :
     attr('aria-label') ? '[aria-label='+q(attr('aria-label'))+']' : '';
   if (!selector || document.querySelectorAll(selector).length !== 1) {
     let n=e, parts=[];
     while(n && n.tagName !== 'BODY') {
       const tag=n.tagName.toLowerCase(), siblings=[...n.parentElement.children].filter(x=>x.tagName===n.tagName);
       parts.unshift(tag+':nth-of-type('+(siblings.indexOf(n)+1)+')'); n=n.parentElement;
     }
     selector='body > '+parts.join(' > ');
   }
   return {selector, tag:e.tagName.toLowerCase(), text:(e.innerText || attr('aria-label') || attr('placeholder')).trim().slice(0,160),
     name:attr('name'), type:attr('type'), testid:attr('data-testid') || attr('data-test'), role:attr('role'), href:attr('href'),
     options:e.tagName==='SELECT'?[...e.options].slice(0,100).map(o=>({label:o.label,value:o.value})):[]};
 });
 return {url:location.href, title:document.title, text:document.body.innerText.slice(0,7000), elements,
   iframe_count:document.querySelectorAll('iframe').length, password_fields:document.querySelectorAll('input[type="password"]').length,
   links:[...document.querySelectorAll('a[href]')].map(e=>e.href).slice(0,80)};
}"""


async def snapshot(page):
    import json
    return json.loads(redact(json.dumps(await page.evaluate(SNAPSHOT))))


async def scope_ambiguous_selector(page, target, anchor):
    """Scope by an already verified sibling anchor, never by the expected result."""
    return await page.evaluate(r"""({target,anchor}) => {
      const anchors=document.querySelectorAll(anchor), matches=[...document.querySelectorAll(target)];
      if(anchors.length!==1 || matches.length<2) return null;
      for(let parent=anchors[0].parentElement; parent && parent.tagName!=='BODY'; parent=parent.parentElement) {
        const inside=matches.filter(e=>parent.contains(e));
        if(inside.length!==1) continue;
        const parts=[]; let node=inside[0];
        while(node && node.tagName!=='BODY') {
          const peers=[...node.parentElement.children].filter(e=>e.tagName===node.tagName);
          parts.unshift(node.tagName.toLowerCase()+':nth-of-type('+(peers.indexOf(node)+1)+')');
          node=node.parentElement;
        }
        return {selector:'body > '+parts.join(' > '), anchor, original_matches:matches.length};
      }
      return null;
    }""", {"target": target, "anchor": anchor})


async def new_context(browser, base, interactions=False, state=None, resource_policy="compatible", navigation_origins=()):
    kwargs = {"viewport": {"width": 1440, "height": 1000}, "service_workers": "block", "accept_downloads": False}
    if state: kwargs["storage_state"] = state
    context = await browser.new_context(**kwargs)
    context.set_default_timeout(5000)
    context.set_default_navigation_timeout(20000)
    context.qa_network_log = []
    async def route_request(route):
        request = route.request
        main_navigation = request.is_navigation_request() and request.frame.parent_frame is None
        reason = request_block_reason(base, request.url, request.method, main_navigation, interactions, resource_policy, navigation_origins)
        if reason:
            if len(context.qa_network_log) < 50:
                context.qa_network_log.append({"type": "blocked_request", "path": urlsplit(request.url).path, "reason": reason})
            return await route.abort()
        await route.continue_()
    await context.route("**/*", route_request)
    return context


async def auth_state(browser, base):
    storage = os.getenv("QA_STORAGE_STATE", "")
    auth_origin = os.getenv("TARGET_AUTH_ORIGIN", "")
    if auth_origin != origin(base): return None
    if storage: return storage
    if not os.getenv("TARGET_USERNAME") or not os.getenv("TARGET_PASSWORD"): return None
    context = await new_context(browser, base, interactions=True)
    try:
        page = await context.new_page()
        await page.goto(target_url(base, os.getenv("TARGET_LOGIN_PATH", "/")), wait_until="domcontentloaded")
        await page.locator(os.getenv("TARGET_USERNAME_SELECTOR", '[data-test="username"]')).fill(os.environ["TARGET_USERNAME"])
        await page.locator(os.getenv("TARGET_PASSWORD_SELECTOR", '[data-test="password"]')).fill(os.environ["TARGET_PASSWORD"])
        await page.locator(os.getenv("TARGET_SUBMIT_SELECTOR", '[data-test="login-button"]')).click()
        await expect(page.locator(os.getenv("TARGET_SUCCESS_SELECTOR", '[data-test="inventory-container"]'))).to_be_visible(timeout=15000)
        return await context.storage_state()
    finally: await context.close()


async def crawl(browser, request, state, event):
    import re
    from .evolution import canonical_url
    context = await new_context(browser, request.url, state=state, resource_policy=request.resource_policy, navigation_origins=request.navigation_origins)
    seeds = re.findall(r'https?://[^\s)<>]+', request.prd_content + '\n' + request.requirements)
    pages, queue, seen = [], list(dict.fromkeys([request.url] + seeds)), set()
    failures = []
    try:
        page = await context.new_page()
        while queue and len(pages) < request.max_pages:
            url = queue.pop(0).split("#")[0]
            if canonical_url(url) in seen: continue
            seen.add(canonical_url(url))
            try:
                target_url(request.url, url, request.navigation_origins)
                context.qa_network_log.clear()
                response = await page.goto(url, wait_until="domcontentloaded")
                await page.locator("body").wait_for()
                try: await page.wait_for_load_state("load", timeout=5000)
                except Exception: pass
                await page.wait_for_timeout(800)
                data = await snapshot(page)
                final_url = canonical_url(data['url'].split('#')[0])
                seen.add(final_url)
                if any(canonical_url(p['url'].split('#')[0]) == final_url for p in pages):
                    continue
                data["http_status"] = response.status if response else None
                data["network_warnings"] = list(context.qa_network_log)
                data["limitations"] = []
                if data["password_fields"] and not state: data["limitations"].append("Login form detected; configure an authenticated session for protected content.")
                if data["iframe_count"]: data["limitations"].append("Embedded frames detected; this version plans and asserts against the main document only.")
                pages.append(data)
                event(f"Observed {data['title'] or 'untitled page'} ({len(data['elements'])} visible elements)")
                for link in data["links"]:
                    try:
                        candidate = target_url(request.url, link, request.navigation_origins).split("#")[0]
                        if canonical_url(candidate) not in seen and candidate not in queue: queue.append(candidate)
                    except ValueError: pass
            except Exception as exc:
                failure = f"{type(exc).__name__}: {redact(str(exc))[:600]}"
                failures.append(failure)
                event(f"Page could not be explored: {failure}")
        if not pages: raise ValueError("No pages could be explored. " + (failures[-1] if failures else "Check the URL and connectivity."))
        if failures: pages[0]["crawl_failures"] = failures
        return pages
    finally: await context.close()


async def execute_flow(browser, request, flow, state, folder=None, attempt="run"):
    context = await new_context(browser, request.url, request.allow_interactions, state, request.resource_policy, request.navigation_origins)
    page = await context.new_page()
    diagnostics = []
    page.on("pageerror", lambda error: diagnostics.append({"type": "page_error", "message": redact(str(error))[:500]}) if len(diagnostics) < 30 else None)
    page.on("response", lambda response: diagnostics.append({"type": "http_error", "status": response.status, "path": urlsplit(response.url).path}) if response.status >= 400 and len(diagnostics) < 30 else None)
    started = time.monotonic()
    result = {"flow_id": flow.id, "name": flow.name, "risk": flow.risk, "oracle": flow.oracle, "status": "passed", "steps": [], "diagnostics": diagnostics, "attempt": attempt}
    index = 0
    try:
        for index, step in enumerate(flow.steps):
            check_action(step, request.allow_interactions)
            if step.action == "navigate":
                response = await page.goto(target_url(request.url, step.target, request.navigation_origins), wait_until="domcontentloaded")
                # A SPA can render its intended state after an HTTP error response.
                # HTTP errors remain separate diagnostics; evaluate the declared UI oracle.
            elif step.action == "assert_url":
                if not step.value: raise ValueError("URL assertion must have an expected value")
                import re
                await expect(page).to_have_url(re.compile(re.escape(step.value)))
            else:
                locator = page.locator(step.target)
                await expect(locator).to_have_count(1)
                await expect(locator).to_be_visible()
                before = await snapshot(page)
                fingerprint = next((e for e in before["elements"] if e["selector"] == step.target), None)
                if step.action == "fill":
                    if await locator.get_attribute("type") == "password": raise PolicyError("Use the configured authenticated session for passwords")
                    await locator.fill(step.value)
                elif step.action == "select_option":
                    options = await locator.locator('option').evaluate_all('(nodes) => nodes.map(n => ({value:n.value,label:n.label}))')
                    if any(o['value'] == step.value for o in options):
                        await locator.select_option(value=step.value)
                    else:
                        await locator.select_option(label=step.value)
                elif step.action == "assert_invalid":
                    valid = await locator.evaluate('(e) => e.validity ? e.validity.valid : null')
                    if valid is None: raise ValueError('assert_invalid requires a form input or select')
                    if valid: raise AssertionError('Expected native form validity to be invalid')
                elif step.action == "click":
                    check_action(step, request.allow_interactions, await locator.inner_text())
                    await locator.click()
                elif step.action == "assert_text":
                    if not step.value.strip(): raise ValueError("Text assertion must have a nonempty expected value")
                    await expect(locator).to_contain_text(step.value, use_inner_text=True)
                result["steps"].append({"index": index, "action": step.action, "target": step.target, "status": "passed", "fingerprint": fingerprint})
                continue
            result["steps"].append({"index": index, "action": step.action, "status": "passed"})
    except Exception as exc:
        action = flow.steps[index].action
        missing = False
        try:
            if action not in {"navigate", "assert_url"}: missing = await page.locator(flow.steps[index].target).count() != 1
        except Exception: pass
        result.update(status="blocked" if isinstance(exc, PolicyError) else "failed", failed_step=index,
            failure_kind="policy" if isinstance(exc, PolicyError) else "selector" if missing else "assertion" if isinstance(exc, AssertionError) else "execution",
            error=redact(str(exc))[:1800])
        try: result["failure_snapshot"] = await snapshot(page)
        except Exception: pass
        if missing and index > 0 and flow.steps[index-1].action == "assert_text":
            try:
                result["scoped_regeneration"] = await scope_ambiguous_selector(page, flow.steps[index].target, flow.steps[index-1].target)
            except Exception: pass
    finally:
        diagnostics.extend(context.qa_network_log[:max(0, 50-len(diagnostics))])
        result["duration_ms"] = round((time.monotonic() - started) * 1000)
        if folder:
            filename = f"{flow.id}-{attempt}.png"
            try:
                await page.screenshot(path=str(folder / filename), full_page=True, mask=[page.locator('input,textarea')], timeout=5000)
                result["screenshot"] = filename
            except Exception: pass
        await context.close()
    return result

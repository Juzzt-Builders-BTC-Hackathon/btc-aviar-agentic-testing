"""Bounded, deterministic discovery of ordinary website sign-in forms."""
import asyncio
import re
from playwright.async_api import expect
from .safety import origin, target_url


class LoginError(ValueError):
    pass


class AuthenticatedState(dict):
    """Playwright storage state with ephemeral navigation metadata."""
    def __init__(self, state, login_url, landing_url):
        super().__init__(state)
        self.login_url = login_url
        self.landing_url = landing_url


async def unique_visible(locators):
    for locator in locators:
        visible = locator.filter(visible=True)
        count = await visible.count()
        if count == 1:
            return visible
        if count > 1:
            raise LoginError("Multiple matching login controls found; the sign-in form is ambiguous.")
    return None


async def controls(page, settings):
    password = await unique_visible([page.locator(settings['password_selector'] or 'input[type="password"]')])
    scope = page
    if password:
        form = password.locator('xpath=ancestor::form')
        if await form.count() == 1:
            scope = form
    username = await unique_visible([scope.locator(settings['username_selector'])] if settings['username_selector'] else [
        scope.locator('input[autocomplete="username"],input[autocomplete="email"],input[type="email"]'),
        scope.get_by_label(re.compile(r'username|user name|email|e-mail|user id', re.I)),
        scope.locator('input[name*="user" i],input[id*="user" i],input[name*="email" i],input[id*="email" i]'),
        scope.locator('input[type="text"],input:not([type])') if password else scope.locator('input[autocomplete="username"]'),
    ])
    return username, password, scope


async def submit(scope, override):
    button = await unique_visible([scope.locator(override)] if override else [
        scope.get_by_role('button', name=re.compile(r'^\s*(sign\s*in|log\s*in|login|logon|continue|next)\s*$', re.I)),
        scope.locator('button[type="submit"],input[type="submit"]'),
    ])
    if not button:
        raise LoginError("Could not identify a unique sign-in button.")
    await button.click()


async def sign_in(page, base, username, password, settings):
    stage = 'opening login page'
    try:
        await page.goto(target_url(base, settings['login_path'] or base), wait_until='domcontentloaded')
        stage = 'finding login form'
        user_control = password_control = None
        # Allow client rendering and follow a visible same-origin sign-in entry.
        followed = False
        async with asyncio.timeout(20):
            while True:
                if origin(page.url) != origin(base):
                    raise LoginError("Login redirected to an external identity provider; use an authenticated storage state.")
                user_control, password_control, scope = await controls(page, settings)
                if user_control or password_control:
                    break
                if not followed:
                    entry = await unique_visible([
                        page.get_by_role('link', name=re.compile(r'^\s*(sign\s*in|log\s*in|login)\s*$', re.I)),
                        page.get_by_role('button', name=re.compile(r'^\s*(sign\s*in|log\s*in|login)\s*$', re.I)),
                    ])
                    if entry:
                        href = await entry.get_attribute('href')
                        if href:
                            target_url(base, href)
                        await entry.click()
                        followed = True
                await asyncio.sleep(.2)
        if not user_control:
            raise LoginError("Could not identify the username or email field.")
        stage = 'entering username'
        await user_control.fill(username)
        if not password_control:
            await submit(scope, settings['submit_selector'])
            stage = 'finding password field'
            async with asyncio.timeout(15):
                while not password_control:
                    if origin(page.url) != origin(base):
                        raise LoginError("External identity provider requires an authenticated storage state.")
                    _, password_control, scope = await controls(page, settings)
                    await asyncio.sleep(.2)
        stage = 'submitting credentials'
        if origin(page.url) != origin(base):
            raise LoginError("Credentials cannot be entered outside the application origin.")
        await password_control.fill(password)
        login_url = page.url
        before = await page.context.storage_state()
        await submit(scope, settings['submit_selector'])
        stage = 'confirming signed-in session'
        if settings['success_selector']:
            await expect(page.locator(settings['success_selector'])).to_be_visible(timeout=20000)
        else:
            # A redirect or disappearing form alone is not evidence of authentication.
            stable = 0
            async with asyncio.timeout(25):
                while stable < 4:
                    if origin(page.url) != origin(base):
                        raise LoginError("External identity provider requires an authenticated storage state.")
                    changed = await page.context.storage_state() != before
                    form_gone = await page.locator('input[type="password"]:visible').count() == 0
                    content = bool((await page.locator('body').inner_text()).strip())
                    stable = stable + 1 if changed and form_gone and content else 0
                    await asyncio.sleep(.4)
        return login_url, page.url
    except LoginError:
        raise
    except Exception as exc:
        # Playwright call logs can include filled secrets: never surface their text.
        raise LoginError(f"Website login failed while {stage} ({type(exc).__name__}). "
                         "Check credentials and whether the page requires MFA or CAPTCHA. "
                         "Automatic detection could not confirm sign-in.") from None

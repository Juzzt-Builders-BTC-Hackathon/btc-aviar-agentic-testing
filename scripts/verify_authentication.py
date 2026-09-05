"""Verify configured login and per-run credentials without printing secrets."""
import asyncio
import os
import sys

from playwright.async_api import async_playwright, expect

from qa_agent import config
from qa_agent.browser import auth_state, new_context
from qa_agent.models import LoginCredentials
from qa_agent.runtime import launch_browser


async def main():
    base = os.environ["TARGET_AUTH_ORIGIN"]
    credentials = LoginCredentials(
        username=os.environ["TARGET_USERNAME"], password=os.environ["TARGET_PASSWORD"],
        **{field: os.environ[env] for field, env in (
            ("login_path", "TARGET_LOGIN_PATH"), ("username_selector", "TARGET_USERNAME_SELECTOR"),
            ("password_selector", "TARGET_PASSWORD_SELECTOR"), ("submit_selector", "TARGET_SUBMIT_SELECTOR"),
            ("success_selector", "TARGET_SUCCESS_SELECTOR")) if os.getenv(env)},
    )
    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        try:
            if "--dashboard" in sys.argv:
                page = await browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(type(error).__name__))
                await page.goto(config.DEMO_ORIGIN)
                await expect(page.locator("#connection-label")).to_have_text("Connected")
                await page.locator("#new-run").click()
                await page.locator("#target-url").fill(base + "/inventory.html")
                await page.locator("#run-mode").select_option("baseline")
                await page.locator("#advanced-options > summary").click()
                await page.locator("#use-login").check()
                await page.locator("#login-username").fill(credentials.username.get_secret_value())
                await page.locator("#login-password").fill(credentials.password.get_secret_value())
                for field in ("login_path", "username_selector", "password_selector", "submit_selector", "success_selector"):
                    await page.locator("#" + field.replace("_", "-")).fill(getattr(credentials, field))
                await page.locator("#max-pages").fill("1")
                await page.locator("#max-flows").fill("1")
                async with page.expect_response(lambda response: response.url.endswith("/api/runs") and response.request.method == "POST") as pending:
                    await page.locator("#launch-run").click()
                response = await pending.value
                assert response.status == 202, "Dashboard run was not accepted"
                run = await response.json()
                await expect(page.locator("#run-dialog")).not_to_be_visible()
                assert await page.locator("#login-password").input_value() == ""
                for _ in range(120):
                    detail = await page.request.get(config.DEMO_ORIGIN + "/api/runs/" + run["id"])
                    run = await detail.json()
                    if run["status"] not in {"queued", "running"}: break
                    await asyncio.sleep(1)
                assert run["status"] == "completed", "Dashboard test run did not complete"
                assert run["summary"].get("passed", 0) > 0, "No passing protected-page test"
                assert "authentication" not in run["request"]
                assert not errors, "Dashboard JavaScript errors"
                print("Dashboard credential submission and protected-page baseline: PASS", flush=True)
                return
            for label, login in (("Existing .env login", None), ("Per-run login", credentials)):
                state = await auth_state(browser, base, login)
                assert state, "No authenticated session returned"
                context = await new_context(browser, base, state=state)
                try:
                    page = await context.new_page()
                    # The configured project target is SauceDemo's protected inventory.
                    await page.goto(base + "/inventory.html")
                    await expect(page.locator(credentials.success_selector)).to_be_visible()
                    print(label + ": PASS (protected page accessible in a fresh context)", flush=True)
                finally:
                    await context.close()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

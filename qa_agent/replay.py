import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from .models import RunRequest, Plan
from .browser import auth_state, execute_flow
from .safety import validate_url
from .runtime import launch_browser


async def replay(path):
    suite = json.loads(path.read_text(encoding="utf-8"))
    request = RunRequest.model_validate(suite["request"])
    plan = Plan.model_validate(suite["plan"])
    validate_url(request.url)
    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        try:
            state = await auth_state(browser, request.url)
            results = [await execute_flow(browser, request, f, state) for f in plan.flows]
        finally: await browser.close()
    print(json.dumps(results, indent=2))
    return 0 if all(r["status"] == "passed" for r in results) else 1


def main(path=None):
    raise SystemExit(asyncio.run(replay(Path(path or sys.argv[1]))))


if __name__ == "__main__": main()

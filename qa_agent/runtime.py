"""Browser launch configuration and real startup readiness checks."""
import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright
from . import config
from .safety import redact


def error_details(exc, stage):
    from .authentication import LoginError
    message = redact(str(exc))[:1500]
    if isinstance(exc, LoginError):
        code = "AUTHENTICATION_FAILED"
        remedy = "Confirm the website credentials. For MFA, CAPTCHA or external identity providers, configure QA_STORAGE_STATE for this origin."
    elif isinstance(exc, PermissionError) or "WinError 5" in message or "Access is denied" in message:
        code = "ACCESS_DENIED"
        remedy = ("Start the app from a normal local terminal using start.ps1; restricted agent sandboxes may block browser subprocess pipes. "
            "Confirm your account can write QA_DATA_DIR and QA_BROWSER_TEMP_DIR and execute the Playwright driver/browser. "
            "If endpoint protection blocks them, ask your IT administrator to approve the project executables. Restart after resolving access.")
    elif "Executable doesn't exist" in message:
        code = "BROWSER_MISSING"
        remedy = "Run ./.venv/Scripts/python.exe -m playwright install chromium, then restart."
    else:
        code = "RUNTIME_ERROR"
        remedy = "Inspect the recorded stage and error. Check the configured browser channel, writable data path, and Python environment."
    return {"code": code, "stage": stage, "message": message, "remedy": remedy}


async def launch_browser(pw):
    temp = Path(os.getenv("QA_BROWSER_TEMP_DIR") or str(config.DATA / "runtime" / "browser-temp")).resolve()
    temp.mkdir(parents=True, exist_ok=True)
    options = {"headless": True, "env": {**os.environ, "TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp)}}
    channel = os.getenv("QA_BROWSER_CHANNEL") or "chromium"
    if channel not in {"chromium", "chrome", "msedge"}: raise ValueError("QA_BROWSER_CHANNEL must be chromium, chrome or msedge")
    if channel != "chromium": options["channel"] = channel
    return await pw.chromium.launch(**options)


async def preflight():
    result = {"ready": False, "checked_at": datetime.now(timezone.utc).isoformat(), "checks": [], "errors": []}
    stage = "filesystem"
    try:
        config.DATA.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=config.DATA) as probe:
            probe.write(b"aviar-readiness"); probe.flush(); probe.seek(0)
            if probe.read() != b"aviar-readiness": raise OSError("Data write/read probe failed")
        result["checks"].append("Data directory write/read")
        stage = "playwright_driver"
        async with asyncio.timeout(35):
            async with async_playwright() as pw:
                stage = "browser_launch"
                browser = await launch_browser(pw)
                try:
                    page = await browser.new_page()
                    await page.set_content('<h1>Aviar readiness</h1>')
                    if await page.locator('h1').inner_text() != "Aviar readiness": raise RuntimeError("Browser DOM probe failed")
                    result["checks"].append("Browser launch and DOM access")
                finally: await browser.close()
        result["ready"] = True
    except Exception as exc:
        result["errors"].append(error_details(exc, stage))
    return result

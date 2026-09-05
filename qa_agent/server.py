import asyncio
import hmac
import io
import os
import secrets
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import config
from .models import RunRequest
from .pipeline_selector import run_pipeline
from .safety import validate_url, redact
from .store import Store
from .runtime import preflight, error_details
from .reporting import export_readme

store = Store(config.DATA)
tasks = {}
session_token = secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app):
    store.recover()
    app.state.runtime = await preflight()
    yield
    for task in tasks.values(): task.cancel()
    if tasks: await asyncio.gather(*tasks.values(), return_exceptions=True)


app = FastAPI(title="AIVAR Autonomous Test Orchestration Agent", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_session(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        if not hmac.compare_digest(request.cookies.get("qa_session", ""), session_token):
            return JSONResponse({"detail": "Open the dashboard to establish a local session"}, status_code=401)
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if origin and origin not in {config.DEMO_ORIGIN, f"http://localhost:{config.PORT}"}:
                return JSONResponse({"detail": "Cross-origin request denied"}, status_code=403)
            if len(await request.body()) > 450000:
                return JSONResponse({"detail": "Request exceeds 450 KB"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.get("/")
async def index():
    response = FileResponse(config.ROOT / "ui" / "index.html")
    response.set_cookie("qa_session", session_token, httponly=True, samesite="strict")
    return response


@app.get("/api/health")
async def health(): return {"status": "ok", "version": "0.1.0"}


@app.get("/api/readiness")
async def readiness():
    result = getattr(app.state, "runtime", {"ready": False, "errors": [], "checks": []})
    return JSONResponse(result, status_code=200 if result["ready"] else 503)


@app.get("/api/config")
async def settings():
    return {"openai_configured": bool(os.getenv("OPENAI_API_KEY")), "model": config.MODEL,
        "pipeline_version": config.PIPELINE_VERSION,
        "allowed_origins": sorted(config.ALLOWED), "allow_all_origins": "*" in config.ALLOWED, "demo_url": config.DEMO_ORIGIN + "/demo/",
        "auth_configured": bool(os.getenv("TARGET_PASSWORD") or os.getenv("QA_STORAGE_STATE")),
        "auth_origin": os.getenv("TARGET_AUTH_ORIGIN", ""), "max_active_runs": 1,
        "runtime": getattr(app.state, "runtime", {"ready": False, "checks": [], "errors": []})}


@app.get("/api/runs")
async def runs():
    rows = store.list()
    for row in rows:
        # Documents belong in detail responses, not every two-second history poll.
        row["request"].pop("prd_content", None)
        row["request"].pop("requirements", None)
    return rows


def find_run(rid):
    run = store.get(rid)
    if not run: raise HTTPException(404, "Run not found")
    return run


@app.post("/api/runs", status_code=202)
async def create_run(request: RunRequest):
    runtime = getattr(app.state, "runtime", None)
    if runtime and not runtime["ready"]:
        error = runtime["errors"][0]
        raise HTTPException(503, f"{error['code']} at {error['stage']}: {error['message']} {error['remedy']}")
    try: validate_url(request.url)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    if request.mode == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(422, "Set OPENAI_API_KEY in .env and restart, or choose the deterministic baseline.")
    if any(not task.done() for task in tasks.values()):
        raise HTTPException(409, "A run is already active. Wait or cancel it first.")
    # Never persist configured secrets even if accidentally pasted into scope.
    request.scope = redact(request.scope)
    request.requirements = redact(request.requirements)
    request.prd_content = redact(request.prd_content)
    request.prd_name = redact(request.prd_name)
    try:
        rid = store.create(request.model_dump())
    except OSError as exc:
        diagnostic = error_details(exc, "run_directory")
        raise HTTPException(503, f"{diagnostic['code']}: {diagnostic['message']} {diagnostic['remedy']}") from exc
    task = asyncio.create_task(run_pipeline(store, rid))
    tasks[rid] = task
    task.add_done_callback(lambda done: tasks.pop(rid, None))
    return store.get(rid)


@app.get("/api/runs/{rid}")
async def detail(rid: str):
    run = find_run(rid)
    run.update(events=store.events(rid), plan=store.read(rid, "plan.json"),
        results=store.read(rid, "run_results.json", []), gaps=store.read(rid, "coverage_gaps.json", []),
        heals=store.read(rid, "heal_log.json", []), traceability=store.read(rid, "traceability.json", []),
        validation=store.read(rid, "validation_report.json", []),
        defects=store.read(rid, "defect_report.json", []), evolution=store.read(rid, "suite_evolution.json", {}))
    run["artifacts"] = sorted(p.name for p in (store.root / rid).iterdir() if p.is_file() and not p.name.endswith(".tmp"))
    return run


@app.post("/api/runs/{rid}/cancel")
async def cancel(rid: str):
    run = find_run(rid)
    task = tasks.get(rid)
    if not task or task.done(): raise HTTPException(409, "Run is no longer active")
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    if store.get(rid)["status"] == "queued": store.update(rid, status="cancelled")
    return store.get(rid)


@app.get("/api/runs/{rid}/artifacts/{name}")
async def artifact(rid: str, name: str):
    find_run(rid)
    path = store.root / rid / name
    if Path(name).name != name or name.endswith(".tmp") or not path.is_file(): raise HTTPException(404, "Artifact not found")
    if path.suffix == ".png": return FileResponse(path, media_type="image/png")
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@app.get("/api/runs/{rid}/export")
async def export(rid: str):
    run = find_run(rid)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (store.root / rid).iterdir():
            if path.is_file() and not path.name.endswith(".tmp"): archive.write(path, path.name)
        import json
        archive.writestr("decision_log.json", json.dumps(store.events(rid), indent=2))
        archive.writestr("START_HERE.md", export_readme(run))
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="qa-run-{rid[:8]}.zip"'})


app.mount("/assets", StaticFiles(directory=config.ROOT / "ui"), name="assets")
app.mount("/demo", StaticFiles(directory=config.ROOT / "demo", html=True), name="demo")

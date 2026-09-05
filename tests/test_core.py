import asyncio
import json
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from qa_agent import config
from qa_agent.models import Flow, Plan, RunRequest, Step
from qa_agent.safety import PolicyError, check_action, target_url, validate_url, redact
from qa_agent.healing import deterministic_candidate, classify
from qa_agent.planning import coverage, requirements_list, ground_oracles
from qa_agent.store import Store
from qa_agent.reporting import reports


def flow():
    return Flow(id="test", name="Test", risk="high", category="happy_path", requirement_ids=["REQ-1"], oracle="requirement", steps=[
        Step(action="navigate", target=config.DEMO_ORIGIN+"/demo/", value="", intent="Open"),
        Step(action="assert_text", target="h1", value="Expected", intent="Check requirement")])


def test_contract_rejects_executable_code_and_assertion_free_flows():
    with pytest.raises(ValidationError): Step(action="eval", target="", value="", intent="Execute code")
    data=flow().model_dump(); data["steps"][1]["action"]="click"
    with pytest.raises(ValidationError): Flow.model_validate(data)
    with pytest.raises(ValidationError): Plan(summary="", flows=[flow(),flow()], gaps=[])


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@www.saucedemo.com", "http://169.254.169.254/latest/meta-data", "http://127.0.0.1:8765/api/config"])
def test_target_boundary(url,monkeypatch):
    monkeypatch.setattr(config,"ALLOWED",{config.DEMO_ORIGIN})
    with pytest.raises(PolicyError): validate_url(url)


def test_wildcard_accepts_arbitrary_targets_and_preserves_run_boundary(monkeypatch):
    monkeypatch.setattr(config,"ALLOWED",{"*"})
    for url in ("https://example.com/app", "http://localhost:4321/", "http://192.168.1.20:8080/test"):
        assert validate_url(url)==url
    with pytest.raises(PolicyError): validate_url("file:///tmp/test")
    with pytest.raises(PolicyError): validate_url("https://user:pass@example.com")
    with pytest.raises(PolicyError): validate_url(config.DEMO_ORIGIN+"/api/config")
    with pytest.raises(PolicyError): target_url("https://example.com/", "https://elsewhere.example/")


def test_explicit_allowlist_still_restricts_targets(monkeypatch):
    monkeypatch.setattr(config,"ALLOWED",{"https://example.com"})
    assert validate_url("https://example.com/test")
    with pytest.raises(PolicyError): validate_url("https://elsewhere.example/test")


def test_redirect_and_action_boundaries():
    base=config.DEMO_ORIGIN+"/demo/"
    with pytest.raises(PolicyError): target_url(base,"https://example.com")
    with pytest.raises(PolicyError): target_url(base,"/demo/delete-account")
    click=Step(action="click",target="button",value="",intent="Proceed")
    with pytest.raises(PolicyError): check_action(click,False)
    with pytest.raises(PolicyError): check_action(click,True,"Finish order")
    check_action(click,True,"Add to cart")


def test_secrets_redacted(monkeypatch):
    monkeypatch.setenv("TARGET_PASSWORD","private-value")
    assert "private-value" not in redact("error private-value")


def test_healing_requires_unique_identity_and_does_not_change_semantics():
    old={"tag":"button","type":"button","text":"Add to cart","name":"","testid":"old-id","role":""}
    new={**old,"testid":"new-id","selector":"#new"}
    match=deterministic_candidate(old,[new])
    assert match["candidate"]["selector"] == "#new"
    old["testid"]="";new["testid"]=""
    assert deterministic_candidate(old,[new])["candidate"]["selector"]=="#new"
    assert deterministic_candidate(old,[new,new]) is None
    assert deterministic_candidate(old,[{**new,"text":"Delete item"}]) is None


def test_classifier_does_not_call_inferred_expectation_a_defect():
    fail={"status":"failed","failure_kind":"assertion","failed_step":2,"oracle":"inferred"}
    assert classify(fail,fail)["label"]=="needs_review"
    fail["oracle"]="requirement"
    assert classify(fail,fail)["label"]=="likely_defect"
    assert classify(fail,{"status":"passed"})["label"]=="flaky_test"
    assert classify(fail,healed=True)["label"]=="healed_ok"


def test_unquoted_or_changed_requirement_literal_is_not_a_verified_oracle():
    plan=Plan(summary="",flows=[flow()],gaps=[])
    notes=ground_oracles(plan,[{"id":"REQ-1","text":"Show Expected."}])
    assert notes and plan.flows[0].oracle=="inferred"
    plan.flows[0].oracle="requirement"
    assert ground_oracles(plan,[{"id":"REQ-1","text":'Show "Expected".'}])==[]
    plan.flows[0].steps[-1].value="Expected."
    assert ground_oracles(plan,[{"id":"REQ-1","text":'Show "Expected".'}])


def test_coverage_and_traceability_are_explicit(tmp_path):
    plan=Plan(summary="<script>bad</script>",flows=[flow()],gaps=[])
    reqs=requirements_list("Expected\nAnother rule")
    gaps=coverage(plan,[],reqs)
    assert any("REQ-2" in g for g in gaps)
    store=Store(tmp_path);request=RunRequest(url=config.DEMO_ORIGIN+"/demo/")
    rid=store.create(request.model_dump())
    result={"flow_id":"test","name":"Test","risk":"high","oracle":"requirement","status":"blocked","classification":{"label":"blocked"}}
    summary=reports(store,rid,request,plan,[result],gaps,[],reqs,{})
    assert summary["pass_rate"]==0 and summary["blocked"]==1
    assert "<script>" not in (tmp_path/rid/"report.html").read_text()
    assert store.read(rid,"traceability.json")[0]["passing_flows"]==[]


def test_recovery_and_artifact_roundtrip(tmp_path):
    store=Store(tmp_path);rid=store.create({"url":"target"});store.update(rid,status="running")
    store.event(rid,"plan","Planning")
    store.artifact(rid,"plan.json",{"value":1})
    Store(tmp_path).recover()
    assert store.get(rid)["status"]=="interrupted"
    assert store.events(rid)[0]["message"]=="Planning"
    assert store.read(rid,"plan.json")=={"value":1}


def test_api_local_session_and_request_validation(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from qa_agent import server
    monkeypatch.setattr(server,"store",Store(tmp_path))
    with TestClient(server.app) as client:
        assert client.get('/api/runs').status_code==401
        assert client.get('/').status_code==200
        assert client.get('/api/runs').json()==[]
        assert client.post('/api/runs',headers={"origin":"https://attacker.example"},json={"url":config.DEMO_ORIGIN+"/demo/"}).status_code==403
        assert client.post('/api/runs',json={"url":"file:///tmp/test"}).status_code==422
        assert client.post('/api/runs',json={"url":config.DEMO_ORIGIN+"/demo/","max_pages":100}).status_code==422
        assert client.get('/api/runs/missing').status_code==404
        assert client.get('/api/config').json().get('api_key') is None


def test_openai_schema_parsing_and_usage(monkeypatch):
    from types import SimpleNamespace
    from qa_agent import llm
    monkeypatch.setenv("OPENAI_API_KEY","unit-test-key")
    parsed=Plan(summary="Test",flows=[flow()],gaps=[])
    response=SimpleNamespace(status="completed",output_parsed=parsed,usage=SimpleNamespace(input_tokens=42,output_tokens=20))
    parse=AsyncMock(return_value=response)
    client=AsyncMock();client.__aenter__.return_value=SimpleNamespace(responses=SimpleNamespace(parse=parse))
    monkeypatch.setattr(llm,"AsyncOpenAI",lambda **kwargs:client)
    model=llm.LLM()
    assert asyncio.run(model.ask(Plan,"system",{}))==parsed
    assert parse.call_args.kwargs["store"] is False
    assert model.usage()["input_tokens"]==42
    response.output_parsed=None
    with pytest.raises(ValueError,match="refusal"):asyncio.run(model.ask(Plan,"system",{}))

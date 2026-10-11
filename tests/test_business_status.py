import json
import secrets
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from quest_rag.applications import business_status, service, store
from quest_rag.api import applications
from quest_rag.auth.dependencies import get_current_user
from quest_rag.rag import tools

CASE = {"id": "1a58a6c0-82c5-4659-953c-a9d1c0ebcdec", "user_id": 7, "business_code": "employment_registration"}


@pytest.fixture
def linked(monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setattr(store, "get_case", lambda user_id, case_id: CASE if user_id == 7 and case_id == CASE["id"] else None)
    monkeypatch.setattr(store, "get_business_link", lambda _: {"query_token": token})
    return token


def http_result(monkeypatch, data, status=200):
    original = httpx.Client
    def handler(request):
        assert request.url.path == '/business/api/case-status'
        return httpx.Response(status, json=data)
    monkeypatch.setattr(business_status.httpx, 'Client', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("status,label", [("PENDING", "待审批"), ("APPROVED", "已通过"), ("REJECTED", "已驳回")])
def test_actual_tool_returns_live_status_without_capabilities(monkeypatch, linked, status, label):
    http_result(monkeypatch, {"case_id":CASE['id'], "business":"employment-registration", "status":status,
        "number":"MOCK-TEST", "business_name":"就业登记", "created_at":"2026-10-11T00:00:00Z", "reviewed_at":"2026-10-11T01:00:00Z", "comment":"核对意见"})
    monkeypatch.setattr(tools, 'assert_tool_permission', lambda *_: None)
    context = tools.current_user_ctx.set(SimpleNamespace(id=7))
    try:
        output = tools.get_application_status.invoke({'case_id':CASE['id']})
    finally:
        tools.current_user_ctx.reset(context)
    result = json.loads(output)
    assert result['status_label'] == label and result['review_comment'] == '核对意见'
    assert result['source'] == '独立模拟业务系统'
    assert linked not in output and 'query_token' not in output


def test_foreign_case_denied_before_network_or_link_lookup(monkeypatch, linked):
    monkeypatch.setattr(store, 'get_business_link', lambda _: pytest.fail('must not read foreign capability'))
    with pytest.raises(HTTPException) as exc:
        service.agent_application_summary(SimpleNamespace(id=8), CASE['id'])
    assert exc.value.status_code == 404


def test_no_link_does_not_infer_unsubmitted(monkeypatch, linked):
    monkeypatch.setattr(store, 'get_business_link', lambda _: None)
    result = json.loads(service.agent_application_summary(SimpleNamespace(id=7), CASE['id']))
    assert result['status'] == 'NO_LINKED_RECEIPT'
    assert '旧申请' in result['message']


@pytest.mark.parametrize('status,data,expected', [(404,{},'NO_LINKED_RECEIPT'),(503,{'detail':'secret upstream'},'UNAVAILABLE'),(200,[], 'UNAVAILABLE'),(200,{'case_id':'foreign'},'UNAVAILABLE')])
def test_unavailable_or_unmatched_receipts_never_return_old_status(monkeypatch, linked, status, data, expected):
    http_result(monkeypatch, data, status)
    output = service.agent_application_summary(SimpleNamespace(id=7), CASE['id'])
    assert json.loads(output)['status'] == expected
    assert 'secret upstream' not in output and linked not in output


def test_timeout_is_an_explicit_unconfirmed_result(monkeypatch, linked):
    original = httpx.Client
    def fail(request):
        raise httpx.ReadTimeout('contains secret', request=request)
    monkeypatch.setattr(business_status.httpx, 'Client', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(fail)))
    output = service.agent_application_summary(SimpleNamespace(id=7), CASE['id'])
    assert json.loads(output)['status'] == 'UNAVAILABLE' and 'secret' not in output


def test_link_endpoint_enforces_auth_permission_ownership_and_no_cache(monkeypatch, linked):
    http_result(monkeypatch, {}, 404)
    app = FastAPI()
    app.include_router(applications.router)
    monkeypatch.setattr(store, 'ensure_business_link', lambda _: {'case_id': CASE['id'], 'query_token': linked})
    with TestClient(app) as client:
        assert client.post('/applications/cases/business-link', json={'case_id':CASE['id']}).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, permissions=[])
        assert client.post('/applications/cases/business-link', json={'case_id':CASE['id']}).status_code == 403
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=8, permissions=['application.case.read_self'])
        assert client.post('/applications/cases/business-link', json={'case_id':CASE['id']}).status_code == 404
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, permissions=['application.case.read_self'])
        response = client.post('/applications/cases/business-link', json={'case_id':CASE['id']})
        assert response.status_code == 200 and response.json()['token'] == linked
        assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('status', ['PENDING', 'APPROVED', 'REJECTED'])
def test_form_tool_uses_received_materials_instead_of_stale_draft(monkeypatch, linked, status):
    material = {'key':'employment_proof', 'name':'contract.pdf', 'size_bytes':1234,
                'status':'received', 'received_at':'2026-10-11T00:00:00Z', 'query_token':'must-not-leak'}
    http_result(monkeypatch, {"case_id":CASE['id'], "business":"employment-registration", "status":status,
        "number":"MOCK-TEST", "business_name":"就业登记", "created_at":"2026-10-11T00:00:00Z", 'materials':[material]})
    monkeypatch.setattr(tools, 'get_application_detail', lambda *_: {**CASE, 'status':'DRAFT',
        'materials':[{'key':'employment_proof','status':'required'}], 'next_action':{'message':'请上传必需申请材料'}})
    monkeypatch.setattr(tools, 'assert_tool_permission', lambda *_: None)
    context = tools.current_user_ctx.set(SimpleNamespace(id=7))
    try:
        output = tools.get_application_form.invoke({'case_id':CASE['id']})
    finally:
        tools.current_user_ctx.reset(context)
    result = json.loads(output)
    assert result['status'] == status
    assert result['materials'][0]['name'] == 'contract.pdf'
    assert result['materials'][0]['status'] == 'received'
    assert not any(value in output for value in ['请上传必需申请材料', 'page_open', 'sync_state', 'must-not-leak'])
    # The opening API must tell the UI to show progress rather than start a fill task.
    monkeypatch.setattr(store, 'ensure_business_link', lambda _: {'case_id':CASE['id'], 'query_token':linked})
    response = applications.prepare_business_link(applications.CaseIdRequest(case_id=CASE['id']), SimpleNamespace(id=7))
    assert json.loads(response.body)['progress_status'] == status

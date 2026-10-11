import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from mock_business_system import portal_api as portal


PASSWORD = "test-password-only-12345"
HEADERS = {"X-Business-Request": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_BUSINESS_DB", str(tmp_path / "business.sqlite3"))
    monkeypatch.setenv("MOCK_ADMIN_PASSWORD", PASSWORD)
    with TestClient(portal.app) as value:
        yield value


def payload(business="employment-registration"):
    data = {"full_name": "合成测试申请人", "phone": "13800138000", "current_address": "测试地址", "submission_id": secrets.token_hex(24)}
    if business == "employment-registration":
        data.update(employment_type="employer", employer_name="测试单位", occupation="开发", employment_start_date="2026-10-11")
    else:
        data.update(unemployment_date="2026-10-11", unemployment_reason="contract_ended", last_employer="测试单位")
    return data


def submit(client, business="employment-registration", data=None, content=b"synthetic proof"):
    return client.post(f"/api/{business}/submit", data=data or payload(business), files={portal.BUSINESSES[business]["proof"]: ("测试材料.txt", content, "text/plain")})


def login(client):
    response = client.post("/business/api/login", json={"username": "admin", "password": PASSWORD}, headers=HEADERS)
    assert response.status_code == 200
    return response


@pytest.mark.parametrize("business", list(portal.BUSINESSES))
def test_form_upgrade_bypasses_old_bridge_cache(client, business):
    page = client.get(f"/{business}/apply")
    assert '/form-bridge.js?v=20261011-progress-1' in page.text
    assert '/business/submission.js?v=20261011-progress-1' in page.text
    bridge = client.get('/form-bridge.js?v=20261011-progress-1')
    assert bridge.status_code == 200
    assert bridge.headers['cache-control'] == 'no-store'
    assert 'businessSubmission?.prepare(body)' in bridge.text
    legacy = payload(business)
    legacy.pop('submission_id')
    rejected = submit(client, business, legacy)
    assert rejected.status_code == 422
    assert rejected.json()['detail'] == '提交标识无效，请刷新页面'
    legacy['submission_id'] = secrets.token_hex(24)
    assert submit(client, business, legacy).status_code == 200


@pytest.mark.parametrize("business", list(portal.BUSINESSES))
def test_submission_approval_query_and_material(client, business):
    submitted = submit(client, business).json()
    number = submitted["application_no"]
    query = {"number": number, "code": submitted["query_code"]}
    assert client.post("/business/api/query", json=query, headers=HEADERS).json()["status"] == "PENDING"
    login(client)
    listing = client.get("/business/api/applications").json()
    assert listing["total"] == 1 and "query_token" not in listing["items"][0]
    detail = client.get(f"/business/api/applications/{number}").json()
    assert detail["fields"][0]["value"] == "合成测试申请人"
    material = client.get(f"/business/api/applications/{number}/material")
    assert material.content == b"synthetic proof"
    assert material.headers["content-disposition"].startswith("attachment;")
    response = client.post(f"/business/api/applications/{number}/decision", json={"action": "approve", "comment": "材料核对通过"}, headers=HEADERS)
    assert response.status_code == 200 and response.json()["status"] == "APPROVED"
    result = client.post("/business/api/query", json=query, headers=HEADERS).json()
    assert result["status"] == "APPROVED" and result["comment"] == "材料核对通过"
    assert result['materials'][0]['name'] == '测试材料.txt'
    assert result['materials'][0]['size_bytes'] == len(b'synthetic proof')
    assert result['materials'][0]['status'] == 'received'
    assert 'file_content' not in str(result) and 'query_token' not in result
    assert "applicant" not in result and "fields" not in result


def test_unauthorized_operations_and_query_secret(client):
    record = submit(client).json()
    number = record["application_no"]
    for url in ("/business/api/applications", f"/business/api/applications/{number}", f"/business/api/applications/{number}/material"):
        assert client.get(url).status_code == 401
    assert client.post(f"/business/api/applications/{number}/decision", json={"action": "approve"}, headers=HEADERS).status_code == 401
    assert client.post("/business/api/query", json={"number": number, "code": "wrong"}, headers=HEADERS).status_code == 404
    assert client.post("/business/api/query", json={"number": number, "code": "错误查询码"}, headers=HEADERS).status_code == 404
    login(client)
    assert client.post(f"/business/api/applications/{number}/decision", json={"action": "approve"}).status_code == 403


def test_idempotent_submission_and_changed_payload(client):
    data = payload()
    first = submit(client, data=data).json()
    assert submit(client, data=data).json() == first
    data["occupation"] = "变更后"
    assert submit(client, data=data).status_code == 409
    login(client)
    assert client.get("/business/api/applications").json()["total"] == 1


def test_distinct_submission_numbers(client):
    assert submit(client).json()["application_no"] != submit(client).json()["application_no"]


def test_rejection_and_atomic_double_decision(client):
    number = submit(client).json()["application_no"]
    login(client)
    url = f"/business/api/applications/{number}/decision"
    assert client.post(url, json={"action": "reject"}, headers=HEADERS).status_code == 422
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda action: client.post(url, json={"action": action, "comment": "测试原因"}, headers=HEADERS).status_code, ["approve", "reject"]))
    assert sorted(results) == [200, 409]


@pytest.mark.parametrize("field,value", [("phone", "123"), ("full_name", " "), ("employment_type", "bad"), ("employment_start_date", "bad"), ("submission_id", "short")])
def test_invalid_submission_not_persisted(client, field, value):
    data = payload()
    data[field] = value
    assert submit(client, data=data).status_code == 422
    login(client)
    assert client.get("/business/api/applications").json()["total"] == 0


def test_material_required_and_bounded(client):
    assert client.post("/api/employment-registration/submit", data=payload()).status_code == 422
    assert submit(client, content=b"").status_code == 422
    assert submit(client, content=b"x" * (portal.MAX_FILE + 1)).status_code == 422


def test_restart_keeps_records_and_credentials(client):
    record = submit(client).json()
    portal.initialize()
    login(client)
    assert client.get("/business/api/applications").json()["items"][0]["number"] == record["application_no"]


def test_session_logout_password_change_and_cookie_flags(client):
    cookie = login(client).headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/business" in cookie
    assert client.post("/business/api/password", json={"current_password": "bad", "new_password": "new-password-12345"}, headers=HEADERS).status_code == 400
    assert client.post("/business/api/password", json={"current_password": PASSWORD, "new_password": "new-password-12345"}, headers=HEADERS).status_code == 200
    assert client.get("/business/api/me").status_code == 401
    assert not (portal.db_path().parent / "initial-admin.txt").exists()
    assert client.post("/business/api/login", json={"username": "admin", "password": PASSWORD}, headers=HEADERS).status_code == 401
    assert client.post("/business/api/login", json={"username": "admin", "password": "new-password-12345"}, headers=HEADERS).status_code == 200
    assert client.post("/business/api/logout", json={}, headers=HEADERS).status_code == 200
    assert client.get("/business/api/me").status_code == 401


def test_filters_and_literal_search(client):
    submit(client)
    submit(client, "unemployment-registration")
    login(client)
    assert client.get("/business/api/applications?business=unemployment-registration").json()["total"] == 1
    assert client.get("/business/api/applications?q=%25").json()["total"] == 0
    assert client.get("/business/api/applications?page=0").status_code == 422


def test_login_throttle(client):
    for _ in range(15):
        assert client.post("/business/api/login", json={"username": "missing", "password": "wrong"}, headers=HEADERS).status_code == 401
    assert client.post("/business/api/login", json={"username": "missing", "password": "wrong"}, headers=HEADERS).status_code == 429


def test_case_status_requires_matching_capability_and_survives_restart(client):
    data = payload()
    data.update(case_id='synthetic-case', link_token=secrets.token_urlsafe(32))
    record = submit(client, data=data).json()
    body = {'case_id': data['case_id'], 'token': data['link_token']}
    assert client.post('/business/api/case-status', json=body).status_code == 403
    assert client.post('/business/api/case-status', json={**body, 'token':secrets.token_urlsafe(32)}, headers=HEADERS).status_code == 404
    assert client.post('/business/api/case-status', json={**body, 'case_id':'foreign'}, headers=HEADERS).status_code == 404
    portal.initialize()
    result = client.post('/business/api/case-status', json=body, headers=HEADERS).json()
    assert result['number'] == record['application_no'] and result['status'] == 'PENDING'
    assert 'query_token' not in result and 'link_hash' not in result
    # A reopened case with a different browser request id returns the original receipt.
    data['submission_id'] = secrets.token_hex(24)
    assert submit(client, data=data).json() == record
    login(client)
    client.post(f"/business/api/applications/{record['application_no']}/decision", json={'action':'reject','comment':'需补齐证明'}, headers=HEADERS)
    result = client.post('/business/api/case-status', json=body, headers=HEADERS).json()
    assert result['status'] == 'REJECTED' and result['comment'] == '需补齐证明'


def test_legacy_case_id_alone_does_not_bind_progress(client):
    data = payload()
    data['case_id'] = 'old-case'
    assert submit(client, data=data).status_code == 200
    assert client.post('/business/api/case-status', json={'case_id':'old-case','token':secrets.token_urlsafe(32)}, headers=HEADERS).status_code == 404

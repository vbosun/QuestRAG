"""Browser smoke test for the application workspace with network contracts mocked at the boundary.

Run through the webapp-testing ``with_server.py`` helper; it verifies the React UI without
requiring a developer's PostgreSQL account or a real public-service login.
"""

import json

from playwright.sync_api import sync_playwright


USER = {
    "id": 7, "full_name": "测试用户", "id_number_masked": "110***********0001",
    "role": "USER", "roles": ["USER"], "rag_scopes": [],
    "permissions": ["application.workspace.view", "application.case.create", "application.case.read_self", "application.case.edit_self", "application.browser.connect"],
}

DETAIL = {
    "id": "case-1", "business_code": "employment_registration", "definition_version": "2026.08.mock.1",
    "status": "DRAFT", "current_step": "basic_info",
    "definition": {"name": "就业登记申请", "region": "试点演示地区", "official_service_name": "人社就业服务平台（演示）", "steps": [
        {"code": "basic_info", "name": "填写基本信息", "state": "DRAFT"},
        {"code": "materials", "name": "补充申请材料", "state": "MATERIALS"},
    ]},
    "fields": [
        {"key": "full_name", "label": "姓名", "type": "text", "required": True, "editable": False, "value": "测试用户", "source": "profile_prefill", "revision": 1, "sync_state": "pending"},
        {"key": "phone", "label": "联系电话", "type": "phone", "required": True, "editable": True, "value": None, "source": None, "revision": 0, "sync_state": "pending"},
    ],
    "materials": [{"key": "employment_proof", "label": "劳动合同、营业执照或灵活就业证明", "required": True, "status": "required"}],
    "browser": None, "next_action": {"code": "FILL_FIELDS", "message": "请补充：联系电话"},
}


def json_route(route, payload):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.add_init_script("sessionStorage.setItem('access_token', 'browser-test-token'); sessionStorage.setItem('refresh_token', 'browser-test-refresh');")
    failures: list[str] = []
    page.on("console", lambda message: failures.append(message.text) if message.type == "error" else None)
    page.route("**/auth/me", lambda route: json_route(route, USER))
    page.route("**/applications/definitions/list", lambda route: json_route(route, [{"business_code": "employment_registration", "version": "2026.08.mock.1", "name": "就业登记申请", "region": "试点演示地区", "official_service_name": "人社就业服务平台（演示）"}]))
    page.route("**/applications/cases/list", lambda route: json_route(route, []))
    page.route("**/applications/cases/create", lambda route: json_route(route, DETAIL))
    updates: list[dict] = []

    def update_route(route):
        updates.append(route.request.post_data_json)
        json_route(route, {"field_key": "phone", "value": "13800138000", "source": "user_manual", "revision": 1, "sync_state": "pending"})

    page.route("**/applications/drafts/update-field", update_route)
    page.goto("http://127.0.0.1:5173/app/applications")
    page.wait_for_load_state("networkidle")
    page.locator(".application-definition-card .ant-btn-primary").click()
    page.locator(".application-form-card").wait_for()
    form_inputs = page.locator(".application-form-card input")
    assert form_inputs.count() == 2
    assert form_inputs.nth(0).is_disabled()
    form_inputs.nth(1).fill("13800138000")
    page.locator(".application-form-card .application-field-row button").click()
    assert updates == [{"case_id": "case-1", "field_key": "phone", "value": "13800138000", "expected_revision": 0}]
    assert page.locator(".application-sidebar .ant-alert-warning").count() == 1
    assert not failures, failures
    browser.close()

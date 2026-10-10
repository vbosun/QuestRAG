"""Actual React + iframe + chat tool + page-state service; synthetic auth/worker API.

Run against local Vite/mock servers, or pass the deployed /app/chat URL. This
does not invoke the model, use real accounts or submit a business application.
Actual Chromium/Browser Use execution is verified separately by the worker smoke.
"""
import asyncio
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from quest_rag.api import applications as api
from quest_rag.applications import form_filling, page_sessions
from quest_rag.applications.browser_use_runtime import runtime
from quest_rag.rag import tools
from quest_rag.rag.tool_registry import current_user_ctx

ROOT = Path(__file__).resolve().parents[1]
case = str(uuid4())
user = SimpleNamespace(id=999999)
detail = {'id': case, 'business_code': 'employment_registration', 'execution_mode': 'browser_use',
          'status': 'DRAFT', 'current_step': 'basic_info', 'definition': {'name': '就业登记申请', 'steps': [{'code': 'basic_info', 'name': '核对信息'}]},
          'fields': [{'key': key, 'label': key, 'required': True, 'editable': key != 'full_name', 'type': 'phone' if key == 'phone' else 'text', 'value': value}
                     for key, value in [('full_name', '测试用户'), ('phone', '13800138000'), ('occupation', ''), ('current_address', ''),
                                        ('employment_type', ''), ('employer_name', ''), ('employment_start_date', '')]],
          'materials': [], 'next_action': {}}
state = {'task_id': 'initial', 'status': 'completed', 'events': [], 'operation_events': [], 'form_fields': {'phone': '13800138000'}}
calls = []
executor = ThreadPoolExecutor(max_workers=1)


def arun(coroutine):
    return executor.submit(asyncio.run, coroutine).result()
tools.assert_tool_permission = lambda *_: None
tools.remember_tool_result = lambda *_: None
api.service.get_application_detail = lambda *_: copy.deepcopy(detail)
api.service.connect_browser = lambda *_: {'entry_url': 'http://127.0.0.1:8020/employment-registration/apply'}
api.service.update_draft_field = lambda *_: {}
runtime.register_session(case, user.id)
runtime._tasks[case] = 'initial'


async def run(*args, **kwargs):
    calls.append(kwargs)
    state.clear()
    state.update(task_id=str(uuid4()), status='running', events=[], operation_events=[], form_fields={},
                 **{key: kwargs[key] for key in ('command_id', 'requested_fields', 'page_id', 'field_revisions')})
    runtime._tasks[case] = state['task_id']
    return copy.deepcopy(state)


async def worker_request(method, path, **kwargs):
    if method == 'DELETE' and state['status'] in ('queued', 'running'):
        state['status'] = 'cancelled'
    return copy.deepcopy(state)


runtime.run = run
runtime._worker_request = worker_request


def invoke(fields):
    return executor.submit(invoke_tool, fields).result()


def invoke_tool(fields):
    token = current_user_ctx.set(user)
    try:
        return json.loads(tools.fill_application_form.invoke({'case_id': case, 'fields': fields}))
    finally:
        current_user_ctx.reset(token)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5173/app/chat'
    item = {'id': 'chat-fill-check', 'title': '连续填写验证', 'created_at': '2026-10-10T00:00:00Z', 'updated_at': '2026-10-10T00:00:00Z'}
    conversation = dict(item, messages=[{'id': 'msg', 'sequence': 1, 'role': 'assistant', 'content': '', 'raw': '',
        'parts': [{'type': 'application', 'artifact': {'type': 'application', 'case_id': case, 'title': '就业登记申请'}}],
        'citations': [], 'status': 'completed'}])
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        errors, submissions = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: submissions.append(request.url) if '/submit' in request.url else None)
        page.add_init_script("sessionStorage.setItem('access_token','fixture-only')")
        def fulfill(route, value):
            route.fulfill(status=200, content_type='application/json', body=json.dumps(value, ensure_ascii=False))
        for path, response in {'/auth/me': {'id': user.id, 'full_name': '测试用户', 'roles': [], 'permissions': ['chat.view'], 'rag_scopes': []},
            '/chat/conversations/list': {'items': [item], 'total': 1, 'page': 1, 'page_size': 30},
            '/chat/conversations/get': conversation, '/documents/doclist': []}.items():
            page.route('**' + path, lambda route, request, value=response: fulfill(route, value))
        def get_detail(route):
            result = copy.deepcopy(detail)
            snapshot = page_sessions.pages.get(case, user.id)
            if snapshot:
                result['page_fields'] = snapshot['fields']
            fulfill(route, result)
        page.route('**/applications/cases/get', get_detail)
        page.route('**/applications/browser/use/start', lambda route: fulfill(route, state))
        page.route('**/applications/browser/use/status', lambda route: fulfill(route, arun(runtime.status(case))))
        page.route('**/applications/browser/use/cancel', lambda route: fulfill(route, arun(runtime.cancel(case))))
        def sync(route):
            result = arun(api.sync_application_page(api.PageSnapshotRequest(**route.request.post_data_json), user))
            fulfill(route, result)
        page.route('**/applications/browser/use/page-state', sync)
        page.goto(url)
        frame = page.frame_locator('iframe')
        phone, occupation, address = frame.locator('#phone'), frame.locator('#occupation'), frame.locator('#current_address')
        expect(phone).to_have_value('13800138000')
        phone.fill('13900139000')
        address.fill('手动地址')
        proof = frame.locator('#employment_proof')
        proof.set_input_files({'name': 'proof.txt', 'mimeType': 'text/plain', 'buffer': b'fixture only'})
        page.wait_for_timeout(1300)
        result = invoke([{'key': 'phone', 'value': '13800000000'}, {'key': 'occupation', 'value': '软件工程师'}])
        assert result['started'] and not result['completed']
        assert calls[-1]['initial_fields']['phone'] == '13900139000'
        assert calls[-1]['initial_fields']['current_address'] == '手动地址'
        state['operation_events'].append({'sequence': 1, 'phase': 'started', 'field_key': 'phone', 'label': '电话'})
        expect(phone).to_have_css('outline-style', 'solid')
        state['form_fields']['phone'] = '13800000000'
        state['operation_events'].append({'sequence': 2, 'phase': 'applied', 'field_key': 'phone', 'label': '电话', 'value': '13800000000'})
        expect(phone).to_have_value('13800000000')
        state['operation_events'].append({'sequence': 3, 'phase': 'started', 'field_key': 'occupation', 'label': '职业'})
        expect(occupation).to_have_css('outline-style', 'solid')
        state['form_fields']['occupation'] = '软件工程师'
        state['operation_events'].append({'sequence': 4, 'phase': 'applied', 'field_key': 'occupation', 'label': '职业', 'value': '软件工程师'})
        state['status'] = 'completed'
        expect(occupation).to_have_value('软件工程师')
        page.wait_for_timeout(1100)
        assert arun(runtime.status(case))['page_sync']['status'] == 'applied'
        assert address.input_value() == '手动地址' and proof.evaluate('el => el.files[0].name') == 'proof.txt'
        # A fresh command is discovered after terminal status; typing after its
        # baseline was captured must win over later confirmed background values.
        result = invoke([{'key': 'phone', 'value': '13700000000'}])
        state['operation_events'].append({'sequence': 1, 'phase': 'started', 'field_key': 'phone', 'label': '电话'})
        expect(phone).to_have_css('outline-style', 'solid')
        phone.fill('')
        state['form_fields']['phone'] = '13700000000'
        state['operation_events'].append({'sequence': 2, 'phase': 'applied', 'field_key': 'phone', 'label': '电话', 'value': '13700000000'})
        state['status'] = 'completed'
        expect(page.get_by_text('保留手动修改', exact=True)).to_be_visible()
        assert phone.input_value() == ''
        assert arun(runtime.status(case))['page_sync']['status'] == 'conflict'
        invoke([{'key': 'phone', 'value': '13600000000'}])
        expect(page.get_by_role('button', name='停止并接管')).to_be_visible()
        page.get_by_role('button', name='停止并接管').click()
        expect(page.get_by_text('已停止', exact=True)).to_be_visible()
        invoke([{'key': 'phone', 'value': '13500000000'}])
        state['form_fields']['phone'] = '13500000000'
        state['operation_events'].append({'sequence': 1, 'phase': 'applied', 'field_key': 'phone', 'label': '电话', 'value': '13500000000'})
        state['status'] = 'completed'
        expect(phone).to_have_value('13500000000')
        page.wait_for_timeout(1200)
        assert arun(runtime.status(case))['page_sync']['status'] == 'applied'
        page.get_by_role('button', name='关闭申请页面', exact=True).click()
        page.wait_for_timeout(1000)
        assert not invoke([{'key': 'phone', 'value': '13800000000'}])['started']
        page.get_by_role('button', name='打开申请页面', exact=True).click()
        expect(phone).to_have_value('13500000000')
        expect(address).to_have_value('手动地址')
        assert proof.evaluate('el => el.files.length') == 0  # files are never persisted
        assert not errors and not submissions, (errors, submissions)
        page.wait_for_timeout(350)  # Let the modal opening motion finish before visual inspection.
        (ROOT / 'output').mkdir(exist_ok=True)
        page.screenshot(path=str(ROOT / 'output/chat-followup-filling.png'))
        browser.close()
        print('Actual chat tool + React/iframe + page-state service passed: multi-field highlights, repeated tasks, actual page receipts, manual conflicts/clears, cancellation/resume, close/reopen restoration; no business submission. Auth/worker responses were synthetic.')


if __name__ == '__main__':
    main()

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from quest_rag.applications import form_filling as filling
from quest_rag.applications.page_sessions import PageSessions
from quest_rag.applications.browser_use_runtime import BrowserUseRuntime


@pytest.fixture
def connected(monkeypatch):
    case_id = str(uuid4())
    pages = PageSessions()
    user = SimpleNamespace(id=42)
    fields = [{'key': 'phone', 'label': '电话', 'type': 'phone', 'editable': True, 'required': True},
              {'key': 'occupation', 'label': '职业', 'type': 'text', 'editable': True},
              {'key': 'full_name', 'value': '测试用户', 'label': '姓名', 'editable': False}]
    detail = {'id': case_id, 'fields': fields, 'execution_mode': 'browser_use'}
    monkeypatch.setattr(filling, 'pages', pages)
    monkeypatch.setattr(filling.service, 'get_application_detail', lambda *_: detail)
    monkeypatch.setattr(filling.service, 'connect_browser', lambda *_: {'entry_url': 'http://mock-business:8020/apply'})
    runtime = BrowserUseRuntime()
    monkeypatch.setattr(filling, 'runtime', runtime)
    snapshot = {'page_id': 'p', 'sequence': 1, 'open': True, 'fields': {'phone': '13900139000', 'occupation': ''},
                'field_revisions': {'phone': 3, 'occupation': 1}, 'task_id': 'old', 'conflicts': []}
    pages.update(case_id, user.id, snapshot)
    return user, case_id, pages, runtime, snapshot, detail


def test_batch_uses_manual_values_and_does_not_persist_before_execution(connected, monkeypatch):
    user, case, pages, runtime, snapshot, _ = connected
    calls = []
    async def run(*args, **kwargs):
        calls.append((args, kwargs))
        return {'task_id': 'new', 'status': 'queued'}
    monkeypatch.setattr(runtime, 'run', run)
    monkeypatch.setattr(filling.service, 'update_draft_field', lambda *_: pytest.fail('queueing is not actual filling'))
    result = asyncio.run(filling.fill_form(user, case, [{'key': 'phone', 'value': '13800138000'}, {'key': 'occupation', 'value': '工程师'}]))
    assert result['status'] == 'queued'
    assert len(calls) == 1
    _, payload = calls[0]
    assert payload['initial_fields'] == snapshot['fields']
    assert payload['field_revisions']['phone'] == 3
    assert payload['requested_fields'] == {'phone': '13800138000', 'occupation': '工程师'}
    assert payload['presentation'] == 'iframe' and payload['page_id'] == 'p'


@pytest.mark.parametrize('changes', [{'open': False}, {'submitted': True}])
def test_closed_or_submitted_page_cannot_start_task(connected, monkeypatch, changes):
    user, case, pages, runtime, snapshot, _ = connected
    pages.update(case, user.id, {**snapshot, **changes, 'sequence': 2})
    with pytest.raises(HTTPException):
        asyncio.run(filling.fill_form(user, case, [{'key': 'phone', 'value': '13800138000'}]))
    assert not runtime._tasks


@pytest.mark.parametrize('fields', [[{'key': 'full_name', 'value': '覆盖'}], [{'key': 'unknown', 'value': 'x'}],
    [{'key': 'phone', 'value': 'invalid'}], [{'key': 'phone', 'value': '13800138000'}] * 2, [{'wrong': 'x'}], []])
def test_rejects_invalid_batch_without_launching_browser(connected, fields):
    user, case, _, runtime, _, _ = connected
    with pytest.raises(HTTPException):
        asyncio.run(filling.fill_form(user, case, fields))
    assert not runtime._tasks


def test_page_order_ownership_retirement_and_freshness(monkeypatch):
    pages = PageSessions()
    snapshot = {'page_id': 'p', 'sequence': 2, 'open': True, 'fields': {'phone': ''}, 'field_revisions': {}}
    pages.update('c', 42, snapshot)
    pages.update('c', 42, {**snapshot, 'sequence': 1, 'fields': {'phone': 'old'}})
    assert pages.get('c', 42)['fields']['phone'] == ''
    assert pages.get('c', 43) is None
    with pytest.raises(HTTPException):
        pages.update('c', 43, snapshot)
    pages.update('c', 42, {**snapshot, 'page_id': 'new', 'sequence': 1})
    pages.update('c', 42, {**snapshot, 'sequence': 50})
    assert pages.get('c', 42)['page_id'] == 'new'
    monkeypatch.setattr('quest_rag.applications.page_sessions.time.monotonic', lambda: pages._pages['c']['seen'] + 6)
    with pytest.raises(HTTPException):
        pages.get('c', 42, fresh=True)


def test_backend_completion_requires_actual_page_receipt(connected, monkeypatch):
    user, case, pages, runtime, snapshot, _ = connected
    import quest_rag.applications.page_sessions as sessions
    monkeypatch.setattr(sessions, 'pages', pages)
    runtime.register_session(case, user.id)
    runtime._tasks[case] = 'new'
    payload = {'task_id': 'new', 'status': 'completed', 'command_id': 'cmd', 'page_id': 'p',
               'requested_fields': {'phone': '13800138000'}, 'form_fields': {'phone': '13800138000'}}
    async def request(*_):
        return dict(payload)
    monkeypatch.setattr(runtime, '_worker_request', request)
    assert asyncio.run(runtime.status(case))['page_sync']['status'] == 'pending'
    pages.update(case, user.id, {**snapshot, 'sequence': 2, 'task_id': 'new', 'conflicts': ['phone']})
    assert asyncio.run(runtime.status(case))['page_sync']['status'] == 'conflict'
    pages.update(case, user.id, {**snapshot, 'sequence': 3, 'task_id': 'new', 'fields': {'phone': '13800138000'}})
    assert asyncio.run(runtime.status(case))['page_sync']['status'] == 'applied'


def test_registered_chat_tool_starts_one_batch_and_does_not_claim_completion(connected, monkeypatch):
    from quest_rag.rag import tools
    from quest_rag.rag.tool_registry import current_user_ctx, TOOL_REGISTRY
    user, case, _, runtime, _, _ = connected
    monkeypatch.setattr(tools, 'assert_tool_permission', lambda *_: None)
    monkeypatch.setattr(tools, 'remember_tool_result', lambda *_: None)
    async def run(*_, **kwargs):
        return {'task_id': 'new', 'status': 'queued', 'requested_fields': kwargs['requested_fields']}
    monkeypatch.setattr(runtime, 'run', run)
    token = current_user_ctx.set(user)
    try:
        result = json.loads(tools.fill_application_form.invoke({'case_id': case, 'fields': [{'key': 'occupation', 'value': '工程师'}]}))
    finally:
        current_user_ctx.reset(token)
    assert result['started'] and not result['completed']
    assert TOOL_REGISTRY['fill_application_form']['permission'] == 'llm.tool.application_form_write'
    assert tools.fill_application_form in tools.tools

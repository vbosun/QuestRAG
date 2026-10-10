import asyncio
from types import SimpleNamespace

from browser_use_worker.app import TaskRecord
from browser_use_worker.operation_feedback import OperationFeedback


def test_operation_mirrors_only_successful_readback_and_keeps_action_order():
    async def scenario():
        fields = {'phone': {'value': '', 'label': '联系电话'}}
        async def evaluate(script):
            return {key: dict(value) for key, value in fields.items()}
        page = SimpleNamespace(url='http://demo/apply', evaluate=evaluate)
        async def get_page():
            return page
        async def get_element(index):
            return SimpleNamespace(attributes={'name': 'phone'})
        live = SimpleNamespace(page=get_page, browser=SimpleNamespace(get_element_by_index=get_element))
        record = TaskRecord(task_id='t', session_id='s', status='running', url=page.url, task='test', presentation='iframe')
        feedback = OperationFeedback(record, live)
        async def fail():
            fields['phone']['value'] = 'unconfirmed'
            return SimpleNamespace(error='failed')
        await feedback.perform({'input': {'index': 1}}, fail)
        assert record.form_fields == {}
        assert [e['phase'] for e in record.operation_events] == ['started', 'failed']
        async def succeed():
            fields['phone']['value'] = '13800138000'
            return SimpleNamespace(error=None)
        await feedback.perform({'input': {'index': 1}}, succeed)
        assert record.form_fields == {'phone': '13800138000'}
        assert record.operation_events[-1]['value'] == '13800138000'
        assert [e['sequence'] for e in record.operation_events] == [1, 2, 3, 4]
        assert record.operation_events[-1]['action_id'] == 2
        async def clear():
            fields['phone']['value'] = ''
            return SimpleNamespace(error=None)
        await feedback.perform({'input': {'index': 1}}, clear)
        assert record.form_fields['phone'] == ''
    asyncio.run(scenario())


def test_dom_targets_are_scoped_to_active_action_and_original_page():
    async def scenario():
        async def page():
            raise RuntimeError('not navigated')
        record = TaskRecord(task_id='t', session_id='s', status='running', url='http://demo/apply', task='test')
        feedback = OperationFeedback(record, SimpleNamespace(page=page))
        source = {'page': SimpleNamespace(url=record.url)}
        feedback.target(source, {'field_key': 'phone', 'label': '电话'})
        assert not record.operation_events
        async def invoke():
            feedback.target({'page': SimpleNamespace(url='http://other/apply')}, {'field_key': 'foreign'})
            feedback.target(source, {'field_key': 'phone', 'label': '电话'})
            raise asyncio.CancelledError()
        try:
            await feedback.perform({'evaluate': {}}, invoke)
        except asyncio.CancelledError:
            pass
        assert [e['phase'] for e in record.operation_events] == ['started', 'cancelled']
        assert record.form_fields == {}
        assert feedback.current is None
    asyncio.run(scenario())


def test_iframe_status_and_takeover_never_capture_screenshots(monkeypatch):
    from browser_use_worker import app as worker
    async def scenario():
        async def capture(*args):
            raise AssertionError('iframe mode must not screenshot')
        record = TaskRecord(task_id='t', session_id='s', status='completed', url='http://demo', task='test', presentation='iframe')
        monkeypatch.setattr(worker, 'TASKS', {'t': record})
        monkeypatch.setattr(worker, 'BROWSERS', {'t': SimpleNamespace(capture=capture)})
        monkeypatch.setattr(worker, 'RUNNERS', {})
        assert (await worker.get_task('t'))['live_frame'] is None
        assert (await worker.cancel_task('t'))['control'] == 'user'
    asyncio.run(scenario())

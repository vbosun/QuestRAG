"""Real Chromium and Browser Use tools, with the model planner replaced by fixed actions.

Run inside the worker's installed runtime with this checkout on PYTHONPATH.
No model request or business submission is performed.
"""
import asyncio
import logging
import os
from types import SimpleNamespace

import browser_use
from browser_use_worker import app as worker

ActualAgent = browser_use.Agent


class FakeHistory:
    def final_result(self):
        return 'fixed-action integration check'

    def is_successful(self):
        return True


class FixedAgent:
    def __init__(self, *, browser, tools, initial_actions, **kwargs):
        self.browser, self.tools, self.initial_actions = browser, tools, initial_actions
        assert kwargs['max_actions_per_step'] == 12
        assert '每个 action 只操作一个字段' in kwargs['extend_system_message']
        self.browser_session = browser
        self.browser_profile = browser.browser_profile
        self.logger = logging.getLogger('batch-smoke')
        self.settings = SimpleNamespace(page_extraction_llm=None)
        self.file_system = self.sensitive_data = self.extraction_schema = None
        self.available_file_paths = []
        self.state = SimpleNamespace(n_steps=1)

    async def _check_stop_or_pause(self):
        pass

    async def _log_action(self, *args):
        pass

    async def _demo_mode_log(self, *args):
        pass

    def _is_connection_like_error(self, error):
        return False

    async def run(self, *, on_step_start, **kwargs):
        model = self.tools.registry.create_action_model()
        result = await self.tools.act(model(**self.initial_actions[0]), browser_session=self.browser)
        assert not result.error, result.error
        await on_step_start(self)
        state = await self.browser.get_browser_state_summary(include_screenshot=False)
        indices = {node.attributes.get('id'): index for index, node in state.dom_state.selector_map.items()}
        def input_field(key, text):
            return model(input={'index': indices[key], 'text': text})
        def evaluate(code):
            return model(evaluate={'code': f'(() => {{{code}}})()'})
        # The real Browser Use queue must stop the batch at a failure, preserve
        # earlier readbacks and skip the following planned field.
        results = await ActualAgent.multi_act(self, [
            input_field('phone', '13800138000'),
            evaluate("const el=document.querySelector('#occupation');el.focus();el.value='unconfirmed';throw new Error('intentional smoke failure')"),
            input_field('current_address', 'must not execute'),
        ])
        assert len(results) == 2 and not results[0].error and results[1].error
        assert '页面实际回读确认' in results[0].extracted_content
        assert '13800138000' in results[0].long_term_memory
        assert '页面实际回读确认' not in (results[1].long_term_memory or '')
        record = next(iter(worker.TASKS.values()))
        assert record.form_fields.get('occupation') != 'unconfirmed'
        assert (await worker.BROWSERS[record.task_id].page()).url == record.url
        assert await (await worker.BROWSERS[record.task_id].page()).locator('#current_address').input_value() == ''
        results = await ActualAgent.multi_act(self, [
            input_field('occupation', '测试岗位'),
            input_field('current_address', '测试地址'),
        ])
        assert len(results) == 2 and not any(result.error for result in results)
        assert 'current_address' in results[1].long_term_memory
        assert (await worker.get_task(record.task_id))['live_frame'] is None
        return FakeHistory()


async def main():
    browser_use.Agent = FixedAgent
    browser_use.ChatOpenAI = lambda **kwargs: object()
    os.environ['BROWSER_USE_FORCE_STRUCTURED_OUTPUT'] = 'true'
    req = worker.TaskRequest(session_id='isolated-iframe-check', url='http://mock-business:8020/employment-registration/apply',
                             task='fixed actions only; do not submit', profile_name='测试用户', presentation='iframe')
    record = worker.TaskRecord(task_id='isolated', session_id=req.session_id, url=req.url, task=req.task,
                               status='queued', presentation='iframe')
    worker.TASKS = {record.task_id: record}
    await worker._execute(record.task_id, req)
    assert record.status == 'completed', record.error
    assert record.form_fields['full_name'] == '测试用户'
    assert record.form_fields['phone'] == '13800138000'
    assert record.form_fields['occupation'] == '测试岗位'
    assert record.form_fields['current_address'] == '测试地址'
    assert any(event['phase'] == 'started' for event in record.operation_events)
    assert any(event['phase'] == 'failed' for event in record.operation_events)
    assert record.live_frame is None
    assert not worker.BROWSERS
    print('Actual Browser Use multi_act + Chromium: sequential batch, failure interrupts remaining actions, confirmed per-field readback, target events and cleanup passed.')


if __name__ == '__main__':
    asyncio.run(main())

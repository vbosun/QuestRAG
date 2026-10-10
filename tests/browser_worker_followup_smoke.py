"""Actual Browser Use tools + Chromium: restore manual state, then execute a new batch.

Run in the worker runtime with the repository on PYTHONPATH. Planner is fixed;
this does not test model understanding, touch real cases or submit the form.
"""
import asyncio
import os
import runpy
from pathlib import Path

import browser_use
from browser_use_worker import app as worker

fixture = runpy.run_path(str(Path(__file__).with_name('browser_worker_feedback_smoke.py')), run_name='fixture')
ActualAgent = browser_use.Agent


class FollowupAgent(fixture['FixedAgent']):
    async def run(self, *, on_step_start, **kwargs):
        model = self.tools.registry.create_action_model()
        result = await self.tools.act(model(**self.initial_actions[0]), browser_session=self.browser)
        assert not result.error, result.error
        await on_step_start(self)
        record = worker.TASKS[self.command_task]
        page = await worker.BROWSERS[record.task_id].page()
        assert await page.locator('#phone').input_value() == '13900139000'
        assert await page.locator('#occupation').input_value() == ''
        assert await page.locator('#current_address').input_value() == '人工地址'
        assert not record.operation_events, 'restoration is not an AI action'
        state = await self.browser.get_browser_state_summary(include_screenshot=False)
        indices = {node.attributes.get('id'): i for i, node in state.dom_state.selector_map.items()}
        for action in [model(input={'index': indices['current_address'], 'text': '不得覆盖'}),
                       model(evaluate={'code': "document.querySelector('#phone').value='不得脚本覆盖'"}),
                       model(navigate={'url': record.url, 'new_tab': False})]:
            assert (await self.tools.act(action, browser_session=self.browser)).error
        assert await page.locator('#current_address').input_value() == '人工地址'
        assert await page.locator('#phone').input_value() == '13900139000'
        results = await ActualAgent.multi_act(self, [model(input={'index': indices[key], 'text': value})
            for key, value in record.requested_fields.items()])
        assert len(results) == 2 and not any(r.error for r in results)
        assert await page.locator('#current_address').input_value() == '人工地址'
        assert await page.locator('#full_name').input_value() == '测试用户'
        return fixture['FakeHistory']()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.command_task = next(reversed(worker.TASKS))


async def main():
    browser_use.Agent = FollowupAgent
    browser_use.ChatOpenAI = lambda **kwargs: object()
    os.environ['BROWSER_USE_FORCE_STRUCTURED_OUTPUT'] = 'true'
    worker.TASKS, worker.RUNNERS, worker.BROWSERS = {}, {}, {}
    req = worker.TaskRequest(session_id='isolated-followup-check', presentation='iframe', command_id='followup-1',
        url='http://mock-business:8020/employment-registration/apply', task='fill phone and occupation only; do not submit',
        profile_name='测试用户', initial_fields={'phone': '13900139000', 'occupation': '', 'current_address': '人工地址'},
        requested_fields={'phone': '13800138000', 'occupation': '软件工程师'}, page_id='p', field_revisions={'phone': 2})
    for command in ('followup-1', 'followup-2'):
        result = await worker.run_task(req.model_copy(update={'command_id': command}))
        await asyncio.gather(*worker.RUNNERS.values())
        record = worker.TASKS[result['task_id']]
        assert record.status == 'completed', record.error
        assert {e['field_key'] for e in record.operation_events} == {'phone', 'occupation'}
        assert record.form_fields['phone'] == '13800138000'
        assert record.form_fields['occupation'] == '软件工程师'
        assert record.live_frame is None and not worker.BROWSERS
    assert len(worker.TASKS) == 2
    print('Actual Chromium follow-up commands: manual state restored (including empty field), 2-field batches, real targets/readbacks, unrelated value preserved, new task IDs and cleanup passed. No submission.')


if __name__ == '__main__':
    asyncio.run(main())

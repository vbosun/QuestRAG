"""Run against local Vite + mock business servers; only task API responses are mocked."""
import json
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


ROOT = Path(__file__).resolve().parents[1]
DETAIL = {
    'id': 'iframe-smoke', 'business_code': 'employment_registration', 'execution_mode': 'browser_use',
    'status': 'DRAFT', 'current_step': 'basic_info', 'definition': {'steps': [{'code': 'basic_info', 'name': '核对信息'}]},
    'fields': [
        {'key': 'full_name', 'label': '姓名', 'required': True, 'editable': False, 'value': '测试用户'},
        {'key': 'phone', 'label': '联系电话', 'required': True, 'editable': True, 'value': '13800138000'},
    ], 'materials': [],
}
HTML = """<!doctype html><html lang="zh"><meta charset="utf-8"><div id="root"></div>
<script type="module">
import RefreshRuntime from '/@react-refresh';
RefreshRuntime.injectIntoGlobalHook(window);
window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;
window.__vite_plugin_react_preamble_installed__=true;
</script>
<script type="module">
import React from '/node_modules/.vite/deps/react.js';
import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
import {App} from '/node_modules/.vite/deps/antd.js';
import {ApplicationFormDialog} from '/src/features/applications/ApplicationFormDialog.tsx';
import '/src/styles.css';
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App,null,
React.createElement(ApplicationFormDialog,{caseId:'iframe-smoke',title:'就业登记申请',open:true,onClose:()=>{}})));
</script></html>"""


def run(entry_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('requestfailed', lambda request: print('Failed browser request:', request.url, request.failure))
        page.add_init_script("try { sessionStorage.setItem('access_token','test-only'); } catch {}")
        operations = []
        state = {'task_id': 't', 'status': 'running', 'events': [], 'operation_events': operations, 'form_fields': {}}
        def fulfill(route, value):
            route.fulfill(status=200, content_type='application/json', body=json.dumps(value, ensure_ascii=False))
        page.route('**/applications/cases/get', lambda route: fulfill(route, DETAIL))
        page.route('**/applications/browser/use/start', lambda route: fulfill(route, state))
        page.route('**/applications/browser/use/status', lambda route: fulfill(route, state))
        def cancel(route):
            state['status'] = 'cancelled'
            fulfill(route, state)
        page.route('**/applications/browser/use/cancel', cancel)
        page.on('request', lambda request: requests.append(request.url) if '/submit' in request.url else None)
        page.goto(entry_url)
        page.wait_for_timeout(1000)
        assert not errors, errors
        try:
            page.locator('iframe').wait_for(timeout=10000)
        except Exception:
            print(page.locator('body').inner_text())
            raise
        frame = page.frame_locator('iframe')
        phone = frame.locator('#phone')
        try:
            frame.locator('#full_name').wait_for(timeout=10000)
        except Exception:
            print([(f.url, f.locator('body').inner_text()[:300]) for f in page.frames])
            raise
        assert frame.locator('#full_name').input_value() == '测试用户'
        assert phone.input_value() == '', 'Known draft values must wait for actual execution'
        operations.append({'sequence': 1, 'action_id': 1, 'phase': 'started', 'field_key': 'phone', 'label': '联系电话'})
        expect(phone).to_have_css('outline-style', 'solid')
        assert phone.input_value() == ''
        assert frame.locator('button[type=submit]').is_disabled()
        screenshot = ROOT / 'output' / 'browser-iframe-feedback.png'
        screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        state['form_fields'] = {'phone': '13800138000'}
        operations.append({'sequence': 2, 'action_id': 1, 'phase': 'applied', 'field_key': 'phone', 'label': '联系电话', 'value': '13800138000'})
        expect(phone).to_have_value('13800138000')
        phone.fill('13900139000')
        page.wait_for_timeout(1900)  # Exercise both the task and draft refresh loops.
        assert phone.input_value() == '13900139000'
        assert not phone.evaluate('el => el.style.outline')
        proof = frame.locator('#employment_proof')
        proof.set_input_files({'name': 'proof.txt', 'mimeType': 'text/plain', 'buffer': b'test only'})
        page.get_by_role('button', name='停止并接管').click()
        page.get_by_text('已停止', exact=True).wait_for()
        assert frame.locator('button[type=submit]').is_enabled()
        assert phone.input_value() == '13900139000'
        assert proof.evaluate('el => el.files[0].name') == 'proof.txt'
        phone.fill('')
        page.wait_for_timeout(1900)
        assert phone.input_value() == ''
        assert not requests, requests
        assert page.locator('.browser-use-screen').count() == 0
        assert not errors, errors
        browser.close()
        print('Native iframe, actual-event highlighting, confirmed sync, manual edits, upload and takeover passed; no submission.')


if __name__ == '__main__':
    # Serve the entry over actual localhost HTTP. Fulfilling its navigation with
    # Playwright changes its address-space classification and blocks local iframes.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.html', prefix='iframe-feedback-smoke-', dir=ROOT / 'web', delete=False) as entry:
        entry.write(HTML)
    entry_path = Path(entry.name)
    try:
        run(f'http://127.0.0.1:5173/{entry_path.name}')
    finally:
        entry_path.unlink()

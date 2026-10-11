"""Real independent-portal UI check using clearly labelled synthetic applications."""
import json
import os
import re
import secrets
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    base = os.environ.get("BUSINESS_TEST_URL", "http://127.0.0.1:8021")
    credential = Path(os.environ.get("BUSINESS_TEST_CREDENTIAL", "tmp/mock-approval-local/initial-admin.txt")).read_text(encoding="utf-8-sig")
    username = re.search(r"审批账号：(.+)", credential)[1].strip()
    password = re.search(r"初始密码：(.+)", credential)[1].strip()
    output = Path(os.environ.get("BUSINESS_TEST_OUTPUT", "output/mock-approval-local"))
    output.mkdir(parents=True, exist_ok=True)
    records = []
    run_label = '验收示例' + secrets.token_hex(2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        applicant = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = applicant.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/business/")
        expect(page.get_by_role("heading", name="办好就业事，安心迈出下一步")).to_be_visible()
        page.screenshot(path=str(output / "home.png"), full_page=True)
        for index, business in enumerate(["employment-registration", "unemployment-registration", "employment-registration"]):
            page.goto(base + f"/{business}/apply?new=1")
            page.locator('#full_name').fill(f"{run_label}-{index + 1}（合成数据）")
            page.locator('#phone').fill('13800138000')
            page.locator('#current_address').fill('演示地址，无真实个人信息')
            if business == 'employment-registration':
                page.locator('#employment_type').select_option('employer')
                page.locator('#employer_name').fill('模拟测试单位')
                page.locator('#occupation').fill('软件开发')
                page.locator('#employment_start_date').fill('2026-10-11')
                proof = '#employment_proof'
            else:
                page.locator('#unemployment_reason').select_option('contract_ended')
                page.locator('#last_employer').fill('模拟测试单位')
                page.locator('#unemployment_date').fill('2026-10-11')
                proof = '#unemployment_proof'
            page.locator(proof).set_input_files({'name':'合成验收材料.txt', 'mimeType':'text/plain', 'buffer':'这是合成验收材料，不是真实证明。'.encode()})
            with page.expect_response(lambda response: response.url.endswith('/submit') and response.request.method == 'POST') as response:
                page.get_by_role('button', name='提交申请', exact=True).click()
            result = response.value.json()
            assert response.value.status == 200, result
            expect(page.locator('#applicationProgress')).to_be_visible()
            records.append(result)
        admin_context = browser.new_context(viewport={"width":1440,"height":1000}, accept_downloads=True)
        admin_page = admin_context.new_page()
        admin_page.on("pageerror", lambda error: errors.append(str(error)))
        admin_page.goto(base + '/business/admin')
        admin_page.get_by_label('审批账号', exact=True).fill(username)
        admin_page.get_by_label('密码', exact=True).fill(password)
        admin_page.get_by_role('button', name='登录工作台').click()
        expect(admin_page.get_by_role('heading', name='审批工作台', exact=True)).to_be_visible()
        admin_page.get_by_label('申请搜索', exact=True).fill(run_label)
        admin_page.get_by_role('button', name='查询', exact=True).click()
        expect(admin_page.locator('#rows tr')).to_have_count(3)
        admin_page.screenshot(path=str(output / 'workbench.png'), full_page=True)
        admin_page.on('dialog', lambda dialog: dialog.accept())
        for index, action in enumerate(['approve', 'reject']):
            admin_page.locator(f'[data-detail="{records[index]["application_no"]}"]').click()
            expect(admin_page.locator('#decisionForm')).to_be_visible()
            with admin_page.expect_download() as download:
                admin_page.get_by_role('link', name='下载查看').click()
            assert Path(download.value.path()).read_bytes() == '这是合成验收材料，不是真实证明。'.encode()
            if action == 'reject':
                admin_page.get_by_role('button', name='驳回申请', exact=True).click()
                expect(admin_page.locator('#decisionError')).to_have_text('请填写驳回原因')
            admin_page.get_by_label('审批意见', exact=True).fill('合成验收：信息与材料一致。' if action == 'approve' else '合成验收：请补充完整证明后重新申请。')
            admin_page.screenshot(path=str(output / f'detail-{action}.png'), full_page=True)
            admin_page.get_by_role('button', name='通过申请' if action == 'approve' else '驳回申请', exact=True).click()
            expect(admin_page.locator('#detail .notice')).to_be_visible()
            admin_page.get_by_role('button', name='关闭详情').click()
            page.goto(base + '/business/query')
            page.get_by_label('申请编号', exact=True).fill(records[index]['application_no'])
            page.get_by_label('查询码', exact=True).fill(records[index]['query_code'])
            page.get_by_role('button', name='查询结果', exact=True).click()
            expect(page.locator('#queryResult .badge')).to_have_text('已通过' if action == 'approve' else '已驳回')
        admin_page.get_by_label('审批状态', exact=True).select_option('')
        admin_page.get_by_role('button', name='查询', exact=True).click()
        expect(admin_page.locator('#rows tr')).to_have_count(3)
        admin_page.screenshot(path=str(output / 'reviewed.png'), full_page=True)
        admin_page.set_viewport_size({'width':390, 'height':844})
        admin_page.screenshot(path=str(output / 'mobile.png'), full_page=True)
        assert admin_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert applicant.request.get(base + '/business/api/applications').status == 401
        assert applicant.request.get(base + '/business/api/applications/' + records[0]['application_no'] + '/material').status == 401
        assert not errors, errors
        browser.close()
    (output / 'receipts.json').write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'ui': 'passed', 'submissions': len(records), 'checks': ['submit both businesses', 'download material', 'approve', 'reject reason', 'public result query', 'mobile layout', 'unauthorized denial'], 'screenshots': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

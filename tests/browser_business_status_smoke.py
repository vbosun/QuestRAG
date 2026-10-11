"""Deployed React -> native business form capability handoff; auth/chat use synthetic fixtures."""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    base = 'http://192.168.1.43:18080'
    fixture = json.loads(Path('tmp/status-verification.json').read_text(encoding='utf-8'))
    output = Path('output/business-status')
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':1440,'height':1080})
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_init_script("sessionStorage.setItem('access_token','synthetic-test-only')")
        def fulfill(route, value):
            route.fulfill(status=200,content_type='application/json',body=json.dumps(value,ensure_ascii=False,default=str))
        for index, case in enumerate(fixture['cases']):
            page.unroute_all()
            item={'id':'status-check','title':'进度查询验收','created_at':'2026-10-11T00:00:00Z','updated_at':'2026-10-11T00:00:00Z'}
            conversation=dict(item,messages=[{'id':'m','sequence':1,'role':'assistant','content':'','raw':'','parts':[{'type':'application','artifact':{'type':'application','case_id':case['case_id'],'title':case['detail']['definition']['name']}}],'citations':[],'status':'completed'}])
            detail = case['detail']
            detail['execution_mode']='embedded'
            for path, value in {'/auth/me':{**fixture['user'],'permissions':['chat.view']},'/chat/conversations/list':{'items':[item],'total':1,'page':1,'page_size':30},
                '/chat/conversations/get':conversation,'/documents/doclist':[], '/applications/cases/get':detail,'/applications/cases/business-link':case['link']}.items():
                page.route('**'+path,lambda route,request,value=value:fulfill(route,value))
            page.goto(base+'/app/chat')
            frame=page.frame_locator('iframe')
            expect(frame.locator('#full_name')).to_have_value('进度工具验收（合成数据）')
            frame.locator('#current_address').fill('合成进度验收地址')
            if case['business']=='employment_registration':
                frame.locator('#employment_type').select_option('employer')
                frame.locator('#employer_name').fill('合成验收单位')
                frame.locator('#occupation').fill('软件开发')
                frame.locator('#employment_start_date').fill('2026-10-11')
                proof='#employment_proof'
            else:
                frame.locator('#unemployment_date').fill('2026-10-11')
                frame.locator('#unemployment_reason').select_option('contract_ended')
                frame.locator('#last_employer').fill('合成验收单位')
                proof='#unemployment_proof'
            frame.locator(proof).set_input_files({'name':'进度验收材料.txt','mimeType':'text/plain','buffer':b'Synthetic status integration proof'})
            # Actual frontend relay, not direct form token injection. Wait for its first periodic handoff.
            page.wait_for_timeout(1200)
            with page.expect_response(lambda r:r.url.endswith('/submit') and r.request.method=='POST') as submitted:
                frame.get_by_role('button',name='提交申请',exact=True).click()
            assert submitted.value.status==200
            body = submitted.value.request.post_data_buffer
            assert case['link']['token'].encode() in body and case['case_id'].encode() in body
            receipt=submitted.value.json()
            case['receipt']=receipt
            expect(frame.locator('#applicationProgress')).to_be_visible()
            page.get_by_role('button',name='关闭申请页面',exact=True).click()
            expect(page.locator('iframe')).to_have_count(0)
        assert not errors,errors
        browser.close()
    Path('tmp/status-verification.json').write_text(json.dumps(fixture,ensure_ascii=False),encoding='utf-8')
    print('PASS: both real React/iframe forms submitted with correct per-case capabilities; closed both pages. Synthetic auth/chat/link API responses, real persisted link values and business submit API.')


if __name__=='__main__':
    main()

"""Render saved real observations and cancel the new detail preview; no fare requests."""
import argparse
import json
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
import httpx
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from flightcore.browser_jobs import BrowserJobs
from flightcore.core import Request
from flightcore.serde import dumps


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output);db_path=output.with_suffix('.db')
    if output.exists() or db_path.exists():parser.error('새 출력 파일명을 지정하세요')
    data=json.loads(Path(args.input).read_text(encoding='utf-8'))
    assert data['detail_status']=='observed'
    detail=data['observations'][data['selected_index']]['seller_detail']
    assert detail['search_payment_transition']['same_search_condition'] is False
    # Real full outbound search snapshot; the one independently inspected
    # detail remains embedded in its original row. No bulk detail run is claimed.
    jobs=BrowserJobs(str(db_path));run='saved-payment-ui-audit'
    with jobs.db() as db:
        db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',(run,'naver','completed_observations',1,'단일 상세 진단 결과 표시 · 전체 상세 조회 미실행'))
        db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',(run,1,dumps(Request('outbound','ICN','NRT',date(2026,12,10))),'observed_partial',dumps(data)))
    preview=jobs.detail_plan(run)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    process=subprocess.Popen([sys.executable,'-m','flightcore.server','--db',str(db_path),'--port',str(port)],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    driver=None
    try:
        with httpx.Client(base_url=base,trust_env=False,timeout=5) as client:
            for _ in range(50):
                try:
                    if client.get('/api/config').status_code==200:break
                except httpx.HTTPError:pass
                if process.poll() is not None:raise RuntimeError('Local server exited')
                time.sleep(.2)
            else:raise RuntimeError('Local server unavailable')
            driver=webdriver.Chrome()
            driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':375,'height':900,'deviceScaleFactor':1,'mobile':True})
            driver.get(base)
            driver.execute_script("sessionStorage.setItem('browserJob',arguments[0])",run)
            driver.refresh();wait=WebDriverWait(driver,15)
            wait.until(lambda d:d.find_elements('css selector','#browserOutput summary'))[0].click()
            message=driver.find_element('xpath',"//p[contains(.,'결제 조건이 다른 검색 표시가')]")
            driver.execute_script('arguments[0].scrollIntoView({block:"start"})',message)
            driver.execute_script('window.scrollBy(0,-160)')
            driver.save_screenshot(str(output.with_suffix('.png')))
            body=driver.find_element('id','browserOutput').text
            assert '성인/삼성카드 → 성인/모든 결제수단' in body
            assert '동일 조건의 가격 인상·하락으로 비교하지 않습니다' in body
            driver.find_element('id','browserDetails').send_keys(Keys.ENTER)
            wait.until(lambda d:d.find_element('id','confirmDialog').is_displayed())
            confirmation=driver.find_element('id','confirmBody').text
            assert f"조건부 검색 카드 {preview['conditional_cards']}개" in confirmation
            driver.save_screenshot(str(output.with_name(output.stem+'-preview.png')))
            driver.find_element('id','confirmNo').click()
            state=client.get('/api/browser-jobs/'+run).json()
            assert state['detail_total']==0 and state['status']=='completed_observations'
            dimensions=driver.execute_script('return {width:innerWidth,scroll:document.documentElement.scrollWidth}')
            errors=[e for e in driver.get_log('browser') if e['level']=='SEVERE']
            assert dimensions['width']==dimensions['scroll']==375 and not errors
            evidence={'real_observation_rendered':True,'preview_only':True,'detail_requests_started':0,
                      'preview_count':preview['count'],'conditional_cards':preview['conditional_cards'],
                      'dimensions':dimensions,'errors':errors}
            output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(evidence))
    finally:
        if driver:driver.quit()
        process.terminate();process.wait(timeout=10)


if __name__=='__main__':main()

"""Preview-only real Chrome check against a snapshot DB; no fare requests."""
import argparse
import json
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
import httpx
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--run',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output)
    snapshot=output.with_suffix('.db')
    if output.exists() or snapshot.exists():parser.error('새 출력 파일명을 지정하세요')
    with sqlite3.connect(args.db) as source, sqlite3.connect(snapshot) as target:
        source.backup(target)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    process=subprocess.Popen([sys.executable,'-m','flightcore.server','--db',str(snapshot),'--port',str(port)],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    driver=None
    try:
        with httpx.Client(base_url=base,trust_env=False,timeout=5) as client:
            for _ in range(50):
                try:
                    if client.get('/api/config').status_code==200:break
                except httpx.HTTPError:pass
                if process.poll() is not None:raise RuntimeError('Local test server exited')
                time.sleep(.2)
            else:raise RuntimeError('Local test server unavailable')
            before=client.get('/api/browser-jobs/'+args.run).json()
            driver=webdriver.Chrome()
            driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':375,'height':900,'deviceScaleFactor':1,'mobile':True})
            driver.get(base)
            driver.execute_script("sessionStorage.setItem('browserJob',arguments[0])",args.run)
            driver.refresh()
            wait=WebDriverWait(driver,15)
            button=wait.until(lambda d: d.find_element('id','browserResumeDetails') if d.find_element('id','browserResumeDetails').is_enabled() else False)
            driver.execute_script('arguments[0].scrollIntoView({block:"center"})',button)
            button.click()
            wait.until(lambda d:d.find_element('id','confirmDialog').is_displayed())
            text=driver.find_element('id','confirmBody').text
            assert str(before['detail_counts']['pending'])+'개' in text
            driver.save_screenshot(str(output.with_suffix('.png')))
            driver.find_element('id','confirmNo').click()
            after=client.get('/api/browser-jobs/'+args.run).json()
            assert before['detail_counts']==after['detail_counts'] and before['status']==after['status']
            dimensions=driver.execute_script('return {width:innerWidth,scroll:document.documentElement.scrollWidth}')
            errors=[entry for entry in driver.get_log('browser') if entry['level']=='SEVERE']
            assert dimensions['width']==dimensions['scroll']==375,dimensions
            assert not errors,errors
            evidence={'preview_only':True,'pending':before['detail_counts']['pending'],
                      'state_unchanged':True,'dimensions':dimensions,'errors':errors}
            output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(evidence))
    finally:
        if driver:driver.quit()
        process.terminate();process.wait(timeout=10)


if __name__=='__main__':main()

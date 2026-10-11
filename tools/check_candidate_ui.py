"""Replay three saved real searches in an isolated DB and inspect local mobile UI."""
import json,socket,subprocess,sys,time
from pathlib import Path
from datetime import date
import httpx
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from flightcore.browser_jobs import BrowserJobs
from flightcore.core import Conditions,Request
from flightcore.serde import dumps

root=Path.cwd();output=root/'candidate-ui-20261010.json';dbpath=output.with_suffix('.db')
if output.exists() or dbpath.exists():raise RuntimeError('Preserving existing evidence; use a new output name')
c=Conditions(('ICN',),('NRT',),date(2026,12,10),date(2026,12,10),5)
jobs=BrowserJobs(str(dbpath));run='saved-real-candidates'
cases=[('roundtrip','naver-conditional-normal-choice-20261009.json'),('outbound','naver-outbound-payment-job-20261009.json'),('inbound','naver-inbound-payment-job-20261009.json')]
with jobs.db() as db:
    db.execute('INSERT INTO browser_runs VALUES(?,?,?,?,?)',(run,'naver','completed_observations',3,'과거 실제 관찰 재검사 · 최신 가격 아님 · 각 검색의 단일 상세만 있음'))
    for n,(kind,name) in enumerate(cases,1):
        data=json.loads((root/name).read_text(encoding='utf-8'));data['evaluated_conditions']=json.loads(dumps(c))
        req=Request(kind,'NRT' if kind=='inbound' else 'ICN','ICN' if kind=='inbound' else 'NRT',date(2026,12,15 if kind=='inbound' else 10),date(2026,12,15) if kind=='roundtrip' else None)
        db.execute('INSERT INTO browser_tasks VALUES(?,?,?,?,?)',(run,n,dumps(req),'observed_partial',dumps(data)))
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
base=f'http://127.0.0.1:{port}'
process=subprocess.Popen([sys.executable,'-m','flightcore.server','--db',str(dbpath),'--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
driver=None
try:
    with httpx.Client(base_url=base,trust_env=False,timeout=30) as client:
        for _ in range(60):
            try:
                if client.get('/api/config').status_code==200:break
            except httpx.HTTPError:pass
            if process.poll() is not None:raise RuntimeError('server exited')
            time.sleep(.2)
        first=client.get(f'/api/browser-jobs/{run}/candidate-comparisons').json()
        assert first['total']==375,first['total']
        all_items=[]
        for p in range(1,first['pages']+1):
            result=client.get(f'/api/browser-jobs/{run}/candidate-comparisons?page={p}').json()
            all_items.extend(result['items'])
        assert len(all_items)==375 and not any(item['rankable'] for item in all_items)
        assert sum(item['kind']=='two_oneways' for item in all_items)==352
        driver=webdriver.Chrome();driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':375,'height':900,'deviceScaleFactor':1,'mobile':True})
        driver.get(base);driver.execute_script("sessionStorage.setItem('browserJob',arguments[0])",run);driver.refresh()
        wait=WebDriverWait(driver,20);wait.until(lambda d:d.find_elements('css selector','#browserOutput summary'))
        driver.find_element('id','browserCandidates').send_keys(Keys.ENTER)
        wait.until(lambda d:'375개' in d.find_element('id','browserCandidateOutput').text)
        panel=driver.find_element('id','browserCandidateOutput')
        driver.find_elements('css selector','#browserCandidateOutput summary')[0].click()
        driver.execute_script('arguments[0].scrollIntoView({block:"start"});window.scrollBy(0,-160)',panel)
        driver.save_screenshot(str(output.with_suffix('.png')))
        dims=driver.execute_script('return {width:innerWidth,scroll:document.documentElement.scrollWidth}')
        errors=[e for e in driver.get_log('browser') if e['level']=='SEVERE']
        assert dims['width']==dims['scroll']==375 and not errors
        evidence={'mode':'saved_real_observations_replay','source_files':[name for _,name in cases],
                  'reconstructed_test_conditions':json.loads(dumps(c)),
                  'total':375,'roundtrip':23,'two_oneways':352,'pages':38,'rankable':0,'new_external_queries':0,'dimensions':dims,'errors':errors,
                  'first_page':first,'last_page':result}
        output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:evidence[k] for k in ('total','pages','rankable','dimensions','errors')}))
finally:
    if driver:driver.quit()
    process.terminate();process.wait(timeout=10)

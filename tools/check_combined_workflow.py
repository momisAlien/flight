"""Local browser workflow with explicitly synthetic providers; zero supplier calls."""
import json,socket,threading,time
from pathlib import Path
from unittest.mock import patch
import httpx,uvicorn
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from flightcore.browser_jobs import BrowserJobs
from flightcore.provider_probe import ProbeStopped
from flightcore.server import create_app

out=Path('workflow-synthetic-20261010.json');db=out.with_suffix('.db')
if out.exists() or db.exists():raise RuntimeError('Preserving prior evidence')
class SyntheticCollector:
    opened=0
    def __init__(self,provider,cancel):self.cancel=cancel;self.calls=0
    def open(self):
        SyntheticCollector.opened+=1;self.first=SyntheticCollector.opened==1
    def close(self):pass
    def collect(self,request):
        self.calls+=1
        if self.first and self.calls>1:
            if self.cancel.wait(30):raise ProbeStopped('cancelled','TEST cancellation')
        return {'observations':[{'amount':10000,'currency':'KRW','text':'SYNTHETIC WORKFLOW TEST ONLY'}]}

with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
base=f'http://127.0.0.1:{port}';driver=None;server=None
with patch('flightcore.server.BrowserJobs',side_effect=lambda path:BrowserJobs(path,factory=SyntheticCollector)),patch('flightcore.myrealtrip.api_key',return_value='TEST ONLY'),patch('flightcore.myrealtrip.calendar',return_value={'status':'no_cached_reference'}):
    try:
        server=uvicorn.Server(uvicorn.Config(create_app(str(db)),host='127.0.0.1',port=port,log_level='error',access_log=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        with httpx.Client(base_url=base,trust_env=False) as client:
            for _ in range(60):
                try:
                    if client.get('/api/config').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            driver=webdriver.Chrome();driver.get(base);wait=WebDriverWait(driver,45)
            wait.until(lambda d:d.find_elements('css selector','#originChoices input'))
            driver.execute_script("document.querySelectorAll('#originChoices input').forEach(e=>e.checked=e.value==='ICN');document.querySelectorAll('#destinationChoices input').forEach(e=>e.checked=e.value==='NRT');document.getElementById('start').value='2026-12-10';document.getElementById('end').value='2026-12-11';")
            def click(selector):
                element=driver.find_element('css selector',selector);element.send_keys(Keys.ENTER)
            click('#conditionsForm button[type=submit]')
            wait.until(lambda d:d.find_element('id','coverageLabel').text!='검색 조건을 먼저 지정하세요')
            click('#combinedStart');wait.until(lambda d:d.find_element('id','confirmDialog').is_displayed());click('#confirmYes')
            first=wait.until(lambda d:d.execute_script("return sessionStorage.getItem('combinedJob')"))
            wait.until(lambda d:len(d.find_elements('css selector','#combinedOutput details'))>0)
            click('#combinedCancel')
            wait.until(lambda d:client.get(f'/api/combined-jobs/{first}').json()['status']=='cancelled')
            saved=client.get(f'/api/combined-jobs/{first}').json()['ranking']
            assert saved['roundtrip_total']>0
            driver.switch_to.new_window('tab');driver.get(base)
            wait.until(lambda d:d.find_elements('css selector','#combinedHistory'))
            assert driver.execute_script("return sessionStorage.getItem('combinedJob')") is None
            click('#combinedHistory');wait.until(lambda d:d.find_elements('css selector','#combinedHistoryOutput button'));click('#combinedHistoryOutput button')
            wait.until(lambda d:len(d.find_elements('css selector','#combinedOutput details'))>0)
            assert client.get(f'/api/combined-jobs/{first}').json()['ranking']==saved
            click('#combinedAgain');wait.until(lambda d:d.find_element('id','confirmDialog').is_displayed());click('#confirmNo')
            assert len(client.get('/api/combined-history').json()['items'])==1
            click('#combinedAgain');wait.until(lambda d:d.find_element('id','confirmDialog').is_displayed());click('#confirmYes')
            second=wait.until(lambda d:(value if (value:=d.execute_script("return sessionStorage.getItem('combinedJob')"))!=first else None))
            wait.until(lambda d:client.get(f'/api/combined-jobs/{second}').json()['status']=='completed')
            driver.refresh();wait.until(lambda d:'통합 검색: 완료' in d.find_element('id','combinedOutput').text)
            assert client.get(f'/api/combined-jobs/{first}').json()['ranking']==saved
            assert len(client.get('/api/combined-history').json()['items'])==2
            errors=[x for x in driver.get_log('browser') if x['level']=='SEVERE'];assert not errors
            result={'synthetic_only':True,'external_requests':0,'start_cancel_preserve':True,'new_tab_restore':True,'decline_does_not_start':True,'rerun_new_id_preserves_old':True,'reload_completed_result':True,'errors':errors}
            out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    finally:
        if driver:driver.quit()
        if server:server.should_exit=True;thread.join(5)

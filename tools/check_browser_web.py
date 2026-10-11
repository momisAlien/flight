"""Explicit real-network acceptance check, not part of unit test discovery.

Run only with the local server using an isolated test database.
"""
import json
import argparse
from pathlib import Path
import time
import httpx
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',choices=('google','naver'),default='google')
    parser.add_argument('--origins',nargs='+',default=['ICN'])
    parser.add_argument('--destinations',nargs='+',default=['NRT'])
    parser.add_argument('--start',default='2026-12-10')
    parser.add_argument('--end',default='2026-12-11')
    parser.add_argument('--output',default='browser-web-acceptance-20261006')
    args=parser.parse_args()
    from datetime import date
    total=len(args.origins)*len(args.destinations)*((date.fromisoformat(args.end)-date.fromisoformat(args.start)).days+1)*3
    driver=webdriver.Chrome()
    try:
        driver.set_window_size(1280,1000)
        driver.get('http://127.0.0.1:8000')
        wait=WebDriverWait(driver,15)
        wait.until(lambda d:d.find_elements('css selector','#originChoices input'))
        for el in driver.find_elements('css selector','#originChoices input'):
            if el.is_selected() != (el.get_attribute('value') in args.origins):el.click()
        for el in driver.find_elements('css selector','#destinationChoices input'):
            if el.is_selected() != (el.get_attribute('value') in args.destinations):el.click()
        # Set native date controls with their public DOM values, then submit the
        # same form the user operates. No app-state or server data injection.
        driver.execute_script("document.getElementById('start').value=arguments[0];document.getElementById('end').value=arguments[1];",args.start,args.end)
        Select(driver.find_element('id','browserProvider')).select_by_value(args.provider)
        driver.find_element('css selector','#conditionsForm button[type="submit"]').click()
        wait.until(lambda d:not d.find_element('id','startCompare').get_attribute('disabled'))
        driver.find_element('id','browserStart').click()
        wait.until(lambda d:d.find_element('id','confirmDialog').is_displayed())
        assert f'검색 {total}조건' in driver.find_element('id','confirmBody').text
        driver.find_element('id','confirmYes').click()
        id=wait.until(lambda d:d.execute_script("return sessionStorage.getItem('browserJob')"))
        deadline=time.monotonic()+total*75+60
        last=None
        with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False) as client:
            while time.monotonic()<deadline:
                state=client.get('/api/browser-jobs/'+id).json()
                if state['counts']!=last:
                    print(json.dumps({'status':state['status'],'counts':state['counts']}),flush=True)
                    last=state['counts']
                if state['status']!='running':break
                time.sleep(2)
            else:raise RuntimeError('Acceptance timeout; inspect job before retrying')
            all_items=list(state['items'])
            for page in range(2,state['pages']+1):
                all_items.extend(client.get('/api/browser-jobs/'+id,params={'page':page}).json()['items'])
            state['items']=all_items
        wait.until(lambda d:'조회 중' not in d.find_element('id','browserStatus').text)
        panel=driver.find_element('id','browserStatus').find_element('xpath','..')
        driver.execute_script('arguments[0].scrollIntoView({block:"start"})',panel)
        driver.save_screenshot(args.output+'.png')
        Path(args.output+'.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'total':state['total'],'observed':state['observed'],'status':state['status']}),flush=True)
        assert state['status']=='completed_observations' and state['observed']==total
    finally:
        driver.quit()


if __name__=='__main__':main()

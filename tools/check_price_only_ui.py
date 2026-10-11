"""Render the completed Naver price-only run using an isolated SQLite snapshot."""
import json,sqlite3,socket,subprocess,sys,time
from pathlib import Path
import httpx
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
out=Path('price-only-ui-final-20261010.json');target=out.with_suffix('.db')
if out.exists() or target.exists():raise RuntimeError('Preserving prior evidence')
run=json.loads(Path('price-only-live-20261010.json').read_text(encoding='utf-8'))['providers']['naver']['run']
with sqlite3.connect('price-only-live-20261010.db') as source,sqlite3.connect(target) as dest:source.backup(dest)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
base=f'http://127.0.0.1:{port}'
process=subprocess.Popen([sys.executable,'-m','flightcore.server','--db',str(target),'--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));driver=None
try:
    with httpx.Client(base_url=base,trust_env=False,timeout=15) as client:
        for _ in range(60):
            try:
                if client.get('/api/config').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        result=client.get(f'/api/browser-jobs/{run}/price-summary').json()
        assert result['queries_with_price']==12 and len(result['comparisons'])==4
        driver=webdriver.Chrome();driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':375,'height':900,'deviceScaleFactor':1,'mobile':True})
        driver.get(base);driver.execute_script("sessionStorage.setItem('browserJob',arguments[0])",run);driver.refresh()
        wait=WebDriverWait(driver,25);wait.until(lambda d:d.find_elements('css selector','#browserOutput summary'))
        driver.find_element('id','browserPriceSummary').send_keys(Keys.ENTER)
        wait.until(lambda d:'12/12' in d.find_element('id','browserPriceOutput').text)
        panel=driver.find_element('id','browserPriceOutput');driver.execute_script('arguments[0].scrollIntoView({block:"start"});window.scrollBy(0,-160)',panel)
        driver.save_screenshot(str(out.with_suffix('.png')))
        dims=driver.execute_script('return {width:innerWidth,scroll:document.documentElement.scrollWidth}')
        errors=[e for e in driver.get_log('browser') if e['level']=='SEVERE']
        assert dims['width']==dims['scroll']==375 and not errors
        out.write_text(json.dumps({'queries_with_price':12,'dates':4,'dimensions':dims,'errors':errors,'new_external_queries':0,'seller_details_required':False},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'queries_with_price':12,'dates':4,'dimensions':dims,'errors':errors}))
finally:
    if driver:driver.quit()
    process.terminate();process.wait(timeout=10)

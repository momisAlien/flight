"""Verify saved real combined results locally; no supplier requests."""
import json,sqlite3,socket,subprocess,sys,time
from pathlib import Path
import httpx
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

out=Path(sys.argv[1] if len(sys.argv)>1 else 'combined-ui-20261010.json');target=out.with_suffix('.db')
if out.exists() or target.exists():raise RuntimeError('Preserving evidence')
evidence=Path(sys.argv[2] if len(sys.argv)>2 else 'combined-live-20261010.json')
run=json.loads(evidence.read_text(encoding='utf-8'))['id']
with sqlite3.connect(evidence.with_suffix('.db')) as source,sqlite3.connect(target) as dest:source.backup(dest)
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
        state=client.get(f'/api/combined-jobs/{run}').json()
        assert len(state['ranking']['roundtrips'])==len(state['ranking']['oneway_combinations'])==20
        driver=webdriver.Chrome();driver.get(base)
        driver.execute_script("sessionStorage.setItem('combinedJob',arguments[0])",run);driver.refresh()
        WebDriverWait(driver,25).until(lambda d:len(d.find_elements('css selector','#combinedOutput details'))==40)
        screenshots=[]
        for width in (1280,375):
            driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width==375})
            panel=driver.find_element('id','combinedOutput')
            driver.execute_script('arguments[0].scrollIntoView({block:"start"});window.scrollBy(0,-160)',panel)
            dims=driver.execute_script('return {width:innerWidth,scroll:document.documentElement.scrollWidth}')
            shot=out.with_name(f'{out.stem}-{width}.png');driver.save_screenshot(str(shot));screenshots.append(str(shot))
            print(json.dumps({'dimensions':dims,'requested':width}),flush=True)
            # Desktop reserves scrollbar width; narrower content is not overflow.
            assert dims['width']==width and dims['scroll']<=width
        errors=[e for e in driver.get_log('browser') if e['level']=='SEVERE']
        assert not errors
        result={'rendered_roundtrips':20,'rendered_oneway_combinations':20,'widths':[1280,375],'horizontal_overflow':False,'errors':errors,'new_external_queries':0,'screenshots':screenshots}
        out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result))
finally:
    if driver:driver.quit()
    process.terminate();process.wait(timeout=10)

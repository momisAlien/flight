"""Inspect public seller rule controls; never follow booking links."""
import json,threading,time
from pathlib import Path
from datetime import date
from selenium.webdriver.common.keys import Keys
from flightcore.browser_prices import BrowserCollector
from flightcore.core import Request
from flightcore.provider_probe import ProbeStopped
p=Path('naver-rules-controls-20261010.json')
if p.exists():raise RuntimeError('Preserving prior evidence')
saved=json.loads(Path('naver-baggage-conditional-live-20261010.json').read_text(encoding='utf-8'))
d=saved['observations'][saved['selected_index']]['seller_detail']
c=BrowserCollector('naver',threading.Event());result={}
try:
    c.open();c.driver.get(d['url'])
    result['detail']=c.read_naver_sellers(Request('outbound','ICN','NRT',date(2026,12,10)),d['selected_label'])
    controls=c.driver.find_elements('xpath',"//button[normalize-space(.)='상세규정']")
    result['controls']=[{'tag':e.tag_name,'text':e.text,'class':e.get_attribute('class'),'parent_text':e.find_element('xpath','..').text} for e in controls if e.is_displayed()]
    linked=[]
    for anchor in c.driver.find_elements('css selector','button[class*="detail_detail_anchor__"]'):
        if not anchor.is_displayed():continue
        wrapper=anchor.find_element('xpath','..')
        buttons=[b for b in wrapper.find_elements('css selector','button') if b.is_displayed() and b.text.strip()=='상세규정']
        if len(buttons)==1:linked.append((anchor.get_attribute('aria-label'),buttons[0]))
    result['linked_sellers']=[name for name,_ in linked]
    if linked:
        before=c.check();result['selected_seller']=linked[0][0]
        linked[0][1].send_keys(Keys.ENTER)
        for _ in range(20):
            body=c.check()
            if body!=before and ('수하물' in body):break
            time.sleep(.5)
        p.with_suffix('.txt').write_text(body,encoding='utf-8')
        c.driver.save_screenshot(str(p.with_suffix('.png')))
        result['visible_dialogs']=c.driver.execute_script("return [...document.querySelectorAll('[role=dialog],dialog,[class*=modal],[class*=Modal],[class*=layer],[class*=Layer]')].filter(e=>e.checkVisibility({checkVisibilityCSS:true,checkOpacity:true})).map(e=>({tag:e.tagName,cls:e.className,role:e.getAttribute('role'),text:e.innerText}));")
        result['modal_buttons']=c.driver.execute_script("return [...document.querySelectorAll('div[class^=container_PolicyModalContainer__] button')].filter(e=>e.checkVisibility({checkVisibilityCSS:true,checkOpacity:true})).map(e=>({text:e.innerText,label:e.getAttribute('aria-label'),cls:e.className}));")
    result['status']='inspected'  
except ProbeStopped as e:result.update(status=e.status,error=e.detail)
finally:
    c.close();p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':result.get('status'),'linked_sellers':result.get('linked_sellers',[]),'modal_buttons':result.get('modal_buttons',[])},ensure_ascii=True))

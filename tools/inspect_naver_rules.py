"""Inspect public seller rule controls; never follow booking links."""
import json,threading
from pathlib import Path
from datetime import date
from flightcore.browser_prices import BrowserCollector
from flightcore.core import Request
from flightcore.provider_probe import ProbeStopped
p=Path('naver-rules-inspection-20261010.json')
if p.exists():raise RuntimeError('Preserving prior evidence')
saved=json.loads(Path('naver-baggage-conditional-live-20261010.json').read_text(encoding='utf-8'))
d=saved['observations'][saved['selected_index']]['seller_detail']
c=BrowserCollector('naver',threading.Event());result={}
try:
    c.open();c.driver.get(d['url'])
    result['detail']=c.read_naver_sellers(Request('outbound','ICN','NRT',date(2026,12,10)),d['selected_label'])
    controls=c.driver.find_elements('xpath',"//button[normalize-space(.)='상세규정']")
    result['controls']=[{'tag':e.tag_name,'text':e.text,'class':e.get_attribute('class'),'parent_text':e.find_element('xpath','..').text} for e in controls if e.is_displayed()]
    result['status']='inspected'
except ProbeStopped as e:result.update(status=e.status,error=e.detail)
finally:
    c.close();p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':result.get('status'),'controls':result.get('controls',[])},ensure_ascii=True))

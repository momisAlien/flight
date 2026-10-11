"""Validate the integrated public seller policy collector on a known outbound route."""
import json,threading
from pathlib import Path
from datetime import date
from collections import Counter
from flightcore.browser_prices import BrowserCollector
from flightcore.core import Request
from flightcore.provider_probe import ProbeStopped
output=Path('naver-integrated-rules-20261010.json')
if output.exists():raise RuntimeError('Preserving prior evidence')
saved=json.loads(Path('naver-baggage-conditional-live-20261010.json').read_text(encoding='utf-8'))
d=saved['observations'][saved['selected_index']]['seller_detail']
c=BrowserCollector('naver',threading.Event());result={}
try:
    c.open();c.driver.get(d['url'])
    result['detail']=c.read_naver_sellers(Request('outbound','ICN','NRT',date(2026,12,10)),d['selected_label'])
    result['status']='observed'
    result['remaining_dialogs']=len([e for e in c.driver.find_elements('css selector','div[class^="container_PolicyModalContainer__"]') if e.is_displayed()])
    assert result['remaining_dialogs']==0
    output.with_suffix('.txt').write_text(c.check(),encoding='utf-8')
    c.driver.save_screenshot(str(output.with_suffix('.png')))
except ProbeStopped as e:result.update(status=e.status,error=e.detail)
finally:
    c.close();output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':result.get('status'),'rules':dict(Counter(o['fare_policy']['status'] for o in result.get('detail',{}).get('offers',[])))}))

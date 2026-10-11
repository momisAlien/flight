"""Single live CJJ search; no seller or booking actions."""
import json,threading
from pathlib import Path
from datetime import date
from collections import Counter
from flightcore.browser_prices import BrowserCollector
from flightcore.observed_schedules import assess
from flightcore.core import Request,Conditions
from flightcore.provider_probe import ProbeStopped
out=Path('cjj-live-20261010.json')
if out.exists():raise RuntimeError('Preserving evidence')
c=BrowserCollector('naver',threading.Event());result={}
req=Request('outbound','CJJ','NRT',date(2026,12,10))
conditions=Conditions(('CJJ',),('NRT',),date(2026,12,10),date(2026,12,10),5)
try:
    c.open();result=c.collect(req)
    for row in result['observations']:row['schedule']=assess('naver',row,req,conditions)
    result['schedule_read']=sum(bool(r['schedule']['legs']) for r in result['observations'])
    result['schedule_states']=dict(Counter(r['schedule']['status'] for r in result['observations']))
except ProbeStopped as error:result.update(status=error.status,error=error.detail)
finally:
    c.close();out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':result.get('status'),'observations':len(result.get('observations',[])),'schedule_read':result.get('schedule_read')}))

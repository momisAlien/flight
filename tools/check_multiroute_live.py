"""Bounded multi-airport/date real validation. No retries or access bypass."""
import json
from collections import Counter
from datetime import date
from pathlib import Path
from flightcore.browser_jobs import BrowserJobs
from flightcore.reference_jobs import ReferenceJobs,tasks
from flightcore.combined_jobs import CombinedJobs
from flightcore.core import Conditions,plan
from flightcore.serde import dumps
from flightcore.combined_prices import amount

out=Path('multiroute-live-20261010.json');db=out.with_suffix('.db')
if out.exists() or db.exists():raise RuntimeError('Preserving prior evidence')
c=Conditions(('ICN','GMP'),('NRT','HND'),date(2026,11,10),date(2026,11,11),5)
wide=Conditions(('ICN','GMP','CJJ'),('NRT','HND'),date(2026,12,10),date(2026,12,31),5)
expected=[json.loads(dumps(req)) for req in plan(c)]
wide_requests=list(plan(wide))
assert len(expected)==24 and len(wide_requests)==396
assert len({(r.kind,r.origin,r.destination,r.departure,r.return_date) for r in wide_requests})==396
assert len(list(tasks(c)))==4
b=BrowserJobs(str(db));r=ReferenceJobs(str(db));jobs=CombinedJobs(str(db),b,r)
id=jobs.start(c)
while jobs.thread.is_alive():
    jobs.thread.join(15);state=jobs.status(id)
    print(json.dumps({'status':state['status'],'providers':state['providers']},ensure_ascii=True),flush=True)
state=jobs.status(id);raw={};audit={}
with jobs.db() as connection:
    for name in ('naver','google'):
        child=state['providers'][name].get('id')
        if not child:
            audit[name]={'not_started':True};continue
        rows=[{'number':n,'request':json.loads(req),'status':status,'result':json.loads(data) if data else None}
              for n,req,status,data in connection.execute('SELECT n,request,status,result FROM browser_tasks WHERE run=? ORDER BY n',(child,))]
        assert [row['request'] for row in rows]==expected
        raw[name]=rows;coverage=[]
        for row in rows:
            req=row['request'];result=row['result'] or {}
            coverage.append({'number':row['number'],**req,'status':row['status'],
                             'valid_prices':sum(amount(x) is not None for x in result.get('observations',[])),
                             'error':result.get('error')})
        audit[name]={'expected':24,'registered':len(rows),'statuses':dict(Counter(x['status'] for x in rows)),
                     'queries_with_prices':sum(x['valid_prices']>0 for x in coverage),'coverage':coverage}
reference=r.status(state['providers']['myrealtrip']['id']) if state['providers']['myrealtrip'].get('id') else None
result={'scope':json.loads(dumps(c)),'wide_plan_only':{'external_requests':0,'requests_per_browser_provider':396,'origins':3,'destinations':2,'departure_dates':22},
        'state':state,'audit':audit,'browser_tasks':raw,'myrealtrip':reference}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'final':state['status'],'audit':{k:{field:v for field,v in value.items() if field!='coverage'} for k,value in audit.items()},
                  'roundtrip_candidates':state['ranking']['roundtrip_total'],'oneway_combinations':state['ranking']['oneway_total']},ensure_ascii=True),flush=True)

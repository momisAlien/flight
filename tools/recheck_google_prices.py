"""One explicit recheck of Google timeout queries after visible-text read fix."""
import json,sqlite3,threading
from pathlib import Path
from datetime import date
from flightcore.browser_prices import BrowserCollector
from flightcore.core import Request
from flightcore.provider_probe import ProbeStopped
from flightcore.search_price_summary import summarize
from flightcore.serde import dumps
out=Path('google-price-recheck-20261010.json')
if out.exists():raise RuntimeError('Preserving evidence')
data=json.loads(Path('price-only-live-20261010.json').read_text(encoding='utf-8'))
g=data['providers']['google']
if g['state']['status'] not in ('completed_observations','completed_partial_observations'):raise RuntimeError('No recheck after access block or active run')
with sqlite3.connect('file:price-only-live-20261010.db?mode=ro',uri=True) as db:
    tasks=[{'number':n,'request':json.loads(req),'status':status,'result':json.loads(raw) if raw else None} for n,req,status,raw in db.execute('SELECT n,request,status,result FROM browser_tasks WHERE run=? ORDER BY n',(g['run'],))]
failures=[t for t in tasks if t['status'] in ('unverified_response','schema_changed')]
c=BrowserCollector('google',threading.Event());attempts=[]
try:
    c.open()
    for task in failures:
        req=dict(task['request']);req['departure']=date.fromisoformat(req['departure'])
        if req.get('return_date'):req['return_date']=date.fromisoformat(req['return_date'])
        attempt={'number':task['number'],'original_status':task['status']}
        try:
            result=c.collect(Request(**req));result['evaluated_conditions']=data['conditions']
            task.update(status='observed_partial',result=result);attempt.update(status='observed_partial',cards=len(result['observations']))
        except ProbeStopped as error:
            attempt.update(status=error.status,error=error.detail)
            if error.status not in ('unverified_response','schema_changed'):
                attempts.append(attempt);break
        attempts.append(attempt)
        print(json.dumps(attempt,ensure_ascii=True),flush=True)
finally:
    c.close();out.write_text(json.dumps({'original_file':'price-only-live-20261010.json','attempts':attempts,'effective_tasks':tasks,'prices':summarize('google',tasks)},ensure_ascii=False,indent=2),encoding='utf-8')

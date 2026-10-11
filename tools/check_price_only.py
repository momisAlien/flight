"""Example range price-only validation on both providers; isolated database."""
from pathlib import Path
from datetime import date
import json,time
from flightcore.browser_jobs import BrowserJobs
from flightcore.core import Conditions
from flightcore.serde import dumps
output=Path('price-only-live-20261010.json');dbpath=output.with_suffix('.db')
if output.exists() or dbpath.exists():raise RuntimeError('Preserving evidence')
c=Conditions(('ICN',),('NRT',),date(2026,10,12),date(2026,10,15),5)
jobs=BrowserJobs(str(dbpath));result={'conditions':json.loads(dumps(c)),'providers':{}}
for provider in ('naver','google'):
    run=jobs.start(c,provider)
    while jobs.thread.is_alive():
        jobs.thread.join(10)
        status=jobs.status(run)
        print(json.dumps({'provider':provider,'status':status['status'],'observed':status['observed'],'total':status['total'],'pending':status['not_attempted']}),flush=True)
    result['providers'][provider]={'run':run,'state':jobs.status(run),'prices':jobs.price_summary(run)}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'provider':provider,'finished':jobs.status(run)['status'],'priced':result['providers'][provider]['prices']['queries_with_price']}),flush=True)

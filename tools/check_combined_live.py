from pathlib import Path
from datetime import date
import json,sys
from flightcore.browser_jobs import BrowserJobs
from flightcore.reference_jobs import ReferenceJobs
from flightcore.combined_jobs import CombinedJobs
from flightcore.core import Conditions
out=Path(sys.argv[1] if len(sys.argv)>1 else 'combined-live-20261010.json');db=out.with_suffix('.db')
if out.exists() or db.exists():raise RuntimeError('Preserving prior evidence')
b=BrowserJobs(str(db));r=ReferenceJobs(str(db));jobs=CombinedJobs(str(db),b,r)
c=Conditions(('ICN',),('NRT',),date(2026,10,12),date(2026,10,13),5)
id=jobs.start(c)
while jobs.thread.is_alive():
 jobs.thread.join(15);state=jobs.status(id)
 print(json.dumps({'status':state['status'],'providers':state['providers'],'rt':state['ranking']['roundtrip_total'],'ow':state['ranking']['oneway_total']},ensure_ascii=True),flush=True)
state=jobs.status(id);out.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')

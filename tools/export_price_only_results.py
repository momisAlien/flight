"""Export current price summaries, preserving initial and recheck evidence."""
import json,sqlite3
from pathlib import Path
from flightcore.search_price_summary import summarize
initial=json.loads(Path('price-only-live-20261010.json').read_text(encoding='utf-8'))
result={'conditions':initial['conditions'],'providers':{},'basis':'search_display_price','baggage_and_cabin_matching':False}
with sqlite3.connect('file:price-only-live-20261010.db?mode=ro',uri=True) as db:
    for provider,record in initial['providers'].items():
        tasks=[{'number':n,'request':json.loads(req),'status':status,'result':json.loads(raw) if raw else None} for n,req,status,raw in db.execute('SELECT n,request,status,result FROM browser_tasks WHERE run=? ORDER BY n',(record['run'],))]
        entry={'initial_summary':summarize(provider,tasks),'tasks':tasks}
        retry=Path('google-price-recheck-20261010.json')
        if provider=='google' and retry.exists():
            updated=json.loads(retry.read_text(encoding='utf-8'));tasks=updated['effective_tasks'];entry['recheck_attempts']=updated['attempts'];entry['effective_tasks']=tasks
        entry['summary']=summarize(provider,tasks);result['providers'][provider]=entry
result['total_queries']=sum(p['summary']['total_queries'] for p in result['providers'].values())
result['queries_with_price']=sum(p['summary']['queries_with_price'] for p in result['providers'].values())
Path('PRICE_ONLY_RESULTS_20261010.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for provider,record in result['providers'].items():
    print(json.dumps({'provider':provider,'priced':record['summary']['queries_with_price'],'comparisons':record['summary']['comparisons']},ensure_ascii=True))

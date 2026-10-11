"""Explicit regression audit of the nine still-unattempted recorded cards.

Not a production cap: BrowserJobs always schedules every observed OW card.
"""
import json
import threading
from pathlib import Path
from datetime import date
from flightcore.browser_prices import BrowserCollector
from flightcore.core import Request
from flightcore.provider_probe import ProbeStopped


def main():
    previous=json.loads(Path('google-batch-details-final-20261007.json').read_text(encoding='utf-8'))
    pending=[(i,row) for i,row in enumerate(previous['items'][0]['result']['observations']) if row.get('detail_status')=='pending']
    output=Path('google-remaining-details-20261007.json')
    if output.exists():raise ValueError('Audit output already exists')
    evidence={'scope':'previously unattempted cards only','total':len(pending),'results':[],'status':'running'}
    request=Request('outbound','ICN','NRT',date(2026,12,10))
    c=BrowserCollector('google',threading.Event())
    try:
        c.open()
        for index,row in pending:
            fresh=c.collect(request)
            if sum(r['text']==row['text'] for r in fresh['observations'])!=1:
                raise ProbeStopped('unverified_response','recorded card changed or ambiguous')
            detail=c.selected_google_details(request,row['text'])
            evidence['results'].append({'original_index':index,'seller_detail':detail})
            output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'observed':len(evidence['results']),'total':len(pending)}),flush=True)
            c.cancel.wait(2)
        evidence['status']='completed_recorded_remaining'
    except ProbeStopped as error:
        evidence['status']=error.status
    finally:
        c.close()
        output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()

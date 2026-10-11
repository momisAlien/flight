"""One ordinary public search to diagnose missing cards; never bypass access checks."""
import json,threading,sys
from pathlib import Path
from datetime import date
from flightcore.browser_prices import BrowserCollector,GOOGLE_ROWS
from flightcore.core import Request
from flightcore.provider_probe import ProbeStopped

out=Path(sys.argv[1] if len(sys.argv)>1 else 'combined-google-diagnostic-20261010.json')
if out.exists():raise RuntimeError('Preserving prior evidence')
prior=json.loads(Path('combined-live-20261010.json').read_text(encoding='utf-8'))
if prior['providers']['google']['status'] not in ('completed_observations','completed_partial_observations'):
    raise RuntimeError('No diagnostic after access block or unfinished search')
c=BrowserCollector('google',threading.Event());result={}
try:
    c.open()
    try:
        data=c.collect(Request(kind='outbound',origin='ICN',destination='NRT',departure=date(2026,10,12)))
        result={'status':'observed_partial','cards':len(data['observations']),'observations':data['observations']}
    except ProbeStopped as error:
        result={'status':error.status,'error':error.detail}
        if error.status not in ('unverified_response','schema_changed'):raise
    # The same allow-host, login and CAPTCHA checks precede reading the public page.
    body=c.check(fast=True)
    result.update(url=c.driver.current_url,body_excerpt=body[:18000],selector_count=len(c.driver.find_elements('css selector',GOOGLE_ROWS)),visible_count=len(c.visible_cards()))
    c.driver.save_screenshot(str(out.with_suffix('.png')))
finally:
    c.close();out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('body_excerpt','observations')},ensure_ascii=True))

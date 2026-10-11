"""Inspect one public itinerary detail expansion without opening a seller."""
import argparse
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from flightcore.browser_prices import BrowserCollector
from flightcore.core import Request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output)
    if output.exists():parser.error('새 출력 파일명을 지정하세요')
    detail=json.loads(Path(args.input).read_text(encoding='utf-8'))
    url=detail['url']
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='flight.naver.com' or not parsed.path.startswith('/flights/international/detail/'):
        parser.error('관찰된 네이버 공개 항공권 상세 URL만 지원합니다')
    collector=BrowserCollector('naver',threading.Event())
    try:
        collector.open();collector.driver.get(url)
        legs=parsed.path.split('/')[4:]
        origin,destination,departure=legs[0].split('-')
        return_date=datetime.strptime(legs[1].split('-')[2],'%Y%m%d').date() if len(legs)==2 else None
        request=Request('roundtrip' if return_date else 'outbound',origin,destination,datetime.strptime(departure,'%Y%m%d').date(),return_date)
        collector.read_naver_sellers(request,detail['selected_label'])
        buttons=[e for e in collector.driver.find_elements('tag name','button') if e.is_displayed() and e.text=='상세보기']
        before=collector.check()
        if not buttons:raise RuntimeError('No visible itinerary details button')
        buttons[0].send_keys(Keys.ENTER)
        WebDriverWait(collector.driver,15).until(lambda _:collector.check()!=before)
        previous=None;stable=0;deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            body=collector.check()
            stable=stable+1 if previous==body else 0
            if stable>=2:break
            previous=body;time.sleep(1)
        else:raise RuntimeError('Unstable visible detail')
        output.write_text(json.dumps({'url':collector.driver.current_url,'text':body},ensure_ascii=False,indent=2),encoding='utf-8')
        collector.driver.save_screenshot(str(output.with_suffix('.png')))
        print(json.dumps({'visible_details_buttons':len(buttons),'output':str(output)}))
    finally:collector.close()


if __name__=='__main__':main()

"""Measure rendered-text reads on one public search, without selecting fares."""
import json
import threading
import time
from datetime import date
from pathlib import Path
from flightcore.browser_prices import BrowserCollector, BLOCK_TEXT
from flightcore.core import Request


def main():
    output=Path('naver-dom-timing-20261008.json')
    if output.exists():raise ValueError('Evidence already exists')
    collector=BrowserCollector('naver',threading.Event())
    try:
        collector.open()
        snapshot=collector.collect(Request('roundtrip','ICN','NRT',date(2026,12,10),date(2026,12,15)))
        start=time.monotonic();standard=collector.driver.find_element('tag name','body').text
        standard_seconds=time.monotonic()-start
        start=time.monotonic();native=collector.driver.execute_script('return document.body.innerText')
        native_seconds=time.monotonic()-start
        markers=(*BLOCK_TEXT,'결과 로드 중','항공편 검색중')
        evidence={'cards':len(snapshot['observations']),'webdriver_text_seconds':standard_seconds,
                  'native_innertext_seconds':native_seconds,
                  'control_marker_presence_equal':all((m in standard.lower())==(m in native.lower()) for m in markers),
                  'same_text':standard==native,'standard_chars':len(standard),'native_chars':len(native)}
        output.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(json.dumps(evidence))
    finally:collector.close()


if __name__=='__main__':main()

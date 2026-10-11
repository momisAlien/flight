"""Explicit live public-page check. No seller redirect or booking action."""
import json
import argparse
import threading
from datetime import date
from pathlib import Path
from selenium.webdriver.common.keys import Keys
from flightcore.browser_prices import BrowserCollector, GOOGLE_ROWS
from flightcore.core import Request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--index',type=int,default=0)
    parser.add_argument('--output',default='google-seller-dom-check-20261006.json')
    args=parser.parse_args()
    c = BrowserCollector('google', threading.Event())
    try:
        c.open()
        result = c.collect(Request('outbound', 'ICN', 'NRT', date(2026,12,10)))
        label = result['observations'][args.index]['text']
        element = next(el for el in c.driver.find_elements('css selector', GOOGLE_ROWS)
                       if el.get_attribute('aria-label') == label)
        element.send_keys(Keys.ENTER)
        for _ in range(30):
            body = c.check()
            if '예약 옵션' in body:
                break
            c.cancel.wait(1)
        else:
            raise RuntimeError('booking options not observed')
        # Visible DOM only; inspect ancestors of the displayed seller action.
        groups = []
        for el in c.driver.find_elements('xpath', '//*[text()="계속"]'):
            if el.is_displayed():
                groups.append([el.find_element('xpath', '/'.join(['..']*i)).text for i in range(1,5)])
        out = {'selected_label': label, 'body': body, 'groups': groups}
        Path(args.output).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'groups':groups},ensure_ascii=False))
    finally:
        c.close()


if __name__ == '__main__': main()

"""Public itinerary selection audit; no seller/booking/login actions."""
import json
import argparse
import threading
import time
from datetime import date
from pathlib import Path
from selenium.webdriver.common.keys import Keys
from flightcore.browser_prices import BrowserCollector, NAVER_ROWS
from flightcore.core import Request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--offers',action='store_true')
    args=parser.parse_args()
    c=BrowserCollector('naver',threading.Event())
    try:
        c.open()
        result=c.collect(Request('roundtrip','ICN','NRT',date(2026,12,10),date(2026,12,15)))
        index=next(i for i,row in enumerate(result['observations']) if row['conditional'] is False)
        card=c.driver.find_elements('css selector',NAVER_ROWS)[index]
        label=card.text
        card.find_element('css selector','button[class*="combination_select_schedule__"]').send_keys(Keys.ENTER)
        if args.offers:
            from selenium.webdriver.support.ui import WebDriverWait
            offer=WebDriverWait(c.driver,20).until(lambda d:card.find_elements('css selector','button[class*="item_anchor__"]'))[0]
            c.check()
            offer.send_keys(Keys.ENTER)
            WebDriverWait(c.driver,30).until(lambda d:'/detail/' in d.current_url)
            c.check()
            more=c.driver.find_elements('css selector','button[class*="detail_more__"]')
            if more and more[0].is_displayed():
                more[0].send_keys(Keys.ENTER)
        previous=None;stable=0
        for _ in range(45):
            body=c.check()
            stable=stable+1 if body==previous else 0
            if stable>=3:break
            previous=body;time.sleep(1)
        buttons=c.driver.execute_script("return [...document.querySelectorAll('button')].filter(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden').map(e=>({text:e.innerText,class:e.className,label:e.getAttribute('aria-label')}))")
        images=c.driver.execute_script("return [...document.querySelectorAll('img')].filter(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden').map(e=>({alt:e.alt,parent:e.parentElement.className,text:e.parentElement.innerText}))")
        seller_nodes=c.driver.execute_script("return [...document.querySelectorAll('button[class*=detail_detail_anchor__]')].filter(e=>e.getClientRects().length).map(e=>{let p=e;const parents=[];for(let i=0;i<4 && p;i++,p=p.parentElement)parents.push({tag:p.tagName,cls:p.className,text:p.innerText});return {label:e.getAttribute('aria-label'),parents}})")
        result={'selected_card':label,'url':c.driver.current_url,'body':body,'buttons':buttons,'images':images,'seller_nodes':seller_nodes}
        name='naver-offers-expanded-20261007' if args.offers else 'naver-detail-inspection-20261007'
        Path(name+'.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        c.driver.save_screenshot(name+'.png')
        print(json.dumps({'status':'inspected','buttons':len(buttons)}),flush=True)
    finally:c.close()


if __name__=='__main__':main()

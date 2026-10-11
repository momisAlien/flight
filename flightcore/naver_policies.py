"""Conservative parsing of the public seller-linked Naver policy dialog."""
import re


def parse_policy(text):
    result={'status':'unverified','raw_text':text,'segments':[],
            'comparison_eligible':False,'notice':'판매처 규정 창 표시 정보 · 결제 총액·전 구간 적용 확정 아님'}
    start=re.search(r'(?:^|\n)수하물\n(?=[A-Z0-9]{2,3}\d{3,4}\s)',text)
    if not start:return result
    body=text[start.end():].split('기내 수하물 :',1)[0].split('\n마일리지',1)[0].strip()
    pattern=r'([A-Z0-9]{2,3}\d{3,4}) ([^\n]+ - [^\n]+)\n타입\s+수량 \(무게\)\n기내 수하물\s+([^\n]+)\n위탁 수하물\s+([^\n]+)'
    matches=list(re.finditer(pattern,body))
    if not matches or re.sub(pattern,'',body).strip():return result
    for m in matches:
        item={'flight_number':m[1],'route_label':m[2]}
        for key,value in [('cabin',m[3]),('checked',m[4])]:
            quantity=re.fullmatch(r'([1-9]\d*)pc, ([1-9]\d*(?:\.\d+)?)kg',value.strip())
            item[key]={'raw':value.strip(),'pieces':int(quantity[1]) if quantity else None,
                       'displayed_weight_kg':quantity[2] if quantity else None,
                       'status':'quantity_observed' if quantity else 'unverified',
                       'weight_scope':'unverified','allowance_verified':False}
        result['segments'].append(item)
    result['status']='observed'
    return result


def collect_policies(collector,detail):
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import StaleElementReferenceException
    from .provider_probe import ProbeStopped
    from datetime import datetime,timezone
    import time
    driver=collector.driver
    selector='div[class^="container_PolicyModalContainer__"]'
    def dialogs():return [e for e in driver.find_elements('css selector',selector) if e.is_displayed()]
    def check():
        collector.check()
        if driver.current_url!=detail['url']:raise ProbeStopped('access_stopped','규정 확인 중 예상 밖 페이지 이동')
    for offer in detail['offers']:
        check()
        if dialogs():raise ProbeStopped('unverified_response','기존 규정 창이 열려 있어 판매처를 구분할 수 없습니다')
        anchors=[e for e in driver.find_elements('css selector','button[class*="detail_detail_anchor__"]') if e.is_displayed() and e.get_attribute('aria-label')==offer['seller']+'에서 예약']
        policy={'status':'unavailable','segments':[],'comparison_eligible':False}
        offer['fare_policy']=policy
        if len(anchors)!=1:
            policy['status']='ambiguous_seller';continue
        buttons=[e for e in anchors[0].find_element('xpath','..').find_elements('tag name','button') if e.is_displayed() and e.text.strip()=='상세규정']
        if not buttons:continue
        if len(buttons)!=1:
            policy['status']='ambiguous_control';continue
        buttons[0].send_keys(Keys.ENTER)
        previous=None;stable=0;modal=None
        deadline=time.monotonic()+min(collector.timeout,15)
        while time.monotonic()<deadline:
            check();found=dialogs()
            if len(found)>1:raise ProbeStopped('unverified_response','규정 창이 여러 개라서 판매처 규정을 확정할 수 없습니다')
            if found:
                modal=found[0]
                try:text=modal.text
                except StaleElementReferenceException:continue
                stable=stable+1 if text==previous else 0;previous=text
                if stable>=2 and '항공권 규정' in text and '수하물' in text:
                    policy.update(parse_policy(text));break
            if collector.cancel.wait(.5):raise ProbeStopped('cancelled','사용자가 중단했습니다')
        else:policy['status']='unverified_response'
        policy.update(seller=offer['seller'],url=driver.current_url,observed_at=datetime.now(timezone.utc).isoformat())
        check();found=dialogs()
        if len(found)!=1:raise ProbeStopped('unverified_response','규정 창 종료 확인 실패')
        closes=[e for e in found[0].find_elements('css selector','button[aria-label="닫기"]') if e.is_displayed()]
        if len(closes)!=1:raise ProbeStopped('unverified_response','규정 창 닫기 버튼 미확인')
        closes[0].send_keys(Keys.ENTER)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            check()
            if not dialogs():break
            if collector.cancel.wait(.25):raise ProbeStopped('cancelled','사용자가 중단했습니다')
        else:raise ProbeStopped('unverified_response','규정 창이 닫히지 않아 다음 판매처 조회 중단')
    return detail

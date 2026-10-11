"""Experimental visible-page collectors. No stealth, proxies or session reuse.

Search observations are deliberately NOT Quote objects: advertised round-trip
prices may be separate tickets, and do not prove seller/baggage/final totals.
"""
from datetime import date, datetime, timezone
import re
import time
from urllib.parse import urlsplit

from .provider_probe import ProbeStopped

GOOGLE_ROWS = '[role="link"][aria-label*="항공편 선택"]'
NAVER_ROWS = '[class*="combination_ConcurrentItemContainer__"]'
BLOCK_TEXT = ("unusual traffic", "our systems have detected", "verify you are human",
              "access denied", "비정상적인 접근", "접근이 제한", "자동입력 방지")


def search_loading(provider, body, has_cards=False):
    # Google retains an accessibility loading announcement even after its
    # results count and cards are rendered. A stable visible-card snapshot is
    # sufficient for partial observations even if that announcement persists.
    # collect() still requires repeated identical cards and checks access first.
    if provider == 'google' and (has_cards or re.search(r'결과\s+[1-9][\d,]*개가\s+반환되었습니다', body)):
        return False
    return any(word in body for word in ('결과 로드 중', '항공편 검색중'))


def validate(c, provider):
    if provider not in ("google", "naver"):
        raise ValueError("지원하지 않는 브라우저 공급사입니다")
    if c.start < date.today():
        raise ValueError("과거 출발일은 조회할 수 없습니다")
    if set(c.origins) & set(c.destinations):
        raise ValueError("출발 공항과 목적지 공항이 겹칩니다")
    if c.passengers.adults != 1 or c.passengers.children or c.passengers.infants or c.cabin != "economy":
        raise ValueError("실험 조회는 성인 1명·일반석만 검증 대상으로 지원합니다")
    if c.baggage != "none_requested" or c.allow_origin_change or c.allow_destination_change or c.arrival_expansion:
        raise ValueError("실험 조회는 수하물 추가·공항 변경·도착일 확장을 아직 지원하지 않습니다")


def search_url(provider, request):
    if provider == "google":
        from fast_flights import FlightQuery, Passengers, create_query
        flights = [FlightQuery(date=request.departure.isoformat(), from_airport=request.origin,
                               to_airport=request.destination)]
        if request.return_date:
            flights.append(FlightQuery(date=request.return_date.isoformat(),
                                       from_airport=request.return_origin or request.destination,
                                       to_airport=request.return_destination or request.origin))
        return create_query(flights=flights, passengers=Passengers(adults=1), seat="economy",
                            trip="round-trip" if request.return_date else "one-way",
                            currency="KRW", language="ko").url()
    if provider != "naver":
        raise ValueError("지원하지 않는 공급사입니다")
    url = f"https://flight.naver.com/flights/international/{request.origin}-{request.destination}-{request.departure:%Y%m%d}"
    if request.return_date:
        url += f"/{request.destination}-{request.origin}-{request.return_date:%Y%m%d}"
    return url + "?adult=1&fareType=Y"


def google_row(label):
    price = re.search(r"(?:최저\s*)?([\d,]+) 대한민국 원", label)
    if "항공편 선택" not in label:
        raise ValueError("Google 가격 문구가 바뀌었습니다")
    amount = int(price[1].replace(",", "")) if price else None
    if amount is not None and amount <= 0:
        raise ValueError("가격이 유효하지 않습니다")
    return {"amount": amount, "currency": "KRW" if price else None, "text": label,
            "price_status": "observed" if price else "unverified",
            "ticket_kind": "separate_tickets" if "따로 구입" in label else "unverified",
            "price_scope": "roundtrip_from" if "왕복" in label else "oneway_from",
            "conditional": None, "comparison_eligible": False}


def google_itinerary_key(label):
    """Exclude only the recognized changing price prefix, keeping the route,
    airline, dates, times and stop wording for conservative unique matching.
    This does not identify a fare family or certify a final ticket price.
    """
    prefix = r'^(?:최저가는 [\d,]+ 대한민국 원입니다\.|(?:총 )?가격 정보가 제공되지 않습니다\.)\s*'
    return re.sub(r'\s+', ' ', re.sub(prefix, '', label)).strip()


def naver_row(text):
    prices = re.findall(r"(왕복|편도)\s*([\d,]+)\s*원", text)
    if len(prices) != 1:
        raise ValueError("네이버 가격 카드에 운임이 없거나 여러 개입니다")
    amount = int(prices[0][1].replace(",", ""))
    if amount <= 0:
        raise ValueError("가격이 유효하지 않습니다")
    # An all-payment label is not proof of a single-ticket RT fare.
    conditional = "성인/모든 결제수단" not in text
    return {"amount": amount, "currency": "KRW", "text": text,
            "ticket_kind": "unverified", "price_scope": "roundtrip_from" if prices[0][0] == "왕복" else "oneway_from",
            "conditional": conditional, "comparison_eligible": False}


def naver_itinerary_key(label):
    # The public card's CO2 badge can disappear between loads. It is not an
    # itinerary or fare condition. Preserve airline, schedule and payment text;
    # any resulting duplicates still require rejection by the caller.
    label='\n'.join(line for line in label.splitlines() if not re.fullmatch(r'CO2 \d+%',line.strip()))
    return re.sub(r'\s+',' ',re.sub(r'(왕복|편도)\s*[\d,]+\s*원~?',r'\1 PRICE',label)).strip()


def naver_payment_label(label):
    labels = re.findall(r'^성인/[^\r\n]+$', label, re.MULTILINE)
    if len(labels) != 1:
        raise ValueError('네이버 검색 카드의 결제 조건을 유일하게 확인하지 못했습니다')
    return labels[0].strip()


def naver_navigation_key(label):
    """Navigation only: never establishes equal fares or discount eligibility.

    A teaser's payment condition may change. Match the remaining itinerary
    uniquely, then independently require all-payment seller prices in detail.
    """
    payment = naver_payment_label(label)
    label = naver_card_header(label)
    lines = [line for line in label.splitlines() if line.strip() not in ('최저가','예약 많은','많이 찾는','CO2 평균배출','상세 여정을 확인해보세요')]
    return naver_itinerary_key('\n'.join('__PAYMENT__' if line.strip()==payment else line for line in lines))


def naver_card_header(label):
    """Expanded cards append payment options after the original teaser."""
    match = re.search(r'(?:왕복|편도)\s*[\d,]+\s*원~?',label)
    if not match:
        raise ValueError('네이버 일정 카드의 검색 가격 영역 미확인')
    return label[:match.end()]


class BrowserCollector:
    def __init__(self, provider, cancel, driver=None, timeout=60):
        self.provider, self.cancel, self.timeout = provider, cancel, timeout
        self.driver = driver

    def open(self):
        if self.driver is None:
            try:
                from selenium import webdriver
            except ImportError:
                raise ProbeStopped("setup_required", "requirements-browser.txt를 설치하세요") from None
            # Standard headed Chrome and a fresh temporary profile. Never connect
            # to the user's signed-in browser or change automation fingerprints.
            self.driver = webdriver.Chrome()
            self.driver.set_page_load_timeout(self.timeout)

    def close(self):
        if self.driver is not None:
            self.driver.quit()

    def check(self, fast=False):
        if self.cancel.is_set():
            raise ProbeStopped("cancelled", "사용자가 중단했습니다")
        url = urlsplit(self.driver.current_url)
        expected = "www.google.com" if self.provider == "google" else "flight.naver.com"
        if url.hostname != expected or any(p in url.path.lower() for p in ("/sorry", "/unsupported", "captcha", "login")):
            raise ProbeStopped("access_stopped", "로그인·지원 안 됨·예상 밖 이동에서 중단했습니다")
        # Only search-page control checks use native rendered text. Seller
        # parsers continue using the format they were validated against.
        body = (self.driver.execute_script('return document.body.innerText')
                if fast else self.driver.find_element("tag name", "body").text)
        if any(marker in body.lower() for marker in BLOCK_TEXT):
            raise ProbeStopped("access_stopped", "차단·사람 확인 화면에서 중단했습니다")
        challenges = self.driver.find_elements("css selector", 'iframe[src*="recaptcha"],iframe[src*="hcaptcha"],input[name="captcha"],input[type="password"]')
        if any(item.is_displayed() for item in challenges):
            raise ProbeStopped("access_stopped", "로그인·CAPTCHA 화면에서 중단했습니다")
        return body

    def visible_cards(self):
        """One DOM read of rendered cards, not app state or network responses.

        Hundreds of per-element WebDriver round trips can exceed the search
        timeout while reading one snapshot. Chrome's visibility check excludes
        hidden clones; all visible duplicates are still retained.
        """
        selector = GOOGLE_ROWS if self.provider == 'google' else NAVER_ROWS
        return self.driver.execute_script("""
            return Array.from(document.querySelectorAll(arguments[0]))
              .filter(el => el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))
              .map(el => ({element:el, text:arguments[1] === 'google'
                ? el.getAttribute('aria-label')
                : el.innerText.replace(/\\u00a0/g,' ').trim()}));
        """, selector, self.provider)

    def selected_google_details(self, request, label):
        """Select one exact observed OW itinerary. Never click seller Continue."""
        from selenium.webdriver.common.keys import Keys
        from .seller_details import google_details
        if self.provider != 'google' or request.return_date:
            raise ValueError('상세 확인은 Google 편도 항공편만 지원합니다')
        self.check()
        matches = [row['element'] for row in self.visible_cards() if row['text'] == label]
        if len(matches) != 1:
            raise ProbeStopped('unverified_response', '선택한 항공편을 유일하게 식별하지 못했습니다')
        matches[0].send_keys(Keys.ENTER)
        deadline = time.monotonic() + self.timeout
        previous, stable = None, 0
        while time.monotonic() < deadline:
            body = self.check()
            stable = stable + 1 if body == previous else 0
            if '예약 옵션' in body and stable >= 2:
                try:
                    detail = google_details(body)
                except ValueError as error:
                    # Parser messages are fixed local strings, never raw HTTP
                    # errors, page contents, cookies or authentication details.
                    raise ProbeStopped('schema_changed', f'예약 옵션 분석 실패: {error}') from None
                detail.update(source='google', observed_at=datetime.now(timezone.utc).isoformat(),
                              url=self.driver.current_url, selected_label=label)
                return detail
            previous = body
            if self.cancel.wait(1):
                raise ProbeStopped('cancelled', '사용자가 중단했습니다')
        raise ProbeStopped('unverified_response', '예약 옵션을 시간 내 확인하지 못했습니다')

    def selected_naver_details(self, request, label):
        """Open all-payment seller listings, never click a seller booking link."""
        from selenium.webdriver.common.keys import Keys
        from selenium.common.exceptions import StaleElementReferenceException
        if self.provider != 'naver':
            raise ValueError('네이버 상세 화면이 필요합니다')
        payment = naver_payment_label(label)
        self.check(fast=True)
        matches = [row['element'] for row in self.visible_cards() if row['text'] == label]
        if len(matches) != 1:
            raise ProbeStopped('unverified_response','네이버 일정을 유일하게 식별하지 못했습니다')
        card = matches[0]
        card.find_element('css selector','button[class*="combination_select_schedule__"]').send_keys(Keys.ENTER)
        expected = urlsplit(search_url('naver',request)).path.replace('/international/','/international/detail/')
        deadline = time.monotonic() + self.timeout
        chosen = False
        expanded_options = set()
        while time.monotonic() < deadline and not chosen:
            self.check(fast=True)
            if urlsplit(self.driver.current_url).path == expected:
                chosen = True
                break
            try:
                cards = []
                for row in self.visible_cards():
                    try:
                        same = naver_navigation_key(naver_card_header(row['text'])) == naver_navigation_key(label)
                    except ValueError:
                        continue
                    if same: cards.append(row['element'])
                if not cards:
                    if self.cancel.wait(1):raise ProbeStopped('cancelled','사용자가 중단했습니다')
                    continue
                if len(cards) != 1:
                    raise ProbeStopped('unverified_response','확장한 네이버 일정 식별 미확인')
                options = []
                for button in cards[0].find_elements('css selector','button[class*="item_anchor__"]'):
                    if not button.is_displayed():continue
                    parent = button.find_element('xpath','..')
                    try: condition = naver_row(parent.text)
                    except ValueError: continue
                    if condition['conditional'] is False:
                        options.append(button)
                if len(options)>1:
                    raise ProbeStopped('unverified_response','모든 결제수단 선택지가 여러 개여서 임의로 선택하지 않았습니다')
                if options:
                    options[0].send_keys(Keys.ENTER);chosen=True
                else:
                    more = [button for button in cards[0].find_elements('tag name','button')
                            if button.is_displayed() and re.fullmatch(r'\d+개\s*요금조건 더보기',button.text)]
                    if len(more)>1:
                        raise ProbeStopped('unverified_response','요금조건 더보기 버튼이 여러 개여서 선택하지 않았습니다')
                    if more:
                        marker=(more[0].text,len(cards[0].find_elements('css selector','button[class*="item_anchor__"]')))
                        if marker not in expanded_options:
                            expanded_options.add(marker)
                            more[0].send_keys(Keys.ENTER)
            except StaleElementReferenceException:
                pass
            if not chosen and self.cancel.wait(1):
                raise ProbeStopped('cancelled','사용자가 중단했습니다')
        if not chosen:
            raise ProbeStopped('unverified_response','모든 결제수단 요금 선택을 확인하지 못했습니다')
        detail = self.read_naver_sellers(request,label)
        detail['search_payment_condition'] = payment
        return detail

    def read_naver_sellers(self,request,label):
        """Read the already selected public detail page; no seller redirect."""
        from selenium.webdriver.common.keys import Keys
        from selenium.common.exceptions import StaleElementReferenceException
        from .seller_details import naver_offer
        from .observed_schedules import assess
        if self.provider!='naver':raise ValueError('네이버 상세 화면이 필요합니다')
        expected = urlsplit(search_url('naver',request)).path.replace('/international/','/international/detail/')
        previous, stable, expected_count = None, 0, 0
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            body = self.check()
            if urlsplit(self.driver.current_url).path != expected:
                if self.cancel.wait(1):raise ProbeStopped('cancelled','사용자가 중단했습니다')
                continue
            if '항공권 판매사 선택\n성인/모든 결제수단' not in body:
                if self.cancel.wait(1):raise ProbeStopped('cancelled','사용자가 중단했습니다')
                continue
            try:
                anchors = [e for e in self.driver.find_elements('css selector','button[class*="detail_detail_anchor__"]') if e.is_displayed()]
                rows = [(e.get_attribute('aria-label'), e.find_element('xpath','..').text) for e in anchors]
                more = [e for e in self.driver.find_elements('css selector','button[class*="detail_more__"]') if e.is_displayed() and '판매사 더보기' in e.text]
                if rows and len(rows) >= expected_count and more:
                    count = re.fullmatch(r'(\d+)개 판매사 더보기',more[0].text)
                    if not count:raise ProbeStopped('schema_changed','판매사 더보기 개수 미확인')
                    expected_count = len(rows) + int(count[1])
                    more[0].send_keys(Keys.ENTER)
                    previous, stable = None, 0
                elif rows and not more and len(rows) >= expected_count:
                    stable = stable + 1 if rows == previous else 0
                    previous = rows
                    if stable >= 2:break
            except StaleElementReferenceException:
                previous, stable = None, 0
            if self.cancel.wait(1):raise ProbeStopped('cancelled','사용자가 중단했습니다')
        else:
            raise ProbeStopped('unverified_response','시간 내 전체 표시 판매사 목록 확인 실패')
        schedule = assess('naver',{'text':label},request)
        if not schedule['legs'] or any(f"{leg['departure'][11:16]}~{leg['arrival'][11:16]}" not in body for leg in schedule['legs']):
            raise ProbeStopped('unverified_response','선택 전후 일정 시각 일치 미확인')
        try: offers = [naver_offer(seller,text) for seller,text in rows]
        except ValueError as error:raise ProbeStopped('schema_changed',str(error)) from None
        detail = {'source':'naver','observed_at':datetime.now(timezone.utc).isoformat(),
                'url':self.driver.current_url,'selected_label':label,'offers':offers,
                'payment_condition':'성인/모든 결제수단','displayed_seller_list_expanded':True,
                'baggage_statements':[line for line in body.splitlines() if '수하물' in line],
                'taxes_and_mandatory_fees_stated_included':None,'baggage_allowance_verified':False,
                'checkout_verified':False,'comparison_eligible':False,'inventory_complete':False,
                'notice':'모든 결제수단의 펼친 판매사 표시 가격. 판매처별 수하물 문구만 확인. 최종 결제 금액·왕복 단일 발권·수하물 무게 미검증.'}

        from .naver_policies import collect_policies
        return collect_policies(self,detail)

    def collect(self, request):
        from selenium.common.exceptions import TimeoutException
        url = search_url(self.provider, request)
        try:
            self.driver.get(url)
        except TimeoutException:
            # Check the resulting page before treating this as a local timeout:
            # a CAPTCHA/login/access block must still stop the whole job.
            self.check()
            raise ProbeStopped('unverified_response','검색 페이지 로딩 시간 초과. 항공편 없음으로 처리하지 않습니다') from None
        deadline = time.monotonic() + self.timeout
        previous, stable = None, 0
        while time.monotonic() < deadline:
            from selenium.common.exceptions import StaleElementReferenceException
            try:
                body = self.check(fast=True)
                texts = [row['text'] for row in self.visible_cards()]
                if self.provider == 'google' and not texts and '죄송합니다. 오류가 발생했습니다.' in body:
                    raise ProbeStopped('unverified_response', 'Google 검색 화면에서 오류를 표시했습니다. 가격 미확인으로 보존합니다')
            except StaleElementReferenceException:
                # A normal re-render only: re-read the same page, never navigate
                # again or retry a blocked request.
                previous, stable = None, 0
                if self.cancel.wait(1):
                    raise ProbeStopped("cancelled", "사용자가 중단했습니다")
                continue
            loading = search_loading(self.provider, body, bool(texts))
            if texts and not loading and texts == previous:
                stable += 1
            else:
                stable = 0
            if stable >= 2:
                break
            previous = texts
            if self.cancel.wait(1):
                raise ProbeStopped("cancelled", "사용자가 중단했습니다")
        else:
            raise ProbeStopped("unverified_response", "시간 내 가격 목록을 확인하지 못했습니다. 항공편 없음으로 처리하지 않습니다")
        parser = google_row if self.provider == "google" else naver_row
        try:
            rows = [parser(text) for text in texts]
        except ValueError:
            raise ProbeStopped("schema_changed", "가격 카드 구조가 바뀌어 수집을 중단했습니다") from None
        return {"source": self.provider, "observed_at": datetime.now(timezone.utc).isoformat(),
                "search_url": url, "status": "observed_partial", "observations": rows,
                "comparison_eligible": False, "inventory_complete": False,
                "notice": "현재 로드된 검색 카드만 수집. 더보기·판매처·수하물·확정 왕복 운임 미검증. 직항·시간·소요시간·귀국 마감 필터 미적용."}

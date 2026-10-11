import unittest
from flightcore.seller_details import google_details

BODY = '편도이코노미\n무료 기내 수하물 1개\n첫 번째 위탁 수하물 유료로 이용 가능\n예약 옵션\n에어부산에서 예약항공사\n비즈니스 정보\n₩122,900\n계속\n가격에는 성인 1명의 필수 세금과 수수료가 포함됩니다.\n통화KRW'


class SellerTests(unittest.TestCase):
    def test_booking_statements_do_not_become_confirmed_fares(self):
        detail = google_details(BODY)
        self.assertEqual(detail['offers'][0]['seller'], '에어부산')
        self.assertEqual(detail['offers'][0]['amount'], 122900)
        self.assertEqual(len(detail['baggage_statements']), 2)
        self.assertTrue(detail['taxes_and_mandatory_fees_stated_included'])
        self.assertFalse(detail['comparison_eligible'])
        self.assertFalse(detail['checkout_verified'])
        self.assertFalse(detail['baggage_allowance_verified'])

    def test_unparsed_seller_or_currency_rejects_the_whole_set(self):
        for text in [BODY.replace('통화KRW','통화USD'),BODY.replace('계속','계속\n다른 업체에서 예약\n가격 미확인'),BODY.replace('₩122,900','₩0')]:
            with self.assertRaises(ValueError): google_details(text)

    def test_missing_fees_statement_stays_unknown(self):
        detail=google_details(BODY.replace('가격에는 성인 1명의 필수 세금과 수수료가 포함됩니다.',''))
        self.assertIsNone(detail['taxes_and_mandatory_fees_stated_included'])

    def test_unpriced_seller_is_preserved_without_zero_price(self):
        detail=google_details(BODY.replace('₩122,900','사이트에서 가격을 확인하세요.'))
        self.assertIsNone(detail['offers'][0]['amount'])
        self.assertIsNone(detail['offers'][0]['currency'])
        self.assertEqual(detail['offers'][0]['price_status'],'not_provided')

    def test_adjacent_sellers_are_all_parsed(self):
        extra='다른 판매처에서 예약\n₩150,000\n계속\n'
        detail=google_details(BODY.replace('가격에는',extra+'가격에는'))
        self.assertEqual(len(detail['offers']),2)

    def test_fee_note_is_preserved_and_not_used_as_ticket_price(self):
        detail=google_details(BODY.replace('비즈니스 정보','신용카드 수수료 ₩6,800 포함'))
        self.assertEqual(detail['offers'][0]['amount'],122900)
        self.assertEqual(detail['offers'][0]['seller_statements'],['신용카드 수수료 ₩6,800 포함'])

    def test_fare_families_keep_separate_prices_and_baggage(self):
        body=BODY.replace('비즈니스 정보\n₩122,900\n계속','Economy Saver\n₩122,900\n위탁 수하물 유료\n계속\nEconomy Flex\n₩180,000\n무료 위탁 수하물 1개\n계속')
        offers=google_details(body)['offers']
        self.assertEqual([offer['amount'] for offer in offers],[122900,180000])
        self.assertIn('위탁 수하물 유료',offers[0]['seller_statements'])
        self.assertNotIn('무료 위탁 수하물 1개',offers[0]['seller_statements'])
        self.assertIn('무료 위탁 수하물 1개',offers[1]['seller_statements'])

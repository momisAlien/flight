import unittest
from flightcore.seller_details import naver_offer


class NaverSellerTests(unittest.TestCase):
    def test_seller_baggage_is_bound_to_its_own_price(self):
        offer=naver_offer('NOL에서 예약','NOL\n상세규정\n무료 위탁수하물 1개(15kg)\n환불정보 확인필요\n342,000\n원')
        self.assertEqual(offer['amount'],342000)
        self.assertIn('무료 위탁수하물 1개(15kg)',offer['seller_statements'])
        self.assertFalse(offer['comparison_eligible'])

    def test_unknown_baggage_is_preserved(self):
        offer=naver_offer('Kiwi.com에서 예약','Kiwi.com\n해외업체\n위탁수하물 포함여부 확인필요\n319,436\n원')
        self.assertIn('위탁수하물 포함여부 확인필요',offer['seller_statements'])

    def test_wrong_seller_multiple_prices_or_zero_fail_closed(self):
        for text in ['다른업체\n319,436\n원','Kiwi.com\n100\n원\n200\n원','Kiwi.com\n0\n원']:
            with self.assertRaises(ValueError):naver_offer('Kiwi.com에서 예약',text)

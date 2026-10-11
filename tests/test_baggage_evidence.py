import unittest
from flightcore.baggage_evidence import baggage_evidence
from flightcore.seller_details import naver_offer, google_details
from test_seller_details import BODY

class BaggageTests(unittest.TestCase):
    def test_weight_and_pieces_are_not_final_allowance(self):
        item=baggage_evidence(['무료 위탁수하물 1개(15kg)'])['checked']
        self.assertEqual((item['state'],item['pieces'],item['displayed_weight_kg']),('included',1,'15'))
        self.assertFalse(item['allowance_verified'])
        self.assertEqual(item['weight_scope'],'unverified')

    def test_unknown_and_conditional_wording_not_guessed(self):
        for line in ['위탁수하물 포함여부 확인필요','무료 위탁수하물 1개(15kg) 일부 구간 제외','무료 위탁수하물 0개','무료 위탁수하물 1개(0kg)','무료 위탁수하물 1개 또는 유료','기본 위탁수하물 포함']:
            self.assertEqual(baggage_evidence([line])['checked']['state'],'unknown')

    def test_contradictions_and_different_allowances_remain_unknown(self):
        for lines in [['무료 위탁수하물 포함','위탁수하물 불포함'],['무료 위탁수하물 1개(15kg)','무료 위탁수하물 1개(20kg)']]:
            self.assertEqual(baggage_evidence(lines)['checked']['state'],'conflicting')
        self.assertEqual(baggage_evidence(['무료 위탁수하물 포함','위탁수하물 포함여부 확인필요'])['checked']['state'],'unknown')

    def test_cabin_and_checked_do_not_leak(self):
        result=baggage_evidence(['무료 기내 수하물 1개','위탁수하물 불포함'])
        self.assertEqual(result['cabin']['state'],'included')
        self.assertEqual(result['checked']['state'],'not_included')
        self.assertIsNone(result['cabin']['displayed_weight_kg'])

    def test_naver_offer_retains_raw_and_scopes_to_seller(self):
        row=naver_offer('TEST에서 예약','TEST\n무료 위탁수하물 1개(15kg)\n100\n원')
        self.assertEqual(row['baggage_evidence']['checked']['pieces'],1)
        self.assertEqual(row['seller_statements'],['무료 위탁수하물 1개(15kg)'])
        self.assertFalse(row['comparison_eligible'])

    def test_google_page_wide_baggage_does_not_spread_to_offers(self):
        result=google_details(BODY)
        self.assertEqual(result['offers'][0]['baggage_evidence']['cabin']['state'],'unknown')
        self.assertEqual(result['offers'][0]['baggage_evidence']['checked']['state'],'unknown')

    def test_google_fare_families_stay_separate(self):
        body=BODY.replace('비즈니스 정보\n₩122,900\n계속','위탁 수하물 유료\n₩122,900\n계속\n무료 위탁수하물 1개(15kg)\n₩180,000\n계속')
        offers=google_details(body)['offers']
        self.assertEqual([x['baggage_evidence']['checked']['state'] for x in offers],['paid','included'])

    def test_repeat_statement_preserves_evidence_without_conflict(self):
        bag=baggage_evidence(['무료 위탁수하물 포함']*2)['checked']
        self.assertEqual(bag['state'],'included')
        self.assertEqual(len(bag['evidence']),2)

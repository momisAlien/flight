"""Synthetic input exists exclusively in automated tests, never production seeds."""
import csv
import io
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_core import quote,back,leg,conditions,NOW
from flightcore.review import assess,coverage,review_stream,quote_reasons
from flightcore.bulk import COLUMNS,parse_csv,template
from flightcore.serde import dumps
from flightcore.core import Passengers,TimeWindow
from flightcore.store import Store
from flightcore.server import create_app,server_parser,lan_address,main
from flightcore.jobs import Jobs


def csv_text(id='csv-test',stops='미확인',taxes='미확인',baggage='미확인'):
    row=dict.fromkeys(COLUMNS,'')
    row.update({'입력ID':id,'여정':'편도','구간번호':'1','출발공항':'ICN','도착공항':'NRT',
       '출발현지시각':'2026-12-10T08:00:00+09:00','도착현지시각':'2026-12-10T10:00:00+09:00',
       '항공사':'TEST ONLY','중간기착':stops,'총액':'100','통화':'KRW','출처':'TEST ONLY','판매처':'TEST SELLER',
       '조회시각':NOW.isoformat(),'링크':'https://example.invalid','성인':'1','소아':'0','유아':'0','좌석':'economy',
       '수하물조건':'none_requested','세금포함':taxes,'필수수수료포함':'미확인','수하물확인':baggage})
    output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=COLUMNS);writer.writeheader();writer.writerow(row)
    return output.getvalue()


class ReviewTests(unittest.TestCase):
    def test_all_reasons_visible_at_once(self):
        q=replace(quote(legs=(leg(hour=23,stops=None),)),baggage_confirmed=False,taxes_included=None,mandatory_fees_included=None)
        b=replace(back(),currency='JPY')
        r=assess((q,b),conditions(),NOW)
        for reason in ('수하물 미확인','숙박일수 불일치','통화 불일치 · 합산 안 함','가는 편: 직항 미확인 (중간 기착 미확인)','세금 미확인 또는 미포함','필수 수수료 미확인'):
            self.assertIn(reason,r['reasons'])
        self.assertIsNone(r['total'])
        self.assertFalse(r['rankable'])

    def test_none_requested_keeps_existing_baggage_policy(self):
        r=assess((replace(quote(),baggage_confirmed=False),back()),conditions(),NOW)
        self.assertIn('수하물 미확인',r['reasons'])

    def test_unknown_direct_never_silently_dropped(self):
        q=quote(legs=(leg(stops=None),))
        rows=list(review_stream([],lambda:iter([q,back()]),conditions(),NOW))
        self.assertEqual(len(rows),1)
        self.assertIn('가는 편: 직항 미확인 (중간 기착 미확인)',rows[0]['reasons'])

    def test_time_filters_run_before_pairing_and_preserve_excluded_inputs(self):
        c=conditions(outbound_window=TimeWindow(time(6),time(12)),inbound_window=TimeWindow(time(15),time(23)))
        late=quote('late',(leg(hour=14),))
        early_back=quote('early-back',(leg('NRT','ICN',15,12),))
        rows=list(review_stream([],lambda:iter([quote(),back(),late,early_back]),c,NOW))
        pairs=[r for r in rows if len(r['quotes'])==2]
        self.assertEqual(len(pairs),1)
        self.assertEqual({q.id for q in pairs[0]['quotes']},{'out','back'})
        singles={r['quotes'][0].id:r for r in rows if len(r['quotes'])==1}
        self.assertIn('가는 편: 출발 시간 조건 불일치',singles['late']['reasons'])
        self.assertIn('오는 편: 출발 시간 조건 불일치',singles['early-back']['reasons'])

    def test_each_unpaired_or_outside_input_remains_visible(self):
        outside=quote('outside',(leg(destination='KIX'),))
        rows=list(review_stream([],lambda:iter([quote(),outside]),conditions(),NOW))
        self.assertEqual({q.id for r in rows for q in r['quotes']},{'out','outside'})
        self.assertTrue(all(not r['rankable'] for r in rows))

    def test_airport_and_time_exclusions_remain(self):
        b=quote('other',(leg('HND','GMP',15,17),))
        rows=list(review_stream([],lambda:iter([quote(),b]),conditions(),NOW))
        self.assertEqual(len(rows),1)
        self.assertIn('한국 공항 변경 허용 안 됨',rows[0]['reasons'])
        self.assertIn('현지 공항 변경 허용 안 됨',rows[0]['reasons'])

    def test_coverage_duplicate_input_counts_once_including_unknown_flags(self):
        q=replace(quote(),baggage_confirmed=False)
        data=coverage(lambda:iter([q,replace(q,id='copy')]),conditions())
        self.assertEqual((data['expected'],data['entered']),(396,1))
        self.assertEqual(data['calendar'][-1]['state'],'미입력')

    def test_two_oneways_do_not_count_as_roundtrip_input(self):
        data=coverage(lambda:iter([quote(),back()]),conditions())
        self.assertEqual(data['entered'],2)
        rt=quote('rt',(leg(),back().legs[0]))
        self.assertEqual(coverage(lambda:iter([quote(),back(),rt]),conditions())['entered'],3)

    def test_cache_and_other_passengers_excluded_from_coverage(self):
        rows=[replace(quote(),cached=True),replace(back(),passengers=Passengers(2))]
        self.assertEqual(coverage(lambda:iter(rows),conditions())['entered'],0)

    def test_calendar_has_all_days_and_no_zero_prices(self):
        data=coverage(lambda:iter([]),conditions())
        self.assertEqual(len(data['calendar']),22)
        self.assertTrue(all(r['state']=='미입력' and 'price' not in r for r in data['calendar']))

    def test_expansion_coverage_includes_new_return_date(self):
        q=quote(legs=(leg(day=31,hour=23),))
        data=coverage(lambda:iter([q]),conditions(arrival_expansion=True))
        self.assertEqual(data['expected'],398)
        self.assertEqual(data['calendar'][-1]['expected'],20)


class CsvTests(unittest.TestCase):
    def test_empty_template_contains_no_prices_or_flights(self):
        self.assertEqual(len(template().splitlines()),1)

    def test_explicit_unknown_is_accepted(self):
        quotes,errors=parse_csv(csv_text())
        self.assertFalse(errors)
        self.assertIsNone(quotes[0].legs[0].segments[0].intermediate_stops)
        self.assertIsNone(quotes[0].taxes_included)
        self.assertFalse(quotes[0].baggage_confirmed)

    def test_blank_confirmation_fields_are_errors_not_defaults(self):
        for kwargs in ({'stops':''},{'taxes':''},{'baggage':''}):
            quotes,errors=parse_csv(csv_text(**kwargs))
            self.assertFalse(quotes)
            self.assertEqual(errors[0]['row'],2)

    def test_multi_leg_roundtrip_has_one_total(self):
        rows=list(csv.DictReader(io.StringIO(csv_text(stops='0'))))
        rows[0]['여정']='가는편'
        inbound=dict(rows[0]);inbound.update({'여정':'오는편','출발공항':'NRT','도착공항':'ICN','출발현지시각':'2026-12-15T17:00:00+09:00','도착현지시각':'2026-12-15T19:00:00+09:00'})
        output=io.StringIO();w=csv.DictWriter(output,fieldnames=COLUMNS);w.writeheader();w.writerows([*rows,inbound])
        q,e=parse_csv(output.getvalue());self.assertFalse(e);self.assertEqual(len(q),1)
        self.assertEqual(len(q[0].legs),2);self.assertEqual(q[0].amount,Decimal(100))

    def test_atomic_duplicate_rollback(self):
        with Store(':memory:') as s:
            s.add_manual(back())
            with self.assertRaises(Exception):
                s.add_batch([quote(),back()])
            self.assertEqual([q.id for q in s.all_quotes()],['back'])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=str(Path(self.temp.name)/'test.db')
        self.client=TestClient(create_app(self.path),base_url='http://127.0.0.1')
        self.client.__enter__()
        self.token=self.client.get('/api/config').json()['csrf']

    def tearDown(self):
        self.client.__exit__(None,None,None);self.temp.cleanup()

    def post(self,path,data,**kwargs):
        return self.client.post(path,json=data,headers={'X-CSRF-Token':self.token},**kwargs)

    def test_default_loopback_lan_explicit_and_private_only(self):
        self.assertIsNone(server_parser().parse_args([]).lan)
        self.assertEqual(lan_address('192.168.1.20'),'192.168.1.20')
        for address in ('0.0.0.0','8.8.8.8','127.0.0.1'):
            with self.assertRaises(Exception):lan_address(address)

    def test_entry_point_passes_loopback_to_uvicorn_without_network_listener(self):
        with patch('sys.argv',['flightcore.server','--db',self.path]),patch('uvicorn.run') as run,patch('builtins.print'):
            main()
        self.assertEqual(run.call_args.kwargs['host'],'127.0.0.1')
        self.assertFalse(run.call_args.kwargs['proxy_headers'])

    def test_explicit_lan_entry_point_warns_and_binds_selected_private_ip(self):
        with patch('sys.argv',['flightcore.server','--db',self.path,'--lan','192.168.1.20']),patch('uvicorn.run') as run,patch('builtins.print') as output:
            main()
        self.assertEqual(run.call_args.kwargs['host'],'192.168.1.20')
        self.assertTrue(any('데이터를 열람·변경' in str(call) for call in output.call_args_list))

    def test_lan_warning_is_returned(self):
        other=str(Path(self.temp.name)/'lan.db')
        with TestClient(create_app(other,lan='192.168.1.20'),base_url='http://192.168.1.20') as c:
            data=c.get('/api/config').json()
            self.assertTrue(data['lan']);self.assertIn('변경',data['notice'])

    def test_csrf_cross_origin_and_rebinding_rejected(self):
        self.assertEqual(self.client.post('/api/manual/delete',json={'id':'x'}).status_code,403)
        self.assertEqual(self.client.post('/api/manual/delete',json={'id':'x'},headers={'X-CSRF-Token':self.token,'Origin':'http://evil.invalid'}).status_code,403)
        self.assertEqual(self.client.get('/api/config',headers={'Host':'evil.invalid'}).status_code,400)
        self.assertEqual(self.client.get('/api/config',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)

    def test_empty_dashboard(self):
        result=self.post('/api/dashboard',{'conditions':json.loads(dumps(conditions()))}).json()
        self.assertEqual(result['coverage']['label'],'예상 조건 396건 중 0건 입력됨')
        self.assertFalse(result['inputs']['items']);self.assertFalse(result['references'])

    def test_manual_requires_explicit_confirmation_keys(self):
        for key in ('taxes_included','mandatory_fees_included','baggage_confirmed'):
            q=json.loads(dumps(quote()));del q[key]
            self.assertEqual(self.post('/api/manual',q).status_code,422)
        q=json.loads(dumps(quote()));del q['legs'][0]['segments'][0]['intermediate_stops']
        self.assertEqual(self.post('/api/manual',q).status_code,422)

    def test_manual_unknown_saved_and_reported(self):
        q=replace(quote(legs=(leg(stops=None),)),baggage_confirmed=False,taxes_included=None)
        self.assertEqual(self.post('/api/manual',json.loads(dumps(q))).status_code,200)
        r=self.post('/api/dashboard',{'conditions':json.loads(dumps(conditions()))}).json()
        self.assertEqual(r['coverage']['entered'],1)
        self.assertIn('가는 편: 직항 미확인 (중간 기착 미확인)',r['inputs']['items'][0]['reasons'])

    def test_csv_preview_does_not_save_and_modified_receipt_rejected(self):
        text=csv_text();preview=self.post('/api/csv/preview',{'text':text}).json()
        self.assertTrue(preview['can_save'])
        with Store(self.path) as s:self.assertEqual(list(s.all_quotes()),[])
        invalid=self.post('/api/csv/commit',{'text':text+'\n','receipt':preview['receipt']})
        self.assertEqual(invalid.status_code,422)
        result=self.post('/api/csv/commit',{'text':text,'receipt':preview['receipt']})
        self.assertEqual(result.json()['saved'],1)

    def test_csv_error_preview_cannot_commit(self):
        text=csv_text(stops='');preview=self.post('/api/csv/preview',{'text':text}).json()
        self.assertFalse(preview['can_save'])
        self.assertEqual(self.post('/api/csv/commit',{'text':text,'receipt':preview['receipt']}).status_code,422)

    def test_stored_source_url_is_not_fetched(self):
        q=replace(quote(),provenance=replace(quote().provenance,url='https://example.invalid/do-not-fetch'))
        self.assertEqual(self.post('/api/manual',json.loads(dumps(q))).status_code,200)

    def test_static_routes_and_no_booking_payment_or_provider_routes(self):
        r=self.client.get('/');self.assertEqual(r.status_code,200)
        self.assertIn("frame-ancestors 'none'",r.headers['content-security-policy'])
        for p in ('/static/style.css','/static/app.js','/api/csv-template'):
            self.assertEqual(self.client.get(p).status_code,200)
        for p in ('/api/booking','/api/payment','/api/travelpayouts','/personal.db','/.env'):
            self.assertEqual(self.client.get(p).status_code,404)

    def test_body_size_is_rejected_without_partial_save(self):
        response=self.post('/api/csv/preview',{'text':'x'*(2*1024*1024)})
        self.assertEqual(response.status_code,413)


class JobTests(unittest.TestCase):
    def test_job_snapshots_inputs_and_returns_paginated_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'jobs.db');jobs=Jobs(path)
            with Store(path) as s:
                s.add_manual(quote(legs=(leg(stops=None),)));s.add_manual(back())
            id=jobs.start(conditions());jobs.thread.join(timeout=5)
            self.assertFalse(jobs.thread.is_alive())
            self.assertEqual(jobs.status(id)['status'],'비교 완료')
            result=jobs.results(id,'uncertain')
            self.assertEqual(result['total'],1)
            self.assertIn('가는 편: 직항 미확인 (중간 기착 미확인)',result['items'][0]['reasons'])
            with Store(path) as s:s.add_manual(quote('later'))
            self.assertEqual(jobs.results(id,'uncertain')['total'],1)

    def test_exact_decimal_sorting_not_float(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'jobs.db');jobs=Jobs(path)
            with Store(path) as s:
                s.add_manual(quote('expensive',(leg(),back().legs[0]),'9007199254740993'))
                s.add_manual(quote('cheaper',(leg(),back().legs[0]),'9007199254740992'))
            id=jobs.start(conditions());jobs.thread.join(timeout=5)
            self.assertEqual(jobs.results(id)['items'][0]['quotes'][0]['id'],'cheaper')

    def test_cancel_leaves_partial_and_inputs_not_lost(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'jobs.db');jobs=Jobs(path)
            with Store(path) as s:
                for i in range(40):s.add_manual(quote(f'o{i}'))
                for i in range(40):s.add_manual(replace(back(),id=f'b{i}'))
            id=jobs.start(conditions());jobs.cancel(id);jobs.thread.join(timeout=5)
            self.assertFalse(jobs.thread.is_alive())
            self.assertIn('취소',jobs.status(id)['status'])
            with Store(path) as s:self.assertEqual(len(list(s.all_quotes())),80)


if __name__=='__main__':unittest.main()

import test from 'node:test';
import assert from 'node:assert/strict';
import {accessBlocked,parsePrice,inspectProvider,SOURCES} from '../lib/provider.mjs';
test('rejects login, CAPTCHA, off-site navigation and access restriction',()=>{
  assert.equal(accessBlocked('google',SOURCES.google.url,''),false);
  for(const url of ['https://accounts.google.com/','https://www.google.com/sorry/index','https://www.google.com/login']) {
    assert.equal(accessBlocked('google',url,''),true);
  }
  assert.equal(accessBlocked('naver',SOURCES.naver.url,'비정상적인 접근'),true);
  assert.equal(accessBlocked('naver',SOURCES.naver.url,'',true),true);
});
test('prices require unambiguous positive displayed amounts',()=>{
  assert.equal(parsePrice('naver','왕복 0원'),null);
  assert.equal(parsePrice('naver','왕복 300,000원 편도 100,000원'),null);
  assert.equal(parsePrice('google','가격 정보가 제공되지 않습니다.'),null);
  const n= parsePrice('naver','성인/모든 결제수단\n왕복 300,000원');
  assert.equal(n.amount,300000);assert.equal(n.conditional,false);assert.equal(n.comparison_eligible,false);
  const g=parsePrice('google','최저가는 280,000 대한민국 원입니다. 왕복 항공편 선택');
  assert.equal(g.amount,280000);assert.equal(g.price_scope,'roundtrip_from');
});
test('HTTP access denial stops immediately without parsing or retry',async()=>{
  let navigations=0;
  const page={setRequestInterception:async()=>{},on:()=>{},
    goto:async()=>{navigations++;return {status:()=>429};},
    evaluate:async()=>{throw Error('must not parse');}};
  const result=await inspectProvider(page,'naver');
  assert.equal(result.status,'access_stopped');assert.deepEqual(result.observations,[]);
  assert.equal(navigations,1);
});
test('Naver price-server 503 stops before reading cards',async()=>{
  const events={};
  let reads=0;
  const page={setRequestInterception:async()=>{},on:(name,callback)=>{events[name]=callback;},
    goto:async()=>{
      events.response({request:()=>({resourceType:()=>'fetch'}),
        url:()=>'https://flight-api.naver.com/flight/international/searchFlights',status:()=>503});
      return {status:()=>200};
    },evaluate:async()=>{reads++;throw Error('must not read');}};
  const result=await inspectProvider(page,'naver');
  assert.equal(result.status,'upstream_unavailable');assert.equal(reads,0);
  assert.equal(result.network.http_errors[0].status,503);
});

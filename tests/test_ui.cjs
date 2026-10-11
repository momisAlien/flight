// DOM unit tests only. Synthetic fixtures never populate the real app or its DB.
'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {JSDOM}=require('jsdom');
const root=path.join(__dirname,'..','flightcore','web');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const script=fs.readFileSync(path.join(root,'app.js'),'utf8');
function emptyDashboard(){return {coverage:{expected:396,entered:0,label:'예상 조건 396건 중 0건 입력됨',note:'입력률',calendar:Array.from({length:22},(_,i)=>({date:`2026-12-${i+10}`,entered:0,expected:18,state:'미입력'}))},inputs:{total:0,page:1,pages:1,items:[]},references:[]};}
async function mount(extra={}){
 const dom=new JSDOM(html,{url:'http://127.0.0.1:8000',runScripts:'outside-only'});
 const win=dom.window,calls=[];
 win.structuredClone=structuredClone;
 win.setTimeout=()=>0; win.clearTimeout=()=>{};
 win.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 win.HTMLDialogElement.prototype.close=function(){this.open=false;};
 win.fetch=async(url,opts={})=>{
  const body=opts.body?JSON.parse(opts.body):undefined;calls.push({url,body,opts});
  let value;
  if(url==='/api/config')value={csrf:'TEST-ONLY',lan:false,...extra.config};
  else if(url==='/api/dashboard')value=emptyDashboard();
  else if(url==='/api/parse')value={year:null,start_month_day:[12,10],end_month_day:null,nights:5,destination_hint:'일본',missing:['연도','출발 마지막 날']};
  else if(url==='/api/csv/preview')value={receipt:'TEST-ONLY',can_save:true,count:1,errors:[],quotes:[]};
  else if(url==='/api/manual')value={saved:body.id};
  else if(url==='/api/browser-plan')value={queries:396,notice:'실험 · 전체 항공편·운임 비교 미완료'};
  else if(url==='/api/browser-jobs')value={id:'browser-test'};
  else if(url==='/api/browser-jobs/browser-test?page=1')value={status:'completed_observations',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'observed_partial',result:{observed_at:'TEST',notice:'미확정',search_url:'https://www.google.com/travel/flights',observations:[{amount:123,conditional:true,ticket_kind:'separate_tickets',text:'<img src=x onerror=alert(1)>'}]}}]};
  else if(url==='/api/reference-plan')value={requests:6,cost:'요금 미확인',notice:'저장 참고 가격'};
  else if(url==='/api/reference-jobs')value={id:'reference-test'};
  else if(url==='/api/reference-jobs/reference-test')value={status:'completed_references',total:6,completed:6,not_attempted:0,results:[{status:'references_received',fetched_at:'TEST TIME',request:{depCityCd:'ICN',arrCityCd:'NRT',startDate:'2026-12-10',endDate:'2026-12-11'},references:[{departureDate:'2026-12-10',returnDate:'2026-12-15',totalPrice:123,airline:'<img src=x onerror=alert(1)>'}],dates:[{date:'2026-12-11',status:'no_cached_reference'}]}]};
  else if(url==='/api/jobs')value={id:'TEST-ONLY'};
  else if(url==='/api/jobs/TEST-ONLY')value={status:'비교 완료',processed:0,eligible:0,uncertain:0};
  else if(url.includes('/results?'))value={items:[],total:0,page:1,pages:1};
  else if(url.endsWith('/daily'))value=[];
  else throw new Error(`Unexpected local API: ${url}`);
  return {ok:true,json:async()=>value};
 };
 vm.runInContext(script,dom.getInternalVMContext());
 vm.runInContext(fs.readFileSync(path.join(root,'references.js'),'utf8'),dom.getInternalVMContext());
 vm.runInContext(fs.readFileSync(path.join(root,'browser-prices.js'),'utf8'),dom.getInternalVMContext());
 vm.runInContext(fs.readFileSync(path.join(root,'combined-prices.js'),'utf8'),dom.getInternalVMContext());
 for(let i=0;i<8;i++)await Promise.resolve();
 assert.doesNotMatch(win.document.getElementById('message').textContent,/초기화 실패/);
 return {dom,win,calls,get:id=>win.document.getElementById(id)};
}
async function apply(ui){ui.get('loadExample').click();await ui.get('conditionsForm').onsubmit(new ui.win.Event('submit',{cancelable:true}));}

test('history restores without searching and rerun uses saved conditions after confirmation',async()=>{
 const u=await mount();
 try{
  const c={origins:['ICN'],destinations:['NRT'],start:'2026-12-10',end:'2026-12-11',nights:5};
  const state={status:'cancelled',conditions:c,providers:{},ranking:{notice:'TEST',roundtrips:[],oneway_combinations:[],roundtrip_total:0,oneway_total:0}};
  const calls=[];
  u.win.fetch=async(url,opts={})=>{calls.push({url,body:opts.body?JSON.parse(opts.body):null});return {ok:true,json:async()=>url==='/api/combined-history'?{items:[{id:'saved',status:'cancelled',conditions:c}]}:url==='/api/combined-plan'?{browser_queries:12,reference_queries:1,notice:'TEST'}:url==='/api/combined-jobs'?{id:'new-run'}:state};};
  await u.get('combinedHistory').onclick();await u.get('combinedHistoryOutput').querySelector('button').onclick();
  assert.deepEqual(calls.map(x=>x.url),['/api/combined-history','/api/combined-jobs/saved']);
  assert.match(u.get('combinedOutput').textContent,/통합 검색: 중단됨/);
  assert.equal(u.get('combinedAgain').disabled,false);
  u.win.confirmAction=async()=>false;await u.get('combinedAgain').onclick();
  assert.equal(calls.filter(x=>x.url==='/api/combined-jobs').length,0);
  u.win.confirmAction=async()=>true;await u.get('combinedAgain').onclick();
  assert.deepEqual(calls.find(x=>x.url==='/api/combined-jobs').body.conditions,c);
  assert.equal(u.win.sessionStorage.getItem('combinedJob'),'new-run');
 }finally{u.dom.window.close();}
});

test('combined search starts all providers and renders separate safe price lists',async()=>{
 const u=await mount();
 try{
  await apply(u);const calls=[];
  const part={source:'myrealtrip',basis:'cached_reference',amount:'123',fetched_at:'TEST',text:'<img src=x onerror=alert(1)>',request:{origin:'ICN',destination:'NRT',departure:'2026-12-10',return_date:'2026-12-15'}};
  u.win.fetch=async(url,opts={})=>{calls.push(url);return {ok:true,json:async()=>url==='/api/combined-plan'?{browser_queries:12,reference_queries:1,notice:'TEST'}:url==='/api/combined-jobs'?{id:'combo-test'}:{status:'completed',providers:{myrealtrip:{status:'completed_references',completed:1,total:1}},ranking:{notice:'TEST',roundtrips:[part],roundtrip_total:99,oneway_combinations:[{kind:'two_oneways',amount:'246',outbound:{...part,source:'naver',basis:'search_display'},inbound:{...part,source:'google',basis:'search_display'}}],oneway_total:999}}};};
  u.win.confirmAction=async()=>true;
  await u.get('combinedStart').onclick();
  assert.deepEqual(calls,['/api/combined-plan','/api/combined-jobs','/api/combined-jobs/combo-test']);
  const output=u.get('combinedOutput');
  for(const text of ['왕복 상위 20개','편도 조합 상위 20개','저장 참고가','네이버 + Google','123원','관찰 후보 999개 중 1개'])assert.ok(output.textContent.includes(text),text);
  assert.equal(output.querySelector('img'),null);
  assert.equal(u.get('combinedCancel').disabled,true);
  assert.equal(u.win.sessionStorage.getItem('combinedJob'),'combo-test');
 }finally{u.dom.window.close();}
});

test('detail button previews count and dispatches the selected saved job',async()=>{
 const u=await mount();
 try{
  const requests=[];
  u.win.fetch=async(url,options={})=>{
   requests.push({url,options});
   const value=url.endsWith('/detail-plan')?{count:38,roundtrip_unsupported:40,notice:'TEST'}:url.endsWith('/details')?{id:'saved-job'}:{provider:'google',status:'running_details',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,items:[],detail_counts:{pending:38},detail_total:38};
   return {ok:true,json:async()=>value};
  };
  u.win.confirmAction=async(title,message)=>{assert.match(message,/38/);assert.match(message,/40/);return true;};
  u.win.eval('browserJobId="saved-job"');
  await u.get('browserDetails').onclick();
  assert.deepEqual(requests.map(r=>r.url),['/api/browser-jobs/saved-job/detail-plan','/api/browser-jobs/saved-job/details','/api/browser-jobs/saved-job?page=1']);
  assert.equal(requests[1].options.method,'POST');
  assert.equal(u.get('browserCancel').disabled,false);
 }finally{u.dom.window.close();}
});

test('seller detail progress preserves cancellation and escapes seller text',async()=>{
 const u=await mount();
 try{
  u.win.fetch=async()=>({ok:true,json:async()=>({provider:'google',status:'running_details',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,detail_total:3,detail_counts:{observed:1,running:1,pending:1},items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'observed_partial',result:{observed_at:'TEST',notice:'미확정',search_url:'https://www.google.com/travel/flights',observations:[{amount:123,text:'TEST',detail_status:'observed',seller_detail:{observed_at:'TEST',notice:'결제 미확인',offers:[{seller:'<img src=x onerror=alert(1)>',amount:123,currency:'KRW'}],baggage_statements:['무료 기내 수하물 1개']}}]}}]})});
  u.win.eval('browserJobId="detail-test"');
  await u.win.refreshBrowserJob();
  assert.match(u.get('browserStatus').textContent,/편도 상세 1\/3/);
  assert.equal(u.get('browserCancel').disabled,false);
  assert.equal(u.get('browserDetails').disabled,true);
  assert.equal(u.get('browserOutput').querySelector('img'),null);
  assert.match(u.get('browserOutput').textContent,/무료 기내 수하물 1개/);
 }finally{u.dom.window.close();}
});

test('observed schedule exclusion and missing confirmations remain visible',async()=>{
 const u=await mount();
 try{
  u.win.fetch=async()=>({ok:true,json:async()=>({provider:'naver',status:'completed_observations',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'observed_partial',result:{observed_at:'TEST',notice:'미확정',search_url:'https://flight.naver.com',observations:[{amount:123,text:'TEST',conditional:false,schedule:{status:'excluded',reasons:['한국 도착 마감 초과'],unknown:['중간 기착 여부 상세 확인 필요'],legs:[{origin:'ICN',destination:'NRT',departure:'2026-12-10T15:35:00+09:00',arrival:'2026-12-10T18:10:00+09:00',duration_minutes:155}],actual_nights:5}}]}}]})});
  u.win.eval('browserJobId="schedule-test"');
  await u.win.refreshBrowserJob();
  assert.equal(u.get('browserDetails').disabled,false);
  assert.match(u.get('browserDetails').textContent,/네이버 모든 결제수단/);
  for(const expected of ['일정 조건 제외','한국 도착 마감 초과','중간 기착 여부 상세 확인 필요','도착 기준 5박','155분'])assert.ok(u.get('browserOutput').textContent.includes(expected));
  assert.equal(u.calls.some(x=>x.url==='/api/jobs'),false);
 }finally{u.dom.window.close();}
});

test('failed search conditions stay visible and successful observations allow details',async()=>{
 const u=await mount();
 try{
  u.win.fetch=async()=>({ok:true,json:async()=>({provider:'naver',status:'completed_partial_observations',observed:1,total:2,failed_queries:1,not_attempted:0,detail:'',page:1,pages:1,items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'unverified_response',result:{observations:[],error:'TEST timeout'}}]})});
  u.win.eval('browserJobId="failed-search"');await u.win.refreshBrowserJob();
  assert.equal(u.get('browserDetails').disabled,false);
  assert.match(u.get('browserStatus').textContent,/검색 미확인 1조건/);
  assert.match(u.get('browserOutput').textContent,/TEST timeout/);
  assert.doesNotMatch(u.get('browserOutput').textContent,/undefined|0 KRW/);
  assert.equal(u.get('browserOutput').querySelector('a'),null);
 }finally{u.dom.window.close();}
});

test('only interrupted pending details can resume and access blocks stay stopped',async()=>{
 const u=await mount();
 try{
  let status='interrupted';const calls=[];
  u.win.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({provider:'naver',status,observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,detail_total:4,detail_counts:{observed:1,interrupted:1,pending:2},items:[]})};};
  u.win.eval('browserJobId="resume-test"');await u.win.refreshBrowserJob();
  assert.equal(u.get('browserResumeDetails').disabled,false);
  const pending=u.get('browserResumeDetails').onclick();
  for(let i=0;i<8;i++)await Promise.resolve();
  assert.match(u.get('confirmBody').textContent,/조회하지 않은 2개/);
  assert.equal(calls.some(x=>x.url.endsWith('/resume-details')),false);
  u.get('confirmYes').click();await pending;
  assert.equal(calls.filter(x=>x.url.endsWith('/resume-details')).length,1);
  status='access_stopped';await u.win.refreshBrowserJob();
  assert.equal(u.get('browserResumeDetails').disabled,true);
 }finally{u.dom.window.close();}
});

test('different payment conditions are not labelled comparable price movements',async()=>{
 const u=await mount();
 try{
  u.win.fetch=async()=>({ok:true,json:async()=>({provider:'naver',status:'completed_details',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'observed_partial',result:{observed_at:'TEST',notice:'TEST',search_url:'https://flight.naver.com',observations:[{amount:100,text:'TEST',seller_detail:{observed_at:'TEST',notice:'TEST',offers:[{seller:'TEST SELLER',amount:110,currency:'KRW'}],baggage_statements:[],search_price_change:{initial_amount:100,latest_amount:80,changed:true,same_search_condition:false},search_payment_transition:{initial:'성인/모든 결제수단',latest:'성인/TEST카드',selected:'성인/모든 결제수단',same_search_condition:false}}}]}}]})});
  u.win.eval('browserJobId="payment-test"');await u.win.refreshBrowserJob();
  assert.match(u.get('browserOutput').textContent,/동일 조건의 가격 인상·하락으로 비교하지 않습니다/);
  assert.match(u.get('browserOutput').textContent,/TEST SELLER · 110 KRW 표시/);
  assert.doesNotMatch(u.get('browserOutput').textContent,/같은 일정의 검색 표시가 변경/);
 }finally{u.dom.window.close();}
});

test('partial detail completion shows unsupported cards and changed prices',async()=>{
 const u=await mount();
 try{
  u.win.fetch=async()=>({ok:true,json:async()=>({provider:'naver',status:'completed_partial_details',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,detail_total:3,detail_counts:{observed:1,unsupported_payment:1,ambiguous_card:1},items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'observed_partial',result:{observed_at:'TEST',notice:'TEST',search_url:'https://flight.naver.com',observations:[{amount:100,text:'TEST',detail_status:'observed',seller_detail:{observed_at:'TEST',notice:'TEST',offers:[],baggage_statements:[],search_price_change:{initial_amount:100,latest_amount:200,changed:true}}},{amount:100,text:'TEST',detail_status:'unsupported_payment'},{amount:100,text:'TEST',detail_status:'ambiguous_card'}]}}]})});
  u.win.eval('browserJobId="partial-test"');await u.win.refreshBrowserJob();
  assert.match(u.get('browserStatus').textContent,/결제조건 미지원 1/);
  assert.match(u.get('browserStatus').textContent,/상세 1\/1 지원 대상/);
  assert.match(u.get('browserStatus').textContent,/중복 식별 미확인 1/);
  assert.match(u.get('browserOutput').textContent,/100 KRW → 200 KRW/);
  assert.equal(u.get('browserDetails').disabled,true);
  assert.equal(u.get('browserCancel').disabled,true);
 }finally{u.dom.window.close();}
});

test('browser observations preserve conditional and separate-ticket labels without entering comparison',async()=>{
 const u=await mount();
 try{
  await apply(u);
  const pending=u.get('browserStart').onclick();
  for(let i=0;i<8;i++)await Promise.resolve();
  assert.equal(u.calls.some(x=>x.url==='/api/browser-jobs'),false);
  assert.match(u.get('confirmBody').textContent,/396조건/);
  u.get('confirmYes').click();await pending;
  assert.match(u.get('browserStatus').textContent,/최저 표시가 비교 가능/);
  assert.match(u.get('browserOutput').textContent,/조건부 할인/);
  assert.match(u.get('browserOutput').textContent,/별도 항공권 구매/);
  assert.equal(u.get('browserOutput').querySelector('img'),null);
  assert.equal(u.calls.some(x=>x.url==='/api/manual'||x.url==='/api/jobs'),false);
 }finally{u.dom.window.close();}
});

test('reference search requires confirmation and never populates live comparison',async()=>{
 const u=await mount();
 try{
  await apply(u);
  const pending=u.get('referenceStart').onclick(new u.win.Event('click'));
  for(let i=0;i<8;i++)await Promise.resolve();
  assert.equal(u.calls.some(x=>x.url==='/api/reference-jobs'),false);
  assert.match(u.get('confirmBody').textContent,/외부 요청 6회/);
  u.get('confirmYes').click(); await pending;
  assert.match(u.get('referenceStatus').textContent,/참고 가격 조회 완료/);
  assert.match(u.get('referenceOutput').textContent,/123 KRW/);
  assert.match(u.get('referenceOutput').textContent,/항공편 없음이 아님/);
  assert.equal(u.get('referenceOutput').querySelector('img'),null);
  assert.equal(u.calls.some(x=>x.url==='/api/manual'||x.url==='/api/jobs'),false);
 }finally{u.dom.window.close();}
});

test('empty app has no seeded fares, and confirmation choices default to required unknown',async()=>{
 const u=await mount();
 try{
  assert.equal(u.get('start').value,'');assert.equal(u.get('end').value,'');
  assert.equal(u.get('amount').value,'');assert.match(u.get('eligibleResults').textContent,/현재 확인된 결과가 없습니다/);
  assert.equal(u.get('startCompare').disabled,true);
  for(const id of ['taxes','fees','bagsConfirmed']){assert.equal(u.get(id).value,'unknown');assert.equal(u.get(id).required,true);}
  assert.equal(u.get('legForms').querySelectorAll('.seg-stops').length,2);
  for(const field of u.get('legForms').querySelectorAll('.seg-stops')){assert.equal(field.value,'unknown');assert.equal(field.required,true);}
  assert.deepEqual(u.calls.map(x=>x.url),['/api/config']);
 }finally{u.dom.window.close();}
});

test('three origin airports, two Tokyo airports, 22 missing dates and 396 conditions reach local server',async()=>{
 const u=await mount();
 try{
  await apply(u);
  const c=u.calls.find(x=>x.url==='/api/dashboard').body.conditions;
  assert.deepEqual(c.origins,['ICN','GMP','CJJ']);assert.deepEqual(c.destinations,['NRT','HND']);
  assert.equal(c.end,'2026-12-31');assert.equal(c.baggage,'none_requested');
  assert.match(u.get('coverageLabel').textContent,/396건 중 0건 입력됨/);
  const rows=u.get('calendar').querySelectorAll('tr');assert.equal(rows.length,22);
  for(const row of rows){assert.equal(row.children[3].textContent,'미입력');assert.doesNotMatch(row.textContent,/0 KRW/);}
  assert.equal(u.get('startCompare').disabled,false);
  assert.equal(u.calls.some(x=>x.url==='/api/jobs'),false);
 }finally{u.dom.window.close();}
});

test('manual unknown confirmations and stops are sent explicitly instead of omitted',async()=>{
 const u=await mount();
 try{
  await apply(u);
  u.get('quoteType').value='outbound';u.get('quoteType').dispatchEvent(new u.win.Event('change'));
  const s=u.get('legForms').querySelector('.segment');
  const values={'.seg-origin':'ICN','.seg-destination':'NRT','.seg-airline':'TEST ONLY','.seg-departure':'2026-12-10T08:00','.seg-arrival':'2026-12-10T10:00'};
  for(const [selector,value]of Object.entries(values))s.querySelector(selector).value=value;
  for(const [id,value]of Object.entries({amount:'100',source:'TEST ONLY',seller:'TEST SELLER',sourceUrl:'https://example.invalid',observed:'2026-10-05T17:00'}))u.get(id).value=value;
  await u.get('manualForm').onsubmit(new u.win.Event('submit',{cancelable:true}));
  const q=u.calls.find(x=>x.url==='/api/manual').body;
  assert.equal(q.legs[0].segments[0].intermediate_stops,null);
  assert.equal(q.taxes_included,null);assert.equal(q.mandatory_fees_included,null);assert.equal(q.baggage_confirmed,false);
  assert.equal(q.provenance.kind,'manual');assert.equal(q.amount,'100');
  assert.equal(u.get('taxes').value,'unknown');
  assert.equal(u.calls.filter(x=>x.url==='/api/jobs').length,1);
 }finally{u.dom.window.close();}
});

test('CSV requires preview and editing invalidates its save receipt',async()=>{
 const u=await mount();
 try{
  u.get('csvTab').click();assert.equal(u.get('manualPanel').hidden,true);assert.equal(u.get('csvPanel').hidden,false);
  assert.equal(u.get('saveCsv').disabled,true);
  u.get('csvText').value='TEST ONLY';await u.get('previewCsv').onclick();
  assert.equal(u.get('saveCsv').disabled,false);assert.match(u.get('csvPreview').textContent,/아직 저장되지 않음/);
  assert.equal(u.calls.some(x=>x.url==='/api/csv/commit'),false);
  u.get('csvText').value='EDITED TEST ONLY';u.get('csvText').dispatchEvent(new u.win.Event('input'));
  assert.equal(u.get('saveCsv').disabled,true);assert.equal(u.get('csvPreview').textContent,'');
 }finally{u.dom.window.close();}
});

test('natural language missing year or end is shown for confirmation without starting search',async()=>{
 const u=await mount();
 try{
  u.get('naturalText').value='12월 10일 이후 일본으로 5박';await u.get('parseText').onclick();
  assert.match(u.get('parsedText').textContent,/연도 미입력/);assert.match(u.get('parsedText').textContent,/출발 마지막 날/);
  assert.equal(u.get('start').value,'');assert.equal(u.calls.some(x=>x.url==='/api/jobs'),false);
 }finally{u.dom.window.close();}
});

test('LAN warning is visible and unsafe source links or user text cannot create executable markup',async()=>{
 const u=await mount({config:{lan:true,notice:'같은 네트워크 사용자가 입력을 볼 수 있음'}});
 try{
  assert.equal(u.get('lanWarning').hidden,false);assert.match(u.get('accessMode').textContent,/LAN 공유 켜짐/);
  assert.equal(u.win.safeLink('javascript:alert(1)','unsafe').tagName,'SPAN');
  assert.equal(u.win.safeLink('https://user:pass@example.invalid','unsafe').tagName,'SPAN');
  const malicious='<img src=x onerror=alert(1)>';
  const q={id:malicious,amount:'100',currency:'KRW',legs:[{segments:[{origin:'ICN',destination:'NRT',airline:'TEST ONLY',flight_number:null,departure:'2026-12-10T08:00:00+09:00',arrival:'2026-12-10T10:00:00+09:00',intermediate_stops:null}]}],passengers:{adults:1,children:0,infants:0},cabin:'economy',taxes_included:null,mandatory_fees_included:null,extra_mandatory_fee:null,baggage:'none_requested',baggage_confirmed:false,baggage_details:'',provenance:{source:'TEST ONLY',seller:'TEST SELLER',observed_at:'2026-10-05T17:00:00+09:00',url:'https://example.invalid'}};
  const card=u.win.resultCard({rankable:false,booking_type:'편도 단독 입력',label:'수동 입력 · 외부 검증 안 됨',total:null,currency:'KRW',actual_nights:null,requested_nights:5,duration:120,reasons:['직항 미확인','수하물 미확인','통화 불일치'],notes:[],quotes:[q]});
  assert.equal(card.querySelector('img'),null);assert.match(card.textContent,/직항 여부 미확인/);assert.match(card.textContent,/방향 총 소요 120분/);
  for(const reason of ['직항 미확인','수하물 미확인','통화 불일치'])assert.equal(card.textContent.includes(reason),true);
  assert.equal(card.textContent.includes(malicious),true);
  assert.equal(card.querySelector('a').rel,'noopener noreferrer');
 }finally{u.dom.window.close();}
});

test('comparison readiness shows blockers without promoting observations to ranked fares',async()=>{
 const u=await mount();
 try{
  u.win.fetch=async()=>({ok:true,json:async()=>({provider:'naver',status:'completed_observations',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'observed_partial',result:{observed_at:'TEST',notice:'미확정',search_url:'https://flight.naver.com',observations:[{amount:123,text:'TEST',comparison_readiness:{status:'unverified',comparison_eligible:false,notice:'진단이며 완성률이 아님',checks:[{state:'observed',label:'판매처 표시 가격 확인'},{state:'missing',label:'수하물 허용량 미검증 <img src=x onerror=alert(1)>'}]}}]}}]})});
  u.win.eval('browserJobId="readiness-test"'); await u.win.refreshBrowserJob();
  const output=u.get('browserOutput');
  assert.match(output.textContent,/확정 비교 미완료/);
  assert.match(output.textContent,/미확인·미연결: 수하물 허용량 미검증/);
  assert.equal(output.querySelector('img'),null);
  assert.equal(u.calls.some(x=>x.url==='/api/jobs'),false);
 }finally{u.dom.window.close();}
});

test('saved candidate comparison is labelled unverified and paginated without starting searches',async()=>{
 const u=await mount();
 try{
  const requests=[];
  u.win.fetch=async(url)=>{requests.push(url);return {ok:true,json:async()=>({label:'저장된 표시가 후보 비교 · 확정 최저가 순위 아님',notice:'전체 재고 미확인',total:11,pages:2,page:1,items:[{kind:'two_oneways',displayed_sum:'200.50',notice:'구매 가능 총액 아님',parts:[{offer:{seller:'<img src=x onerror=alert(1)>',amount:'100.25'},observed_at:'TEST',payment_condition:'미확인',url:'https://example.invalid',legs:[]}]}]})};};
  u.win.eval('browserJobId="candidate-test"');await u.get('browserCandidates').onclick();
  assert.deepEqual(requests,['/api/browser-jobs/candidate-test/candidate-comparisons?page=1']);
  const output=u.get('browserCandidateOutput');
  assert.match(output.textContent,/판매처 조합 11개/);
  assert.match(output.textContent,/확정 최저가 순위 아님/);
  assert.match(output.textContent,/구매 가능 총액 아님/);
  assert.equal(output.querySelector('img'),null);
  const buttons=output.querySelectorAll('button');assert.equal(buttons[0].disabled,true);assert.equal(buttons[1].disabled,false);
  await buttons[1].onclick();assert.equal(requests[1],'/api/browser-jobs/candidate-test/candidate-comparisons?page=2');
 }finally{u.dom.window.close();}
});

test('seller policy preserves segment quantities and unknown cabin without claiming completion',async()=>{
 const u=await mount();
 try{
  u.win.fetch=async()=>({ok:true,json:async()=>({provider:'naver',status:'completed_observations',observed:1,total:1,not_attempted:0,detail:'',page:1,pages:1,items:[{request:{origin:'ICN',destination:'NRT',departure:'2026-12-10'},status:'observed_partial',result:{observed_at:'TEST',notice:'미확정',search_url:'https://flight.naver.com',observations:[{amount:100,text:'TEST',seller_detail:{observed_at:'TEST',notice:'TEST',url:'https://flight.naver.com',baggage_statements:[],offers:[{seller:'TEST ONLY',amount:100,currency:'KRW',fare_policy:{status:'observed',raw_text:'<img src=x onerror=alert(1)>',segments:[{flight_number:'BX0265',route_label:'인천 - 나리타',cabin:{raw:'정보확인필요'},checked:{raw:'1pc, 15kg'}}]}}]}}]}}]})});
  u.win.eval('browserJobId="policy-test"');await u.win.refreshBrowserJob();
  const output=u.get('browserOutput');assert.match(output.textContent,/판매처 상세규정 · 표시 확인/);
  assert.match(output.textContent,/기내: 정보확인필요 \/ 위탁: 1pc, 15kg/);
  assert.match(output.textContent,/모든 구간 적용은 미확정/);assert.equal(output.querySelector('img'),null);
 }finally{u.dom.window.close();}
});

test('price only summary compares raw search minima without seller detail requests',async()=>{
 const u=await mount();
 try{
  const requests=[];u.win.fetch=async(url)=>{requests.push(url);return {ok:true,json:async()=>({source:'google',label:'검색 화면 최저 표시가',notice:'수하물·좌석 조건 비교 제외',total_queries:3,queries_with_price:3,queries:[{number:1,request:{kind:'roundtrip'},minimum:{amount:'200',text:'TEST ONLY'},observed_at:'TEST',url:'https://example.invalid'}],comparisons:[{request:{origin:'ICN',destination:'NRT',departure:'2026-10-12',return_date:'2026-10-17'},roundtrip:'200',two_oneways:'170',lower_displayed:'two_oneways',displayed_difference:'30',conditional:true,roundtrip_query:1,outbound_query:2,inbound_query:3}]})};};
  u.win.eval('browserJobId="price-test"');await u.get('browserPriceSummary').onclick();
  assert.deepEqual(requests,['/api/browser-jobs/price-test/price-summary']);
  const text=u.get('browserPriceOutput').textContent;
  assert.match(text,/왕복 표시가 200원 \/ 편도 두 장 170원/);
  assert.match(text,/편도 두 장 표시가가 30원 낮음/);
  assert.match(text,/조건부 할인 가격 포함/);
 }finally{u.dom.window.close();}
});

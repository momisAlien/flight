import {plan,rank,dayAfter} from './ranking.mjs';
const $=id=>document.getElementById(id),node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const names={google:'Google',naver:'네이버',myrealtrip:'마이리얼트립'};
const reasons={upstream_unavailable:'가격 서버 5xx · 추가 조회 중단',access_stopped:'접근 제한 · 추가 조회 중단',unverified_response:'시간 내 가격 미확인',schema_changed:'가격 표시 형식 미확인',http_error:'서비스 HTTP 오류',provider_error:'서비스 오류',page_unreadable:'화면 읽기 실패',not_configured:'API 키 미설정',unsupported:'조건 미지원',failed:'조회 실패',skipped:'앞선 오류로 미조회',no_cached_reference:'저장 참고가 없음'};
let airports=[],groups={},selected=new Set(),job=null,running=false,selectedCity='',controllers=new Set(),cooldownUntil=0;
for(const [code,name] of [['ICN','인천'],['GMP','김포'],['CJJ','청주'],['PUS','김해'],['TAE','대구'],['CJU','제주'],['MWX','무안'],['YNY','양양']]){
 const label=node('label'),input=node('input');input.type='checkbox';input.value=code;input.checked=code==='ICN';label.append(input,document.createTextNode(`${name} ${code}`));$('origins').append(label);
}
const today=new Date().toLocaleDateString('en-CA');
$('start').min=today;$('end').min=today;$('start').value=dayAfter(today,30);$('end').value=$('start').value;
$('mode').onchange=()=>{const exact=$('mode').value==='exact';$('startLabel').textContent=exact?'가는 날':'출발 가능 시작일';$('endLabel').textContent=exact?'오는 날':'출발 가능 마지막 날';$('nightsLabel').hidden=exact;if(exact&&$('end').value<=$('start').value)$('end').value=dayAfter($('start').value,+$('nights').value||3);};
const cityOf=code=>Object.entries(groups).find(([,codes])=>codes.includes(code))?.[0]||airports.find(a=>a.code===code)?.city||code;
function drawSelected(){
 $('destinations').replaceChildren();for(const code of selected){const b=node('button',`${cityOf(code)} · ${code} ×`);b.type='button';b.setAttribute('aria-label',`${code} 선택 해제`);b.onclick=()=>{selected.delete(code);drawSelected();};$('destinations').append(b);}
}
$('airport').oninput=()=>{
 const q=$('airport').value.trim().toLowerCase();$('suggestions').replaceChildren();if(!q)return;
 const add=(label,codes)=>{const b=node('button',label);b.type='button';b.onclick=()=>{codes.forEach(code=>selected.add(code));drawSelected();$('suggestions').replaceChildren();$('airport').value='';};$('suggestions').append(b);};
 Object.entries(groups).filter(([name,codes])=>name.toLowerCase().includes(q)||codes.some(c=>c.toLowerCase()===q)).slice(0,8).forEach(([name,codes])=>add(`${name} · 공항 함께 선택 (${codes.join(', ')})`,codes));
 airports.filter(a=>`${a.code} ${a.name} ${a.city}`.toLowerCase().includes(q)).slice(0,12).forEach(a=>add(`${a.city} · ${a.code} — ${a.name}`,[a.code]));
};
function save(){try{localStorage.setItem('journey-cloud-v1',JSON.stringify(job));}catch{$('status').textContent+=' · 브라우저 저장 공간 부족: 기록 저장 실패';}}
function message(text,cls='warn'){$('status').textContent=text;$('status').className=cls;}
function ticket(item,index,kind){
 const card=node('article',undefined,'ticket'),heading=node('header');heading.append(node('span',`${index+1} · ${selectedCity}`,'badge'),node('strong',`${item.amount.toLocaleString('ko-KR')}원`,'price'));card.append(heading);
 const parts=kind==='pairs'?[item.outbound,item.inbound]:[item];
 for(const [i,row] of parts.entries()){
  const c=row.task;card.append(node('div',`${kind==='pairs'?(i===0?'가는 편':'오는 편'):'가는 편'} · ${c.departure}${c.return_date?' → '+c.return_date:''}`,'route'));
  card.append(node('p',`${names[c.provider]} · ${c.origin} → ${c.destination}${c.return_date?' → '+c.origin:''}`));
  const carrier=row.text.match(/원입니다\.\s*(.*?)의\s.*?항공편입니다\./)?.[1];
  const depart=row.text.match(/(\d+월\s*\d+\s*(?:오전|오후)\s*\d+:\d+)에\s*.*?에서 출발하여/)?.[1];
  const arrive=(row.text.split('에서 출발하여')[1]||'').match(/(\d+월\s*\d+\s*(?:오전|오후)\s*\d+:\d+)에/)?.[1];
  card.append(node('p',`${carrier||'항공사: 아래 원문 확인'} · ${depart||'출발 시각 미확인'} → ${arrive||'도착 시각 미확인'}`));
  card.append(node('small',`${row.observed_at?new Date(row.observed_at).toLocaleString('ko-KR'):''} 조회 · 각 공항 현지 시각`));
  if(c.return_date)card.append(node('p',c.kind==='reference'?'저장 참고가 · 실시간 가격 아님':'왕복 최저 표시가 · 오는 편 및 최종 금액은 원본 확인'));
  if(row.url){try{const url=new URL(row.url);if(['www.google.com','flight.naver.com','www.myrealtrip.com'].includes(url.hostname)&&url.protocol==='https:'){const a=node('a',parts.length===2?(i===0?'가는 편 확인 ↗':'오는 편 확인 ↗'):'항공편 확인 ↗');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';card.append(a);}}catch{}}
  const details=node('details');details.append(node('summary','수집한 원문 · 가격 조건'),node('p',row.text));card.append(details);
 }
 return card;
}
function drawResults(){
 if(!job)return;const data=rank(job.records,selectedCity,job.conditions);$('results').replaceChildren();
 if(data.excluded)$('results').append(node('p',`시간대 밖 또는 시각 미확인 ${data.excluded}개 제외`));
 for(const [key,title] of [['roundtrips','왕복 상위 20개'],['pairs','편도 조합 상위 20개'],['references','저장 왕복 참고가']]){
  if(key==='pairs'&&!job.conditions.pairs)continue;
  $('results').append(node('h3',title));
  if(!data[key].length)$('results').append(node('p','확인한 가격이 없습니다. 항공편이 없다는 뜻은 아닙니다.','muted'));
  data[key].forEach((item,i)=>$('results').append(ticket(item,i,key)));
 }
}
function render(){
 if(!job)return;
 $('controls').disabled=running;$('stop').disabled=!running;$('history').disabled=running;
 $('resume').disabled=running||job.records.length>=job.tasks.length;
 $('progress').hidden=false;$('progress').max=job.tasks.length;$('progress').value=job.records.length;
 const c=job.conditions;$('searchConditions').textContent=`${c.origins.join(', ')} → ${c.destinations.join(', ')} · 출발 ${c.start} ~ ${c.end} · ${c.nights}박 · ${new Date(job.created_at).toLocaleString('ko-KR')} 시작`;
 const failed=job.records.some(r=>!['observed_partial','references_received','no_cached_reference'].includes(r.result.status));
 message(running?`최저가 검색 중… ${job.records.length}/${job.tasks.length}`:job.records.length===job.tasks.length?`검색 완료${failed?' · 일부 조건 미확인':''}`:'검색 중단 · 미조회 조건을 이어서 검색할 수 있습니다.',running?'running':failed?'warn':'done');
 $('providers').replaceChildren();
 for(const provider of Object.keys(names)){
  const expected=job.tasks.filter(t=>t.provider===provider).length,records=job.records.filter(r=>r.task.provider===provider),ok=records.filter(r=>['observed_partial','references_received','no_cached_reference'].includes(r.result.status)).length;
  const firstFailure=records.find(r=>!['observed_partial','references_received','no_cached_reference'].includes(r.result.status));
  $('providers').append(node('p',`${names[provider]} · ${ok}/${expected}조건 확인 · ${running?'미확인':'누락'} ${expected-ok}개${firstFailure?' · '+(firstFailure.result.reason||reasons[firstFailure.result.status]||'조회 실패'):''}`));
  if(provider==='naver'&&firstFailure){
   const links=node('details');links.append(node('summary','네이버 자동 조회 실패 · 원본에서 확인'));
   for(const t of job.tasks.filter(t=>t.provider==='naver'&&t.kind==='roundtrip')){
    const a=node('a',`${t.city} · ${t.origin} → ${t.destination} · ${t.departure} ~ ${t.return_date}`);
    a.href=`https://flight.naver.com/flights/international/${t.origin}-${t.destination}-${t.departure.replaceAll('-','')}/${t.destination}-${t.origin}-${t.return_date.replaceAll('-','')}?adult=1&fareType=Y`;
    a.target='_blank';a.rel='noopener noreferrer';const line=node('p');line.append(a);links.append(line);
   }
   $('providers').append(links);
  }
 }
 const cities=[...new Set(Object.values(c.cities))];if(!cities.includes(selectedCity))selectedCity=cities[0];$('tabs').replaceChildren();
 cities.forEach(city=>{const b=node('button',`${city} · 상위 20개`);b.setAttribute('role','tab');b.setAttribute('aria-selected',String(city===selectedCity));b.onclick=()=>{selectedCity=city;render();};$('tabs').append(b);});drawResults();
}
async function run(){
 if(running||!job)return;
 if(Date.now()<cooldownUntil){message(`중단한 서버 조회 정리 중입니다. ${Math.ceil((cooldownUntil-Date.now())/1000)}초 뒤 이어서 검색하세요.`);return;}
 running=true;render();
 // Separate functions run providers concurrently, each with at most one browser.
 const done=new Set(job.records.map(r=>r.index)),stopped=new Map();
 for(const r of job.records)if(['access_stopped','upstream_unavailable','not_configured'].includes(r.result.status))stopped.set(r.task.provider,r.result.reason||reasons[r.result.status]);
 await Promise.all(Object.keys(names).map(async provider=>{
 for(let index=0;index<job.tasks.length&&running;index++){
  if(done.has(index)||job.tasks[index].provider!==provider)continue;const task=job.tasks[index];let result;
  if(stopped.has(task.provider))result={status:'skipped',reason:stopped.get(task.provider),observations:[]};
  else{
   const controller=new AbortController();controllers.add(controller);const timeout=setTimeout(()=>controller.abort(),95000);
   try{const response=await fetch(`/api/${provider==='myrealtrip'?'reference':provider}-search`,{method:'POST',headers:{'Content-Type':'application/json','X-Journey-Search':'1'},body:JSON.stringify(task),signal:controller.signal});result=await response.json();if(!response.ok)result={status:[401,403,429].includes(response.status)?'access_stopped':'failed',reason:result.error||`HTTP ${response.status}`,observations:[]};}
   catch{if(!running)break;result={status:'failed',reason:'서버 연결 또는 조회 시간 초과',observations:[]};}
   finally{clearTimeout(timeout);controllers.delete(controller);}
  }
  if(!running)break;
  if(['access_stopped','upstream_unavailable','not_configured'].includes(result.status))stopped.set(task.provider,result.reason||reasons[result.status]);
  job.records.push({index,task,result});save();render();
 }}));
 running=false;save();render();
}
$('stop').onclick=()=>{running=false;cooldownUntil=Date.now()+95000;controllers.forEach(c=>c.abort());message('검색 중단 중… 서버에서 실행 중인 조회는 최대 90초 내 정리됩니다.');};
$('resume').onclick=run;
$('history').onclick=()=>{try{
 const saved=JSON.parse(localStorage.getItem('journey-cloud-v1'));if(!saved||!Array.isArray(saved.tasks)||!Array.isArray(saved.records))throw Error();job=saved;
 const c=job.conditions;selected=new Set(c.destinations);drawSelected();
 $('origins').querySelectorAll('input').forEach(input=>input.checked=c.origins.includes(input.value));
 $('mode').value='range';$('mode').onchange();$('start').value=c.start;$('end').value=c.end;$('nights').value=c.nights;$('pairs').checked=c.pairs;
 $('outStart').value=c.outbound?.start||'';$('outEnd').value=c.outbound?.end||'';$('inStart').value=c.inbound?.start||'';$('inEnd').value=c.inbound?.end||'';
 render();
 }catch{message('저장된 검색 기록이 없습니다.');}};
$('searchForm').onsubmit=event=>{
 event.preventDefault();if(running)return;
 try{
  if(Date.now()<cooldownUntil)throw Error(`이전 서버 조회 정리 중입니다. ${Math.ceil((cooldownUntil-Date.now())/1000)}초 뒤 검색하세요.`);
  const exact=$('mode').value==='exact';const conditions={origins:[...$('origins').querySelectorAll('input:checked')].map(e=>e.value),destinations:[...selected],cities:Object.fromEntries([...selected].map(c=>[c,cityOf(c)])),start:$('start').value,end:exact?$('start').value:$('end').value,nights:exact?(Date.parse($('end').value)-Date.parse($('start').value))/864e5:+$('nights').value,pairs:$('pairs').checked,outbound:{start:$('outStart').value,end:$('outEnd').value},inbound:{start:$('inStart').value,end:$('inEnd').value}};
  for(const w of [conditions.outbound,conditions.inbound])if(Boolean(w.start)!==Boolean(w.end))throw Error('시간대의 시작과 끝을 모두 입력하세요.');
  if(conditions.start<today)throw Error('출발일은 오늘 이후여야 합니다.');
  job={conditions,tasks:plan(conditions),records:[],created_at:new Date().toISOString()};save();void run();
 }catch(error){message(error.message);}
};
try{[airports,groups]=await Promise.all([fetch('/airports.json').then(r=>r.json()),fetch('/city-groups.json').then(r=>r.json())]);}catch{message('공항 목록을 불러오지 못했습니다. 새로고침해 주세요.');$('startSearch').disabled=true;}

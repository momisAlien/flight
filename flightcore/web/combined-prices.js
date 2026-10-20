'use strict';
let combinedId=sessionStorage.getItem('combinedJob'),combinedTimer=null,combinedConditions=null,combinedStarting=false;
let selectedResultCity=null,selectedResultRun=null;
const combinedStart=el('button','3개 서비스 함께 검색 · 상위 20개');combinedStart.type='button';combinedStart.id='combinedStart';$('browserStart').before(combinedStart);
const combinedCancel=el('button','통합 검색 중단');combinedCancel.type='button';combinedCancel.id='combinedCancel';combinedCancel.disabled=true;combinedStart.after(combinedCancel);
const combinedOutput=el('section');combinedOutput.id='combinedOutput';$('browserOutput').before(combinedOutput);
const combinedHistory=el('button','최근 검색 기록 불러오기');combinedHistory.type='button';combinedHistory.id='combinedHistory';combinedCancel.after(combinedHistory);
const combinedHistoryOutput=el('div');combinedHistoryOutput.id='combinedHistoryOutput';combinedOutput.before(combinedHistoryOutput);
const combinedAgain=el('button','이 결과의 조건으로 새 검색');combinedAgain.type='button';combinedAgain.id='combinedAgain';combinedAgain.disabled=true;combinedHistory.after(combinedAgain);
const sourceName={naver:'네이버',google:'Google',myrealtrip:'마이리얼트립'};
const combinedStatusName={pending:'대기',running:'검색 중',completed_references:'참고가 조회 완료',completed_observations:'표시가 조회 완료',completed_partial:'일부 완료',failed_partial:'일부 조회 실패',cancelled_partial:'중단됨',interrupted:'실행 중 끊김',setup_or_conditions_unsupported:'설정 또는 조건 확인 필요',provider_error:'조회 오류'};
Object.assign(combinedStatusName,{queued:'검색 대기 중',completed_partial_observations:'일부 조건 조회 실패',access_stopped:'로그인·접근 제한으로 중단',browser_error:'브라우저 오류',cancelled:'중단됨',setup_required:'Chrome 설정 필요'});
function showSearchState(status){
 const running=['running','queued'].includes(status),complete=['completed','completed_partial'].includes(status);
 const title=status==='queued'?'앞선 검색이 끝나기를 기다리는 중…':running?'최저가 검색 중…':complete?'검색 완료':status==='cancelled'?'검색 중단':status==='interrupted'?'검색이 중단되었습니다':status==='connection_error'?'진행 상태 연결 확인 중':'검색 상태 확인 필요';
 const banner=el('div','','search-state '+(running?'is-searching':complete?'is-complete':'is-warning'));banner.id='searchState';banner.setAttribute('role','status');banner.setAttribute('aria-live','polite');
 banner.append(el('span',running?'◌':complete?'✓':'!','search-state-icon'),el('strong',title));
 if(running){const bar=el('div','','search-wait-bar');bar.setAttribute('role','progressbar');bar.setAttribute('aria-label','최저가 검색 진행 중');bar.append(el('span'));banner.append(bar);}
 const previous=$('searchState');if(previous)previous.replaceWith(banner);else combinedOutput.prepend(banner);
 combinedOutput.setAttribute('aria-busy',String(running));
}
function flightLines(part){
 const text=part.text||'',r=part.request||{},lines=[];
 if(part.source==='naver'){
  const pattern=/(\d{2}:\d{2})([A-Z]{3})[ \t]*\n(\d{2}:\d{2})([A-Z]{3})(?:[ \t]*\n[ \t]*\+(\d+)일)?/g;
  for(const m of text.matchAll(pattern)){
   const before=text.slice(0,m.index).trim().split('\n').pop();
   const carrier=before&&!/^(직항|경유|\+)/.test(before)?before:null;
   lines.push(`${carrier||'오는 편 (항공사 별도 미표시)'} · ${m[2]} ${m[1]} → ${m[4]} ${m[3]}${m[5]?' (+'+m[5]+'일)':''}`);
  }
 }else if(part.source==='google'){
  const airline=text.match(/원입니다\.\s*(.*?)의\s.*?항공편입니다\./)?.[1];
  const dep=text.match(/(\d+월\s*\d+\s*(?:오전|오후)\s*\d+:\d+)에\s*(.*?)에서 출발하여/);
  const arr=(text.split('에서 출발하여')[1]||'').match(/(\d+월\s*\d+\s*(?:오전|오후)\s*\d+:\d+)에\s*(.*?)에 도착합니다/);
  if(airline||dep||arr)lines.push(`${airline||'항공사 미확인'} · ${r.origin||''} ${dep?.[1]||'출발 시각 미확인'} → ${r.destination||''} ${arr?.[1]||'도착 시각 미확인'}`);
 }else if(part.source==='myrealtrip')lines.push(`${text.split(' · ')[0]||'항공사 미확인'} · 출발·도착 시각 미제공`);
 if(!lines.length)lines.push('항공사·출발·도착 시각 미확인');
 if(r.kind==='roundtrip'&&part.source!=='myrealtrip'&&lines.length<2)lines.push('오는 편 항공사·시각 미확인');
 return lines;
}
function flightPreview(item){
 const box=el('div','','flight-preview');
 const parts=item.kind==='two_oneways'?[['가는 편',item.outbound],['오는 편',item.inbound]]:[['',item]];
 for(const [label,part] of parts){const r=part.request||{};box.append(el('div',`${label?label+' · ':''}${r.departure||''}${r.return_date?' ~ '+r.return_date:''}`,'flight-date'));for(const line of flightLines(part))box.append(el('div',line));}
 box.append(el('small','검색 화면 표시 시각 · 각 공항 현지 시간'));return box;
}
function ticketDestinationName(code){
 if(!code)return '목적지 미확인';
 const city=typeof airportAliases!=='undefined'?Object.entries(airportAliases).find(([,codes])=>codes.includes(code))?.[0]:null;
 const airport=typeof worldAirports!=='undefined'?worldAirports.find(a=>a.code===code):null;
 return city||airport?.city||code;
}
function flightTicket(item,index){
 const card=el('article','','flight-ticket'),body=el('div','','ticket-itinerary'),priceBox=el('div','','ticket-price');
 const parts=item.kind==='two_oneways'?[item.outbound,item.inbound]:[item];
 const source=item.kind==='two_oneways'?sourceName[item.outbound.source]+' + '+sourceName[item.inbound.source]:sourceName[item.source];
 body.append(el('div',`${index+1} · ${source}${item.basis==='cached_reference'?' · 저장 참고가':''}`,'ticket-source'));
 for(const [partIndex,part] of parts.entries()){
  const r=part.request||{},lines=flightLines(part),count=item.kind==='two_oneways'?1:r.kind==='roundtrip'?2:1;
  for(let i=0;i<count;i++){
   const inbound=item.kind==='two_oneways'?partIndex===1:r.kind==='inbound'||i===1;
   const day=i===1?r.return_date:r.departure,line=lines[i]||'',parsed=line.match(/^(.*?) · ([A-Z]{3}) (.*?) → ([A-Z]{3}) (.*)$/);
   const row=el('div','','ticket-leg');
   const routeOrigin=i===1?(r.return_origin||r.destination):r.origin,routeDestination=i===1?(r.return_destination||r.origin):r.destination;
   const airline=parsed?.[1]|| (part.source==='myrealtrip'?(part.text||'').split(' · ')[0]:'항공사 미확인');
   const legHeading=el('div','','ticket-leg-heading');
   legHeading.append(el('div',`${inbound?'오는 편':'가는 편'} · ${day||'날짜 미확인'}`,'ticket-leg-date'));
   if(!inbound){const code=parsed?.[4]||routeDestination;const destination=el('strong',ticketDestinationName(code),'ticket-destination');destination.setAttribute('aria-label',`여행 목적지 ${destination.textContent}${code?' · '+code:''}`);legHeading.append(destination);}
   row.append(legHeading);
   const carrier=el('div','','ticket-carrier');carrier.append(el('span','✈','carrier-symbol'),el('span',airline||'항공사 미확인'));row.append(carrier);
   const point=(code,value)=>{const node=el('div','','ticket-point');const clock=value?.match(/(?:오전|오후)?\s*\d{1,2}:\d{2}/)?.[0]?.trim();node.append(el('strong',clock||'미확인'),el('span',code||'—'));const offset=value?.match(/\(\+\d+일\)/)?.[0];if(offset)node.append(el('small',offset));return node;};
   row.append(point(parsed?.[2]||routeOrigin,parsed?.[3]));
   const connector=el('div','','ticket-connector');
   const schedules=[...(part.text||'').matchAll(/(직항|경유\s*\d+),\s*([^\n]+)/g)];
   const duration=part.source==='naver'?schedules[i]?.[2]:(i===0?(part.text||'').match(/총 비행 시간은\s*(.*?)입니다/)?.[1]:null);
   const stops=part.source==='naver'?schedules[i]?.[1]:(i===0&&(part.text||'').includes('직항 항공편')?'직항':null);
   connector.append(el('small',duration||'소요시간 미확인'),el('div','→','ticket-route-line'),el('small',stops||'경유 미확인'));row.append(connector);
   row.append(point(parsed?.[4]||routeDestination,parsed?.[5]));body.append(row);
  }
 }
 priceBox.append(el('span',item.kind==='two_oneways'?'편도 2장 합계':'왕복 표시가','ticket-fare-label'),el('strong',Number(item.amount).toLocaleString('ko-KR')+'원','ticket-amount'));
 if(parts.some(p=>p.conditional))priceBox.append(el('small','할인 조건 확인 필요'));
 for(const [i,part] of parts.entries())if(part.url){const link=safeLink(part.url,parts.length===2?(i===0?'가는 편 확인 ↗':'오는 편 확인 ↗'):'항공편 확인 ↗');link.classList.add('ticket-link');priceBox.append(link);}
 const detail=el('details','','ticket-detail');detail.append(el('summary','가격·출처 상세'));for(const part of parts)detail.append(combinedPart(part));
 card.append(body,priceBox,el('small','각 공항 현지 시각 · 미표시 정보는 원본에서 확인','ticket-footnote'),detail);return card;
}
function combinedPart(part){
 const box=el('div'),r=part.request;
 box.append(el('p',`${sourceName[part.source]} · ${Number(part.amount).toLocaleString('ko-KR')}원 · ${r.origin} → ${r.destination} · ${r.departure}${r.return_date?' / '+r.return_date:''}`));
 box.append(el('p',part.basis==='cached_reference'?`저장 왕복 참고가 · API 수신 ${part.fetched_at} · 원 가격 갱신 시각 미확인`:`검색 표시가 · 관찰 ${part.observed_at||'미확인'}`));
 if(part.conditional)box.append(el('p','조건부 할인 가격 · 적용 조건 확인 필요'));
 box.append(el('p',part.text));if(part.url)box.append(safeLink(part.url,'원본 서비스 열기'));
 return box;
}
async function refreshCombined(){
 const id=combinedId,state=await api(`/api/combined-jobs/${id}`);if(id!==combinedId)return;
 const priceNotice=el('details');priceNotice.append(el('summary','가격 안내'),el('p',state.ranking.notice));combinedOutput.replaceChildren(priceNotice);
 showSearchState(state.status);
 const c=state.conditions;combinedConditions=c?structuredClone(c):null;if(c)combinedOutput.append(el('p',`이 결과의 검색 조건: ${c.origins.join(', ')} → ${c.destinations.join(', ')} · 출발 ${c.start} ~ ${c.end} · ${c.nights}박`));
 const running=['running','queued'].includes(state.status);combinedStart.disabled=running;combinedCancel.disabled=!running;
 if(state.status==='queued')combinedOutput.append(el('p',`검색 대기 중 · 앞선 검색이 끝나면 자동 시작합니다. 대기 순서 ${state.queue_position||1}`));
 combinedAgain.disabled=running||!combinedConditions;combinedHistory.disabled=running;
 if(!['completed','completed_partial'].includes(state.status))combinedOutput.append(el('p',`통합 검색: ${combinedStatusName[state.status]||state.status}`));
 for(const [name,p] of Object.entries(state.providers)){
  const missing=running?(p.failed_queries||0):p.total!==undefined?Math.max(0,p.total-(p.completed||0)):(p.failed_queries||0);
  combinedOutput.append(el('p',`${sourceName[name]} · ${running?(combinedStatusName[p.status]||p.status)+' · ':''}${p.total!==undefined?`${p.completed||0}/${p.total}조건 확인 · 누락 ${missing}개`:p.notice||combinedStatusName[p.status]||p.status}`));
 }
 if(state.ranking.time_filter){
  const ranges=[['가는 편',c?.outbound_window],['오는 편',c?.inbound_window]].filter(([,w])=>w).map(([name,w])=>`${name} ${w.start.slice(0,5)}~${w.end.slice(0,5)}`);
  combinedOutput.append(el('p',`현지 출발 시간대: ${ranges.join(' · ')}`));
  for(const [name,count] of Object.entries(state.ranking.time_filter))combinedOutput.append(el('p',`${sourceName[name]} · 시간대 밖 ${count.outside}개 · 시각 미확인 ${count.unknown}개 제외 (수집 후보 기준)`));
 }
 const cities=state.ranking.cities||[];
 const resultPanel=el('div');resultPanel.id='cityResultPanel';
 const draw=ranking=>{
  resultPanel.replaceChildren();
  if(ranking.name)resultPanel.append(el('p',`${ranking.name} · ${ranking.airports.join(' · ')}`,'city-result-caption'));
  for(const [title,items,total] of [['왕복 상위 20개',ranking.roundtrips,ranking.roundtrip_total],['편도 조합 상위 20개',ranking.oneway_combinations,ranking.oneway_total]]){
   resultPanel.append(el('h3',title),el('p',`관찰 후보 ${total}개 중 ${items.length}개 · 낮은 표시가 순`));
   if(!items.length)resultPanel.append(el('p','아직 비교할 가격이 없습니다. 0원 또는 항공편 없음이라는 뜻이 아닙니다.'));
   items.forEach((item,index)=>resultPanel.append(flightTicket(item,index)));
  }
 };
 if(cities.length>1){
  if(selectedResultRun!==id||!cities.some(city=>city.id===selectedResultCity))selectedResultCity=cities[0].id;
  selectedResultRun=id;
  const tabs=el('div','','city-result-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','목적지 도시별 최저가');
  resultPanel.setAttribute('role','tabpanel');
  const buttons=cities.map((city,index)=>{
   const button=el('button',`${city.name} · 상위 20개`);button.type='button';button.id=`cityResultTab${index}`;
   button.setAttribute('role','tab');button.setAttribute('aria-controls',resultPanel.id);
   button.onclick=()=>{selectedResultCity=city.id;select();};
   button.onkeydown=event=>{let next;if(event.key==='ArrowRight')next=(index+1)%cities.length;else if(event.key==='ArrowLeft')next=(index+cities.length-1)%cities.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=cities.length-1;else return;event.preventDefault();buttons[next].click();buttons[next].focus();};
   tabs.append(button);return button;
  });
  function select(){const index=cities.findIndex(city=>city.id===selectedResultCity);buttons.forEach((button,i)=>{button.setAttribute('aria-selected',String(i===index));button.tabIndex=i===index?0:-1;});resultPanel.setAttribute('aria-labelledby',buttons[index].id);draw(cities[index]);}
  combinedOutput.append(tabs);select();
 }else draw(cities[0]||state.ranking);
 combinedOutput.append(resultPanel);
 clearTimeout(combinedTimer);if(running)combinedTimer=setTimeout(pollCombined,5000);
}
async function pollCombined(){const id=combinedId;try{await refreshCombined();}catch(error){if(id!==combinedId)return;showSearchState('connection_error');clearTimeout(combinedTimer);combinedTimer=setTimeout(pollCombined,5000);}}
async function restoreActiveCombined(){
 if(sharedPC)return false; // A new visitor may enqueue a search instead of taking over another person's.
 const history=await api('/api/combined-history');
 const active=Array.isArray(history.items)?history.items.find(item=>item.status==='running'):null;
 if(!active)return false;
 clearTimeout(combinedTimer);combinedId=active.id;sessionStorage.setItem('combinedJob',combinedId);
 await refreshCombined();return true;
}
async function initializeCombined(){
 try{if(await restoreActiveCombined())return;if(combinedId)await refreshCombined();}
 catch(error){toast('검색 상태를 불러오지 못했습니다. 새로고침해 주세요.');}
}
async function startCombined(selected,quick=false){
 if(combinedStarting)return;
 if(!selected)throw new Error('여행 조건을 먼저 적용하세요');
 combinedStarting=true;
 try{
 const input={conditions:structuredClone(selected)},preview=await api('/api/combined-plan',input);
 if((!quick||preview.browser_queries>120)&&!await confirmAction('3개 서비스 통합 검색',`브라우저 검색 ${preview.browser_queries}조건 · 마이리얼트립 ${preview.reference_queries===null?'조건 미지원':preview.reference_queries+'요청'}. ${preview.notice}`))return;
 showSearchState('running');
 let run;try{run=await api('/api/combined-jobs',input);}catch(error){
  try{if(await restoreActiveCombined()){toast('이미 진행 중인 검색으로 연결했습니다. 새 조건은 검색 중단 후 시작하세요.');return;}}catch{}
  showSearchState('error');throw error;
 }
 combinedId=run.id;sessionStorage.setItem('combinedJob',combinedId);await pollCombined();
 }finally{combinedStarting=false;}
}
combinedStart.onclick=guard(async()=>startCombined(conditions));
combinedAgain.onclick=guard(async()=>startCombined(combinedConditions));
combinedHistory.onclick=guard(async()=>{
 const history=await api('/api/combined-history');combinedHistoryOutput.replaceChildren(el('p','최근 검색 20개 · 불러오기는 외부 재검색을 실행하지 않습니다.'));
 if(!history.items.length)combinedHistoryOutput.append(el('p','저장된 통합 검색이 없습니다.'));
 for(const item of history.items){
  const c=item.conditions,button=el('button',`${c.origins.join(', ')} → ${c.destinations.join(', ')} · ${c.start} ~ ${c.end} · ${c.nights}박 · ${combinedStatusName[item.status]||item.status}`);button.type='button';
  button.onclick=guard(async()=>{clearTimeout(combinedTimer);combinedId=item.id;sessionStorage.setItem('combinedJob',combinedId);await refreshCombined();});
  combinedHistoryOutput.append(button);
 }
});
combinedCancel.onclick=guard(async()=>{await api(`/api/combined-jobs/${combinedId}/cancel`,{});await refreshCombined();});

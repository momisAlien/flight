'use strict';
let combinedId=sessionStorage.getItem('combinedJob'),combinedTimer=null,combinedConditions=null,combinedStarting=false;
const combinedStart=el('button','3개 서비스 함께 검색 · 상위 20개');combinedStart.type='button';combinedStart.id='combinedStart';$('browserStart').before(combinedStart);
const combinedCancel=el('button','통합 검색 중단');combinedCancel.type='button';combinedCancel.id='combinedCancel';combinedCancel.disabled=true;combinedStart.after(combinedCancel);
const combinedOutput=el('section');combinedOutput.id='combinedOutput';$('browserOutput').before(combinedOutput);
const combinedHistory=el('button','최근 검색 기록 불러오기');combinedHistory.type='button';combinedHistory.id='combinedHistory';combinedCancel.after(combinedHistory);
const combinedHistoryOutput=el('div');combinedHistoryOutput.id='combinedHistoryOutput';combinedOutput.before(combinedHistoryOutput);
const combinedAgain=el('button','이 결과의 조건으로 새 검색');combinedAgain.type='button';combinedAgain.id='combinedAgain';combinedAgain.disabled=true;combinedHistory.after(combinedAgain);
const sourceName={naver:'네이버',google:'Google',myrealtrip:'마이리얼트립'};
const combinedStatusName={pending:'대기',running:'검색 중',completed_references:'참고가 조회 완료',completed_observations:'표시가 조회 완료',completed_partial:'일부 완료',failed_partial:'일부 조회 실패',cancelled_partial:'중단됨',interrupted:'실행 중 끊김',setup_or_conditions_unsupported:'설정 또는 조건 확인 필요',provider_error:'조회 오류'};
Object.assign(combinedStatusName,{completed_partial_observations:'일부 조건 조회 실패',access_stopped:'로그인·접근 제한으로 중단',browser_error:'브라우저 오류',cancelled:'중단됨',setup_required:'Chrome 설정 필요'});
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
 combinedOutput.replaceChildren(el('h3','3개 서비스 가격 비교'),el('p',state.ranking.notice));
 const c=state.conditions;combinedConditions=c?structuredClone(c):null;if(c)combinedOutput.append(el('p',`이 결과의 검색 조건: ${c.origins.join(', ')} → ${c.destinations.join(', ')} · 출발 ${c.start} ~ ${c.end} · ${c.nights}박`));
 const running=state.status==='running';combinedStart.disabled=running;combinedCancel.disabled=!running;
 combinedAgain.disabled=running||!combinedConditions;combinedHistory.disabled=running;
 combinedOutput.append(el('p',`통합 검색: ${state.status==='completed'?'완료':combinedStatusName[state.status]||state.status} · 이전에 받은 가격은 현재 가격과 다를 수 있습니다.`));
 for(const [name,p] of Object.entries(state.providers))combinedOutput.append(el('p',`${sourceName[name]}: ${combinedStatusName[p.status]||p.status}${p.total!==undefined?' · 결과 '+(p.completed||0)+'/'+p.total:''}${p.failed_queries?' · 미확인 '+p.failed_queries+'조건':''}${p.notice?' · '+p.notice:''}`));
 for(const [title,items,total] of [['왕복 상위 20개',state.ranking.roundtrips,state.ranking.roundtrip_total],['편도 조합 상위 20개',state.ranking.oneway_combinations,state.ranking.oneway_total]]){
  combinedOutput.append(el('h3',title),el('p',`관찰 후보 ${total}개 중 ${items.length}개 · 낮은 표시가 순`));
  if(!items.length)combinedOutput.append(el('p','아직 비교할 가격이 없습니다. 0원 또는 항공편 없음이라는 뜻이 아닙니다.'));
  items.forEach((item,index)=>{const card=el('details');card.append(el('summary',`${index+1}. ${Number(item.amount).toLocaleString('ko-KR')}원 · ${item.kind==='two_oneways'?sourceName[item.outbound.source]+' + '+sourceName[item.inbound.source]:sourceName[item.source]+(item.basis==='cached_reference'?' · 저장 참고가':'')}`));
   if(item.kind==='two_oneways'){card.append(combinedPart(item.outbound),combinedPart(item.inbound));}else card.append(combinedPart(item));combinedOutput.append(card);
  });
 }
 clearTimeout(combinedTimer);if(running)combinedTimer=setTimeout(()=>refreshCombined().catch(e=>{$('message').textContent=e.message;}),5000);
}
async function startCombined(selected){
 if(combinedStarting)return;
 if(!selected)throw new Error('여행 조건을 먼저 적용하세요');
 combinedStarting=true;
 try{
 const input={conditions:structuredClone(selected)},preview=await api('/api/combined-plan',input);
 if(!await confirmAction('3개 서비스 통합 검색',`브라우저 검색 ${preview.browser_queries}조건 · 마이리얼트립 ${preview.reference_queries===null?'조건 미지원':preview.reference_queries+'요청'}. ${preview.notice}`))return;
 const run=await api('/api/combined-jobs',input);combinedId=run.id;sessionStorage.setItem('combinedJob',combinedId);await refreshCombined();
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
if(combinedId)refreshCombined().catch(()=>{$('message').textContent='이전 통합 조회 결과를 불러오지 못했습니다';});

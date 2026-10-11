'use strict';
let referenceId=null, referenceTimer=null;
const referenceLabels={running:'조회 중',completed_references:'참고 가격 조회 완료 · 실시간 비교 아님',cancelled_partial:'중단 · 일부 결과',failed_partial:'실패 · 일부 결과',interrupted:'서버 종료로 중단됨'};
async function refreshReference(){
 const state=await api(`/api/reference-jobs/${referenceId}`);
 $('referenceStatus').textContent=`${referenceLabels[state.status]||state.status} · 요청 처리 ${state.completed}/${state.total} · 미조회 ${state.not_attempted}`;
 $('referenceOutput').replaceChildren();
 for(const result of state.results){
  const section=el('div'); const req=result.request;
  section.append(el('h3',`${req.depCityCd} → ${req.arrCityCd} · ${req.startDate}~${req.endDate}`));
  section.append(el('p',`상태: ${result.status} · 수신 ${result.fetched_at} · 원 운임 갱신시각 미확인`));
  for(const row of result.references||[])section.append(el('p',`${row.departureDate} → ${row.returnDate} · ${Number(row.totalPrice).toLocaleString('ko-KR')} KRW · ${row.airline||'항공사 미확인'} · 저장 참고 가격`));
  const missing=(result.dates||[]).filter(row=>row.status==='no_cached_reference').map(row=>row.date);
  if(missing.length)section.append(el('p',`저장 가격 없음 (항공편 없음이 아님): ${missing.join(', ')}`));
  $('referenceOutput').append(section);
 }
 const running=state.status==='running';
 $('referenceStart').disabled=running; $('referenceCancel').disabled=!running;
 if(running)referenceTimer=setTimeout(()=>refreshReference().catch(error=>{
  $('referenceStatus').textContent=`상태 확인 실패: ${error.message}. 서버 작업은 계속될 수 있습니다. 중단 버튼을 사용하세요.`;
 }),1200);
 else {referenceTimer=null;}
}
$('referenceStart').onclick=guard(async()=>{
 if(!conditions)throw new Error('왼쪽에서 여행 조건을 먼저 적용하세요');
 const snapshot=structuredClone(conditions);
 const preview=await api('/api/reference-plan',{conditions:snapshot});
 if(!await confirmAction('참고 가격 자동 조회',`${snapshot.origins.join(', ')} → ${snapshot.destinations.join(', ')} / ${snapshot.start}~${snapshot.end}. 외부 요청 ${preview.requests}회. ${preview.cost}. ${preview.notice}`))return;
 $('referenceStart').disabled=true;
 try {const run=await api('/api/reference-jobs',{conditions:snapshot});referenceId=run.id;sessionStorage.setItem('referenceJob',referenceId);await refreshReference();}
 catch(error){$('referenceStart').disabled=false;throw error;}
});
$('referenceCancel').onclick=guard(async()=>{if(referenceId){await api(`/api/reference-jobs/${referenceId}/cancel`,{});$('referenceStatus').textContent='중단 요청됨 · 진행 중 요청이 끝나면 중단합니다';}});
referenceId=sessionStorage.getItem('referenceJob');
if(referenceId)refreshReference().catch(()=>{sessionStorage.removeItem('referenceJob');$('referenceStatus').textContent='이전 조회 상태를 불러오지 못했습니다';});

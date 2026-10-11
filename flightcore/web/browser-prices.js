'use strict';
let browserJobId=sessionStorage.getItem('browserJob'), browserPage=1, browserTimer=null;
const browserStates={running:'조회 중',completed_observations:'가격 검색 종료 · 최저 표시가 비교 가능',observed_partial:'현재 로드된 카드 관찰',pending:'미조회',interrupted:'서버 종료로 중단',cancelled:'사용자 중단',setup_required:'설치 필요',access_stopped:'접근 제한으로 중단',schema_changed:'응답 구조 변경',unverified_response:'결과 확인 실패',browser_error:'브라우저 실행 오류'};
async function refreshBrowserJob(){
 const state=await api(`/api/browser-jobs/${browserJobId}?page=${browserPage}`);
 const source=state.provider==='naver'?'네이버':state.provider==='google'?'Google':'공급사 미확인';
 $('browserStatus').textContent=`${source} 결과 · ${browserStates[state.status]||state.status} · 관찰 ${state.observed}/${state.total} · 미조회 ${state.not_attempted}. ${state.detail}`;
 $('coverageLabel').textContent=`${source} 검색 결과 ${state.observed}/${state.total}조건 확인`;
 $('coverageSmall').textContent='현재 검색 작업의 결과 확인 수 · 제품 전체 완성률이나 최저가 보장 아님';
 $('coverageProgress').max=Math.max(1,state.total);$('coverageProgress').value=state.observed;
 const running=['running','running_details'].includes(state.status);
 $('browserDetails').disabled=!['google','naver'].includes(state.provider)||!['completed_observations','completed_partial_observations'].includes(state.status)||Boolean(state.detail_total)||!state.observed;
 if(state.failed_queries)$('browserStatus').textContent+=` · 검색 미확인 ${state.failed_queries}조건`;
 $('browserDetails').textContent=state.provider==='naver'?'네이버 모든 결제수단 상세 조회':'Google 편도 전체 상세 조회';
 $('browserResumeDetails').disabled=!['interrupted','cancelled','browser_error'].includes(state.status)||!(state.detail_counts?.pending);
 if(state.detail_total){
  const counts=state.detail_counts;
  const target=state.detail_total-(counts.unsupported_payment||0)-(counts.ambiguous_card||0);
  const unknown=['unverified_response','schema_changed','interrupted','cancelled','browser_error','access_stopped'].reduce((sum,key)=>sum+(counts[key]||0),0);
  $('browserStatus').textContent+=` · ${state.provider==='naver'?'왕복·편도':'편도'} 상세 ${counts.observed||0}/${target} 지원 대상 · 상세 미확인 ${unknown} · 상세 미조회 ${counts.pending||0} · 결제조건 미지원 ${counts.unsupported_payment||0} · 중복 식별 미확인 ${counts.ambiguous_card||0}`;
 }
 $('browserStart').disabled=running;$('browserCancel').disabled=!running;
 const output=$('browserOutput');output.replaceChildren();
 for(const item of state.items){
  const box=el('details'),req=item.request;
  box.append(el('summary',`${req.origin} → ${req.destination} · ${req.departure}${req.return_date?' / '+req.return_date:''} · ${browserStates[item.status]||item.status}`));
  if(item.result?.error)box.append(el('p',`검색 미확인: ${item.result.error}. 항공편 없음으로 처리하지 않습니다.`));
  if(item.result&&!item.result.error){
   box.append(el('p',`${source} · 관찰 시각 ${item.result.observed_at} · ${item.result.notice}`));
   for(const row of item.result.observations){
    const price=row.amount===null?'가격 미확인':`${Number(row.amount).toLocaleString('ko-KR')} KRW부터`;
    const kind=row.price_scope==='oneway_from'?'편도 검색 표시가':row.ticket_kind==='separate_tickets'?'별도 항공권 구매':'단일 왕복 예약 여부 미확인';
    const text=el('p',`${price} · ${row.conditional===true?'조건부 할인':row.conditional===false?'모든 결제수단 표시':'결제 조건 미확인'} · ${kind}\n${row.text}`);
    box.append(text);
    if(row.detail_status)box.append(el('p',`판매처 상세: ${browserStates[row.detail_status]||row.detail_status}`));
    if(row.detail_message)box.append(el('p',row.detail_message));
    if(row.seller_detail){
     const detail=row.seller_detail;
     box.append(el('p',`상세 관찰 ${detail.observed_at} · ${detail.notice}`));
     if(detail.search_payment_transition){
      const payment=detail.search_payment_transition;
      box.append(el('p',`검색 결제 조건: ${payment.initial} → ${payment.latest}. 상세에서 확인한 조건: ${payment.selected}.`));
     }
     if(detail.search_price_change?.changed){
      const change=detail.search_price_change;
      const amount=value=>value===null?'가격 미제공':Number(value).toLocaleString('ko-KR')+' KRW';
      box.append(el('p',change.same_search_condition===false
       ? `결제 조건이 다른 검색 표시가: ${amount(change.initial_amount)} → ${amount(change.latest_amount)}. 동일 조건의 가격 인상·하락으로 비교하지 않습니다.`
       : `같은 일정의 검색 표시가 변경: ${amount(change.initial_amount)} → ${amount(change.latest_amount)}. 판매처별 상세 가격은 아래 표시합니다.`));
     }
     box.append(el('p',`필수 세금·수수료 포함 문구: ${detail.taxes_and_mandatory_fees_stated_included===true?'확인 · 결제 총액 보장 아님':'미확인'}`));
     for(const offer of detail.offers){
      box.append(el('p',`${offer.seller} · ${offer.amount===null?'가격 미제공 · 판매처 확인 필요':Number(offer.amount).toLocaleString('ko-KR')+' '+offer.currency+' 표시'}`));
      if(offer.baggage_evidence){
       const states={included:'포함 표시',not_included:'불포함 표시',paid:'유료 표시',unknown:'미확인',conflicting:'서로 다른 안내 · 미확인'};
       for(const [kind,bag] of Object.entries(offer.baggage_evidence)){
        box.append(el('p',`${kind==='checked'?'위탁':'기내'} 수하물: ${states[bag.state]||'미확인'}${bag.pieces!==null?' · '+bag.pieces+'개':''}${bag.displayed_weight_kg!==null?' · '+bag.displayed_weight_kg+'kg 표시':''} · 구간별 적용·무게 기준·추가 비용 미검증`));
       }
      }
      if(offer.fare_policy){
       const policy=offer.fare_policy, view=el('details');
       view.append(el('summary',policy.status==='observed'?'판매처 상세규정 · 표시 확인':'판매처 상세규정 · 미제공 또는 미확인'));
       view.append(el('p','결제 총액·수하물 무게 기준·모든 구간 적용은 미확정입니다.'));
       for(const segment of policy.segments||[]){
        view.append(el('p',`${segment.flight_number} · ${segment.route_label}`));
        view.append(el('p',`기내: ${segment.cabin.raw} / 위탁: ${segment.checked.raw}`));
       }
       if(policy.raw_text)view.append(el('p',policy.raw_text));
       box.append(view);
      }
      for(const statement of offer.seller_statements||[])box.append(el('p',statement));
     }
     if(detail.baggage_statements.length)box.append(el('p','화면 전체 수하물 안내 · 운임별 적용 조건은 위 판매처 선택지 문구를 확인하세요. 무게·최종 요금 미확인.'));
     for(const statement of detail.baggage_statements)box.append(el('p',statement));
     box.append(safeLink(detail.url,'판매처 표시 화면 열기'));
    }
    if(row.comparison_readiness){
     const readiness=row.comparison_readiness, panel=el('details');
     panel.append(el('summary',readiness.status==='excluded'?'비교 진단 · 일정 조건 제외':'비교 진단 · 확정 비교 미완료'));
     panel.append(el('p',readiness.notice));
     const labels={observed:'표시 확인',missing:'미확인·미연결',excluded:'제외'};
     for(const check of readiness.checks)panel.append(el('p',`${labels[check.state]||'미확인'}: ${check.label}`));
     box.append(panel);
    }
    if(row.schedule){
     const schedule=row.schedule;
     const stateLabel={excluded:'일정 조건 제외',unverified:'일정 일부 미확인',schedule_matches:'표시 일정 조건 일치 · 운임 미확정',schedule_observed:'일정 읽기 완료'};
     box.append(el('p',`${stateLabel[schedule.status]||'일정 미확인'} · ${[...new Set([...schedule.reasons,...schedule.unknown])].join(' / ')}`));
     for(const leg of schedule.legs)box.append(el('p',`${leg.origin} ${leg.departure} → ${leg.destination} ${leg.arrival} · ${leg.duration_minutes}분`));
     if(schedule.actual_nights!==undefined)box.append(el('p',`도착 기준 ${schedule.actual_nights}박`));
    }
   }
   const link=el('a','원본 검색 열기');link.href=item.result.search_url;link.target='_blank';link.rel='noopener noreferrer';box.append(link);
  }
  output.append(box);
 }
 $('browserPage').textContent=`${state.page} / ${state.pages}`;
 $('browserPrev').disabled=state.page<=1;$('browserNext').disabled=state.page>=state.pages;
 clearTimeout(browserTimer);
 if(running)browserTimer=setTimeout(()=>refreshBrowserJob().catch(error=>{$('browserStatus').textContent=`상태 확인 실패: ${error.message}. 작업은 계속될 수 있으니 중단 버튼을 이용하세요.`;}),1500);
}
$('browserStart').onclick=guard(async()=>{
 if(!conditions)throw new Error('여행 조건을 먼저 적용하세요');
 const input={conditions:structuredClone(conditions),provider:$('browserProvider').value};
 const preview=await api('/api/browser-plan',input);
 if(!await confirmAction('브라우저 관찰 실행',`${input.conditions.origins.join(',')} → ${input.conditions.destinations.join(',')} / ${input.conditions.start}~${input.conditions.end}. 검색 ${preview.queries}조건. ${preview.notice}`))return;
 $('browserStart').disabled=true;
 try{const result=await api('/api/browser-jobs',input);browserJobId=result.id;browserPage=1;sessionStorage.setItem('browserJob',browserJobId);candidateOutput.replaceChildren();priceOutput.replaceChildren();await refreshBrowserJob();}
 catch(error){$('browserStart').disabled=false;throw error;}
});
browserStates.running_details='판매처 상세 조회 중';
browserStates.completed_partial_observations='조건별 조회 종료 · 검색 미확인 조건 있음';
browserStates.completed_details='대상 카드 상세 조회 종료 · 전체 재고·확정 비교 미완료';
browserStates.completed_partial_details='지원 대상 상세 조회 종료 · 미지원·미확인 항목 있음 · 확정 비교 미완료';
browserStates.unsupported_payment='결제 조건 미해석 또는 이전 버전 미지원 · 원본 관찰 보존';
browserStates.ambiguous_card='중복 카드 식별 미확인 · 상세 선택 안 함';
browserStates.observed='판매처 표시 확인 · 결제 총액 미확정';
const detailButton=el('button','Google 편도 전체 상세 조회');
detailButton.id='browserDetails';detailButton.type='button';detailButton.disabled=true;
$('browserStart').after(detailButton);
const resumeDetailButton=el('button','미조회 상세 이어서 조회');
resumeDetailButton.id='browserResumeDetails';resumeDetailButton.type='button';resumeDetailButton.disabled=true;
detailButton.after(resumeDetailButton);
resumeDetailButton.onclick=guard(async()=>{
 const state=await api(`/api/browser-jobs/${browserJobId}`);
 if(!['interrupted','cancelled','browser_error'].includes(state.status)||!state.detail_counts?.pending)throw new Error('이어서 조회할 미조회 상세 항목이 없습니다');
 if(!await confirmAction('미조회 상세 이어서 조회',`아직 조회하지 않은 ${state.detail_counts.pending}개만 이어갑니다. 성공·실패·중단 중이던 항목은 다시 조회하지 않습니다. 로그인·CAPTCHA·접근 차단에서는 멈춥니다.`))return;
 resumeDetailButton.disabled=true;
 await api(`/api/browser-jobs/${browserJobId}/resume-details`,{});
 await refreshBrowserJob();
});
detailButton.onclick=guard(async()=>{
 const preview=await api(`/api/browser-jobs/${browserJobId}/detail-plan`);
 if(!preview.count)throw new Error('상세 조회할 지원 대상 카드가 없습니다');
 if(!await confirmAction('판매처 상세 조회',`대상 카드 ${preview.count}개. 조건부 검색 카드 ${preview.conditional_cards||0}개 포함 · 일반 결제 요금 선택지 확인. 검색 미확인 ${preview.failed_queries||0}조건. 왕복 미지원 ${preview.roundtrip_unsupported}개. 결제조건 미지원 ${preview.unsupported_payment||0}개, 중복 식별 미확인 ${preview.ambiguous_card||0}개. ${preview.notice}`))return;
 detailButton.disabled=true;
 await api(`/api/browser-jobs/${browserJobId}/details`,{});
 await refreshBrowserJob();
});
$('browserCancel').onclick=guard(async()=>{if(browserJobId){await api(`/api/browser-jobs/${browserJobId}/cancel`,{});$('browserStatus').textContent='중단 요청됨 · 진행 중 페이지 로딩은 최대 60초까지 걸릴 수 있습니다';}});
$('browserPrev').onclick=guard(async()=>{browserPage--;await refreshBrowserJob();});
$('browserNext').onclick=guard(async()=>{browserPage++;await refreshBrowserJob();});
if(browserJobId)refreshBrowserJob().catch(()=>{$('browserStatus').textContent='이전 작업 상태를 불러오지 못했습니다';});

const candidateButton=el('button','저장된 표시가 후보 비교');
candidateButton.id='browserCandidates';candidateButton.type='button';
$('browserStart').after(candidateButton);
const candidateOutput=el('section');candidateOutput.id='browserCandidateOutput';
$('browserOutput').after(candidateOutput);
async function showBrowserCandidates(page=1){
 if(!browserJobId)throw new Error('먼저 브라우저 검색을 실행하세요');
 const id=browserJobId;
 const result=await api(`/api/browser-jobs/${id}/candidate-comparisons?page=${page}`);
 if(id!==browserJobId)return;
 candidateOutput.replaceChildren(el('h3',result.label),el('p',result.notice));
 candidateOutput.append(el('p',`저장된 일정의 판매처 조합 ${result.total}개 · 확정 비교 대상 아님`));
 if(!result.items.length)candidateOutput.append(el('p','이 페이지에 조합 가능한 상세 결과가 없습니다. 최저가 0원 또는 항공편 없음이라는 뜻이 아닙니다.'));
 for(const item of result.items){
  const box=el('details');
  box.append(el('summary',`${item.kind==='two_oneways'?'편도 2건 별도 예약 후보':'왕복 표시 후보'} · 표시가 합계 ${Number(item.displayed_sum).toLocaleString('ko-KR')} KRW`));
  box.append(el('p',item.notice));
  for(const part of item.parts){
   box.append(el('p',`${part.offer.seller} · ${part.offer.amount} KRW · 관찰 ${part.observed_at||'미확인'} · ${part.payment_condition}`));
   for(const leg of part.legs)box.append(el('p',`${leg.origin} ${leg.departure} → ${leg.destination} ${leg.arrival}`));
   for(const statement of part.offer.seller_statements||[])box.append(el('p',statement));
   box.append(safeLink(part.url,'저장된 출처 열기'));
  }
  candidateOutput.append(box);
 }
 const prev=el('button','이전 후보'),next=el('button','다음 후보');
 prev.type=next.type='button';prev.disabled=page<=1;next.disabled=page>=result.pages;
 prev.onclick=guard(()=>showBrowserCandidates(page-1));next.onclick=guard(()=>showBrowserCandidates(page+1));
 candidateOutput.append(prev,el('span',`${page} / ${result.pages}`),next);
}
candidateButton.onclick=guard(()=>showBrowserCandidates());

const priceButton=el('button','최저 표시가 비교 · 상세 조회 불필요');
priceButton.type='button';priceButton.id='browserPriceSummary';$('browserStart').after(priceButton);
const priceOutput=el('section');priceOutput.id='browserPriceOutput';$('browserOutput').before(priceOutput);
async function showPriceSummary(){
 if(!browserJobId)throw new Error('브라우저 검색을 먼저 실행하세요');
 const requestedId=browserJobId;
 const result=await api(`/api/browser-jobs/${requestedId}/price-summary`);
 if(requestedId!==browserJobId)return;
 priceOutput.replaceChildren(el('h3',result.label),el('p',result.notice));
 priceOutput.append(el('p',`${result.source==='google'?'Google':'네이버'} · 가격 확인 ${result.queries_with_price}/${result.total_queries} 검색 조건`));
 const amount=value=>value===null?'미확인':Number(value).toLocaleString('ko-KR')+'원';
 for(const row of result.comparisons){
  const card=el('details'),r=row.request;
  card.append(el('summary',`${r.origin} → ${r.destination} · ${r.departure} 출발 / ${r.return_date} 귀국 · 왕복 ${amount(row.roundtrip)} / 편도 합계 ${amount(row.two_oneways)}`));
  card.append(el('p',`왕복 표시가 ${amount(row.roundtrip)} / 편도 두 장 ${amount(row.two_oneways)}`));
  if(row.lower_displayed)card.append(el('p',row.lower_displayed==='equal'?'표시가 합계 같음':`${row.lower_displayed==='roundtrip'?'왕복':'편도 두 장'} 표시가가 ${amount(row.displayed_difference)} 낮음`));
  else card.append(el('p','왕복 또는 편도 가격이 부족하여 차액 미확인'));
  if(row.conditional)card.append(el('p','조건부 할인 가격 포함 · 적용 카드 등 원문 확인 필요'));
  for(const number of [row.roundtrip_query,row.outbound_query,row.inbound_query]){
   const query=result.queries.find(q=>q.number===number);if(!query)continue;
   card.append(el('p',`${query.request.kind} · ${query.observed_at||'조회 시각 미확인'} · ${amount(query.minimum?.amount??null)}`));
   if(query.minimum)card.append(el('p',query.minimum.text));
   if(query.url)card.append(safeLink(query.url,'검색 화면 열기'));
  }
  priceOutput.append(card);
 }
 if(!result.comparisons.length)priceOutput.append(el('p','왕복 검색 결과가 아직 없습니다. 조회 완료 후 다시 비교하세요.'));
}
priceButton.onclick=guard(showPriceSummary);

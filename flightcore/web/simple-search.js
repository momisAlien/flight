'use strict';
// Keep specialist tools available, but make the default workflow one search.
const airportAliases = {
 '도쿄':['NRT','HND'],'오사카':['KIX','UKB'],'후쿠오카':['FUK'],'삿포로':['CTS'],
 '오키나와':['OKA'],'나고야':['NGO'],'서울':['ICN','GMP'],'부산':['PUS'],'제주':['CJU'],
 '방콕':['BKK','DMK'],'다낭':['DAD'],'하노이':['HAN'],'호치민':['SGN'],'싱가포르':['SIN'],
 '타이베이':['TPE','TSA'],'홍콩':['HKG'],'마카오':['MFM'],'상하이':['PVG','SHA'],
 '베이징':['PEK','PKX'],'세부':['CEB'],'마닐라':['MNL'],'발리':['DPS'],
 '런던':['LHR','LGW','STN','LTN','LCY'],'파리':['CDG','ORY'],'로마':['FCO','CIA'],
 '바르셀로나':['BCN'],'마드리드':['MAD'],'프랑크푸르트':['FRA'],'뮌헨':['MUC'],
 '이스탄불':['IST','SAW'],'두바이':['DXB'],'시드니':['SYD'],'멜버른':['MEL'],
 '오클랜드':['AKL'],'뉴욕':['JFK','EWR','LGA'],'로스앤젤레스':['LAX'],'샌프란시스코':['SFO'],
 '시애틀':['SEA'],'라스베이거스':['LAS'],'호놀룰루':['HNL'],'하와이':['HNL'],
 '토론토':['YYZ'],'밴쿠버':['YVR'],'멕시코시티':['MEX'],'상파울루':['GRU'],
 '카이로':['CAI'],'케이프타운':['CPT'],'요하네스버그':['JNB'],'나이로비':['NBO']
};
let worldAirports=[];
const cityGroupNames={tokyo:'도쿄',osaka:'오사카',paris:'파리',london:'런던',bangkok:'방콕',taipei:'타이베이',beijing:'베이징',shanghai:'상하이',rome:'로마',istanbul:'이스탄불','new york':'뉴욕',seoul:'서울'};
function findAirports(query) {
 const q=query.trim().toLocaleLowerCase();if(!q)return [];
 const aliases=Object.entries(airportAliases).filter(([name])=>name.includes(q)||name===cityGroupNames[q]).flatMap(([,codes])=>codes);
 return worldAirports.filter(a=>aliases.includes(a.code)||`${a.code} ${a.city} ${a.name} ${a.countryName||''} ${a.country}`.toLocaleLowerCase().includes(q))
  .sort((a,b)=>Number(b.code.toLowerCase()===q)-Number(a.code.toLowerCase()===q)||a.city.localeCompare(b.city)).slice(0,30);
}
function selectedDestinationCodes(){return [...new Set($('destinationCodes').value.toUpperCase().split(/[\s,]+/).filter(Boolean))];}
function renderDestinationChips(){
 const box=$('destinationChips');box.replaceChildren();
 for(const code of selectedDestinationCodes()){
  const airport=worldAirports.find(a=>a.code===code),button=el('button',`${airport?.city||code} · ${code} ×`,'destination-chip');
  button.type='button';button.setAttribute('aria-label',`${code} 선택 해제`);
  button.onclick=()=>{$('destinationCodes').value=selectedDestinationCodes().filter(c=>c!==code).join(',');renderDestinationChips();};box.append(button);
 }
}
function groupTools(nodes,title,parent){const details=el('details','','extra-tools');details.append(el('summary',title));for(const node of nodes)details.append(node);parent.append(details);return details;}
async function setupSimpleSearch(){
 await window.flightReady;
 document.body.classList.add('simple-ui');
 document.querySelector('.intro h1').textContent='어디로 떠나볼까요?';
 document.querySelector('.intro>div>p:last-child').textContent='유연한 날짜, 세 곳의 가격을 한 번에.';
 document.querySelector('.intro-note').hidden=true;
 document.querySelector('.coverage-bar').hidden=true;
 const form=$('conditionsForm');
 $('country').closest('label').hidden=true;
 $('city').closest('label').hidden=true;$('city').value='custom';destinations();
 const label=el('label','목적지 도시 · 공항'),input=el('input');input.id='airportSearch';input.placeholder='도시명 또는 공항 코드 검색';input.autocomplete='off';
 input.setAttribute('aria-controls','airportMatches');label.append(input);
 const matches=el('div','','airport-matches');matches.id='airportMatches';matches.setAttribute('aria-label','공항 검색 결과');
 const chips=el('div','','destination-chips');chips.id='destinationChips';
 $('customDestination').before(label,matches,chips);
 const codeDetails=el('details');codeDetails.append(el('summary','공항 코드 직접 입력'));$('customDestination').before(codeDetails);codeDetails.append($('customDestination'));
 $('destinationCodes').placeholder='예: CDG, LHR, JFK';$('destinationCodes').addEventListener('input',renderDestinationChips);
 // Do not preselect an unrelated destination.
 $('destinationCodes').value='';
 for(const hint of form.querySelectorAll(':scope > .hint'))hint.hidden=true;
 const advanced=[];let node=$('adults').closest('.three');const end=$('compareOneWays').closest('label');
 while(node&&node!==end){const next=node.nextElementSibling;advanced.push(node);node=next;}
 const advancedBox=el('details','','extra-tools');advancedBox.append(el('summary','추가 조건 · 수동 비교용'));for(const item of advanced)advancedBox.append(item);end.before(advancedBox);
 end.hidden=true;$('directOnly').checked=false;
 $('deadline').closest('label').hidden=true;
 const rangeRow=$('start').closest('.two'),nightsRow=$('nights').closest('.two');
 const modeBar=el('div','','date-search-modes');modeBar.setAttribute('role','group');modeBar.setAttribute('aria-label','날짜 검색 방식');
 const rangeMode=el('button','출발일 범위 · 박수'),fixedMode=el('button','가는 날 · 오는 날');
 rangeMode.id='dateModeRange';fixedMode.id='dateModeFixed';
 for(const button of [rangeMode,fixedMode]){button.type='button';modeBar.append(button);}
 rangeRow.before(modeBar);
 const fixedRow=el('div','','two');fixedRow.id='fixedDateFields';
 for(const [id,text] of [['departureDate','가는 날'],['returnDate','오는 날']]){const label=el('label',text),input=el('input');input.id=id;input.type='date';label.append(input);fixedRow.append(label);}
 rangeRow.before(fixedRow);
 const fixedNote=el('p','오는 날은 현지 귀국편 출발일입니다. 날짜 지정 검색에서는 네이버·Google을 조회하며, 마이리얼트립 참고가는 현재 지원하지 않습니다.','search-caption');fixedRow.after(fixedNote);
 let dateMode='range';
 function setDateMode(mode){
  dateMode=mode;const fixed=mode==='fixed';
  rangeMode.setAttribute('aria-pressed',String(!fixed));fixedMode.setAttribute('aria-pressed',String(fixed));
  rangeRow.hidden=fixed;nightsRow.hidden=fixed;fixedRow.hidden=!fixed;fixedNote.hidden=!fixed;
  for(const id of ['start','end','nights'])$(id).disabled=fixed;
  for(const id of ['departureDate','returnDate']){$(id).disabled=!fixed;$(id).required=fixed;}
 }
 rangeMode.onclick=()=>setDateMode('range');fixedMode.onclick=()=>setDateMode('fixed');setDateMode('range');
 function readSearchDates(){
  const start=dateMode==='fixed'?$('departureDate').value:$('start').value;
  const end=dateMode==='fixed'?$('returnDate').value:$('end').value;
  if(!start||!end)throw new Error(dateMode==='fixed'?'가는 날과 오는 날을 모두 선택하세요.':'출발 가능 시작일과 마지막 날을 모두 선택하세요.');
  if(end<start)throw new Error(dateMode==='fixed'?'오는 날은 가는 날 이후로 선택하세요.':'출발 가능 마지막 날은 시작일보다 빠를 수 없습니다.');
  if(dateMode==='fixed'){
   const nights=(Date.parse(end+'T00:00:00Z')-Date.parse(start+'T00:00:00Z'))/86400000;
   if(!Number.isInteger(nights)||nights<1)throw new Error('오는 날은 가는 날보다 최소 하루 뒤로 선택하세요.');
   return {start,end:start,nights};
  }
  const nights=number('nights');if(!Number.isInteger(nights)||nights<1)throw new Error('숙박일수는 1 이상의 정수로 입력하세요.');
  return {start,end,nights};
 }

 const timeBox=el('details','','search-time-settings');timeBox.append(el('summary','출발 시간대 · 선택'));
 for(const [prefix,title] of [['searchOut','가는 편 출발'],['searchIn','오는 편 출발']]){
  timeBox.append(el('p',title));const row=el('div','','two');
  for(const [suffix,text] of [['Start','부터'],['End','까지']]){const label=el('label',text),input=el('input');input.id=prefix+suffix;input.type='time';input.setAttribute('aria-label',`${title} ${text}`);label.append(input);row.append(label);}
  timeBox.append(row);
 }
 timeBox.append(el('p','각 공항 현지 출발 시각 기준 · 비우면 제한 없음. 22:00~06:00처럼 자정을 넘겨 지정할 수 있습니다. 시각 미확인 항공편과 마이리얼트립 참고가는 시간대 지정 시 제외됩니다.','search-caption'));
 advancedBox.before(timeBox);
 const submit=form.querySelector('[type=submit]');submit.textContent='최저가 검색';submit.id='quickSearch';
 submit.before(el('p','성인 1명 · 일반석 · 왕복 + 편도 조합','search-caption'));
 $('loadExample').hidden=true;document.querySelector('.natural').hidden=true;
 const main=document.querySelector('.main-column'),panels=[...main.children],primary=panels[0];
 const heading=primary.querySelector('h2');heading.textContent='최저가 비교';
 const tools=el('details','','extra-tools');tools.append(el('summary','개별 서비스 · 상세 조회'));
 const keep=new Set([heading,$('combinedStart'),$('combinedCancel'),$('combinedHistory'),$('combinedAgain'),$('combinedOutput'),$('combinedHistoryOutput')]);
 for(const child of [...primary.children])if(!keep.has(child))tools.append(child);
 primary.append(tools);
 $('combinedStart').hidden=true;$('combinedCancel').textContent='검색 중단';$('combinedHistory').textContent='최근 검색';$('combinedAgain').textContent='같은 조건 재검색';
 const providers=el('div','','provider-badges');for(const name of ['네이버','Google','마이리얼트립'])providers.append(el('span',name));heading.after(providers);
 providers.after(el('p','왕복 · 편도 조합 각각 최저가 20개','search-caption'));
 const note=el('p','마이리얼트립은 2~6박의 저장 왕복 참고가를 조회합니다.','search-caption');primary.append(note);
 const empty=el('div','','search-empty');empty.id='searchEmpty';empty.append(el('span','↗','empty-symbol'),el('h3','여행 조건을 선택해 주세요'),el('p','세 서비스의 가격을 모아 비교합니다.'));$('combinedOutput').before(empty);
 const observer=new MutationObserver(()=>{empty.hidden=!!$('combinedOutput').children.length;submit.disabled=$('combinedCancel').disabled===false||combinedStarting;});
 observer.observe($('combinedOutput'),{childList:true,subtree:true});
 empty.hidden=!!$('combinedOutput').children.length;submit.disabled=!$('combinedCancel').disabled;
 groupTools(panels.slice(1),'직접 입력 · 참고가 · 고급 도구',main);
 form.onsubmit=guard(async event=>{
  event.preventDefault();if(combinedStarting||!$('combinedCancel').disabled)return;
  if(!csrf)throw new Error('연결을 확인한 뒤 다시 검색해 주세요');
  const codes=selectedDestinationCodes();if(!codes.length)throw new Error('검색 결과에서 목적지 공항을 선택해 주세요');
  if(codes.some(code=>!worldAirports.some(a=>a.code===code)))throw new Error('목록에 있는 3자리 공항 코드를 선택해 주세요');
  conditions={origins:selected('originChoices'),destinations:codes,...readSearchDates()};
  // Default search has one supported passenger/cabin configuration. Legacy fields belong to manual tools.
  Object.assign(conditions,{passengers:{adults:1,children:0,infants:0},cabin:'economy',baggage:'none_requested',direct_only:false,max_stops:99,max_duration_minutes:null,outbound_window:windowValue('searchOutStart','searchOutEnd'),inbound_window:windowValue('searchInStart','searchInEnd'),return_deadline:null,allow_origin_change:false,allow_destination_change:false,arrival_expansion:false,compare_oneways:true});
  submit.disabled=true;try{await startCombined(conditions,true);}finally{submit.disabled=!$('combinedCancel').disabled;}
 });
 input.oninput=()=>{
  matches.replaceChildren();const found=findAirports(input.value);
  const choose=codes=>{$('destinationCodes').value=[...new Set([...selectedDestinationCodes(),...codes])].join(',');renderDestinationChips();input.value='';matches.replaceChildren();input.focus();};
  const query=input.value.trim().toLocaleLowerCase(),cityName=cityGroupNames[query]||query;
  const cityCodes=(airportAliases[cityName]||[]).filter(code=>worldAirports.some(a=>a.code===code));
  const groupCodes=cityCodes.length>1?cityCodes:found.map(a=>a.code);
  if(groupCodes.length>1){
   const title=cityCodes.length>1?`${cityName} 공항 모두 선택`:'검색된 공항 모두 선택';
   const all=el('button',`${title} · ${groupCodes.length}개\n${groupCodes.join(' · ')}`,'airport-select-all');all.type='button';
   all.onclick=()=>choose(groupCodes);matches.append(all);
  }
  for(const airport of found){const button=el('button',`${airport.city||airport.name} · ${airport.code}\n${airport.countryName||airport.country} · ${airport.name}`);button.type='button';
   button.onclick=()=>choose([airport.code]);matches.append(button);}
  if(input.value.trim()&&!found.length)matches.append(el('p','일치하는 공항이 없습니다. 영문 도시명이나 IATA 코드를 입력하세요.','hint'));
 };
 try{const response=await fetch('/static/airports.json');if(!response.ok)throw new Error();worldAirports=await response.json();
  const names=new Intl.DisplayNames(['ko'],{type:'region'});worldAirports.forEach(a=>{a.countryName=names.of(a.country)||a.country;});
  label.firstChild.textContent=`목적지 · 전 세계 ${worldAirports.length.toLocaleString('ko-KR')}개 공항`;renderDestinationChips();
 }catch{toast('공항 목록을 불러오지 못했습니다. 새로고침해 주세요.');}
 await initializeCombined();
}
setupSimpleSearch().catch(error=>toast(`화면 준비 실패: ${error.message}`));

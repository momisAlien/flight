// One fixed, public round-trip observation. No sessions, proxies, stealth or retries.
export const CONDITION = Object.freeze({origin:'ICN',destination:'NRT',
  departure:'2027-01-18',return_date:'2027-01-24',adults:1,cabin:'economy'});
export const SOURCES = Object.freeze({
  naver:{host:'flight.naver.com',selector:'[class*="combination_ConcurrentItemContainer__"]',
    url:'https://flight.naver.com/flights/international/ICN-NRT-20270118/NRT-ICN-20270124?adult=1&fareType=Y'},
  google:{host:'www.google.com',selector:'[role="link"][aria-label*="항공편 선택"]',
    url:'https://www.google.com/travel/flights/search?tfs=GhoSCjIwMjctMDEtMThqBRIDSUNOcgUSA05SVBoaEgoyMDI3LTAxLTI0agUSA05SVHIFEgNJQ05CAQFIAZgBAQ==&hl=ko&curr=KRW'}
});
export function accessBlocked(provider, url, body, challenge = false) {
  let parsed;
  try {parsed=new URL(url);} catch {return true;}
  return parsed.hostname !== SOURCES[provider].host
    || /\/sorry|\/unsupported|captcha|login|consent/i.test(parsed.pathname)
    || challenge
    || /unusual traffic|our systems have detected|verify you are human|access denied|비정상적인 접근|접근이 제한|자동입력 방지|사람인지 확인/i.test(body);
}
export function parsePrice(provider,text) {
  const match=provider==='naver' ? text.match(/(왕복|편도)\s*([\d,]+)\s*원/)
    : text.match(/([\d,]+) 대한민국 원/);
  if (!match) return null;
  if (provider==='naver' && [...text.matchAll(/(왕복|편도)\s*([\d,]+)\s*원/g)].length!==1) return null;
  const amount=Number((provider==='naver'?match[2]:match[1]).replaceAll(',',''));
  if (!Number.isSafeInteger(amount)||amount<=0) return null;
  return {amount,currency:'KRW',text:text.slice(0,4000),
    price_scope: /왕복/.test(text)?'roundtrip_from':'unverified',
    conditional:provider==='naver'?!text.includes('성인/모든 결제수단'):null,
    comparison_eligible:false};
}
export async function inspectProvider(page,provider) {
  const source=SOURCES[provider];
  if (!source) throw Error('Unsupported provider');
  const base={source:provider,conditions:CONDITION,search_url:source.url,
    observed_at:new Date().toISOString(),inventory_complete:false,
    notice:'현재 보이는 표시가만 확인. 최종 결제금액·전체 항공편·시간 필터는 미검증.'};
  let blockedNavigation=false;
  await page.setRequestInterception(true);
  page.on('request',request=>{
    if (request.isNavigationRequest() && request.frame()===page.mainFrame()
        && accessBlocked(provider,request.url(),'')) {
      blockedNavigation=true;
      void request.abort();
    } else {void request.continue();}
  });
  let navigationError=false;
  let response;
  try {response=await page.goto(source.url,{waitUntil:'domcontentloaded',timeout:20000});}
  catch {navigationError=true;}
  if (blockedNavigation || [401,403,429].includes(response?.status())) {
    return {...base,status:'access_stopped',reason:'로그인·접근 제한에서 중단',observations:[]};
  }
  if (response && response.status()>=400) return {...base,status:'http_error',http_status:response.status(),observations:[]};
  const deadline=Date.now()+30000;
  let previous='',stable=0,lastBody='';
  while (Date.now()<deadline) {
    let snapshot;
    try {
      snapshot=await page.evaluate(({selector,provider})=>{
        const visible=el=>el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true});
        const body=document.body?.innerText || '';
        const challenge=[...document.querySelectorAll('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],input[name="captcha"],input[type="password"]')].some(visible);
        const rows=[...document.querySelectorAll(selector)].filter(visible)
          .map(el=>provider==='google'?el.getAttribute('aria-label'):(el.innerText||'').replaceAll('\u00a0',' ').trim());
        return {body,challenge,rows};
      },{selector:source.selector,provider});
    } catch {return {...base,status:'page_unreadable',observations:[]};}
    lastBody=snapshot.body;
    if (blockedNavigation || accessBlocked(provider,page.url(),lastBody,snapshot.challenge)) {
      return {...base,status:'access_stopped',reason:'로그인·CAPTCHA·접근 제한에서 중단',observations:[]};
    }
    if (/죄송합니다. 오류가 발생했습니다./.test(lastBody)) return {...base,status:'provider_error',observations:[]};
    const serialized=JSON.stringify(snapshot.rows);
    stable=snapshot.rows.length && serialized===previous ? stable+1:0;
    if (stable>=2) {
      const rows=snapshot.rows.map(text=>parsePrice(provider,text)).filter(Boolean);
      return {...base,status:rows.length?'observed_partial':'schema_changed',
        visible_cards:snapshot.rows.length,parsed_cards:rows.length,
        observations:rows.sort((a,b)=>a.amount-b.amount).slice(0,5)};
    }
    previous=serialized;
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
  return {...base,status:'unverified_response',navigation_error:navigationError,
    reason:'제한 시간 안에 가격 카드를 확인하지 못함. 항공편 없음으로 간주하지 않음.',
    observations:[],page_excerpt:lastBody.slice(0,1500)};
}

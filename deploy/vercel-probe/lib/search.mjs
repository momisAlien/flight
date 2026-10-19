import {probeBrowser} from './probe.mjs';
import {inspectProvider} from './provider.mjs';

// Public Google Flights URL encoding, matching fast-flights' FlightData/Info schema.
const bytes=(tag,value)=>{const b=Buffer.isBuffer(value)?value:Buffer.from(value);return Buffer.concat([Buffer.from([tag,b.length]),b]);};
const leg=(date,origin,destination)=>bytes(26,Buffer.concat([
  bytes(18,date),bytes(106,bytes(18,origin)),bytes(114,bytes(18,destination))]));
export function googleURL(c){
  const parts=[leg(c.departure,c.origin,c.destination)];
  if(c.return_date)parts.push(leg(c.return_date,c.destination,c.origin));
  parts.push(Buffer.from([66,1,1,72,1,152,1,c.return_date?1:2]));
  return `https://www.google.com/travel/flights/search?tfs=${Buffer.concat(parts).toString('base64')}&hl=ko&curr=KRW`;
}
export function naverURL(c){
  const day=s=>s.replaceAll('-','');
  return `https://flight.naver.com/flights/international/${c.origin}-${c.destination}-${day(c.departure)}`+
    (c.return_date?`/${c.destination}-${c.origin}-${day(c.return_date)}`:'')+'?adult=1&fareType=Y';
}
export function validate(value,now=new Date()){
  if(!value||!['google','naver','myrealtrip'].includes(value.provider))throw Error('서비스를 확인하세요.');
  const {origin,destination,departure,return_date}=value;
  if(!/^[A-Z]{3}$/.test(origin)||!/^[A-Z]{3}$/.test(destination)||origin===destination)throw Error('서로 다른 공항 코드가 필요합니다.');
  const date=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!isNaN(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s;
  if(!date(departure)||(return_date&&!date(return_date)))throw Error('날짜를 확인하세요.');
  const today=new Date(now);today.setUTCHours(0,0,0,0);
  if(Date.parse(departure)<+today||Date.parse(departure)>+today+365*864e5)throw Error('출발일은 오늘부터 365일 이내로 지정하세요.');
  if(return_date&&(return_date<=departure||Date.parse(return_date)-Date.parse(departure)>60*864e5))throw Error('귀국일은 출발 다음 날부터 60일 이내입니다.');
  return {origin,destination,departure,...(return_date?{return_date}:{}),adults:1,cabin:'economy'};
}
export function authorized(req,env){
  // Vercel team authentication protects this preview deployment, including its API.
  // Fail closed in production: do not promote without configuring app authentication.
  return env.VERCEL==='1'&&env.VERCEL_ENV==='preview'
    &&env.VERCEL_GIT_COMMIT_REF==='codex/vercel-runtime-check'
    &&[env.VERCEL_URL,env.VERCEL_BRANCH_URL].filter(Boolean).some(host=>req.headers.origin===`https://${host}`)
    &&req.headers['sec-fetch-site']==='same-origin'&&req.headers['x-journey-search']==='1';
}
export async function searchProvider(provider,c){
  if(provider==='myrealtrip')return reference(c);
  const [{default:puppeteer},{default:chromium}]=await Promise.all([import('puppeteer-core'),import('@sparticuz/chromium')]);
  const result=await probeBrowser(puppeteer,chromium,page=>inspectProvider(page,provider,c,provider==='google'?googleURL(c):naverURL(c)));
  // Retain explicit scope: round-trip "from" fares do not confirm the inbound flight.
  result.observations=result.observations.filter(row=>c.return_date?row.price_scope==='roundtrip_from':!row.text.includes('왕복'))
    .map(row=>({...row,price_scope:c.return_date?'roundtrip_from':'oneway_displayed'}));
  return result;
}
export async function reference(c,env=process.env,request=fetch){
  const base={source:'myrealtrip',observed_at:new Date().toISOString(),search_url:'https://www.myrealtrip.com/',observations:[]};
  if(!env.MYREALTRIP_API_KEY)return {...base,status:'not_configured',reason:'Vercel에 마이리얼트립 API 키가 설정되지 않았습니다. 로컬 저장 참고가는 전송되지 않습니다.'};
  const nights=(Date.parse(c.return_date)-Date.parse(c.departure))/864e5;
  if(!Number.isInteger(nights)||nights<2||nights>6)return {...base,status:'unsupported',reason:'저장 왕복 참고가는 2~6박만 지원합니다.'};
  // The calendar requires at least two dates; retain only the explicitly requested day.
  const end=new Date(Date.parse(c.departure)+864e5).toISOString().slice(0,10);
  const response=await request('https://partner-ext-api.myrealtrip.com/v1/products/flight/calendar',{
    method:'POST',headers:{Authorization:`Bearer ${env.MYREALTRIP_API_KEY}`,'Content-Type':'application/json'},redirect:'error',signal:AbortSignal.timeout(30000),
    body:JSON.stringify({depCityCd:c.origin,arrCityCd:c.destination,startDate:c.departure,endDate:end,period:nights+1})});
  if(!response.ok)return {...base,status:'access_stopped',reason:`마이리얼트립 HTTP ${response.status} · 추가 조회 중단`};
  const body=await response.json();
  if(body?.result?.status!==200||body?.result?.code!=='success'||!Array.isArray(body.data))return {...base,status:'provider_error',reason:'마이리얼트립 응답 형식 확인 필요'};
  const rows=body.data.filter(r=>r.fromCity===c.origin&&r.toCity===c.destination&&r.departureDate===c.departure&&r.returnDate===c.return_date&&r.period===nights+1&&r.transfer===0&&Number.isSafeInteger(r.totalPrice)&&r.totalPrice>0);
  return {...base,status:rows.length?'references_received':'no_cached_reference',observations:rows.map(r=>({amount:r.totalPrice,currency:'KRW',text:`${r.airline||'항공사 미제공'} · 저장 참고가 · 시각 미제공`,price_scope:'cached_reference'}))};
}
export function searchHandler(run=searchProvider,env=process.env,provider=null){
  let busy=false;
  return async(req,res)=>{
    res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
    if(req.method!=='POST')return res.status(405).json({error:'POST_REQUIRED'});
    if(!authorized(req,env))return res.status(403).json({error:'보호된 Vercel 미리보기 주소에서 로그인 후 이용하세요. 공개 Production 검색은 비활성화되어 있습니다.'});
    if(provider&&req.body?.provider!==provider)return res.status(400).json({error:'서비스 경로가 맞지 않습니다.'});
    let c;
    try{c=validate(req.body);}catch(e){return res.status(400).json({error:e.message});}
    if(busy)return res.status(429).json({error:'다른 조회가 실행 중입니다. 잠시 후 다시 시도하세요.'});
    busy=true;
    try{return res.status(200).json(await run(req.body.provider,c));}
    catch{return res.status(502).json({error:'가격 조회에 실패했습니다. 확인하지 못한 조건으로 기록했습니다.'});}
    finally{busy=false;}
  };
}

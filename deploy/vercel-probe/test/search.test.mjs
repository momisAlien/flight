import test from 'node:test';
import assert from 'node:assert/strict';
import {googleURL,validate,authorized,searchHandler,reference} from '../lib/search.mjs';
import {plan,rank,inWindow} from '../public/ranking.mjs';
const c={provider:'google',origin:'ICN',destination:'NRT',departure:'2027-01-18',return_date:'2027-01-24'};
test('roundtrip URL agrees with independent fast-flights protobuf fixture',()=>{
 assert.equal(new URL(googleURL(c)).searchParams.get('tfs'),'GhoSCjIwMjctMDEtMThqBRIDSUNOcgUSA05SVBoaEgoyMDI3LTAxLTI0agUSA05SVHIFEgNJQ05CAQFIAZgBAQ==');
 assert.notEqual(googleURL({...c,return_date:undefined}),googleURL(c));
});
test('rejects impossible dates, past trips, arbitrary hosts and reversed return',()=>{
 for(const change of [{departure:'2027-02-30'},{origin:'https://localhost'},{return_date:'2027-01-17'},{departure:'2020-01-01'}])assert.throws(()=>validate({...c,...change},new Date('2026-10-19')));
 assert.equal(validate(c,new Date('2026-10-19')).origin,'ICN');
});
const env={VERCEL:'1',VERCEL_ENV:'preview',VERCEL_GIT_COMMIT_REF:'codex/vercel-runtime-check',VERCEL_BRANCH_URL:'branch.example'};
const req={method:'POST',headers:{origin:'https://branch.example','sec-fetch-site':'same-origin','x-journey-search':'1'},body:c};
test('cloud search fails closed in production, foreign origins and other branches',()=>{
 assert.equal(authorized(req,env),true);
 assert.equal(authorized(req,{...env,VERCEL_ENV:'production'}),false);
 assert.equal(authorized(req,{...env,VERCEL_GIT_COMMIT_REF:'main'}),false);
 assert.equal(authorized({...req,headers:{...req.headers,origin:'https://evil.example'}},env),false);
});
test('request failure releases browser slot and does not expose secrets',async()=>{
 let attempts=0;const handler=searchHandler(async()=>{attempts++;throw Error('SECRET');},env);
 const res={setHeader(){},status(code){this.code=code;return this;},json(value){this.value=value;}};
 await handler(req,res);assert.equal(res.code,502);assert.ok(!JSON.stringify(res.value).includes('SECRET'));
 await handler(req,res);assert.equal(attempts,2);
});
const conditions={origins:['ICN'],destinations:['NRT','HND','KIX'],start:'2027-01-18',end:'2027-01-19',nights:3,pairs:true,cities:{NRT:'도쿄',HND:'도쿄',KIX:'오사카'}};
test('plan covers every airport, date and direction without silent truncation',()=>{
 const tasks=plan(conditions);assert.equal(tasks.length,42);
 assert.equal(tasks.filter(t=>t.provider==='google'&&t.kind==='roundtrip').length,6);
 assert.throws(()=>plan({...conditions,end:'2027-02-17'}),/120/);
 assert.throws(()=>plan({...conditions,end:'2027-01-17'}));
});
const record=(task,amount,text='오전 9:00에 인천에서 출발하여')=>({task,result:{status:'observed_partial',observations:[{amount,text}]}});
test('city ranking happens before top20; paired fares must share departure day and home airport',()=>{
 const records=Array.from({length:30},(_,i)=>record({kind:'roundtrip',city:'오사카',provider:'google'},100+i));
 records.push(record({kind:'roundtrip',city:'도쿄',provider:'google'},999));
 assert.equal(rank(records,'도쿄',{}).roundtrips[0].amount,999);
 const out={kind:'outbound',city:'도쿄',origin:'ICN',destination:'NRT',departure:'2027-01-18',provider:'google'};
 const back={kind:'inbound',city:'도쿄',origin:'HND',destination:'ICN',outbound_date:'2027-01-18',provider:'naver'};
 const result=rank([record(out,100),record(back,200),record({...back,outbound_date:'2027-01-19'},1)],'도쿄',{});
 assert.equal(result.pairs.length,1);assert.equal(result.pairs[0].amount,300);
});
test('midnight windows and unknown inbound times are excluded honestly',()=>{
 assert.equal(inWindow(30,{start:'22:00',end:'02:00'}),true);
 assert.equal(inWindow(null,{start:'22:00',end:'02:00'}),false);
 const rows=[record({kind:'roundtrip',city:'도쿄'},100)];
 assert.equal(rank(rows,'도쿄',{inbound:{start:'09:00',end:'12:00'}}).roundtrips.length,0);
});
test('reference API remains disabled without key and retains only requested date',async()=>{
 assert.equal((await reference(c,{},()=>{throw Error('must not request');})).status,'not_configured');
 const row={fromCity:'ICN',toCity:'NRT',departureDate:c.departure,returnDate:c.return_date,period:7,transfer:0,totalPrice:50000,airline:'TEST'};
 const fake=async(url,options)=>{assert.equal(JSON.parse(options.body).endDate,'2027-01-19');return {ok:true,json:async()=>({result:{status:200,code:'success'},data:[row,{...row,departureDate:'2027-01-19'}]})};};
 const result=await reference(c,{MYREALTRIP_API_KEY:'TEST_ONLY'},fake);assert.equal(result.observations.length,1);
});

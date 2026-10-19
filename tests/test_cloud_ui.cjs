// Synthetic unit fixtures only. Never inject these into the deployed UI.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {JSDOM}=require('jsdom');
const base=path.resolve(__dirname,'../deploy/vercel-probe/public');
async function mount(){
 const dom=new JSDOM(fs.readFileSync(path.join(base,'cloud.html'),'utf8'),{url:'https://example.test',runScripts:'outside-only'});
 const w=dom.window,lib=await import(pathToFileURL(path.join(base,'ranking.mjs')));
 Object.assign(w,{plan:lib.plan,rank:lib.rank,dayAfter:lib.dayAfter,AbortController});
 const pending=[],calls=[];
 w.fetch=async(url,opts)=>{
  if(url==='/airports.json')return {json:async()=>[{code:'NRT',city:'Narita',name:'Narita Airport'}]};
  if(url==='/city-groups.json')return {json:async()=>({'도쿄':['NRT','HND']})};
  calls.push(url);
  return new Promise((resolve,reject)=>{pending.push(()=>resolve({ok:true,json:async()=>({status:'observed_partial',observations:[]})}));opts.signal.addEventListener('abort',()=>reject(Error('aborted')));});
 };
 await w.eval('(async()=>{'+fs.readFileSync(path.join(base,'cloud.mjs'),'utf8').replace(/^import .*?;\r?\n/,'')+'})()');
 const $=id=>w.document.getElementById(id);
 $('airport').value='NRT';$('airport').oninput();$('suggestions').querySelectorAll('button')[1].click();
 $('start').value='2027-01-18';$('end').value='2027-01-18';
 return {dom,w,$,calls,pending};
}
test('all providers begin concurrently; cancel preserves resumable plan without fake results',async()=>{
 const {dom,w,$,calls}=await mount();$('searchForm').dispatchEvent(new w.Event('submit',{cancelable:true}));
 assert.deepEqual(calls.sort(),['/api/google-search','/api/naver-search','/api/reference-search']);
 assert.equal($('controls').disabled,true);assert.match($('status').textContent,/검색 중/);
 $('stop').click();await new Promise(r=>setImmediate(r));
 assert.equal($('controls').disabled,false);assert.equal($('resume').disabled,false);
 const saved=JSON.parse(w.localStorage.getItem('journey-cloud-v1'));
 assert.equal(saved.records.length,0);assert.equal(saved.tasks.length,7);
 $('resume').click();assert.match($('status').textContent,/정리 중/);assert.equal(calls.length,3);dom.window.close();
});
test('invalid date range sends no requests; exact dates derive correct stay',async()=>{
 const {dom,w,$,calls}=await mount();$('end').value='2027-01-17';$('searchForm').dispatchEvent(new w.Event('submit',{cancelable:true}));assert.equal(calls.length,0);
 $('mode').value='exact';$('mode').onchange();$('end').value='2027-01-24';$('searchForm').dispatchEvent(new w.Event('submit',{cancelable:true}));
 assert.equal(JSON.parse(w.localStorage.getItem('journey-cloud-v1')).conditions.nights,6);
 $('stop').click();await new Promise(r=>setImmediate(r));dom.window.close();
});
test('history restores conditions without fetching prices',async()=>{
 const {dom,w,$,calls}=await mount();
 w.localStorage.setItem('journey-cloud-v1',JSON.stringify({conditions:{origins:['ICN'],destinations:['NRT'],cities:{NRT:'도쿄'},start:'2027-01-18',end:'2027-01-18',nights:6,pairs:true},tasks:[],records:[],created_at:'2026-10-19T00:00:00Z'}));
 $('history').click();assert.equal($('start').value,'2027-01-18');assert.equal($('nights').value,'6');assert.equal(calls.length,0);assert.match($('destinations').textContent,/NRT/);dom.window.close();
});
test('failed Naver query offers original link without claiming a price',async()=>{
 const {dom,w,$}=await mount();
 const task={provider:'naver',kind:'roundtrip',city:'도쿄',origin:'ICN',destination:'NRT',departure:'2027-01-18',return_date:'2027-01-24'};
 w.localStorage.setItem('journey-cloud-v1',JSON.stringify({conditions:{origins:['ICN'],destinations:['NRT'],cities:{NRT:'도쿄'},start:'2027-01-18',end:'2027-01-18',nights:6,pairs:false},tasks:[task],records:[{task,result:{status:'upstream_unavailable',observations:[]}}],created_at:'2026-10-19T00:00:00Z'}));
 $('history').click();assert.match($('providers').textContent,/누락 1개/);
 assert.match($('providers').querySelector('a').href,/ICN-NRT-20270118\/NRT-ICN-20270124/);
 assert.equal($('results').querySelectorAll('.ticket').length,0);dom.window.close();
});

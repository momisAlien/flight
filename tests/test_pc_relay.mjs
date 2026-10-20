import test from 'node:test';
import assert from 'node:assert/strict';
import {relay,backendOrigin} from '../deploy/pc/relay.mjs';
const env={FLIGHT_SHARE_USER:'test',FLIGHT_SHARE_PASSWORD:'test-only-password-32-characters!',
 FLIGHT_BRIDGE_TOKEN:'test-bridge-token-32-characters-long',FLIGHT_PC_URL:'https://test-only.trycloudflare.com'};
function req(extra={}){
 return {method:'GET',query:{path:'api/config'},headers:{host:'flight.example',
 authorization:'Basic '+Buffer.from(env.FLIGHT_SHARE_USER+':'+env.FLIGHT_SHARE_PASSWORD).toString('base64')},...extra};
}
function res(){return {headers:{},setHeader(k,v){this.headers[k]=v;},
 status(n){this.code=n;return this;},json(v){this.body=v;return this;},send(v){this.body=v;return this;}};}
test('invalid targets and missing authentication never call the PC',async()=>{
 for(const value of ['http://localhost:8001','https://127.0.0.1','https://evil.example','https://ok.trycloudflare.com/x'])
  assert.throws(()=>backendOrigin(value));
 let calls=0;const handler=relay(env,async()=>{calls++;});
 const response=res();await handler(req({headers:{host:'flight.example'}}),response);
 assert.equal(response.code,401);assert.equal(calls,0);
 const bad=res();await relay({},async()=>{calls++;})(req(),bad);
 assert.equal(bad.code,503);assert.equal(calls,0);
});
test('authenticated relay forwards only bridge and CSRF credentials, rejects cross origin',async()=>{
 let sent;
 const handler=relay(env,async(url,options)=>{sent={url,options};return new Response('{"ok":true}',{headers:{'content-type':'application/json','set-cookie':'must-not-forward'}});});
 const request=req();request.headers.cookie='private';request.headers['x-csrf-token']='csrf';
 const response=res();await handler(request,response);
 assert.equal(response.code,200);
 assert.equal(sent.options.headers['X-Flight-Bridge'],env.FLIGHT_BRIDGE_TOKEN);
 assert.equal(sent.options.headers.Authorization,undefined);
 assert.equal(sent.options.headers.cookie,undefined);
 assert.equal(response.headers['set-cookie'],undefined);
 const blocked=res();await handler(req({method:'POST',headers:{...request.headers,origin:'https://evil.example'}}),blocked);
 assert.equal(blocked.code,403);
});
test('offline PC produces a safe error; redirects are forbidden; paths cannot change origin',async()=>{
 let calls=0;
 const handler=relay(env,async(url,options)=>{calls++;assert.equal(options.redirect,'error');throw Error('sensitive upstream error');});
 const response=res();await handler(req(),response);assert.equal(response.code,503);
 assert.ok(!JSON.stringify(response.body).includes('sensitive'));
 for(const path of ['//evil.example','../private','%2f%2fevil.example']){
  const blocked=res();await handler(req({query:{path}}),blocked);assert.equal(blocked.code,400);
 }
 assert.equal(calls,1);
});

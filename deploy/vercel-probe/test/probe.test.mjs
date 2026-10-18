import test from 'node:test';
import assert from 'node:assert/strict';
import {createHandler, probeBrowser} from '../lib/probe.mjs';
const token = 'test-only-'.repeat(4);
const env = {FLIGHT_PROBE_TOKEN: token, FLIGHT_PROBE_ENABLED: '1'};
const request = () => ({method: 'POST', headers: {authorization: `Bearer ${token}`}});
const response = () => ({headers: {}, setHeader(k,v) {this.headers[k]=v;},
  status(code) {this.code=code;return this;}, json(body) {this.body=body;return this;}});

test('disabled, unauthenticated and GET requests never launch Chrome', async () => {
  let calls = 0;
  const run = async () => {calls++;};
  for (const [settings,req,expected] of [
    [{},request(),503], [env,{method:'GET',headers:{}},405],
    [env,{method:'POST',headers:{}},401],
    [env,{method:'POST',headers:{authorization:'Bearer wrong'}},401]
  ]) {
    const res=response(); await createHandler(run,settings)(req,res);
    assert.equal(res.code,expected);
  }
  assert.equal(calls,0);
});
test('success is explicitly not flight verification', async () => {
  const res=response();
  await createHandler(async()=>({title:'Journey Note browser probe',version:'test'}),env)(request(),res);
  assert.equal(res.code,200);assert.equal(res.body.flight_search_verified,false);
  assert.equal(res.headers['Cache-Control'],'no-store');
});
test('failure hides details and releases the busy guard', async () => {
  const handler=createHandler(async()=>{throw Error('private-secret');},env);
  for (let i=0;i<2;i++) {
    const res=response();await handler(request(),res);
    assert.equal(res.code,502);assert.ok(!JSON.stringify(res.body).includes('private-secret'));
  }
});
test('concurrent requests within an instance are rejected', async () => {
  let finish;
  const handler=createHandler(()=>new Promise(resolve=>{finish=resolve;}),env);
  const first=handler(request(),response()); const second=response();
  await handler(request(),second); assert.equal(second.code,409);
  finish({title:'Journey Note browser probe',version:'test'}); await first;
});
test('browser is closed even if rendering fails', async () => {
  let closed=false;
  const browser={newPage:async()=>{throw Error('render error');},close:async()=>{closed=true;}};
  await assert.rejects(probeBrowser({defaultArgs:x=>x.args,launch:async()=>browser},
    {args:[],executablePath:async()=>'/test'}));
  assert.equal(closed,true);
});
test('protected preview is restricted by environment, branch, date and same origin', async () => {
  const settings = {FLIGHT_PROTECTED_PREVIEW:'1',VERCEL:'1',VERCEL_ENV:'preview',
    VERCEL_GIT_COMMIT_REF:'codex/vercel-runtime-check',VERCEL_URL:'test.vercel.app'};
  const req={method:'POST',headers:{origin:'https://test.vercel.app',
    'x-flight-probe':'runtime-check','sec-fetch-site':'same-origin'}};
  let calls=0;
  const run=async()=>{calls++;return {title:'Journey Note browser probe',version:'test'};};
  const clock=()=>Date.parse('2026-10-18T10:00:00+09:00');
  const handler=createHandler(run,settings,clock);
  for (let i=0;i<2;i++) {const res=response();await handler(req,res);assert.equal(res.code,200);}
  assert.equal(calls,1);
  for (const override of [{VERCEL_ENV:'production'},{VERCEL_GIT_COMMIT_REF:'main'},{VERCEL:'0'}]) {
    const res=response();await createHandler(run,{...settings,...override},clock)(req,res);
    assert.equal(res.code,503);
  }
  const cross=response();await createHandler(run,settings,clock)(
    {...req,headers:{...req.headers,origin:'https://evil.example'}},cross);
  assert.equal(cross.code,401);
  const expired=response();await createHandler(run,settings,()=>Date.parse('2026-10-20'))(req,expired);
  assert.equal(expired.code,503);assert.equal(calls,1);
});

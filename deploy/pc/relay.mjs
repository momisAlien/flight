import {createHash,timingSafeEqual} from 'node:crypto';

const equal=(a,b)=>timingSafeEqual(createHash('sha256').update(a).digest(),createHash('sha256').update(b).digest());
export function backendOrigin(value) {
 const url=new URL(value);
 if(url.protocol!=='https:'||!/^[-a-z0-9]+\.trycloudflare\.com$/.test(url.hostname)
    ||url.username||url.password||url.port||url.pathname!=='/'||url.search||url.hash)
  throw Error('Invalid PC tunnel origin');
 return url.origin;
}
const outputHeaders={
 'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
 'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'
};
export function relay(env=process.env,fetcher=fetch){
 return async function handler(req,res){
  for(const [name,value] of Object.entries(outputHeaders))res.setHeader(name,value);
  const json=(status,detail)=>res.status(status).json({detail});
  const user=env.FLIGHT_SHARE_USER||'';
  const password=env.FLIGHT_SHARE_PASSWORD||'';
  const token=env.FLIGHT_BRIDGE_TOKEN||'';
  if(!user||user.includes(':')||password.length<4||token.length<32)
   return json(503,'공유 접속 설정이 아직 완료되지 않았습니다.');
  let supplied='';
  try{
   const auth=req.headers.authorization||'';
   if(auth.startsWith('Basic '))supplied=Buffer.from(auth.slice(6),'base64').toString('utf8');
  }catch{}
  if(!equal(supplied,`${user}:${password}`)){
   res.setHeader('WWW-Authenticate','Basic realm="Journey Note", charset="UTF-8"');
   return json(401,'공유받은 아이디와 비밀번호를 입력하세요.');
  }
  const host=req.headers.host;
  if(!host||!/^[a-z0-9.-]+(?::\d+)?$/i.test(host))return json(400,'잘못된 접속 주소입니다.');
  const site=req.headers['sec-fetch-site'];
  const navigation=['GET','HEAD'].includes(req.method)&&req.headers['sec-fetch-mode']==='navigate';
  if((['cross-site','same-site'].includes(site)&&!navigation)
     ||(!['GET','HEAD'].includes(req.method)&&req.headers.origin!==`https://${host}`))
   return json(403,'동일한 사이트에서만 요청할 수 있습니다.');
  if(!['GET','HEAD','POST'].includes(req.method))return json(405,'지원하지 않는 요청입니다.');
  let origin;
  try{origin=backendOrigin(env.FLIGHT_PC_URL);}catch{return json(503,'검색 PC 연결 주소를 설정해야 합니다.');}
  // The routed path is data, never an arbitrary destination.
  let path=typeof req.query?.path==='string'?req.query.path:'';
  if(/[%\\\x00-\x1f]/.test(path)||path.split('/').includes('..')||path.startsWith('/'))
   return json(400,'잘못된 경로입니다.');
  const target=new URL('/'+path,origin);
  for(const [key,value] of Object.entries(req.query||{})){
   if(key==='path')continue;
   for(const item of Array.isArray(value)?value:[value])target.searchParams.append(key,item);
  }
  const headers={'X-Flight-Bridge':token};
  if(req.headers['x-csrf-token'])headers['X-CSRF-Token']=req.headers['x-csrf-token'];
  let body;
  if(req.method==='POST'){
   if((req.headers['content-type']||'').split(';')[0]!=='application/json')return json(415,'JSON 요청만 지원합니다.');
   body=typeof req.body==='string'?req.body:JSON.stringify(req.body??{});
   if(Buffer.byteLength(body)>2*1024*1024)return json(413,'요청이 너무 큽니다.');
   headers['Content-Type']='application/json';
  }
  try{
   const result=await fetcher(target,{method:req.method,headers,body,
    redirect:'error',signal:AbortSignal.timeout(20000)});
   if(result.status>=500||[401,403].includes(result.status))
    return json(503,'검색 PC가 오프라인이거나 연결 인증이 맞지 않습니다.');
   // No upstream cookies, redirects or Cloudflare diagnostic pages are forwarded.
   for(const name of ['content-type','content-security-policy']){
    const value=result.headers.get(name);if(value)res.setHeader(name,value);
   }
   res.status(result.status);
   return res.send(req.method==='HEAD'?'':Buffer.from(await result.arrayBuffer()));
  }catch{return json(503,'검색 PC에 연결할 수 없습니다. PC와 공유 연결이 켜져 있는지 확인하세요.');}
 };
}

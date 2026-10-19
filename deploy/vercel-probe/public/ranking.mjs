export const dayAfter=(day,n)=>new Date(Date.parse(day)+n*864e5).toISOString().slice(0,10);
export function plan(c){
  if(!c.origins.length||!c.destinations.length)throw Error('출발 공항과 목적지를 선택하세요.');
  if(!/^\d{4}-\d{2}-\d{2}$/.test(c.start)||!/^\d{4}-\d{2}-\d{2}$/.test(c.end)||c.end<c.start)throw Error('출발 날짜 범위를 확인하세요.');
  if(!Number.isInteger(c.nights)||c.nights<1||c.nights>60)throw Error('숙박일수는 1~60박입니다.');
  const days=(Date.parse(c.end)-Date.parse(c.start))/864e5+1;
  if(days>31)throw Error('출발일 범위는 최대 31일입니다.');
  const tasks=[];
  for(let i=0;i<days;i++)for(const origin of c.origins)for(const destination of c.destinations){
    if(origin===destination)throw Error('출발 공항과 목적지가 같을 수 없습니다.');
    const departure=dayAfter(c.start,i),return_date=dayAfter(departure,c.nights);
    for(const provider of ['google','naver']){
      tasks.push({provider,origin,destination,departure,return_date,kind:'roundtrip',city:c.cities[destination]});
      if(c.pairs){tasks.push({provider,origin,destination,departure,kind:'outbound',city:c.cities[destination]});tasks.push({provider,origin:destination,destination:origin,departure:return_date,kind:'inbound',city:c.cities[destination],outbound_date:departure});}
    }
    tasks.push({provider:'myrealtrip',origin,destination,departure,return_date,kind:'reference',city:c.cities[destination]});
  }
  if(tasks.length>120)throw Error(`총 ${tasks.length}회 조회입니다. 무료 사용량 보호를 위해 120회 이하가 되도록 조건을 나눠 주세요.`);
  return tasks;
}
export function clock(text){
  const m=text.match(/(오전|오후)\s*(\d{1,2}):(\d{2})에\s*.*?에서 출발하여/);
  if(m)return ((+m[2]%12)+(m[1]==='오후'?12:0))*60+ +m[3];
  const n=text.match(/(\d{2}):(\d{2})[A-Z]{3}/);return n?+n[1]*60+ +n[2]:null;
}
export function inWindow(value,window){
  if(!window?.start||!window?.end)return true;
  if(value===null)return false;
  const min=s=>+s.slice(0,2)*60+ +s.slice(3,5),a=min(window.start),b=min(window.end);
  return a<=b?value>=a&&value<=b:value>=a||value<=b;
}
export function rank(records,city,conditions){
  let excluded=0;const all=[];
  for(const {task,result} of records){
    if(task.city!==city)continue;
    for(const row of result.observations||[]){
      const window=task.kind==='inbound'?conditions.inbound:conditions.outbound;
      const inboundUnknown=task.kind==='roundtrip'&&conditions.inbound?.start&&conditions.inbound?.end;
      if(inboundUnknown||!inWindow(clock(row.text),window)){excluded++;continue;}
      all.push({...row,task,url:result.search_url,observed_at:result.observed_at});
    }
  }
  const unique=rows=>[...new Map(rows.map(r=>[JSON.stringify([r.task.provider,r.task.origin,r.task.destination,r.task.departure,r.task.return_date,r.amount,r.text]),r])).values()];
  const rt=unique(all.filter(r=>r.task.kind==='roundtrip')),references=unique(all.filter(r=>r.task.kind==='reference'));
  const out=unique(all.filter(r=>r.task.kind==='outbound')),inbound=unique(all.filter(r=>r.task.kind==='inbound')),pairs=[];
  for(const a of out)for(const b of inbound){
    if(a.task.origin!==b.task.destination||a.task.departure!==b.task.outbound_date)continue;
    pairs.push({amount:a.amount+b.amount,outbound:a,inbound:b});
    if(pairs.length>200){pairs.sort((a,b)=>a.amount-b.amount);pairs.length=20;}
  }
  const top=rows=>rows.sort((a,b)=>a.amount-b.amount).slice(0,20);
  return {roundtrips:top(rt),pairs:top(pairs),references:top(references),excluded};
}

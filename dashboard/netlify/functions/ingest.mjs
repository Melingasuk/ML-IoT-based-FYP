import {getStore} from '@netlify/blobs';
import {body,digest,equal,json} from '../../lib/security.mjs';
import {validateUpload} from '../../lib/telemetry.mjs';
export function createHandler(storeFactory=getStore) { return async function(req) {
 if(req.method!=='POST') return json({error:'Method not allowed'},405);
 const key=process.env.INGEST_KEY_HASH;
 if(!key) return json({error:'Not configured'},503);
 const token=(req.headers.get('authorization')||'').replace(/^Bearer /,'');
 if(!/^[A-Za-z0-9_-]{43}$/.test(token)||!equal(digest(token),key)) return json({error:'Unauthorized'},401);
 let record;try {record=validateUpload(await body(req));}catch{return json({error:'Invalid or stale telemetry'},400);}
 try {
  const store=storeFactory({name:'soilhealth-data',consistency:'strong'});
  const old=await store.get('latest',{type:'json'});
  if(old&&old.received_at>=record.received_at) return json({ok:true,ignored:true});
  const history=await store.get('history',{type:'json'})||[];
  const identity=r=>r.telemetry.boot_id+':'+r.telemetry.sequence;
  const records=[...history.filter(r=>identity(r)!==identity(record)),record].sort((a,b)=>a.received_at-b.received_at).slice(-240);
  await store.setJSON('history',records);
  await store.setJSON('latest',record);return json({ok:true});
 } catch {return json({error:'Storage unavailable'},503);}
}
}
export default createHandler();
export const config={path:'/api/ingest',rateLimit:{windowLimit:30,windowSize:60,aggregateBy:['ip','domain']}};

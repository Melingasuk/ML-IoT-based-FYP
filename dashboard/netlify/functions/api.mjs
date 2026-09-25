import {getStore} from '@netlify/blobs';
import {cookie,digest,getSession,json,sameOrigin,sessionToken} from '../../lib/security.mjs';
export function createHandler(storeFactory=getStore) { return async function(req) {
 try {
  const route=new URL(req.url).pathname;
  const auth=storeFactory({name:'soilhealth-auth',consistency:'strong'});
  if(route==='/api/logout'&&req.method==='POST') {
   if(!sameOrigin(req)) return json({error:'Origin denied'},403);
   const token=sessionToken(req); if(token) await auth.delete('session/'+digest(token));
   return json({ok:true},200,{'Set-Cookie':cookie('',0)});
  }
  if(req.method!=='GET') return json({error:'Method not allowed'},405);
  if(!process.env.DASHBOARD_PASSWORD_HASH) return json({error:'Not configured'},503);
  const session=await getSession(req,auth,digest(process.env.DASHBOARD_PASSWORD_HASH));
  if(!session) return json({error:'Sign in required'},401);
  if(route==='/api/session') return json({username:session.username,role:session.role});
  if(route!=='/api/telemetry') return json({error:'Not found'},404);
  const store=storeFactory({name:'soilhealth-data',consistency:'strong'});
  const record=await store.get('latest',{type:'json'});
  const age=record?Math.max(0,Date.now()/1000-record.received_at):null;
  const history=await store.get('history',{type:'json'})|| (record?[record]:[]);
  return json({record,history,age_seconds:age,stale:age===null||age>45,server_time:Date.now()/1000});
 } catch {return json({error:'Data service temporarily unavailable'},503);}
}
}
export default createHandler();
export const config={path:['/api/session','/api/logout','/api/telemetry']};

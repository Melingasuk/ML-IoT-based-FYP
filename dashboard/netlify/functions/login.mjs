import {getStore} from '@netlify/blobs';
import {body,cookie,digest,equal,json,randomToken,sameOrigin,verifyPassword} from '../../lib/security.mjs';
export function createHandler(storeFactory=getStore) { return async function(req) {
 if(req.method!=='POST') return json({error:'Method not allowed'},405);
 if(!sameOrigin(req)) return json({error:'Origin denied'},403);
 try {
  if(!process.env.DASHBOARD_PASSWORD_HASH||!process.env.DASHBOARD_USERNAME) return json({error:'Login has not been configured'},503);
  let data;try {data=await body(req);}catch{return json({error:'Invalid request'},400);}
  if(typeof data.username!=='string'||typeof data.password!=='string'||data.password.length>256||data.username.length>128) return json({error:'Invalid credentials'},401);
  const valid=await verifyPassword(data.password,process.env.DASHBOARD_PASSWORD_HASH);
  if(!valid||!equal(data.username,process.env.DASHBOARD_USERNAME)) return json({error:'Invalid credentials'},401);
  const token=randomToken();const store=storeFactory({name:'soilhealth-auth',consistency:'strong'});
  const user={username:process.env.DASHBOARD_USERNAME,role:'viewer'};
  await store.setJSON('session/'+digest(token),{...user,expires:Date.now()+8*3600*1000,version:digest(process.env.DASHBOARD_PASSWORD_HASH)});
  return json(user,200,{'Set-Cookie':cookie(token,8*3600)});
 } catch {return json({error:'Login service temporarily unavailable'},503);}
}
}
export default createHandler();
export const config={path:'/api/login',rateLimit:{windowLimit:5,windowSize:60,aggregateBy:['ip','domain']}};

import {getStore} from '@netlify/blobs';
export function createHandler(storeFactory=getStore){return async req=>{
 const headers={'Cache-Control':'no-store'};
 if(req.method!=='GET')return new Response(null,{status:405,headers});
 const boot=new URL(req.url).searchParams.get('boot');
 if(!/^[a-f0-9]{16}$/.test(boot||''))return new Response(null,{status:400,headers});
 try{const r=await storeFactory({name:'soilhealth-data',consistency:'strong'}).get('latest',{type:'json'});
 const age=Date.now()/1000-r?.received_at;
 const ok=r?.telemetry?.boot_id===boot&&!r.retained&&age>=0&&age<45;
 return new Response(null,{status:ok?204:404,headers});
 }catch{return new Response(null,{status:503,headers});}
};}
export default createHandler();
export const config={path:'/api/receipt',rateLimit:{windowLimit:12,windowSize:60,aggregateBy:['ip','domain']}};

import {createHash, timingSafeEqual, scrypt, randomBytes} from 'node:crypto';
import {promisify} from 'node:util';
const derive=promisify(scrypt);
export const digest=s=>createHash('sha256').update(s).digest('hex');
export const randomToken=()=>randomBytes(32).toString('base64url');
export function equal(a,b) {return timingSafeEqual(Buffer.from(digest(a)),Buffer.from(digest(b)));}
export async function verifyPassword(password,encoded) {
  const [salt,hash]=encoded.split(':');
  if(!/^[a-f0-9]{32}$/.test(salt||'')||!/^[a-f0-9]{128}$/.test(hash||'')) throw Error('Password configuration missing');
  const actual=await derive(password,salt,64,{N:32768,r:8,p:1,maxmem:64*1024*1024});
  return timingSafeEqual(actual,Buffer.from(hash,'hex'));
}
export function json(data,status=200,headers={}) {
 return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...headers}});
}
export function sameOrigin(req) {return req.headers.get('origin')===new URL(req.url).origin;}
export async function body(req) {
 if(!req.headers.get('content-type')?.startsWith('application/json')) throw Error('Expected JSON');
 const text=await req.text(); if(Buffer.byteLength(text)>8192) throw Error('Body too large'); return JSON.parse(text);
}
export const COOKIE='__Host-soilhealth';
export const cookie=(token,seconds)=>`${COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${seconds}`;
export function sessionToken(req) {const value=(req.headers.get('cookie')||'').split(';').map(s=>s.trim()).find(s=>s.startsWith(COOKIE+'='))?.slice(COOKIE.length+1); return /^[A-Za-z0-9_-]{43}$/.test(value||'')?value:null;}
export async function getSession(req,store,version) {
 const token=sessionToken(req); if(!token) return null;
 const session=await store.get('session/'+digest(token),{type:'json'});
 return session&&session.expires>Date.now()&&session.version===version?session:null;
}

import test from 'node:test';
import assert from 'node:assert/strict';
import {createHandler} from '../netlify/functions/receipt.mjs';
test('cloud receipt requires matching boot, recent stored data and non-retained sample',async()=>{
 let record={received_at:Date.now()/1000,retained:false,telemetry:{boot_id:'1234567890abcdef'}};
 const handler=createHandler(()=>({get:async()=>record}));
 const req=()=>new Request('https://example.com/api/receipt?boot=1234567890abcdef');
 assert.equal((await handler(req())).status,204);
 record.telemetry.boot_id='0000000000000000';assert.equal((await handler(req())).status,404);
 record.telemetry.boot_id='1234567890abcdef';record.received_at-=70;assert.equal((await handler(req())).status,404);
 record.received_at=Date.now()/1000;record.retained=true;assert.equal((await handler(req())).status,404);
 assert.equal((await handler(new Request('https://example.com/api/receipt?boot=no'))).status,400);
 assert.equal((await handler(new Request('https://example.com/api/receipt',{method:'POST'}))).status,405);
});

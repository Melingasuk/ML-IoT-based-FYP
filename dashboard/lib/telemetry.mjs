export const ranges={moisture_pct:[0,100],soil_temp_c:[-55,125],ph:[0,14],ec_us_cm:[0,65535],nitrogen_mg_kg:[0,65535],phosphorus_mg_kg:[0,65535],potassium_mg_kg:[0,65535]};
const number=(v,lo,hi)=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
export function validateUpload(input,now=Date.now()/1000) {
 if(!input||typeof input!=='object'||input.retained!==false||!number(input.received_at,now-120,now+30)) throw Error('Only recent non-retained telemetry is accepted');
 const d=input.telemetry;
 if(!d||d.device_id!=='esp32-01'||d.source!=='hardware'||d.schema_version!==1||!/^[a-f0-9]{16}$/.test(d.boot_id)) throw Error('Invalid device');
 for(const k of ['sequence','uptime_ms']) if(!Number.isInteger(d[k])||!number(d[k],0,4294967295)) throw Error('Invalid counter');
 for(const k of ['sensor_online','sensor_map_verified','reference_online','pump_on','pump_fault']) if(typeof d[k]!=='boolean') throw Error('Invalid status');
 if(d.timestamp!==null&&(!Number.isInteger(d.timestamp)||!number(d.timestamp,1700000000,now+300))) throw Error('Invalid timestamp');
 for(const [k,[lo,hi]] of Object.entries(ranges)) if(d.sensor_online?!number(d[k],lo,hi):d[k]!==null) throw Error('Invalid soil value');
 if(d.reference_online?!number(d.reference_temp_c,-55,125):d.reference_temp_c!==null) throw Error('Invalid reference value');
 if(d.pump_test!==undefined&&typeof d.pump_test!=='boolean') throw Error('Invalid pump test flag');
 if(d.pump_on&&(d.pump_fault||!d.sensor_online||(!d.sensor_map_verified&&d.pump_test!==true))) throw Error('Invalid pump status');
 // Allowlist fields; client-supplied labels, permissions and HTML never enter storage.
 const keys=['schema_version','device_id','source','boot_id','sequence','uptime_ms','timestamp','sensor_online','sensor_map_verified','reference_online','pump_on','pump_fault',...Object.keys(ranges),'reference_temp_c'];
 const extra={pump_test:d.pump_test===true};
 if(d.capacitive!==undefined) {
  const c=d.capacitive;
  if(!c||!Number.isInteger(c.raw)||!number(c.raw,0,4095)||!Number.isInteger(c.mv)||!number(c.mv,0,3300)||typeof c.signal_valid!=='boolean'||typeof c.calibrated!=='boolean') throw Error('Invalid capacitive signal');
  if(c.signal_valid&&c.calibrated?!number(c.moisture_pct,0,100):c.moisture_pct!==null) throw Error('Invalid capacitive percentage');
  extra.capacitive=Object.fromEntries(['raw','mv','signal_valid','calibrated','moisture_pct'].map(k=>[k,c[k]]));
 }

 if(d.prediction!==undefined) {
  const p=d.prediction;
  if(!p||p.version!=='four-crop-v1'||!['banana','cabbage','kidneybeans','maize'].includes(p.crop)) throw Error('Invalid prediction');
  for(const [k,max] of [['measured_features',7],['missing_mask',511],['invalid_mask',511],['substituted_mask',127],['disagreement_mask',3]])
   if(!Number.isInteger(p[k])||p[k]<0||p[k]>max) throw Error('Invalid prediction diagnostics');
  const count=n=>n.toString(2).replace(/0/g,'').length;
  if(p.measured_features!==7-count(p.substituted_mask)||p.missing_mask&p.invalid_mask||((p.disagreement_mask&p.substituted_mask)!==p.disagreement_mask)) throw Error('Inconsistent prediction diagnostics');
  if(p.status!==(p.measured_features===0?'default_data_only':p.measured_features<7?'provisional':'complete_inputs')) throw Error('Invalid prediction status');
  extra.prediction=Object.fromEntries(['version','crop','status','measured_features','missing_mask','invalid_mask','substituted_mask','disagreement_mask'].map(k=>[k,p[k]]));
 }
 if(d.sms!==undefined) {
  if(!d.sms||typeof d.sms.enabled!=='boolean'||typeof d.sms.configured!=='boolean'||!Number.isInteger(d.sms.submitted)||!Number.isInteger(d.sms.failed)||!number(d.sms.submitted,0,4294967295)||!number(d.sms.failed,0,4294967295)) throw Error('Invalid SMS status');
  extra.sms=Object.fromEntries(['enabled','configured','submitted','failed'].map(k=>[k,d.sms[k]]));
 }
 return {received_at:input.received_at,uploaded_at:now,telemetry:{...Object.fromEntries(keys.map(k=>[k,d[k]])),...extra},test_context:'Bench test â€” probes in air'};
}

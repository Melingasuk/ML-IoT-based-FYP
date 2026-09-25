'use strict';
const $=id=>document.getElementById(id);
let signedIn=false,record=null,serverOffset=0,fetchFailed=false,history=[],chart=null,currentParam=null;
const fields={capacitive:['capacitive_relative_pct','Capacitive relative moisture','%'],moisture:['moisture_pct','Moisture','%'],ph:['ph','pH',''],nitrogen:['nitrogen_mg_kg','Nitrogen','mg/kg'],phosphorus:['phosphorus_mg_kg','Phosphorus','mg/kg'],potassium:['potassium_mg_kg','Potassium','mg/kg'],ec:['ec_us_cm','Conductivity','µS/cm'],temp:['soil_temp_c','Soil temperature','°C']};
const units=Object.fromEntries(Object.values(fields).map(([k,,u])=>[k,u]));units.reference_temp_c='°C';
async function api(path,options={}) {
 const res=await fetch('/api/'+path,{credentials:'same-origin',cache:'no-store',...options});
 let data;try {data=await res.json();}catch {data={error:res.status===429?'Too many attempts. Wait a minute.':'Service unavailable.'};}
 if(!res.ok){const error=Error(data.error||'Request failed');error.status=res.status;throw error;}return data;
}
function showLogin() {signedIn=false;record=null;history=[];if(chart){chart.destroy();chart=null;}fetchFailed=false;$('main-system-application').classList.add('hidden');$('auth-portal-screen').classList.remove('hidden');render();}
function showDashboard(user) {signedIn=true;$('active-user-badge').textContent=user.username+' · Read-only';$('auth-portal-screen').classList.add('hidden');$('main-system-application').classList.remove('hidden');navigate('view-dashboard');refresh();}
$('loginForm').addEventListener('submit',async event=>{
 event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;$('login-error').classList.add('hidden');
 try {const user=await api('login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('username').value.trim(),password:$('password').value})});$('password').value='';showDashboard(user);}
 catch(error){$('login-error').textContent=error.message;$('login-error').classList.remove('hidden');}finally{button.disabled=false;}
});
$('logout').addEventListener('click',async event=>{event.preventDefault();try{await api('logout',{method:'POST'});showLogin();}catch{$('connection-status').textContent='Logout failed — retry';}});
function navigate(id){if(!signedIn)return;document.querySelectorAll('.dashboard-view-panel').forEach(el=>el.classList.toggle('hidden',el.id!==id));document.querySelectorAll('.nav-links [data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===id));$('page-title').textContent=({'view-dashboard':'Dashboard Overview','view-sensors-spec':'IoT Nodes / Sensors','view-parameter':'Sensor readings','view-settings-panel':'System Settings','view-ml-diagnostics':'ML Analysis'})[id]||'Dashboard';}
document.querySelectorAll('[data-view]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault();navigate(el.dataset.view);}));
document.querySelectorAll('[data-theme]').forEach(el=>el.addEventListener('click',()=>{document.body.classList.toggle('dark-theme-active',el.dataset.theme==='dark');document.querySelectorAll('[data-theme]').forEach(b=>b.classList.toggle('active-toggle',b===el));}));
document.querySelectorAll('[data-param]').forEach(el=>{el.tabIndex=0;el.setAttribute('role','button');el.addEventListener('click',()=>{currentParam=el.dataset.param;navigate('view-parameter');drawChart();});el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click();}});});
function render(){
 const age=record?Math.max(0,(Date.now()+serverOffset)/1000-record.received_at):null;
 const stale=age===null||age>45;const d=record?.telemetry;
 $('connection-status').textContent=fetchFailed?'Cloud connection interrupted':!record?'Waiting for receiver':stale?'Device offline — showing saved reading':d.sensor_online?'Receiving hardware readings':'Soil sensor offline';
 $('connection-status').classList.toggle('online',!!record&&!stale&&!fetchFailed&&d.sensor_online);
 $('last-update').textContent=record?'Last received: '+new Date(record.received_at*1000).toLocaleString()+(stale?' · Saved reading':' · Live'):'No readings received yet.';
 $('reading-age').textContent=age===null?'—':Math.floor(age)+' seconds';$('reading-sequence').textContent=d?String(d.sequence):'—';$('pump-report').textContent=d?((d.pump_fault?'FAULT · ': '')+(d.pump_on?'Reported ON':'Reported OFF')+(d.pump_test?' Ã‚· Demonstration':'')+(stale?' · Last received':'')):'Unknown';
 const prediction=d?.prediction;
 const names=['moisture','temperature','pH','N','P','K','EC','reference temperature','backup moisture'];
 const list=mask=>names.filter((_,i)=>mask&(1<<i)).join(', ')||'none';
 const medians=[52.734085,23.193949,6.278273,82.055542,52.358665,55.835072,1.119932];
 const replacements=mask=>names.slice(0,7).map((n,i)=>mask&(1<<i)?n+'='+medians[i].toFixed(3):null).filter(Boolean).join(', ')||'none';
 const cropNames={banana:'Banana',cabbage:'Cabbage',kidneybeans:'Kidney beans',maize:'Maize'};
 const summary=prediction?(prediction.status==='default_data_only'?'Default-input result: ':prediction.status==='provisional'?'Provisional crop: ':'Recommended crop: ')+cropNames[prediction.crop]+(stale?' · Saved result':''):'Waiting for the ESP32 crop model update.';
 $('crop-summary').textContent=summary;
 $('crop-detail').textContent=prediction?summary+'. Measured parameters: '+prediction.measured_features+'/7. Missing: '+list(prediction.missing_mask)+'. Invalid: '+list(prediction.invalid_mask)+'. Substituted with training medians: '+replacements(prediction.substituted_mask)+'. Sensor disagreement: '+list(prediction.disagreement_mask)+'. This is a model estimate, not a guarantee of crop suitability.':summary;
 const sms=d?.sms;
 $('sms-status').textContent=!sms?'Awaiting GSM status':!sms.configured?'Recipient not configured':!sms.enabled?'Configured; sending disabled':'Modem submissions: '+sms.submitted+' · Failed: '+sms.failed;
 document.querySelectorAll('[data-field]').forEach(el=>{const key=el.dataset.field;const cap=d?.capacitive;if(key==='capacitive'){el.textContent=cap?.calibrated&&cap.signal_valid?cap.moisture_pct.toFixed(1)+' % relative':'— %';el.nextElementSibling.textContent=!cap?'Awaiting sensor firmware':stale||fetchFailed?'Last received':!cap.signal_valid?'Check analog signal':cap.calibrated?'Live · relative scale':'Percentage calibration needed';return;}const value=d?.[key];el.textContent=typeof value==='number'?value.toLocaleString(undefined,{maximumFractionDigits:2})+' '+(units[key]||''):'—';el.nextElementSibling.classList.toggle('normal',!!record&&!stale&&!fetchFailed&&typeof value==='number');el.nextElementSibling.classList.toggle('saved',!record||stale||fetchFailed||typeof value!=='number');el.nextElementSibling.textContent=!record?'Waiting':stale||fetchFailed?'Last received':value==null?'Unavailable':'Live';});
}
async function refresh(){if(!signedIn||document.hidden)return;try{const result=await api('telemetry');if(!signedIn)return;serverOffset=result.server_time*1000-Date.now();fetchFailed=false;record=result.record;if(Array.isArray(result.history))history=result.history;if(record){const last=history.at(-1);if(!last||last.telemetry.boot_id!==record.telemetry.boot_id||last.telemetry.sequence!==record.telemetry.sequence){history.push(record);history=history.slice(-240);}if(currentParam)drawChart();}render();}catch(error){if(error.status===401){showLogin();return;}fetchFailed=true;render();}}
function drawChart(){if(!currentParam||!signedIn)return;const [key,label,unit]=fields[currentParam];$('parameter-screen-title').textContent=label;$('parameter-screen-desc').textContent='Received hardware values ('+(unit||'pH units')+'). Saved receiver history.';if(chart)chart.destroy();chart=new Chart($('agriTechChart'),{type:'line',data:{labels:history.map(r=>new Date(r.received_at*1000).toLocaleTimeString()),datasets:[{label,data:history.map(r=>currentParam==='capacitive'?(r.telemetry.capacitive?.calibrated&&r.telemetry.capacitive?.signal_valid?r.telemetry.capacitive.moisture_pct:null):r.telemetry[key]),borderColor:'#0073E6',spanGaps:false},...(currentParam==='temp'?[{label:'Reference temperature',data:history.map(r=>r.telemetry.reference_temp_c),borderColor:'#7F8C8D',spanGaps:false}]:[])]},options:{responsive:true,maintainAspectRatio:false,animation:false}});}
setInterval(refresh,2000);setInterval(()=>{if(signedIn)render();},1000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
api('session').then(showDashboard).catch(()=>showLogin());

$('export-history').addEventListener('click',()=>{
 const keys=['moisture_pct','soil_temp_c','ph','nitrogen_mg_kg','phosphorus_mg_kg','potassium_mg_kg','ec_us_cm','reference_temp_c','pump_on','pump_fault'];
 const rows=[['received_utc',...keys,'capacitive_mv','capacitive_relative_pct','crop','prediction_status'],...history.map(r=>[new Date(r.received_at*1000).toISOString(),...keys.map(k=>r.telemetry[k]??''),r.telemetry.capacitive?.mv??'',r.telemetry.capacitive?.moisture_pct??'',r.telemetry.prediction?.crop||'',r.telemetry.prediction?.status||''])];
 const url=URL.createObjectURL(new Blob([rows.map(r=>r.join(',')).join('\r\n')],{type:'text/csv'}));
 const a=document.createElement('a');a.href=url;a.download='soilhealth-recent-readings.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});

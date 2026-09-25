#include <Arduino.h>
#include <Preferences.h>
#include <esp_timer.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <SPI.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <time.h>
#include <math.h>
#include "config.h"
#include "logic.h"
#include "transparent_inference.h"
#include "trust.h"
#include "cloud_trust.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

Adafruit_ST7789 tft(TFT_CS,TFT_DC,TFT_MOSI,TFT_SCLK,TFT_RST);
HardwareSerial rs485(2), gsm(1);
OneWire oneWire(ONE_WIRE_PIN);
DallasTemperature dallas(&oneWire);
Preferences capPrefs;
uint16_t capRaw=0,capMv=0,capDry=0,capWet=0;
bool capSignal=false,capCalibrated=false;
float capPercent=NAN;
bool soilOnline=false, refOnline=false, pumpOn=false, pumpFault=false;
bool haveGoodSample=false, haveReadAttempt=false;
CropResult currentCrop();
String cropSMSBody(const char* event);
void queueSMS(const String& message);
void enqueueTelemetry();
bool pumpTestActive=false;
bool demoArmed=false;
uint32_t drySince=0,lastPumpOff=0;
uint32_t pumpTestStarted=0;
esp_timer_handle_t pumpCutoff=nullptr;
volatile bool pumpCutoffFired=false;
volatile uint32_t pumpCutoffAt=0;
void cutPumpPower(void*) {
  digitalWrite(PUMP_RELAY,RELAY_ACTIVE_LOW?HIGH:LOW);
  pumpCutoffAt=millis();pumpCutoffFired=true;
}
float moisture=NAN, soilTemp=NAN, ph=NAN, refTemp=NAN;
uint16_t ec=0,nitrogen=0,phosphorus=0,potassium=0;
uint32_t lastGood=0,pumpStarted=0,lastRead=0,lastPublish=0,conversionStarted=0;
constexpr uint32_t TFT_REFRESH_MS=2000;
uint32_t lastDisplay=0;
uint8_t goodStreak=0;
char bootId[17];
uint32_t sequenceNumber=0;
struct Payload { char text[2048]; uint32_t created; };
QueueHandle_t telemetryQueue=nullptr;
volatile uint32_t cloudReceiptAt=0;
bool gsmRegistered=false; uint32_t gsmCheckedAt=0;
bool smsAwaitingDelivery=false; uint32_t smsDeliveryDeadline=0;
int smsMessageRef=-1; uint32_t smsDelivered=0;
bool rgbPWM=false,rgbInitialized=false,rgbTesting=false;
uint32_t rgbTestStarted=0;
void rgbWrite(int r,int g,int b){
  if(!rgbInitialized)return;
  int pins[3]={LED_RED,LED_GREEN,LED_BLUE};int v[3]={r,g,b};
  for(int i=0;i<3;++i){int duty=RGB_COMMON_ANODE?255-v[i]:v[i];
    if(rgbPWM)ledcWrite(pins[i],duty);else digitalWrite(pins[i],duty>=128?HIGH:LOW);
  }
}
void serviceIndicators();
bool smsInProgress();
esp_timer_handle_t buzzerCutoff=nullptr;
void cutBuzzer(void*){digitalWrite(BUZZER_PIN,LOW);}
uint8_t beepsRemaining=0;
bool buzzerOn=false;
uint32_t buzzerDeadline=0,buzzerPulseMs=200;
void startBeep(uint8_t count,uint32_t pulseMs) {
  if(beepsRemaining){beepsRemaining=min(12,int(beepsRemaining)+count);return;}
  beepsRemaining=count; buzzerPulseMs=pulseMs; buzzerOn=true;
  digitalWrite(BUZZER_PIN,HIGH);if(buzzerCutoff){esp_timer_stop(buzzerCutoff);esp_timer_start_once(buzzerCutoff,pulseMs*1000);}
  buzzerDeadline=millis()+pulseMs;
}
void serviceBuzzer() {
  if(!beepsRemaining || int32_t(millis()-buzzerDeadline)<0) return;
  if(buzzerOn) { buzzerOn=false; digitalWrite(BUZZER_PIN,LOW); --beepsRemaining; }
  else { buzzerOn=true; digitalWrite(BUZZER_PIN,HIGH);if(buzzerCutoff){esp_timer_stop(buzzerCutoff);esp_timer_start_once(buzzerCutoff,buzzerPulseMs*1000);} }
  buzzerDeadline=millis()+buzzerPulseMs;
}

void setPump(bool on) {
  if(on==pumpOn) return;
  if(on) {
    if(!pumpCutoff){Serial.println("Pump denied: independent timer unavailable");return;}
    pumpCutoffFired=false;
    esp_timer_stop(pumpCutoff);
    if(esp_timer_start_once(pumpCutoff,uint64_t(pumpTestActive?3000:PUMP_MAX_MS)*1000)!=ESP_OK){Serial.println("Pump denied: cutoff timer failed");return;}
  } else if(pumpCutoff) esp_timer_stop(pumpCutoff);
  digitalWrite(PUMP_RELAY,(on==RELAY_ACTIVE_LOW)?LOW:HIGH);
  pumpOn=on;
  if(on) pumpStarted=millis();else {lastPumpOff=millis();drySince=0;}
  if(on) startBeep(1,150);
  Serial.println(on?"Pump ON":"Pump OFF");
  // Capture each transition immediately; periodic summary throttling cannot hide it.
  queueSMS(cropSMSBody("Event"));
  enqueueTelemetry();
}
void servicePumpSafety() {
  serviceBuzzer(); serviceIndicators();
  const uint32_t now=millis();
  if(pumpCutoffFired) {
    const uint32_t actualOff=pumpCutoffAt;pumpCutoffFired=false;
    if(!pumpTestActive)pumpFault=true;
    Serial.printf("Independent relay cutoff after %lu ms\n",(unsigned long)(actualOff-pumpStarted));
    setPump(false);pumpTestActive=false;
  }
  if(pumpTestActive && now-pumpTestStarted>=3000){setPump(false);pumpTestActive=false;Serial.println("Three-second pump test ended");}
  if(pumpOn && now-pumpStarted>=PUMP_MAX_MS) {
    pumpFault=true; setPump(false);
    Serial.println("PUMP TIMEOUT: latched off. Inspect irrigation before reboot/reset.");
  }
  if(pumpOn&&!pumpTestActive&&(!capSignal||!capCalibrated||!isfinite(capPercent)||capPercent>=CAP_PUMP_INHIBIT_PCT))setPump(false);
  if(pumpOn && (!soilOnline || !haveGoodSample || now-lastGood>STALE_MS)) setPump(false);
}

// SMS state machine: no multi-second delays and no real sending by default.
uint32_t smsSubmitted=0,smsFailed=0;
String smsQueue[8], smsReply;
uint8_t smsHead=0,smsCount=0,smsPhase=0;
uint32_t smsDeadline=0,smsNextTry=0;
bool smsInProgress(){return smsPhase!=0||smsAwaitingDelivery;}
void queueSMS(const String& message) {
  Serial.println(message);
  if(!ENABLE_SMS || !SMS_PHONE[0]) return;
  // Numbered ASCII messages preserve every reading without silent truncation.
  unsigned parts=(message.length()+149)/150;
  if(!parts) return;
  if(parts>8-smsCount) {Serial.println("SMS queue full; complete summary deferred");return;}
  for(unsigned i=0;i<parts;++i) {
    String part=message.substring(i*150,(i+1)*150);
    if(parts>1) part=String(i+1)+"/"+String(parts)+" "+part;
    smsQueue[(smsHead+smsCount)%8]=part; ++smsCount;
  }
}
void finishSMS(bool ok) {
  if(ok) ++smsSubmitted; else ++smsFailed;
  Serial.println(ok?"SMS modem confirmed submission":"SMS failed/timed out; delivery unconfirmed");
  if(smsCount){ smsQueue[smsHead]=""; smsHead=(smsHead+1)%8; --smsCount; }
  smsPhase=0; smsReply=""; smsNextTry=millis()+10000;
}
void smsCommand(const String& command,uint8_t phase,uint32_t timeout) {
  smsReply=""; gsm.print(command); gsm.print('\r');
  smsPhase=phase; smsDeadline=millis()+timeout;
}
void modemLine(String line) {
  line.trim();
  if(line.startsWith("+CREG:")) {
    int mode=-1,state=-1;
    if(sscanf(line.c_str(),"+CREG: %d,%d",&mode,&state)==2) {
      gsmRegistered=(state==1||state==5);gsmCheckedAt=millis();
      Serial.printf("GSM registration state=%d\n",state);
    }
  }
  if(line.startsWith("+CDS:")) {
    int fo=-1,mr=-1; const int comma=line.lastIndexOf(',');
    if(sscanf(line.c_str(),"+CDS: %d,%d",&fo,&mr)==2 && comma>=0 &&
       smsAwaitingDelivery && mr==smsMessageRef) {
      String status=line.substring(comma+1);status.trim();
      if(status=="0") {smsAwaitingDelivery=false;++smsDelivered;startBeep(1,150);Serial.println("SMS delivery confirmed by network status report");}
      else Serial.println("SMS status report: delivery not confirmed");
    }
  }
}
void serviceIndicators() {
  const uint32_t now=millis();
  bool wifi=WiFi.status()==WL_CONNECTED;
  bool cloud=wifi&&cloudReceiptAt&&now-cloudReceiptAt<60000;
  static bool oldWifi=false,oldCloud=false;
  if(wifi&&!oldWifi)startBeep(1,120);
  if(cloud&&!oldCloud)startBeep(1,180);
  oldWifi=wifi;oldCloud=cloud;
  if(smsAwaitingDelivery&&int32_t(now-smsDeliveryDeadline)>=0){smsAwaitingDelivery=false;Serial.println("SMS delivery receipt timed out; delivery unconfirmed");}
  bool ready=soilOnline&&refOnline&&capSignal&&haveGoodSample&&now-lastGood<STALE_MS&&!pumpFault;
  bool busy=(pumpOn&&!pumpCutoffFired)||smsInProgress();
  if(rgbTesting){
    uint32_t phase=(now-rgbTestStarted)/5000;
    if(phase<4){static int oldPhase=-1;if(int(phase)!=oldPhase){Serial.printf("RGB TEST %s\n",phase==0?"RED":phase==1?"GREEN":phase==2?"BLUE":"YELLOW");oldPhase=phase;}
      rgbWrite(phase==0||phase==3?STATUS_LED_BRIGHTNESS:0,phase==1||phase==3?STATUS_LED_BRIGHTNESS:0,phase==2?STATUS_LED_BRIGHTNESS:0);
      if(!rgbPWM){static uint32_t lastReadback=0;if(now-lastReadback>1000){lastReadback=now;Serial.printf("RGB pin levels R25=%d G33=%d B23=%d phase=%lu\n",digitalRead(LED_RED),digitalRead(LED_GREEN),digitalRead(LED_BLUE),(unsigned long)phase);}}return;}
    rgbTesting=false;Serial.println("RGB test ended; restoring readiness colour");
  }
  rgbWrite((busy||!ready)?STATUS_LED_BRIGHTNESS:0,(busy||ready)?STATUS_LED_BRIGHTNESS:0,0);
}
void serviceSMS() {
  if(!ENABLE_SMS || !SMS_PHONE[0]) return;
  int readBudget=128;
  while(gsm.available() && readBudget-- > 0) {
    char ch=char(gsm.read());smsReply+=ch;
    static String line;
    if(ch=='\n'){modemLine(line);line="";}else if(ch!='\r'){line+=ch;if(line.length()>350)line="";}
    if(smsPhase==0) Serial.write(smsReply[smsReply.length()-1]);
    if(smsReply.length()>512) smsReply.remove(0,128);
  }
  if(!smsPhase) {
    static uint32_t lastPoll=0;
    if(millis()-lastPoll>30000){lastPoll=millis();gsm.print("AT+CREG?\r");smsNextTry=millis()+1000;}
    if(smsCount && !smsAwaitingDelivery && int32_t(millis()-smsNextTry)>=0) {
      while(gsm.available()) gsm.read();
      smsCommand("AT",4,3000);
    }
    return;
  }
  if(smsReply.indexOf("ERROR")>=0 || int32_t(millis()-smsDeadline)>=0) { finishSMS(false); return; }
  if(smsPhase==4 && smsReply.indexOf("OK")>=0) smsCommand("AT+CMGF=1",5,3000);
  else if(smsPhase==5 && smsReply.indexOf("OK")>=0) smsCommand("AT+CSMP=49,167,0,0",6,3000);
  else if(smsPhase==6 && smsReply.indexOf("OK")>=0) smsCommand("AT+CNMI=2,1,0,1,0",1,3000);
  else if(smsPhase==1 && smsReply.indexOf("OK")>=0)
    smsCommand(String("AT+CMGS=\"")+SMS_PHONE+"\"",2,5000);
  else if(smsPhase==2 && smsReply.indexOf('>')>=0) {
    gsm.print(smsQueue[smsHead]); gsm.write(0x1a); smsReply="";
    smsPhase=3; smsDeadline=millis()+30000;
  } else if(smsPhase==3 && smsReply.indexOf("+CMGS:")>=0 && smsReply.indexOf("OK")>=0) {int at=smsReply.indexOf("+CMGS:");smsMessageRef=smsReply.substring(at+6).toInt();smsAwaitingDelivery=true;smsDeliveryDeadline=millis()+120000;finishSMS(true);}
}

bool readRegisters(uint16_t address,uint8_t count,uint16_t* values) {
  if(count<1 || count>3) return false;
  servicePumpSafety();
  // Silent interval and stale-frame drain; bounded response time.
  delay(30);
  while(rs485.available()) rs485.read();
  uint8_t frame[8]={MODBUS_SLAVE,3,uint8_t(address>>8),uint8_t(address),0,count,0,0};
  const uint16_t crc=crc16(frame,6); frame[6]=uint8_t(crc); frame[7]=uint8_t(crc>>8);
  digitalWrite(RS485_DE,HIGH); delayMicroseconds(200);
  rs485.write(frame,8); rs485.flush(); digitalWrite(RS485_DE,LOW);
  // Match the known-working sketch response settling time.
  const uint32_t settled=millis();
  while(millis()-settled<60) {servicePumpSafety(); serviceSMS(); delay(1);}
  uint8_t response[11]; size_t received=0;
  const size_t expected=5+2*count;
  const uint32_t started=millis();
  while(received<expected && millis()-started<MODBUS_TIMEOUT_MS) {
    if(rs485.available()) response[received++]=rs485.read();
    else { servicePumpSafety(); serviceSMS(); delay(1); }
    if(received==5 && (response[1]&0x80)) break;
  }
  if(!decodeRegisters(response,received,MODBUS_SLAVE,count,values)) {
    soilOnline=false; goodStreak=0; setPump(false);
    Serial.printf("Invalid/no Modbus reply at 0x%04X: bytes=%u raw=",address,unsigned(received));
    for(size_t i=0;i<received;++i) Serial.printf("%02X ",response[i]);
    Serial.println(); return false;
  }
  static uint8_t npkLogs=0;
  if(address==REG_N && count==3 && npkLogs<5) {
    ++npkLogs; Serial.print("NPK block CRC OK raw=");
    for(size_t i=0;i<received;++i) Serial.printf("%02X ",response[i]);
    Serial.printf("=> N=%u P=%u K=%u mg/kg\n",values[0],values[1],values[2]);
  }
  return true;
}
bool readRegister(uint16_t address,uint16_t& value) {return readRegisters(address,1,&value);}
void readSoil() {
  haveReadAttempt=true;
  uint16_t m,t,e,h,n,p,k;
  // Do not mix partial fresh values with an older sample.
  bool ok=readRegister(REG_MOISTURE,m) && readRegister(REG_TEMP,t) &&
    readRegister(REG_EC,e) && readRegister(REG_PH,h);
  if(ok) {
    uint16_t npk[3];
    if(readRegisters(REG_N,3,npk)) {n=npk[0];p=npk[1];k=npk[2];}
    else ok=readRegister(REG_N,n)&&readRegister(REG_P,p)&&readRegister(REG_K,k);
  }
  if(ok) {
    const float mm=m/MOISTURE_SCALE, tt=signedTemperature(t,TEMPERATURE_SCALE), hh=h/PH_SCALE;
    ok=isfinite(mm)&&isfinite(tt)&&isfinite(hh)&&mm>=0&&mm<=100&&tt>=-55&&tt<=125&&hh>=0&&hh<=14;
    if(ok) {
      moisture=mm; soilTemp=tt; ph=hh; ec=e; nitrogen=n; phosphorus=p; potassium=k;
      lastGood=millis(); haveGoodSample=true; if(goodStreak<3) ++goodStreak;
    }
  }
  soilOnline=ok;
  if(!ok) { goodStreak=0; setPump(false); }
}
void serviceReference() {
  if(millis()-conversionStarted<800) return;
  const float value=dallas.getTempCByIndex(0);
  refOnline=value!=DEVICE_DISCONNECTED_C && isfinite(value) && value>=-55 && value<=125;
  refTemp=refOnline?value:NAN;
  dallas.requestTemperatures(); conversionStarted=millis();
}
uint8_t oldAlerts=0;
uint32_t lastAlert=0;
void processAlerts() {
  if(pumpTestActive)return;
  bool valid=soilOnline&&haveGoodSample&&millis()-lastGood<STALE_MS&&capSignal&&capCalibrated&&isfinite(capPercent);
  bool dry=valid&&moisture<35.0f&&capPercent<35.0f;
  if(!dry)drySince=0;else if(!drySince)drySince=millis();
  bool stableStart=drySince&&millis()-drySince>=30000&&millis()-lastPumpOff>=60000;
  bool allowed=(ENABLE_AUTO_PUMP||demoArmed)&&(SENSOR_MAP_VERIFIED||DEMO_IRRIGATION)&&goodStreak>=3&&millis()>=PUMP_BOOT_DELAY_MS&&(pumpOn||stableStart);
  bool next=demoPumpDemand(pumpOn,valid,allowed,pumpFault,moisture,capPercent);

  if(next!=pumpOn) { setPump(next); /* Pump changes are included in the combined crop/pump SMS. */ }
  uint8_t alerts=(ph<PH_LOW?1:0)|(ph>PH_HIGH?2:0)|(nitrogen<N_LOW?4:0)|
                 (phosphorus<P_LOW?8:0)|(potassium<K_LOW?16:0);
  if((alerts & ~oldAlerts) && (!lastAlert || millis()-lastAlert>=300000)) {
    startBeep(3,200);
    /* Combined crop/pump SMS reports status without prescribing fertilizer. */
    lastAlert=millis();
  }
  oldAlerts=alerts;
}
void drawRow(int y,const char* label,const char* value) {
  tft.fillRect(16,y,208,19,ST77XX_BLACK);tft.setTextSize(2);tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(18,y+1);tft.print(label);tft.setCursor(126,y+1);tft.print(value);
}
void drawUI() {
  char b[20];tft.fillRect(0,0,240,35,0x0410);tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(2);tft.setCursor(48,12);tft.print("SOIL MONITOR");
  if(soilOnline)snprintf(b,sizeof(b),"%.1f%%",moisture);else strcpy(b,"--");drawRow(38,"Moist",b);
  if(soilOnline)snprintf(b,sizeof(b),"%.1f C",soilTemp);else strcpy(b,"--");drawRow(57,"Soil T",b);
  if(soilOnline)snprintf(b,sizeof(b),"%.2f",ph);else strcpy(b,"--");drawRow(76,"pH",b);
  if(soilOnline)snprintf(b,sizeof(b),"%u",ec);else strcpy(b,"--");drawRow(95,"EC uS/cm",b);
  if(soilOnline)snprintf(b,sizeof(b),"%u",nitrogen);else strcpy(b,"--");drawRow(114,"N mg/kg",b);
  if(soilOnline)snprintf(b,sizeof(b),"%u",phosphorus);else strcpy(b,"--");drawRow(133,"P mg/kg",b);
  if(soilOnline)snprintf(b,sizeof(b),"%u",potassium);else strcpy(b,"--");drawRow(152,"K mg/kg",b);
  if(refOnline)snprintf(b,sizeof(b),"%.1f C",refTemp);else strcpy(b,"--");drawRow(171,"Ref T",b);
  if(capSignal&&capCalibrated)snprintf(b,sizeof(b),"%.1f%%",capPercent);else strcpy(b,"-- %");drawRow(190,"Cap ref",b);
  tft.fillRect(16,212,208,66,ST77XX_BLACK);tft.setTextSize(2);
  tft.setCursor(24,214);tft.print(pumpFault?"Pump FAULT":pumpOn?"Pump ON":(ENABLE_AUTO_PUMP||demoArmed)?"Pump OFF":"Pump OFF (Setup)");
  CropResult shown=currentCrop();tft.setCursor(30,234);tft.print(SOIL_CLASS_NAMES[shown.crop]);tft.print(" est");
  tft.setCursor(42,254);tft.print(capCalibrated?"Cap: ready":!capDry||!capWet?"Cap: pending":"Cap: re-test");
}
void numberJSON(char* buf,size_t length,float value,bool valid) {
  if(valid && isfinite(value)) snprintf(buf,length,"%.2f",value); else snprintf(buf,length,"null");
}

CropResult currentCrop() {
  const float raw[9]={soilOnline?moisture:NAN,soilOnline?soilTemp:NAN,soilOnline?ph:NAN,
    soilOnline?float(nitrogen):NAN,soilOnline?float(phosphorus):NAN,soilOnline?float(potassium):NAN,
    soilOnline?float(ec)/1000.0f:NAN,refOnline?refTemp:NAN,capCalibrated&&capSignal?capPercent:NAN};
  return inferCropTransparent(raw);
}
void predictionMasks(const CropResult& r,unsigned& missing,unsigned& invalid,unsigned& substituted) {
  missing=invalid=substituted=0;
  // Include the installed capacitive backup; uncalibrated percentages remain missing.
  for(int i=0;i<9;++i) {if(r.inputIssues[i]==1) missing|=1u<<i;else if(r.inputIssues[i]==2) invalid|=1u<<i;}
  for(int i=0;i<7;++i) if(r.substituted[i]) substituted|=1u<<i;
}
const char* cropStatus(const CropResult& r) {
  return r.measuredFeatures==0?"default_data_only":r.measuredFeatures<7?"provisional":"complete_inputs";
}
String cropSMSBody(const char* event) {
  CropResult r=currentCrop();unsigned missing,invalid,substituted;predictionMasks(r,missing,invalid,substituted);
  const char* shortNames[9]={"SM","T","pH","N","P","K","EC","RefT","Cap"};
  auto names=[&](unsigned mask){String out;for(int i=0;i<9;++i)if(mask&(1u<<i)){if(out.length())out+=",";out+=shortNames[i];}return out.length()?out:String("none");};
  auto reading=[](float value,bool valid,int decimals){return valid&&isfinite(value)?String(value,decimals):String("NA");};
  bool fresh=soilOnline&&haveGoodSample&&millis()-lastGood<STALE_MS;
  // Same order and units as the nine TFT rows. Cap is relative moisture.
  String body=String(event)+":SM="+reading(moisture,fresh,1)+"%;T="+reading(soilTemp,fresh,1)+"C;pH="+reading(ph,fresh,2)+
    ";EC="+reading(ec,fresh,0)+"uS/cm;N="+reading(nitrogen,fresh,0)+";P="+reading(phosphorus,fresh,0)+
    ";K="+reading(potassium,fresh,0)+"mg/kg;RefT="+reading(refTemp,refOnline,1)+"C;Cap="+reading(capPercent,capSignal&&capCalibrated,1)+"%"+
    ";Pump="+(pumpFault?"FAULT":pumpOn?"ON":(ENABLE_AUTO_PUMP||demoArmed)?"OFF":"OFF(setup)")+
    ";Crop="+SOIL_CLASS_NAMES[r.crop]+" PROVISIONAL"+(r.measuredFeatures==0?String("(default inputs)"):String(""))+
    ";Miss:"+names(missing)+";Bad:"+names(invalid)+";Fill:"+names(substituted);
  if(r.moistureDisagreement||r.temperatureDisagreement)body+=";Diff:"+String(r.moistureDisagreement?"SM":"")+String(r.temperatureDisagreement?"T":"");
  return body;
}
void serviceCropSMS() {
  if(!ENABLE_SMS || !SMS_PHONE[0] || !haveReadAttempt) return;
  static bool started=false;static uint32_t lastSent=0;static String previous;
  String body=cropSMSBody("Status");
  if(shouldSendCropSummary(started,body!=previous,millis()-lastSent)) {
    if((body.length()+149)/150<=8-smsCount) {queueSMS(body);previous=body;lastSent=millis();started=true;}
  }
}

void enqueueTelemetry() {
  if(!telemetryQueue) return;
  char cm[20],m[20],t[20],h[20],r[20],e[20],n[20],p[20],k[20],stamp[32];
  numberJSON(m,sizeof(m),moisture,soilOnline); numberJSON(t,sizeof(t),soilTemp,soilOnline);
  numberJSON(h,sizeof(h),ph,soilOnline); numberJSON(r,sizeof(r),refTemp,refOnline);
  numberJSON(e,sizeof(e),ec,soilOnline); numberJSON(n,sizeof(n),nitrogen,soilOnline);
  numberJSON(p,sizeof(p),phosphorus,soilOnline); numberJSON(k,sizeof(k),potassium,soilOnline);
  numberJSON(cm,sizeof(cm),capPercent,capCalibrated&&capSignal);
  const time_t now=time(nullptr);
  if(now>1700000000) snprintf(stamp,sizeof(stamp),"%lld",(long long)now); else strcpy(stamp,"null");
  Payload payload{}; payload.created=millis();
  int size=snprintf(payload.text,sizeof(payload.text),
    "{\"schema_version\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\",\"sequence\":%lu,"
    "\"source\":\"hardware\",\"timestamp\":%s,\"uptime_ms\":%lu,\"sensor_online\":%s,"
    "\"sensor_map_verified\":%s,\"reference_online\":%s,\"pump_on\":%s,\"pump_fault\":%s,"
    "\"moisture_pct\":%s,\"soil_temp_c\":%s,\"reference_temp_c\":%s,\"ph\":%s,"
    "\"ec_us_cm\":%s,\"nitrogen_mg_kg\":%s,\"phosphorus_mg_kg\":%s,\"potassium_mg_kg\":%s}",
    DEVICE_ID,bootId,(unsigned long)sequenceNumber++,stamp,(unsigned long)millis(),
    soilOnline?"true":"false",SENSOR_MAP_VERIFIED?"true":"false",refOnline?"true":"false",
    pumpOn?"true":"false",pumpFault?"true":"false",m,t,r,h,e,n,p,k);
  if(size>0 && size<int(sizeof(payload.text))) {
    CropResult prediction=currentCrop();unsigned missing,invalid,substituted;predictionMasks(prediction,missing,invalid,substituted);
    int extra=snprintf(payload.text+size-1,sizeof(payload.text)-size+1,
      ",\"prediction\":{\"version\":\"four-crop-v1\",\"crop\":\"%s\",\"status\":\"%s\",\"measured_features\":%u,\"missing_mask\":%u,\"invalid_mask\":%u,\"substituted_mask\":%u,\"disagreement_mask\":%u},"
      "\"pump_test\":%s,\"capacitive\":{\"raw\":%u,\"mv\":%u,\"signal_valid\":%s,\"calibrated\":%s,\"moisture_pct\":%s},\"sms\":{\"enabled\":%s,\"configured\":%s,\"submitted\":%lu,\"failed\":%lu}}",
      SOIL_CLASS_NAMES[prediction.crop],cropStatus(prediction),prediction.measuredFeatures,missing,invalid,substituted,
      (prediction.moistureDisagreement?1:0)|(prediction.temperatureDisagreement?2:0),
      (pumpTestActive||(DEMO_IRRIGATION&&pumpOn))?"true":"false",capRaw,capMv,capSignal?"true":"false",capCalibrated?"true":"false",cm,
      ENABLE_SMS?"true":"false",SMS_PHONE[0]?"true":"false",(unsigned long)smsSubmitted,(unsigned long)smsFailed);
    if(extra>0 && extra<int(sizeof(payload.text)-size+1))xQueueOverwrite(telemetryQueue,&payload);
  }
}
// Networking is isolated from the local sensor/pump loop. Only this task owns MQTT/Wi-Fi.
void networkTask(void*) {
  if(!WIFI_SSID[0] || !MQTT_PASSWORD[0] || !MQTT_ROOT_CA[0]) {
    Serial.println("MQTT disabled: fill secrets.h (Wi-Fi and device password)");
    vTaskDelete(nullptr); return;
  }
  WiFiClientSecure tls; tls.setCACert(MQTT_ROOT_CA); tls.setHandshakeTimeout(8);
  PubSubClient mqtt(tls); mqtt.setServer(MQTT_HOST,MQTT_PORT);
  mqtt.setBufferSize(2304); mqtt.setKeepAlive(30); mqtt.setSocketTimeout(5);
  WiFi.onEvent([](WiFiEvent_t event,WiFiEventInfo_t info){
    if(event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED)Serial.printf("WiFi disconnected reason=%u\n",info.wifi_sta_disconnected.reason);
    if(event==ARDUINO_EVENT_WIFI_STA_GOT_IP)Serial.println("WiFi obtained IP");
  });
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  configTime(0,0,"pool.ntp.org","time.google.com");
  uint32_t receiptPoll=0;
  uint32_t retry=millis(), wifiRetry=millis(); bool hadConnection=false;
  char clientId[64]; snprintf(clientId,sizeof(clientId),"soilhealth-%s-%s",DEVICE_ID,bootId);
  for(;;) {
    uint32_t now=millis();
    if(WiFi.status()!=WL_CONNECTED) {
      if(hadConnection) { tls.stop(); hadConnection=false; }
      if(now-wifiRetry>=15000) { wifiRetry=now; WiFi.reconnect(); }
    } else if(time(nullptr)>1700000000) {
      if(!mqtt.connected() && int32_t(now-retry)>=0) {
        retry=now+15000;
        if(mqtt.connect(clientId,MQTT_USER,MQTT_PASSWORD,STATUS_TOPIC,1,true,"{\"device_id\":\"esp32-01\",\"online\":false}")) {
          hadConnection=true;
          mqtt.publish(STATUS_TOPIC,"{\"device_id\":\"esp32-01\",\"online\":true}",true);
          Serial.println("MQTT connected with certificate validation");
        } else Serial.printf("MQTT connect failed, state=%d\n",mqtt.state());
      }
      if(mqtt.connected()) {
        if(millis()-receiptPoll>20000){
          receiptPoll=millis();WiFiClientSecure cloudTLS;cloudTLS.setCACert(CLOUD_ROOT_CA);cloudTLS.setHandshakeTimeout(5);
          HTTPClient http;http.setConnectTimeout(4000);http.setTimeout(4000);
          String url=String("https://soilhealth-gateway-melingasuk.netlify.app/api/receipt?boot=")+bootId;
          if(http.begin(cloudTLS,url)){int code=http.GET();if(code==204){cloudReceiptAt=millis();Serial.println("Cloud storage receipt confirmed");}else Serial.printf("Cloud receipt pending HTTP=%d\n",code);http.end();}
        }
        mqtt.loop(); Payload pending;
        if(xQueueReceive(telemetryQueue,&pending,0)==pdTRUE && millis()-pending.created<15000) {
          // PubSubClient publishes QoS 0: success is a local send, not a delivery receipt.
          if(!mqtt.publish(TELEMETRY_TOPIC,pending.text,false)) Serial.println("MQTT send failed; sample dropped");
          else Serial.println("MQTT telemetry sent (QoS 0; check receiver for delivery)");
        }
      }
    }
    vTaskDelay(pdMS_TO_TICKS(25));
  }
}

void readCapacitive() {
  uint32_t raw=0,mv=0;
  for(int i=0;i<16;++i){raw+=analogRead(CAP_PIN);mv+=analogReadMilliVolts(CAP_PIN);}
  capRaw=raw/16;capMv=mv/16;
  // A plausible analog signal does not independently prove a connected sensor.
  capSignal=capRaw>10&&capRaw<4085&&capMv>50&&capMv<3100;
  capCalibrated=capDry>capWet+100&&capWet>50&&capDry<3100;
  capPercent=capCalibrated&&capSignal?constrain(100.0f*(float(capDry)-capMv)/(capDry-capWet),0.0f,100.0f):NAN;
  Serial.printf("CAP GPIO35 raw=%u mv=%u calibration=%s pct=%.2f\n",capRaw,capMv,capCalibrated?"relative endpoints":"pending",capPercent);
}
void serviceConsole() {
  static String command;
  while(Serial.available()) {
    char c=Serial.read();
    if(c=='\r')continue;
    if(c!='\n'){if(command.length()<80)command+=c;continue;}
    command.trim();if(!command.length())continue;
    if(command=="CAP_DRY"||command=="CAP_WET") {
      readCapacitive();
      if(capSignal){if(command=="CAP_DRY"){capDry=capMv;capPrefs.putUShort("dry",capDry);}else{capWet=capMv;capPrefs.putUShort("wet",capWet);}Serial.printf("CAP endpoints dry=%u mV wet=%u mV; requires dry > wet + 100 mV\n",capDry,capWet);}
    } else if(command=="RGB_TEST"){rgbTesting=true;rgbTestStarted=millis();Serial.printf("RGB PWM initialized=%d; test RED GREEN BLUE YELLOW, five seconds each\n",rgbPWM);}
    else if(command=="RGB_DC_TEST"){for(int pin:{LED_RED,LED_GREEN,LED_BLUE}){ledcDetach(pin);pinMode(pin,INPUT|OUTPUT);}rgbPWM=false;rgbTesting=true;rgbTestStarted=millis();Serial.println("RGB steady GPIO test (no PWM), RED GREEN BLUE YELLOW");}
    else if(command=="RGB_PWM"){bool a=ledcAttach(LED_RED,5000,8),b=ledcAttach(LED_GREEN,5000,8),c=ledcAttach(LED_BLUE,5000,8);rgbPWM=a&&b&&c;Serial.printf("RGB PWM restored=%d\n",rgbPWM);}
    else if(command=="PUMP_STOP"){demoArmed=false;setPump(false);smsCount=0;smsPhase=0;smsAwaitingDelivery=false;Serial.println("Pump OFF; demonstration disarmed");}
    else if(command=="ARM_DEMO"){demoArmed=true;drySince=0;Serial.println("Demo armed: both moisture inputs must stay below 35% for 30s");}
    else if(command=="TFT_RESET"){tft.init(240,280);tft.setRotation(0);tft.setTextWrap(false);tft.fillScreen(ST77XX_BLACK);drawUI();Serial.println("TFT reinitialized");}
    else if(command=="SENSOR_SCAN"){
      demoArmed=false;setPump(false);
      Serial.println("Read-only function 03 scan 0x0000..0x0024; unknown registers are NOT telemetry");
      for(uint16_t address=0;address<=0x24;++address){
        uint16_t raw=0;
        if(readRegister(address,raw))Serial.printf("SCAN 0x%04X raw=%u hex=%04X CRC=OK\n",address,raw,raw);
      }
      Serial.println("SCAN complete; normal documented sensor reads resume; pump remains disarmed");
    }
    else if(command=="CAP_STATUS"){Serial.printf("CAP endpoints dry=%u wet=%u mV\n",capDry,capWet);}
    else if(command=="SMS_TEST") queueSMS(cropSMSBody("Check"));
    else if(command=="GSM_AT"&&!smsPhase&&!smsCount){gsm.print("AT\r");}
    else if(command=="PUMP_TEST"){if(soilOnline&&goodStreak>=3&&!pumpFault){pumpTestActive=true;pumpTestStarted=millis();setPump(true);}else Serial.println("Pump test denied: need valid recent soil frames and no fault");}
    else if(command=="GSM_STATUS"&&!smsPhase&&!smsCount){gsm.print("AT+CPIN?\r");}
    else if(command=="GSM_SIGNAL"&&!smsPhase&&!smsCount){gsm.print("AT+CSQ\r");}
    else if(command=="GSM_NETWORK"&&!smsPhase&&!smsCount){gsm.print("AT+CREG?\r");}
    else if(command=="STATUS"){Serial.printf("SOIL moisture=%.2f temp=%.2f pH=%.2f EC=%u N=%u P=%u K=%u RefT=%.2f\n",moisture,soilTemp,ph,ec,nitrogen,phosphorus,potassium,refTemp);Serial.println(cropSMSBody("Inference"));Serial.printf("STATUS WiFi=%d IP=%s soil=%d ref=%d pump=%d sms_ok=%lu sms_fail=%lu\n",WiFi.status(),WiFi.localIP().toString().c_str(),soilOnline,refOnline,pumpOn,(unsigned long)smsSubmitted,(unsigned long)smsFailed);}
    else Serial.println("Unknown command or GSM busy");
    command="";
  }
}

void setup() {
  // Establish OFF before display initialization, modem work or network setup.
  digitalWrite(PUMP_RELAY,RELAY_ACTIVE_LOW?HIGH:LOW); pinMode(PUMP_RELAY,OUTPUT);
  digitalWrite(PUMP_RELAY,RELAY_ACTIVE_LOW?HIGH:LOW);
  Serial.begin(115200);
  esp_timer_create_args_t timerArgs{};timerArgs.callback=cutPumpPower;timerArgs.name="pump_cutoff";
  if(esp_timer_create(&timerArgs,&pumpCutoff)!=ESP_OK)Serial.println("Pump cutoff timer initialization failed; pump stays disabled");
  esp_timer_create_args_t buzzArgs{};buzzArgs.callback=cutBuzzer;buzzArgs.name="buzzer_cutoff";esp_timer_create(&buzzArgs,&buzzerCutoff);
  Serial.println("SoilHealth GPIO35 commissioning firmware 2026-09-20");
  analogReadResolution(12); analogSetPinAttenuation(CAP_PIN,ADC_11db); pinMode(CAP_PIN,INPUT);
  capPrefs.begin("soil-cap",false);capDry=capPrefs.getUShort("dry",0);capWet=capPrefs.getUShort("wet",0);
  for(int pin:{LED_RED,LED_GREEN,LED_BLUE,BUZZER_PIN}) { pinMode(pin,OUTPUT); digitalWrite(pin,LOW); }
  bool lr=ledcAttach(LED_RED,5000,8),lg=ledcAttach(LED_GREEN,5000,8),lb=ledcAttach(LED_BLUE,5000,8);
  rgbPWM=lr&&lg&&lb;
  if(!rgbPWM){for(int pin:{LED_RED,LED_GREEN,LED_BLUE}){ledcDetach(pin);pinMode(pin,OUTPUT);}}
  rgbInitialized=true;rgbWrite(STATUS_LED_BRIGHTNESS,0,0);
  Serial.printf("RGB PWM attach: red=%d green=%d blue=%d\n",lr,lg,lb);startBeep(1,150);
  pinMode(RS485_DE,OUTPUT); digitalWrite(RS485_DE,LOW);
  rs485.begin(MODBUS_BAUD,SERIAL_8N1,RS485_RX,RS485_TX);
  for(int i=0;i<100;++i){serviceBuzzer();delay(10);}
  uint16_t bootReading=0;
  Serial.print("Sensor before peripheral init: ");
  if(readRegister(REG_TEMP,bootReading)) Serial.printf("raw temperature=%u\n",bootReading);
  if(ENABLE_SMS) gsm.begin(9600,SERIAL_8N1,GSM_RX,GSM_TX);
  dallas.begin(); dallas.setResolution(12); dallas.setWaitForConversion(false);
  dallas.requestTemperatures(); conversionStarted=millis();
  tft.init(240,280); tft.setRotation(0); tft.setTextWrap(false); tft.fillScreen(ST77XX_BLACK); lastDisplay=millis(); drawUI();
  Serial.print("Sensor after peripheral init: ");
  if(readRegister(REG_TEMP,bootReading)) Serial.printf("raw temperature=%u\n",bootReading);
  snprintf(bootId,sizeof(bootId),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
  telemetryQueue=xQueueCreate(1,sizeof(Payload));
  if(!telemetryQueue || xTaskCreate(networkTask,"mqtt",12288,nullptr,1,nullptr)!=pdPASS)
    Serial.println("Network task allocation failed; local monitoring remains active");
  lastRead=millis()-READ_INTERVAL_MS; lastPublish=millis()-PUBLISH_INTERVAL_MS;
}
void loop() {
  servicePumpSafety(); serviceSMS(); serviceReference(); serviceCropSMS(); serviceConsole();
  if(millis()-lastRead>=READ_INTERVAL_MS) {
    lastRead=millis(); readCapacitive(); readSoil(); servicePumpSafety(); processAlerts();
  }
  if(millis()-lastDisplay>=TFT_REFRESH_MS) { lastDisplay=millis(); drawUI(); }
  if(millis()-lastPublish>=PUBLISH_INTERVAL_MS) { lastPublish=millis(); enqueueTelemetry(); }
  delay(2);
}

#pragma once
#include <stdint.h>
#include <stddef.h>
constexpr uint16_t crc16(const uint8_t* data, size_t length) {
  uint16_t crc=0xffff;
  for (size_t p=0;p<length;++p) {
    crc ^= data[p];
    for (int bit=0;bit<8;++bit) crc=(crc&1)?(crc>>1)^0xa001:(crc>>1);
  }
  return crc;
}
constexpr bool decodeRegister(const uint8_t* data, size_t n, uint8_t slave, uint16_t& out) {
  if(n!=7 || data[0]!=slave || data[1]!=3 || data[2]!=2) return false;
  if(crc16(data,5)!=(uint16_t(data[5]) | uint16_t(data[6])<<8)) return false;
  out=uint16_t(data[3])<<8 | data[4]; return true;
}
constexpr float signedTemperature(uint16_t raw, float scale) {
  return (raw&0x8000 ? int32_t(raw)-65536 : int32_t(raw))/scale;
}
constexpr bool demandPump(bool current, bool valid, bool permitted, bool fault,
                          float moisture, float low, float high) {
  return valid && permitted && !fault && (current ? moisture<high : moisture<low);
}
constexpr uint8_t crcExample[]={1,3,0,0,0,10};
static_assert(crc16(crcExample,6)==0xcdc5,"Modbus reference CRC");
static_assert(signedTemperature(0xff9c,10.0f)==-10.0f,"Signed temperature");
static_assert(!demandPump(true,false,true,false,20,35,60),"Sensor fault shuts pump off");
static_assert(!demandPump(true,true,true,true,20,35,60),"Timeout lockout");
static_assert(!demandPump(false,true,true,false,35,35,60),"No start at low threshold");
static_assert(demandPump(true,true,true,false,35,35,60),"Hysteresis holds");
static_assert(!demandPump(true,true,true,false,60,35,60),"Stop at high threshold");
constexpr bool checkDecoder() {
  uint8_t frame[7]={1,3,2,0x01,0xa4,0,0};
  const uint16_t crc=crc16(frame,5); frame[5]=uint8_t(crc); frame[6]=uint8_t(crc>>8);
  uint16_t value=0;
  if(!decodeRegister(frame,7,1,value) || value!=420) return false;
  if(decodeRegister(frame,6,1,value) || decodeRegister(frame,7,2,value)) return false;
  frame[3]^=1;
  if(decodeRegister(frame,7,1,value) || value!=420) return false;
  frame[3]^=1; frame[2]=4;
  if(decodeRegister(frame,7,1,value)) return false;
  frame[2]=2; frame[1]=0x83;
  return !decodeRegister(frame,7,1,value);
}
static_assert(checkDecoder(),"Modbus rejects CRC, length, slave, function and byte-count errors");

constexpr bool shouldSendCropSummary(bool started, bool changed, uint32_t elapsed) {
  return !started || (changed && elapsed>=60000u) || elapsed>=1800000u;
}
static_assert(shouldSendCropSummary(false,false,0),"First attempt yields a transparent summary");
static_assert(!shouldSendCropSummary(true,true,59999),"Changed summary rate limit");
static_assert(shouldSendCropSummary(true,true,60000),"Changed summary sent at limit");
static_assert(!shouldSendCropSummary(true,false,1799999),"Unchanged summary waits");
static_assert(shouldSendCropSummary(true,false,1800000),"Periodic summary");

constexpr bool demoPumpDemand(bool current,bool valid,bool allowed,bool fault,float soil,float cap){
 return valid&&allowed&&!fault&&(current?(soil<60.0f&&cap<60.0f):(soil<35.0f&&cap<35.0f));
}
static_assert(demoPumpDemand(false,true,true,false,34,20),"Dry soil starts pump");
static_assert(!demoPumpDemand(false,true,true,false,35,20),"No start at 35");
static_assert(demoPumpDemand(true,true,true,false,50,20),"Hold until 60");
static_assert(!demoPumpDemand(true,true,true,false,60,20),"Stop at 60");
static_assert(!demoPumpDemand(false,true,true,false,10,60),"Wet capacitive veto");
static_assert(!demoPumpDemand(true,false,true,false,10,10),"Invalid calibration stops pump");

static_assert(!demoPumpDemand(false,true,true,false,0,59),"Do not start with damp capacitive input");
static_assert(demoPumpDemand(true,true,true,false,40,40),"Both inputs hold hysteresis");

// Manual: function 03, contiguous N/P/K registers 0x001E..0x0020.
constexpr bool decodeRegisters(const uint8_t* data,size_t n,uint8_t slave,uint8_t count,uint16_t* out) {
  if(count<1||count>3||n!=size_t(5+2*count)||data[0]!=slave||data[1]!=3||data[2]!=2*count)return false;
  if(crc16(data,n-2)!=(uint16_t(data[n-2])|uint16_t(data[n-1])<<8))return false;
  for(uint8_t i=0;i<count;++i)out[i]=(uint16_t(data[3+2*i])<<8)|data[4+2*i];
  return true;
}
constexpr bool checkBlockDecoder(){
 uint8_t f[11]={1,3,6,0,0,0,42,1,44,0,0};uint16_t v[3]={};
 uint16_t c=crc16(f,9);f[9]=uint8_t(c);f[10]=uint8_t(c>>8);
 if(!decodeRegisters(f,11,1,3,v)||v[0]!=0||v[1]!=42||v[2]!=300)return false;
 if(decodeRegisters(f,10,1,3,v)||decodeRegisters(f,11,2,3,v)||decodeRegisters(f,11,1,2,v))return false;
 f[3]^=1;return !decodeRegisters(f,11,1,3,v);
}
static_assert(checkBlockDecoder(),"NPK block validates zeros, values, length, slave, count and CRC");

#include <Arduino.h>

// Read-only Modbus test. No Wi-Fi, SMS or irrigation commands.
// Disconnect pump power before flashing: software cannot control reset-time pins.
constexpr int RX_PIN=19, TX_PIN=4, DIRECTION_PIN=27, RELAY_PIN=13;
constexpr uint8_t SLAVE=1;
HardwareSerial sensor(2);

uint16_t crc16(const uint8_t* b,size_t n) {
  uint16_t c=0xffff;
  for(size_t i=0;i<n;i++) {
    c^=b[i];
    for(int j=0;j<8;j++) c=(c&1)?(c>>1)^0xa001:c>>1;
  }
  return c;
}
void hexDump(const uint8_t* b,size_t n) {
  for(size_t i=0;i<n;i++) Serial.printf("%02X ",b[i]);
}
bool readOne(uint16_t address,uint16_t& value) {
  delay(30);
  while(sensor.available()) sensor.read();
  uint8_t q[8]={SLAVE,3,uint8_t(address>>8),uint8_t(address),0,1,0,0};
  uint16_t c=crc16(q,6); q[6]=uint8_t(c); q[7]=uint8_t(c>>8);
  digitalWrite(DIRECTION_PIN,HIGH); delayMicroseconds(200);
  sensor.write(q,8); sensor.flush(); digitalWrite(DIRECTION_PIN,LOW);
  uint8_t r[32]; size_t n=0; uint32_t start=millis(),last=start;
  while(millis()-start<500) {
    while(sensor.available() && n<sizeof(r)) {r[n++]=sensor.read(); last=millis();}
    if(n==sizeof(r) || (n && millis()-last>=30)) break;
    delay(1);
  }
  Serial.printf("reg=0x%04X TX=",address); hexDump(q,8); Serial.print(" RX="); hexDump(r,n);
  if(n==0) {Serial.println(" NO_REPLY"); return false;}
  if(n<5 || crc16(r,n-2)!=(uint16_t(r[n-2])|(uint16_t(r[n-1])<<8))) {
    Serial.println(" INVALID_CRC_OR_LENGTH"); return false;
  }
  if(r[0]!=SLAVE) {Serial.println(" WRONG_SLAVE"); return false;}
  if(n==5 && r[1]==0x83) {Serial.printf(" VALID_EXCEPTION code=%u\n",r[2]); return false;}
  if(n!=7 || r[1]!=3 || r[2]!=2) {Serial.println(" UNEXPECTED_FRAME"); return false;}
  value=(uint16_t(r[3])<<8)|r[4];
  int32_t signedValue=value&0x8000?int32_t(value)-65536:value;
  Serial.printf(" VALID raw=%u signed=%ld\n",value,(long)signedValue);
  return true;
}
void runTests() {
  const uint32_t bauds[]={4800,9600,2400};
  const uint16_t regs[]={0,1,2,3,4,5,6,0x12,0x13,0x15,0x1e,0x1f,0x20};
  Serial.println("BEGIN READ-ONLY PROBE; slave=1; 8N1; function=03; no sensor writes");
  for(uint32_t baud:bauds) {
    sensor.end(); sensor.begin(baud,SERIAL_8N1,RX_PIN,TX_PIN); delay(100);
    Serial.printf("BAUD=%lu\n",(unsigned long)baud);
    unsigned valid=0;
    for(uint16_t address:regs) {uint16_t value=0; if(readOne(address,value)) ++valid;}
    Serial.printf("RESULT baud=%lu valid_registers=%u/13\n",(unsigned long)baud,valid);
  }
  Serial.println("END PROBE. Raw replies do not prove calibration or model identity. Send t to repeat.");
}
void setup() {
  digitalWrite(RELAY_PIN,HIGH); pinMode(RELAY_PIN,OUTPUT); digitalWrite(RELAY_PIN,HIGH);
  pinMode(DIRECTION_PIN,OUTPUT); digitalWrite(DIRECTION_PIN,LOW);
  Serial.begin(115200); delay(3000); runTests();
}
void loop() {
  if(Serial.available() && Serial.read()=='t') runTests();
  delay(10);
}

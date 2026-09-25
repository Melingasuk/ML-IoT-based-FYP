#include "transparent_inference.h"

// Seven primary readings, or nine including temperature/moisture backups.
// SM, soil temperature, pH, N, P, K, EC(mS/cm), [backup temperature, backup moisture].
void printResult(const float raw[9], int inputCount) {
  CropResult r = inferCropTransparent(raw);
  const char* status = r.measuredFeatures == 0 ? "default_data_only" : r.measuredFeatures < 7 ? "provisional" : "complete_inputs";
  Serial.print("{\"prototype\":true,\"status\":\""); Serial.print(status);
  Serial.print("\",\"crop\":\""); Serial.print(SOIL_CLASS_NAMES[r.crop]);
  Serial.print("\",\"measured_features\":"); Serial.print(r.measuredFeatures);
  Serial.print(",\"required_features\":7,\"issues\":[");
  bool comma = false;
  for (int i=0; i<inputCount; ++i) if (r.inputIssues[i]) {
    if (comma) Serial.print(','); comma = true;
    Serial.print("{\"input\":\""); Serial.print(INPUT_NAMES[i]);
    Serial.print("\",\"reason\":\"");
    Serial.print(r.inputIssues[i] == 1 ? "missing_or_nonfinite_or_marked_failed" : "outside_prototype_range");
    Serial.print("\"}");
  }
  if (r.moistureDisagreement || r.temperatureDisagreement) {
    if (comma) Serial.print(',');
    Serial.print("{\"disagreement\":[");
    if (r.moistureDisagreement) Serial.print("\"moisture\"");
    if (r.moistureDisagreement && r.temperatureDisagreement) Serial.print(',');
    if (r.temperatureDisagreement) Serial.print("\"temperature\"");
    Serial.print("]}");
  }
  Serial.print("],\"substitutions\":["); comma=false;
  for (int i=0; i<7; ++i) if (r.substituted[i]) {
    if (comma) Serial.print(','); comma=true;
    Serial.print("{\"feature\":\""); Serial.print(FEATURE_NAMES[i]);
    Serial.print("\",\"method\":\"training_median\",\"value\":"); Serial.print(r.features[i], 6); Serial.print('}');
  }
  Serial.print("],\"moisture_source\":\"");
  Serial.print(r.substituted[0] ? "training_median" : r.inputIssues[0] ? "backup" : r.inputIssues[8] ? "primary" : "fused");
  Serial.print("\",\"temperature_source\":\"");
  Serial.print(r.substituted[1] ? "training_median" : r.inputIssues[1] ? "backup" : r.inputIssues[7] ? "primary" : "fused");
  Serial.println("\",\"field_validated\":false}");
}
void setup() {
  Serial.begin(115200);
  Serial.println("Four-crop prototype: enter 7 or 9 CSV readings; nan for unavailable. EC must be mS/cm.");
}
void loop() {
  static char line[256]; static size_t length=0; static bool overflow=false;
  while (Serial.available()) {
    char c=(char)Serial.read(); if(c=='\r') continue;
    if(c!='\n') { if(length<sizeof(line)-1) line[length++]=c; else overflow=true; continue; }
    line[length]='\0';
    float raw[9]; for(int i=0;i<9;++i) raw[i]=NAN;
    int count=0; char* cursor=line; bool valid=!overflow;
    while(valid && *cursor && count<9) {
      char* end=nullptr; raw[count]=strtof(cursor,&end);
      if(end==cursor) {valid=false;break;}
      while(*end==' ' || *end=='\t') ++end;
      ++count;
      if(*end=='\0') {cursor=end;break;}
      if(*end!=',' || end[1]=='\0') {valid=false;break;}
      cursor=end+1;
    }
    if(valid && !*cursor && (count==7 || count==9)) printResult(raw,count);
    else Serial.println("Invalid input: expected exactly 7 or 9 CSV numbers; use nan for unavailable readings.");
    length=0; overflow=false;
  }
  delay(10);
}

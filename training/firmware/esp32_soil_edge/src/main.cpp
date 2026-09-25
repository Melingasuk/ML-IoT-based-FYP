#include <Arduino.h>
#include "crop_model.h"
#include "recommendation_map.h"
#include "sensor_fusion.h"

String runLocalInference(const float raw[9]) {
  FusionResult r = fuseSensors(raw);
  String prefix = String("Prototype ") + (r.available < 7 ? "monitor" : r.degraded ? "degraded" : "normal")
    + " cov=" + String(r.available * 100.0f / 7, 1) + "%: ";
  String sms;
  if (r.available < 7)
    sms = prefix + "SM=" + String(r.features[0], 1) + "% T=" + String(r.features[1], 1)
      + "C. Crop advice paused: temp disagreement or missing/invalid sensors.";
  else sms = prefix + recommendationForCrop(SOIL_CLASS_NAMES[predict_soil_crop(r.features)]);
  return sms.length() < 160 ? sms : sms.substring(0, 156) + "...";
}
void setup() {
  Serial.begin(115200);
  Serial.println("Soil fusion ready. SIM800C SMS output over serial.");
}
void loop() {
  static char line[192];
  static size_t length = 0;
  static bool overflow = false;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c != '\n') {
      if (length < sizeof(line)-1) line[length++] = c;
      else overflow = true;
      continue;
    }
    line[length] = '\0';
    float raw[9];
    char extra;
    int count = sscanf(line, "%f,%f,%f,%f,%f,%f,%f,%f,%f %c",
      &raw[0], &raw[1], &raw[2], &raw[3], &raw[4], &raw[5], &raw[6], &raw[7], &raw[8], &extra);
    if (!overflow && count == 9) Serial.println(runLocalInference(raw));
    else Serial.println("Check sensors: expected 9 CSV readings; use nan for failed channels.");
    length = 0;
    overflow = false;
  }
  // SIM800C UART transmission remains a hardware integration step.
  delay(10);
}


#pragma once
#include "crop_model.h"
#include "sensor_fusion.h"
#include "fallback_values.h"

static const char* const INPUT_NAMES[9] = {
  "moisture", "temperature", "pH", "N", "P", "K", "EC",
  "backup_temperature", "backup_moisture"
};
static const char* const FEATURE_NAMES[7] = {"moisture", "temperature", "pH", "N", "P", "K", "EC"};
static const float INPUT_LOW[9] = {0,-10,3.5,0,0,0,0,-10,0};
static const float INPUT_HIGH[9] = {100,60,9.5,200,200,250,5,60,100};
// Acquisition must mark stale/CRC-failed/disconnected values NAN; no old value is fresh.
// Issue codes: 0=valid, 1=unavailable/nonfinite, 2=outside prototype range.
struct CropResult {
  float features[7];
  uint8_t inputIssues[9];
  bool substituted[7];
  bool moistureDisagreement;
  bool temperatureDisagreement;
  uint8_t measuredFeatures;
  uint8_t crop;
};
inline CropResult inferCropTransparent(const float raw[9]) {
  CropResult result = {};
  FusionResult fused = fuseSensors(raw);
  result.measuredFeatures = fused.available;
  for (int i=0; i<9; ++i)
    result.inputIssues[i] = !isfinite(raw[i]) ? 1 : sensorValid(raw[i], INPUT_LOW[i], INPUT_HIGH[i]) ? 0 : 2;
  result.moistureDisagreement = !result.inputIssues[0] && !result.inputIssues[8] && fabsf(raw[0]-raw[8])>15;
  result.temperatureDisagreement = !result.inputIssues[1] && !result.inputIssues[7] && fabsf(raw[1]-raw[7])>5;
  for (int i=0; i<7; ++i) {
    result.substituted[i] = !isfinite(fused.features[i]);
    result.features[i] = result.substituted[i] ? TRAINING_MEDIANS[i] : fused.features[i];
  }
  result.crop = predict_soil_crop(result.features);
  return result;
}

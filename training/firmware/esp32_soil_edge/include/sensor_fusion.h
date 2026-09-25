#pragma once
#include <math.h>
inline bool sensorValid(float v, float low, float high) {
  return isfinite(v) && v >= low && v <= high;
}
inline float fusePair(float a, float b, float low, float high, float tolerance, bool& degraded) {
  bool av = sensorValid(a, low, high), bv = sensorValid(b, low, high);
  if (av && bv) return fabsf(a-b) <= tolerance ? (a+b)/2 : NAN;
  degraded = true;
  return av ? a : bv ? b : NAN;
}
struct FusionResult { float features[7]; int available; bool degraded; };
// Raw: SM, ST7in1, pH, N, P, K, EC, STDS18B20, SMCap.
// Acquisition must mark stale, failed or quarantined channels NAN.
inline FusionResult fuseSensors(const float raw[9]) {
  FusionResult r = {{0}, 0, false};
  r.features[0] = fusePair(raw[0], raw[8], 0, 100, 15, r.degraded);
  r.features[1] = fusePair(raw[1], raw[7], -10, 60, 5, r.degraded);
  const float lows[5] = {3.5,0,0,0,0}, highs[5] = {9.5,200,200,250,5};
  for (int i=0; i<5; ++i)
    r.features[i+2] = sensorValid(raw[i+2], lows[i], highs[i]) ? raw[i+2] : NAN;
  for (int i=0; i<7; ++i) if (isfinite(r.features[i])) ++r.available;
  return r;
}

# Dataset Schema Report

- Source: `D:/My FYP/FYP Dataset/Crop_recommendation.csv`
- Rows: 2200
- Columns: N, P, K, temperature, humidity, ph, rainfall, label
- Target labels (22): apple, banana, blackgram, chickpea, coconut, coffee, cotton, grapes, jute, kidneybeans, lentil, maize, mango, mothbeans, mungbean, muskmelon, orange, papaya, pigeonpeas, pomegranate, rice, watermelon

## Required ESP32 Sensor Vector

SM, ST7in1, pH, N, P, K, EC, STDS18B20, SMCap

## Comparison

- Matching required features: N, P, K, ph
- Missing required features: SM, ST7in1, EC, STDS18B20, SMCap
- Public-dataset-only features: temperature, humidity, rainfall

## Methodological Mismatch

The public dataset records laboratory/agronomic variables (N, P, K, temperature, humidity, ph, rainfall). The FYP edge vector requires direct ESP32 sensor readings (SM, ST7in1, pH, N, P, K, EC, STDS18B20, SMCap). Missing physical measurements cannot be recovered through preprocessing without collecting or simulating those sensor channels.

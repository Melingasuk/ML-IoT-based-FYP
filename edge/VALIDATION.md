# Validation — 19 September 2026

- Original desktop forest and exported crop_model.h match the previous artifacts byte for byte. No training was run.
- Desktop float32 reference agrees with the original model's predictions on all 1,000 existing synthetic rows with complete inputs.
- All 512 missingness combinations across the nine raw channels return a four-class prediction, disclose input gaps, and substitute exactly the unavailable physical quantities.
- 36 nonfinite/out-of-range input cases disclose the affected input.
- Checked valid backup recovery, conflicting sensor pairs, seven-primary-input mode, and all-missing default-data labeling.
- Arduino build passes for `esp32:esp32:esp32` with ESP32 Arduino core 3.3.7: 294,600 bytes flash (22% of selected application partition), 22,332 bytes static RAM (6%). These figures are for the standalone model sketch, not the full MQTT gateway.

Not yet verified: execution on the physical ESP32, live sensor calibration and units, compiled C++ versus Python prediction parity at runtime, integration into the active MQTT gateway, or receiver/dashboard display of prediction diagnostics. The tests above do not validate agronomic suitability or accuracy under missing data.

No board was flashed; no cloud service was changed.

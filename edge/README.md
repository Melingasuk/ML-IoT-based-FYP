# Four-crop edge model: transparent fallback

The original trained forest and its exported C++ model header are unchanged byte for byte. No retraining, tomato class, GitHub learning workflow, board upload, or live-dashboard deployment was performed.

Allowed outputs: banana, cabbage, kidneybeans, maize. These are prototype rankings among four trained classes, not a guarantee that any crop is suitable. Synthetic training has not established field accuracy.

## What changed

The inference wrapper continues predicting when inputs are unavailable. It uses valid primary/backup readings, fuses agreeing pairs, and fills remaining unavailable features with medians from the original 700-row training split. Medians never replace valid readings. Disagreeing pairs are disclosed and replaced with their training median rather than silently choosing a sensor.

The result reports the crop, number of measured physical quantities, each missing/nonfinite or out-of-range input, pair disagreements, each substituted feature and value, and primary/backup/fused data sources. Completeness is not confidence. No probability or field accuracy is claimed.

Statuses:
- `complete_inputs`: all seven quantities available, potentially through valid backups.
- `provisional`: at least one feature substituted; the result depends partly on training defaults.
- `default_data_only`: no measured quantities; the crop is a default-input model result, not evidence about the soil.

The acquisition layer must detect stale/disconnected/CRC-failed channels and pass NAN. The wrapper cannot detect a plausible but incorrect sensor value. It distinguishes unavailable/nonfinite from outside-range input, but NAN alone cannot identify the underlying hardware fault.

## Arduino use

Open `SoilCropEdge/SoilCropEdge.ino` in Arduino IDE with **ESP32 Dev Module** selected. This standalone sketch accepts readings through Serial Monitor at 115200 baud. It is a model test harness, not a replacement for the working MQTT/sensor gateway firmware. Flashing it would replace that gateway program. For the deployed system, include `transparent_inference.h` and call `inferCropTransparent(raw)` from the existing acquisition code, then extend the receiver/dashboard payload schema to preserve the returned diagnostics.

CSV order for seven readings:

`moisture_percent,soil_temperature_C,pH,N,P,K,EC_mS_per_cm`

Optionally append `backup_temperature_C,backup_moisture_percent` for nine readings. Missing optional backups are not shown as faults in seven-input mode. Use `nan` for failed primary channels. Invalid CSV is rejected rather than guessed.

Example (missing phosphorus, invalid EC):

`52,24,6.4,92,nan,48,-1`

**Unit contract:** the live gateway labels EC as uS/cm; divide by 1000 before passing it to this model, which uses mS/cm. Do not infer NPK calibration/unit parity from column names. The synthetic training NPK values still need validation against the physical sensor. Limits inherited from the prototype are software bounds, not universal agronomic limits.

Desktop example:

`python predict.py "52,24,6.4,92,nan,48,-1"`

`fallback_metadata.json` records medians, feature order and original model hashes. `soil_rf_desktop.json` is the unchanged desktop model, not an ESP32 loadable file.

## Computer receiver versus cloud receiver

In both designs, the ESP32 reads sensors and runs the model; HiveMQ transports messages; the receiver validates/stores them and forwards the latest result to Netlify. Moving the receiver does not move ML off the board.

Computer: ESP32 -> HiveMQ -> receiver + bridge on your computer -> Netlify dashboard.

Cloud: ESP32 -> HiveMQ -> receiver + bridge on a continuously running cloud server -> Netlify dashboard.

If your computer sleeps in the first design, forwarding stops. In the second design it continues while the ESP32, its internet connection, broker and cloud service are available. Cloud hosting cannot recover messages the device never sent. The present design does not establish durable replay of every missed sample.

For the least disruptive first migration, run the existing Python receiver and bridge on one small Linux VM with persistent disk, automatic service restart, private broker credentials and backups. Keep one active bridge to avoid duplicated forwarding. Store full history there; the current Netlify backend holds only the latest reading. Later the two processes can be combined if useful, but that is not required to remove the computer dependency.

A cloud receiver adds hosting cost and server maintenance. Your computer remains useful for firmware updates and testing but need not stay on. The ESP32 still needs power and internet to publish; local inference itself can run offline. The dashboard currently marks old readings stale after 45 seconds.

GitHub is not the continuously running receiver. Netlify remains the web/API host; its time-limited functions are not a persistent MQTT subscriber.

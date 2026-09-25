# SoilHealth Monitor — ML and IoT final-year project



Source snapshot published 25 September 2026.



- `soilhealth-iot/firmware/SoilHealthGateway/`: current ESP32 firmware, TFT, SIM800C SMS, RGB, pump safeguards, Modbus acquisition and embedded four-crop model.

- `soilhealth-iot/receiver/`: MQTT receiver, SQLite storage and cloud bridge.

- `dashboard/`: Netlify HTML/CSS/JavaScript dashboard and server functions.

- `training/`: synthetic data generation, model training, export and evaluation source.

- `edge/`: desktop inference and standalone edge-model example.



## Setup

Copy `secrets.example.h` to `secrets.h` beside the gateway sketch and fill in your Wi-Fi, MQTT and SMS settings locally. Select ESP32 Dev Module in Arduino IDE. Install the libraries required by the sketch includes. The firmware source is supplied; flashed binaries are excluded because they contain private credentials.



For the receiver, install `soilhealth-iot/receiver/requirements.txt`, copy `bridge.example.json` to `bridge.json` and enter your own endpoint and ingestion key. Run `python run_monitor.py` from that directory; enter the MQTT receiver password at the prompt. Existing PowerShell helper scripts retain the original computer's paths: use the portable Python command on other computers. Review MQTT host/user configuration in receiver.py and firmware config.h for your broker.



For the dashboard, follow `dashboard/README.md` and configure its environment variables in Netlify. Do not publish credentials.



## Verified limitations

The four-crop model uses synthetic training data and produces provisional recommendations; it has not been validated as a soil laboratory substitute. On 23 September 2026 the probe returned CRC-valid zero EC/NPK values across documented registers. Its exact measurement capability remains unresolved. A register scan does not validate unknown registers as nutrient measurements. Automatic irrigation remains disabled by default following the shared-supply blackout observed when the pump operated. Fix and verify power integrity before enabling pump operation.



The current firmware is the integrated gateway sketch, not the standalone example under edge. Supporting component READMEs may describe earlier implementation stages.


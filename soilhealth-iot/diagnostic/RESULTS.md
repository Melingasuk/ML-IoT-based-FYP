# ESP32 sensor probe result

The diagnostic was uploaded to COM4 with flash hashes verified. The connected chip identified itself as ESP32-D0WD-V3 revision 3.1. Pump power was disconnected by the user before upload.

The complete fresh test used slave address 1, 8N1 and read-only function 03. It made no sensor configuration writes.

| Baud | Result |
|---|---|
| 4800 | No replies for the tested registers |
| 9600 | CRC-valid replies for every register used by the gateway firmware |
| 2400 | No replies for the tested registers |

At 9600 baud, addresses 0x0000 through 0x0003 returned CRC-valid exception 02 responses (illegal data address), rather than the readings expected by the alternative sequential map. Registers 0x0004 and 0x0005 returned zero but their meanings are not inferred.

| Gateway field | Register | Raw value | Candidate decoded value |
|---|---|---:|---|
| Moisture | 0x0012 | 0 | 0% |
| Temperature | 0x0013 | 281 | 28.1 C |
| Conductivity | 0x0015 | 0 | 0 uS/cm |
| pH | 0x0006 | 700 | 7.00 |
| Nitrogen | 0x001E | 0 | 0 mg/kg |
| Phosphorus | 0x001F | 0 | 0 mg/kg |
| Potassium | 0x0020 | 0 | 0 mg/kg |

This supports the existing gateway's baud rate, slave address and register selection. It does not verify calibration, pH scaling against a reference, or the meaning of all-zero soil readings. Keep automatic irrigation disabled and SENSOR_MAP_VERIFIED=false until physical checks pass. The complete raw replies are in verified-probe-results.txt.

The board now runs the MQTT gateway, uploaded on COM4 with flash hash verification. TLS MQTT connection succeeded and the receiver database stored fresh hardware telemetry. A serialization error swapping pH and reference temperature was corrected and verified through the stored payload. All seven receiver tests pass.

An earlier gateway test returned zero bytes while sensor power was off. After the user powered the sensor and confirmed the power/connectivity checks, the gateway recovered: fresh telemetry was stored with sensor_online=true. Two consecutive messages, sequences 6 and 7 from boot d66b0de14fae7a47, arrived about 10 seconds apart; the latest was only 0.6 seconds old when inspected. Reported readings: soil temperature 27.0 C, reference temperature 27.38 C, pH 7.0, moisture 0%, and EC/N/P/K all zero. The serial capture is in work/gateway-powered-sensor-check.txt in the workspace.

This verifies sensor-to-ESP32-to-HiveMQ-to-local-receiver delivery, not measurement accuracy. Probe placement and reference/calibration checks remain necessary, particularly for the zero readings and pH scale. SENSOR_MAP_VERIFIED remains false; pump and automatic irrigation remain off. Dashboard integration and secure backend authentication are not established by this test.

Do not include secrets.h, credential-bearing firmware binaries, or the receiver database in a public deployment or distributable archive.

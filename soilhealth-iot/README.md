# SoilHealth ESP32 and read-only MQTT receiver

This package replaces the supplied Arduino sketch with a Wi-Fi MQTT version and provides a separate Python receiver. The receiver subscribes to one device and stores validated events in a local SQLite database. It does not publish, control the pump, expose a web API, or add secure dashboard login.

## HiveMQ configuration

Host: `7d0cd4a2144a434fa144922e570374ba.s1.eu.hivemq.cloud`, TLS port `8883`.

| Component | Username | Permission | Topic filter |
|---|---|---|---|
| ESP32 | soilhealth-esp32-01-scoped | soilhealth-esp32-01-publish: PUBLISH_ONLY | soilhealth/devices/esp32-01/# |
| Python receiver | soilhealth-receiver-01 | soilhealth-esp32-01-read: SUBSCRIBE_ONLY | soilhealth/devices/esp32-01/# |

The custom receiver permission was created and verified in HiveMQ. The receiver credential form was prepared; finish it by entering a new password, confirming it, and clicking Save. Use different passwords for the two clients. The older broad publisher credential `soilhealth-esp32-01` was not removed.

Keep credentials out of the Netlify frontend, public repositories, notebooks, and chat. The receiver uses the operating system's trusted certificate store. The firmware includes ISRG Root X1 in `trust.h`, downloaded from [Let's Encrypt](https://letsencrypt.org/certs/isrgrootx1.pem); the broker's chain was verified against that root on 2026-09-15. Certificate-chain changes may require a firmware trust update. TLS verification is never disabled.

## Start the receiver on Windows

Install Python 3.10 or later if needed. Open PowerShell in this package's `receiver` folder:

```powershell
python -m pip install -r requirements.txt
python receiver.py
```

Enter the password for `soilhealth-receiver-01` at the hidden prompt. The program connects with certificate validation and must report **Subscription accepted**. Alternatively run `start_receiver.ps1` from PowerShell. A private service environment may supply `SOILHEALTH_RECEIVER_PASSWORD`; do not hardcode it in the source. Stop with Ctrl+C.

Data is stored beside the script as `soilhealth.sqlite3`. Use `--database PATH` for another location. The `events` table stores receipt time, topic, message kind, retained flag, original validated fields as JSON, and a deduplication key. Back up the database with a SQLite-aware tool or after stopping the receiver. Protect the local folder with your normal account permissions. The database grows while reception runs; this prototype does not implement archival/retention.

The computer must remain on and connected to receive data. This is not yet an always-on hosted ingestion service. Netlify static hosting does not run this Python process. Colab can test a receiver, but its runtime and local files are temporary; use an always-on host for unattended collection.

## Prove the connection before flashing hardware

1. Start the receiver and wait for **Subscription accepted**.
2. In HiveMQ Web Client, connect using `soilhealth-esp32-01-scoped` and its password. Give it a different MQTT client ID from the ESP32.
3. Publish to `soilhealth/devices/esp32-01/test`, QoS 1, retain **off**:

```json
{"device_id":"esp32-01","source":"manual_connection_test","message":"SoilHealth MQTT connection test"}
```

4. The receiver must print **Manual connection test received and saved (not a sensor reading)**. A publisher's Connected label alone does not prove reception. Messages published before this receiver subscribes are not replayed unless retained.

The receiver contains no publish operation. HiveMQ's SUBSCRIBE_ONLY permission enforces read-only access at the broker; an application without publish calls alone would not enforce it.

## Configure and upload the ESP32 sketch

The target assumption is a **classic ESP32 Dev Module**, using Wi-Fi for MQTT. The exact board, soil probe register map, and GSM model are still unconfirmed. ESP32-C3/S2 or boards reserving GPIO16/17 for PSRAM need a different pin/UART configuration.

1. Open `firmware/SoilHealthGateway/SoilHealthGateway.ino` in Arduino IDE.
2. Install Espressif ESP32 board support **3.3.7**. Install Adafruit GFX **1.12.6**, Adafruit ST7735 and ST7789 **1.11.0**, OneWire **2.3.8**, DallasTemperature **4.0.6**, and PubSubClient **2.8.0** with dependencies.
3. Copy `secrets.example.h` to `secrets.h` in the same sketch folder. Fill `WIFI_SSID`, `WIFI_PASSWORD`, and `MQTT_PASSWORD` using the ESP32 publisher credential. Leave `SMS_PHONE` empty unless enabling the modem. Do not rename the example itself or share your completed secrets file.
4. Confirm your board, pin connections, relay polarity, sensor slave ID, baud rate, addresses and scales in `config.h`. The original addresses were preserved, not independently identified from a sensor datasheet. Function 03 and 9600 8N1 are assumed. Temperature is interpreted as signed 16-bit, divided by 10; pH is divided by 100. Change these if the actual sensor manual differs.
5. Upload initially with `SENSOR_MAP_VERIFIED=false`, `ENABLE_AUTO_PUMP=false`, and `ENABLE_SMS=false`. Keep the pump power disconnected for the first bench check. Open Serial Monitor at **115200 baud**.
6. Compare all seven readings with the sensor's reference/manual and confirm the TFT displays them correctly. Then set `SENSOR_MAP_VERIFIED=true`. The retained register addresses are moisture `0x0012`, temperature `0x0013`, EC `0x0015`, pH `0x0006`, N/P/K `0x001E/0x001F/0x0020`.
7. Confirm Wi-Fi and internet time synchronization are available. TLS waits for NTP time. Look for **MQTT connected with certificate validation**, then receiver telemetry messages about every 10 seconds.
8. Only after verifying the relay and moisture readings, enable automatic irrigation if desired. It starts below 35% after three valid samples, stops at 60%, and latches off after the configured 60-second bench limit. Set crop-appropriate thresholds and a measured maximum runtime before field use. Sensor communication failure turns it off. Inspect the fault before rebooting; reboot clears the latch.

The relay is driven OFF at the start of setup. GPIO levels during reset/boot occur before software can control them: verify the relay's hardware pull resistor and fail-off behavior. Check boot-strapping GPIO2/5 and all peripheral voltage levels against your exact ESP32 board. The DS18B20 bus requires the appropriate pull-up; RS485 requires a suitable transceiver, not a direct sensor-to-GPIO connection. GSM power supply and logic levels must match the modem.

## What was repaired

- Modbus reads now validate slave, function, byte count, response length and CRC; partial samples cannot mix with old readings.
- Negative soil temperatures decode correctly for the assumed signed register format. Missing readings become `null` in telemetry and `--` on screen.
- Pump initialization occurs before peripheral/network setup. Read failures, stale data and maximum runtime stop irrigation. Hardware actuation is disabled by default pending register verification.
- MQTT runs in a separate task so network connection delays do not block local pump supervision. An overwrite queue bounds memory and drops old unsent samples.
- DS18B20 conversions, buzzer patterns and GSM response handling avoid the original long delays. SMS has bounded waits, modem acknowledgement and alert cooldown; delivery itself is not guaranteed. SMS defaults off and requires modem bench testing.
- The 240x280 TFT uses separate rows for N/P/K and fits all values within the screen.
- Wi-Fi/TLS MQTT is added with a unique boot/client ID, device-scoped publishing and a retained online/offline Last Will status.

## Message semantics and limits

Telemetry uses schema version 1, explicit units, a boot ID and sequence number. The receiver validates bounds and stores unverified-map readings with `sensor_map_verified=false`; these are not confirmed measurements. The `source=hardware` label describes the firmware path, not cryptographic proof of device identity. This package does not implement signed payload verification.

Firmware telemetry publishes QoS 0 (the supported publish mode in [PubSubClient](https://github.com/knolleary/pubsubclient)); local send success is not a broker delivery acknowledgement. Telemetry is not retained and this prototype has no durable device offline queue. Gaps during outages are expected. Status is retained; a retained online status is not proof that telemetry is fresh. The receiver reports missing new telemetry after 30 seconds and stores retained flags separately. Receiver deduplication uses device/boot/sequence.

The existing [Netlify dashboard](https://soilhealth-gateway-melingasuk.netlify.app/) is unchanged by this package. Connecting this receiver's data to that dashboard still requires a deployed database/API and real user authentication. MQTTS alone does not implement device signatures, a reverse proxy, or session enforcement.

## Validation

Run receiver validation tests with:

```powershell
python -m unittest discover -s receiver -v
```

Firmware compile-time checks cover a known CRC vector, corrupt and malformed replies, signed temperature and pump hysteresis/fault decisions. Build results and remaining hardware checks are recorded in `VALIDATION.md`.

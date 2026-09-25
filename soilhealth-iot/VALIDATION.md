# Validation record — 2026-09-15

## Completed

- Python receiver: 7 automated tests passed. Coverage includes malformed/oversized messages, wrong devices and fields, NaN and boolean-as-number rejection, offline null requirements, telemetry deduplication, separate manual-test storage, network errors and authentication rejection. Lifecycle tests mock MQTT; they are not live broker delivery tests.
- Paho MQTT 2.1.0 was imported and its version-2 callback client initialized successfully.
- A real TLS connection to the cluster on port 8883 validated its hostname and chain using the system trust store. A second connection validated against only the downloaded ISRG Root X1 certificate. These checks did not authenticate an MQTT client or receive sensor messages.
- HiveMQ custom permission `soilhealth-esp32-01-read` was saved and verified as SUBSCRIBE_ONLY for `soilhealth/devices/esp32-01/#`.
- Deliverable source was checked to exclude a completed `secrets.h`, sensor database and compiled image with placeholder credentials.

## ESP32 build

Build target: `esp32:esp32:esp32` (classic ESP32 Dev Module), Espressif Arduino core 3.3.7. Library versions are in README.md.

The compile fixture enables the sensor-map flag, automatic pump and SMS, and supplies obviously fake Wi-Fi/MQTT/phone placeholders, so the compiler includes all feature paths. The delivered configuration remains in bench mode. No binary from this fixture is intended for flashing.

The Windows self-extracting build helpers failed before compilation because their temporary extraction returned Permission denied. The successful workaround uses Espressif esptool 5.1.0's Python source distribution plus the board package's own Python partition/insights scripts. The ESP32 C/C++ compiler and libraries remain those supplied by Espressif core 3.3.7. Downloaded Python distributions were checked against their PyPI SHA-256 metadata.

Final compile/link result: **PASS** (exit code 0). All-feature fixture uses **1,067,426 bytes (81%)** of program storage and **49,412 bytes (15%)** of static RAM. Dynamic task/heap allocations and actual hardware behavior still require on-device testing. The compile-time Modbus/temperature/pump assertions passed as part of this build.

## Still requires the user's hardware/account

- Finish saving the prepared receiver credential and enter its password locally to test an authenticated MQTT subscription. Publish the documented manual test while the receiver is running and verify a stored event.
- Identify the exact ESP32 board, soil probe model/register manual and GSM modem. The original pinout and register addresses are assumptions, not verified documentation.
- Upload and test actual soil/DS18B20 readings, negative-temperature handling where applicable, display layout, relay OFF at startup, disconnected/corrupt sensor responses, pump hysteresis, runtime cutoff, Wi-Fi outages and recovery.
- Test the GSM modem and SMS delivery separately before enabling SMS; the code cannot confirm carrier delivery just from modem submission.
- Deploying a persistent receiver/database/API and real dashboard authentication is separate remaining integration work. This package does not change the public dashboard's demonstration authentication.

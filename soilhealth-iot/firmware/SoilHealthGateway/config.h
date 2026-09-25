#pragma once
// Original pinout assumes a classic ESP32 with UART0/1/2, not ESP32-C3/S2.
constexpr int TFT_CS=5, TFT_DC=18, TFT_RST=2, TFT_MOSI=21, TFT_SCLK=22;
constexpr int RS485_DE=27, RS485_RX=19, RS485_TX=4;
constexpr int GSM_RX=17, GSM_TX=16, PUMP_RELAY=13, ONE_WIRE_PIN=14;
constexpr int LED_RED=25, LED_GREEN=33, LED_BLUE=23, BUZZER_PIN=26;
constexpr bool RELAY_ACTIVE_LOW=true;
constexpr uint8_t MODBUS_SLAVE=1;
constexpr uint32_t MODBUS_BAUD=9600, MODBUS_TIMEOUT_MS=500;
// COM4 bench probe: slave 1 at 9600 8N1 returned CRC-valid replies for all seven
// addresses below. Conversion scales remain subject to physical/reference checks.
constexpr uint16_t REG_MOISTURE=0x0012, REG_TEMP=0x0013, REG_EC=0x0015;
constexpr uint16_t REG_PH=0x0006, REG_N=0x001E, REG_P=0x001F, REG_K=0x0020;
constexpr float MOISTURE_SCALE=10.0f, TEMPERATURE_SCALE=10.0f, PH_SCALE=100.0f;
constexpr bool SENSOR_MAP_VERIFIED=false;
// Bench defaults: no physical irrigation or SMS until explicitly configured.
constexpr bool ENABLE_AUTO_PUMP=false, ENABLE_SMS=true;
constexpr uint32_t READ_INTERVAL_MS=2000, STALE_MS=8000;
constexpr uint32_t PUMP_MAX_MS=60000; // bench limit, not a crop irrigation prescription
constexpr float MOISTURE_LOW=35.0f, MOISTURE_HIGH=60.0f;
constexpr float PH_LOW=5.7f, PH_HIGH=7.2f;
constexpr uint16_t N_LOW=20, P_LOW=20, K_LOW=150;
constexpr char MQTT_HOST[]="7d0cd4a2144a434fa144922e570374ba.s1.eu.hivemq.cloud";
constexpr uint16_t MQTT_PORT=8883;
constexpr char MQTT_USER[]="soilhealth-esp32-01-scoped";
constexpr char DEVICE_ID[]="esp32-01";
constexpr char TELEMETRY_TOPIC[]="soilhealth/devices/esp32-01/telemetry";
constexpr char STATUS_TOPIC[]="soilhealth/devices/esp32-01/status";
constexpr uint32_t PUBLISH_INTERVAL_MS=10000;

constexpr int CAP_PIN=35;

// Steady moderate brightness; change polarity only to match physical RGB wiring.
constexpr bool RGB_COMMON_ANODE=false;
constexpr int STATUS_LED_BRIGHTNESS=128;

// Explicit demonstration mode; this is not laboratory calibration.
constexpr bool DEMO_IRRIGATION=true;
constexpr uint32_t PUMP_BOOT_DELAY_MS=120000;
constexpr float CAP_PUMP_INHIBIT_PCT=60.0f;

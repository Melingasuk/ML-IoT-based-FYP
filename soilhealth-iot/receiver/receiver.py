"""Subscribe-only MQTT receiver. Never publishes; persists validated events locally."""
import argparse
import getpass
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import ssl
import time
import uuid

HOST = '7d0cd4a2144a434fa144922e570374ba.s1.eu.hivemq.cloud'
PREFIX = 'soilhealth/devices/esp32-01/'
DEVICE = 'esp32-01'
RANGES = {'moisture_pct': (0, 100), 'soil_temp_c': (-55, 125),
          'ph': (0, 14), 'ec_us_cm': (0, 65535),
          'nitrogen_mg_kg': (0, 65535), 'phosphorus_mg_kg': (0, 65535),
          'potassium_mg_kg': (0, 65535)}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def bounded_number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def validate(topic, payload):
    if not topic.startswith(PREFIX) or len(payload) > 4096:
        raise ValueError('Unexpected topic or oversized message')
    kind = topic[len(PREFIX):]
    if kind not in ('telemetry', 'status', 'test'):
        raise ValueError('Unexpected topic suffix')
    data = json.loads(payload.decode('utf-8'), object_pairs_hook=unique_keys,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    if not isinstance(data, dict) or data.get('device_id') != DEVICE:
        raise ValueError('Wrong device or JSON shape')
    if kind == 'test':
        if data.get('source') != 'manual_connection_test' or not isinstance(data.get('message'), str):
            raise ValueError('Invalid manual test')
    elif kind == 'status':
        if type(data.get('online')) is not bool:
            raise ValueError('Invalid status flag')
    else:
        if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
            raise ValueError('Unsupported schema')
        if data.get('source') != 'hardware':
            raise ValueError('Telemetry must identify its source')
        if not isinstance(data.get('boot_id'), str) or not re.fullmatch(r'[0-9a-f]{16}', data['boot_id']):
            raise ValueError('Invalid boot ID')
        for key in ('sequence', 'uptime_ms'):
            if type(data.get(key)) is not int or not 0 <= data[key] <= 0xffffffff:
                raise ValueError('Invalid counter')
        for key in ('sensor_online', 'sensor_map_verified', 'reference_online', 'pump_on', 'pump_fault'):
            if type(data.get(key)) is not bool:
                raise ValueError('Missing or invalid boolean')
        if 'timestamp' not in data or (data['timestamp'] is not None and
                (type(data['timestamp']) is not int or not 1700000000 <= data['timestamp'] <= time.time()+300)):
            raise ValueError('Invalid device timestamp')
        for key, (low, high) in RANGES.items():
            if key not in data or (data['sensor_online'] and not bounded_number(data[key], low, high)):
                raise ValueError('Invalid sensor field: '+key)
            if not data['sensor_online'] and data[key] is not None:
                raise ValueError('Offline sensors must use null')
        if 'reference_temp_c' not in data or (data['reference_online'] and
                not bounded_number(data['reference_temp_c'], -55, 125)):
            raise ValueError('Invalid reference temperature')
        if not data['reference_online'] and data['reference_temp_c'] is not None:
            raise ValueError('Offline reference must use null')
        if 'pump_test' in data and type(data['pump_test']) is not bool:
            raise ValueError('Invalid pump test flag')
        if data['pump_on'] and (data['pump_fault'] or not data['sensor_online'] or (not data['sensor_map_verified'] and not data.get('pump_test', False))):
            raise ValueError('Inconsistent pump state')
    cap = data.get('capacitive')
    if cap is not None:
        if not isinstance(cap, dict) or type(cap.get('raw')) is not int or not 0 <= cap['raw'] <= 4095 or type(cap.get('mv')) is not int or not 0 <= cap['mv'] <= 3300 or type(cap.get('signal_valid')) is not bool or type(cap.get('calibrated')) is not bool:
            raise ValueError('Invalid capacitive signal')
        if cap['signal_valid'] and cap['calibrated']:
            if not bounded_number(cap.get('moisture_pct'), 0, 100):
                raise ValueError('Invalid capacitive percentage')
        elif cap.get('moisture_pct') is not None:
            raise ValueError('Uncalibrated capacitive percentage must be null')
    if kind == 'telemetry':
        prediction = data.get('prediction')
        if prediction is not None:
            if not isinstance(prediction, dict) or prediction.get('version') != 'four-crop-v1' or prediction.get('crop') not in ('banana','cabbage','kidneybeans','maize'):
                raise ValueError('Invalid edge prediction')
            for key, maximum in [('measured_features',7),('missing_mask',511),('invalid_mask',511),('substituted_mask',127),('disagreement_mask',3)]:
                if type(prediction.get(key)) is not int or not 0 <= prediction[key] <= maximum:
                    raise ValueError('Invalid prediction diagnostics')
            measured=prediction['measured_features']
            if measured != 7-prediction['substituted_mask'].bit_count() or prediction['missing_mask'] & prediction['invalid_mask'] or prediction['disagreement_mask'] & prediction['substituted_mask'] != prediction['disagreement_mask']:
                raise ValueError('Inconsistent prediction diagnostics')
            if prediction.get('status') != ('default_data_only' if measured == 0 else 'provisional' if measured < 7 else 'complete_inputs'):
                raise ValueError('Invalid prediction status')
        sms = data.get('sms')
        if sms is not None:
            if not isinstance(sms,dict) or any(type(sms.get(k)) is not bool for k in ('enabled','configured')) or any(type(sms.get(k)) is not int or not 0 <= sms[k] <= 0xffffffff for k in ('submitted','failed')):
                raise ValueError('Invalid SMS status')
    return kind, data


def open_database(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY, received_at REAL NOT NULL, topic TEXT NOT NULL,
        kind TEXT NOT NULL, retained INTEGER NOT NULL, payload TEXT NOT NULL,
        dedup_key TEXT UNIQUE)''')
    db.execute('CREATE INDEX IF NOT EXISTS events_by_kind_time ON events(kind, received_at)')
    db.commit()
    return db


def save_event(db, topic, payload, retained=False):
    kind, data = validate(topic, payload)
    # Retained telemetry is historical, never evidence that a device is live.
    key = f"{DEVICE}:{data['boot_id']}:{data['sequence']}" if kind == 'telemetry' else None
    with db:
        cursor = db.execute('''INSERT OR IGNORE INTO events
            (received_at,topic,kind,retained,payload,dedup_key) VALUES (?,?,?,?,?,?)''',
            (time.time(), topic, kind, int(retained), json.dumps(data, allow_nan=False), key))
    return kind, data, cursor.rowcount == 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=str(Path(__file__).with_name('soilhealth.sqlite3')))
    args = parser.parse_args()
    import paho.mqtt.client as mqtt
    password = os.environ.get('SOILHEALTH_RECEIVER_PASSWORD') or getpass.getpass('HiveMQ receiver password: ')
    if not password:
        parser.error('A receiver password is required')
    db = open_database(args.database)
    state = {'last_telemetry': None, 'stale_reported': False, 'fatal': None, 'connected': False}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id='soilhealth-receiver-'+uuid.uuid4().hex[:16],
                         protocol=mqtt.MQTTv311, clean_session=True)
    client.username_pw_set('soilhealth-receiver-01', password)
    client.tls_set_context(ssl.create_default_context())
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def connected(c, userdata, flags, reason, properties):
        if reason.is_failure:
            state['fatal'] = 'Broker rejected receiver authentication: '+str(reason)
            return
        result, _ = c.subscribe(PREFIX+'#', qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            state['fatal'] = 'Could not submit subscription'

    def subscribed(c, userdata, mid, reasons, properties):
        if not reasons or any(reason.is_failure for reason in reasons):
            state['fatal'] = 'Broker denied subscription; check the scoped receive permission'
        else:
            state['connected'] = True
            print('Subscription accepted. Waiting for messages from esp32-01.', flush=True)

    def disconnected(c, userdata, flags, reason, properties):
        state['connected'] = False
        print('MQTT disconnected; readings are not live. Reconnecting.', flush=True)

    def message(c, userdata, msg):
        try:
            kind, data, inserted = save_event(db, msg.topic, msg.payload, msg.retain)
        except (ValueError, UnicodeError, RecursionError, OverflowError) as error:
            print('Rejected message: '+str(error), flush=True)
            return
        except sqlite3.Error:
            state['fatal'] = 'Database write failed; reception stopped to avoid silent data loss'
            return
        if not inserted:
            return
        if kind == 'telemetry':
            if not msg.retain:
                state['last_telemetry'] = time.monotonic()
                state['stale_reported'] = False
            print(f"Telemetry saved: sequence={data['sequence']}, sensor_online={data['sensor_online']}, "
                  f"map_verified={data['sensor_map_verified']}, retained={bool(msg.retain)}", flush=True)
        elif kind == 'test':
            print('Manual connection test received and saved (not a sensor reading).', flush=True)
        else:
            print(f"Device reports online={data['online']}; retained={bool(msg.retain)}. "
                  'Use recent telemetry to assess freshness.', flush=True)

    client.on_connect, client.on_subscribe = connected, subscribed
    client.on_disconnect, client.on_message = disconnected, message
    print('TLS certificate validation enabled. Receiver has no publish operations.', flush=True)
    retry_at = 0
    socket_open = False
    try:
        while not state['fatal']:
            if not socket_open:
                if time.monotonic() < retry_at:
                    time.sleep(0.2)
                    continue
                try:
                    client.connect(HOST, 8883, keepalive=30)
                    socket_open = True
                except OSError:
                    print('Connection unavailable; retrying in 10 seconds.', flush=True)
                    retry_at = time.monotonic()+10
                    continue
            result = client.loop(timeout=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                socket_open = False
                retry_at = time.monotonic()+10
            age = time.monotonic() - state['last_telemetry'] if state['last_telemetry'] is not None else None
            if age is not None and age > 30 and not state['stale_reported']:
                print('Telemetry stale: no new non-retained reading for 30 seconds.', flush=True)
                state['stale_reported'] = True
    except KeyboardInterrupt:
        print('\nReceiver stopped.')
    finally:
        client.disconnect()
        db.close()
    if state['fatal']:
        raise SystemExit(state['fatal'])


if __name__ == '__main__':
    main()

import json
import unittest
from unittest.mock import MagicMock, patch
import receiver
from receiver import PREFIX, open_database, save_event, validate


def reading():
    return dict(schema_version=1, device_id='esp32-01', boot_id='0123456789abcdef', sequence=1,
                source='hardware', timestamp=None, uptime_ms=12345, sensor_online=True,
                sensor_map_verified=False, reference_online=False, pump_on=False, pump_fault=False,
                moisture_pct=42.5, soil_temp_c=-10, ph=6.5, reference_temp_c=None,
                ec_us_cm=350, nitrogen_mg_kg=20, phosphorus_mg_kg=21, potassium_mg_kg=150)


class ReceiverTests(unittest.TestCase):
    def encode(self, data):
        return json.dumps(data).encode()

    def test_valid_and_deduplicated(self):
        db = open_database(':memory:')
        payload = self.encode(reading())
        self.assertTrue(save_event(db, PREFIX+'telemetry', payload)[2])
        self.assertFalse(save_event(db, PREFIX+'telemetry', payload)[2])
        self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 1)
        db.close()

    def test_rejects_invalid_fields(self):
        for key, value in [('moisture_pct', 101), ('ph', float('nan')), ('sequence', True),
                           ('source', 'demo'), ('device_id', 'esp32-02'), ('pump_on', True),
                           ('soil_temp_c', -127), ('sensor_online', 'true'), ('boot_id', 'bad')]:
            with self.subTest(key=key):
                data = reading(); data[key] = value
                with self.assertRaises(ValueError):
                    validate(PREFIX+'telemetry', self.encode(data))

    def test_offline_requires_null(self):
        data = reading(); data['sensor_online'] = False
        with self.assertRaises(ValueError):
            validate(PREFIX+'telemetry', self.encode(data))
        for key in ('moisture_pct', 'soil_temp_c', 'ph', 'ec_us_cm', 'nitrogen_mg_kg',
                    'phosphorus_mg_kg', 'potassium_mg_kg'):
            data[key] = None
        self.assertEqual(validate(PREFIX+'telemetry', self.encode(data))[0], 'telemetry')

    def test_manual_tests_separate_and_retained_marked(self):
        db = open_database(':memory:')
        data = dict(device_id='esp32-01', source='manual_connection_test', message='connection test')
        save_event(db, PREFIX+'test', self.encode(data), True)
        self.assertEqual(db.execute('SELECT kind,retained FROM events').fetchone(), ('test', 1))
        db.close()

    def test_bad_envelopes(self):
        for topic, payload in [(PREFIX+'telemetry', b'{'), (PREFIX+'test', b'x'*4097),
                               ('other/topic', self.encode(reading())),
                               (PREFIX+'status', b'{"device_id":"esp32-01","online":true,"online":false}')]:
            with self.assertRaises(ValueError):
                validate(topic, payload)

    def test_network_failure_stops_cleanly(self):
        client = MagicMock()
        client.connect.side_effect = OSError('network unavailable')
        with patch('paho.mqtt.client.Client', return_value=client), \
             patch.dict('os.environ', {'SOILHEALTH_RECEIVER_PASSWORD': 'test-placeholder'}), \
             patch('sys.argv', ['receiver.py', '--database', ':memory:']), \
             patch('receiver.time.sleep', side_effect=KeyboardInterrupt):
            receiver.main()
        client.disconnect.assert_called_once()
        client.publish.assert_not_called()

    def test_broker_rejection_is_fatal(self):
        client = MagicMock()
        def loop(timeout):
            client.on_connect(client, None, None, MagicMock(is_failure=True), None)
            return 0
        client.loop.side_effect = loop
        with patch('paho.mqtt.client.Client', return_value=client), \
             patch.dict('os.environ', {'SOILHEALTH_RECEIVER_PASSWORD': 'test-placeholder'}), \
             patch('sys.argv', ['receiver.py', '--database', ':memory:']):
            with self.assertRaisesRegex(SystemExit, 'rejected receiver authentication'):
                receiver.main()
        client.subscribe.assert_not_called()
        client.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()

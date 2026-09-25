"""Forward the latest validated receiver reading to the private Netlify API.

Run alongside receiver.py. Reads SQLite without changing it; never uses MQTT
credentials and cannot control the ESP32 or pump.
"""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from receiver import validate, PREFIX


def latest(database, now=None):
    now = time.time() if now is None else now
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro', uri=True) as db:
        row = db.execute("SELECT received_at, payload, retained FROM events WHERE kind='telemetry' ORDER BY id DESC LIMIT 1").fetchone()
    if not row or row[2] or not 0 <= now-row[0] <= 45:
        return None
    _, data = validate(PREFIX+'telemetry', row[1].encode())
    return {'received_at': row[0], 'retained': False, 'telemetry': data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Private bridge JSON file; never deploy it')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    endpoint = config['endpoint']
    if endpoint != 'https://soilhealth-gateway-melingasuk.netlify.app/api/ingest':
        raise SystemExit('Unexpected cloud destination; configuration rejected')
    database = config.get('database', str(Path(__file__).with_name('soilhealth.sqlite3')))
    previous = None
    last_stale_notice = float("-inf")
    print('Cloud bridge started. Waiting for live receiver readings.', flush=True)
    while True:
        try:
            record = latest(database)
            identity = (record['telemetry']['boot_id'], record['telemetry']['sequence']) if record else None
            if record and identity != previous:
                request = Request(endpoint, data=json.dumps(record, allow_nan=False).encode(),
                                  headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+config['key']}, method='POST')
                with urlopen(request, timeout=15) as response:
                    if response.status != 200:
                        raise RuntimeError('Unexpected cloud response')
                previous = identity
                print('Cloud accepted telemetry: sequence='+str(identity[1]), flush=True)
            elif not record and time.monotonic()-last_stale_notice >= 30:
                last_stale_notice=time.monotonic()
                print('No fresh receiver reading; cloud will show stale data.', flush=True)
        except HTTPError as error:
            print('Cloud upload HTTP '+str(error.code)+'; will retry. Credentials are not logged.', flush=True)
        except (URLError, OSError, ValueError, sqlite3.Error, RuntimeError):
            print('Cloud bridge unavailable or invalid local reading; will retry.', flush=True)
        if args.once:
            return
        time.sleep(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Cloud bridge stopped.')

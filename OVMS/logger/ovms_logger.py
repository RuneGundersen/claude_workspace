#!/usr/bin/env python3
"""
OVMS MQTT Logger
Subscribes to all OVMS metrics and stores them in SQLite with timestamps.
Runs as a background service on the Pi.
"""

import paho.mqtt.client as mqtt
import ssl
import sqlite3
import time
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger('ovms-logger')

# ── Config ──────────────────────────────────────────────────────────────────

BROKER     = 'e15ab5a391184740942bb3aa44acb808.s1.eu.hivemq.cloud'
PORT       = 8883
USERNAME   = 'EV88283'
PASSWORD   = 'hm$lKN3Q3J6^B'
VEHICLE_ID = 'EV88283'

DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ovms_log.db')

# Metrics worth logging (skip noisy/internal ones)
SKIP_PREFIXES = ['client/', 'notify/info', 'notify/alert']

# ── Database ─────────────────────────────────────────────────────────────────

def init_db(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metrics (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        INTEGER NOT NULL,   -- unix timestamp (seconds)
            metric    TEXT    NOT NULL,   -- e.g. "v/b/soc"
            value     TEXT    NOT NULL
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ts     ON metrics(ts)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_metric ON metrics(metric)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ts   INTEGER,
            end_ts     INTEGER,
            start_soc  REAL,
            end_soc    REAL,
            distance   REAL,
            notes      TEXT
        )
    ''')
    conn.commit()
    log.info(f'Database: {DB_PATH}')

# ── MQTT ─────────────────────────────────────────────────────────────────────

db_conn = None

def on_connect(c, u, f, rc, p=None):
    if not rc.is_failure:
        log.info('Connected to HiveMQ — subscribing to metrics')
        c.subscribe(f'{USERNAME}/metric/#')
        c.subscribe(f'{USERNAME}/notify/#')
    else:
        log.error(f'MQTT connect failed: {rc}')

def on_disconnect(c, u, f, rc=None, p=None):
    log.warning(f'Disconnected ({rc}) — will reconnect automatically')

def on_message(c, u, msg):
    global db_conn
    topic   = msg.topic
    payload = msg.payload.decode('utf-8', errors='replace').strip()
    ts      = int(time.time())

    # Strip prefix to get clean metric key, e.g. "v/b/soc"
    prefix = f'{USERNAME}/metric/'
    if topic.startswith(prefix):
        metric = topic[len(prefix):]
    elif topic.startswith(f'{USERNAME}/notify/'):
        metric = 'notify/' + topic[len(f'{USERNAME}/notify/'):]
    else:
        return

    if any(metric.startswith(s) for s in SKIP_PREFIXES):
        return

    try:
        db_conn.execute(
            'INSERT INTO metrics (ts, metric, value) VALUES (?, ?, ?)',
            (ts, metric, payload)
        )
        db_conn.commit()
    except Exception as e:
        log.error(f'DB write failed: {e}')

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global db_conn
    db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    init_db(db_conn)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='ovms-logger')
    client.username_pw_set(USERNAME, PASSWORD)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    log.info(f'Connecting to {BROKER}:{PORT}...')
    client.connect(BROKER, PORT, keepalive=60)

    try:
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        log.info('Stopped.')
    finally:
        db_conn.close()

if __name__ == '__main__':
    main()

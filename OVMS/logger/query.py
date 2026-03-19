#!/usr/bin/env python3
"""
Query the OVMS log database.
Usage:
  python query.py trips              — list all trips
  python query.py trip <id>          — detailed metrics for a trip
  python query.py last               — latest value of every metric
  python query.py metric v/b/soc     — history for one metric
  python query.py since 2h           — all metrics from last 2h (or 30m, 1d)
"""

import sqlite3, sys, os, time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ovms_log.db')

def fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def parse_duration(s):
    """'2h' -> seconds, '30m' -> seconds, '1d' -> seconds"""
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    return int(s[:-1]) * units[s[-1]]

def cmd_last(conn):
    rows = conn.execute('''
        SELECT metric, value, MAX(ts) as ts
        FROM metrics GROUP BY metric ORDER BY metric
    ''').fetchall()
    print(f"{'Metric':<35} {'Value':<20} {'Last seen'}")
    print('-' * 75)
    for metric, value, ts in rows:
        print(f'{metric:<35} {value:<20} {fmt_ts(ts)}')

def cmd_metric(conn, metric):
    rows = conn.execute(
        'SELECT ts, value FROM metrics WHERE metric=? ORDER BY ts DESC LIMIT 200',
        (metric,)
    ).fetchall()
    if not rows:
        print(f'No data for metric: {metric}')
        return
    print(f"{'Time':<22} Value")
    print('-' * 40)
    for ts, value in rows:
        print(f'{fmt_ts(ts):<22} {value}')

def cmd_since(conn, duration_str):
    since = int(time.time()) - parse_duration(duration_str)
    rows = conn.execute(
        'SELECT ts, metric, value FROM metrics WHERE ts >= ? ORDER BY ts DESC LIMIT 1000',
        (since,)
    ).fetchall()
    if not rows:
        print(f'No data in last {duration_str}')
        return
    print(f"{'Time':<22} {'Metric':<35} Value")
    print('-' * 75)
    for ts, metric, value in rows:
        print(f'{fmt_ts(ts):<22} {metric:<35} {value}')

def cmd_trips(conn):
    # Auto-detect trips: periods where v/p/speed > 0 with gaps > 5 min
    rows = conn.execute('''
        SELECT ts, value FROM metrics
        WHERE metric = 'v/p/speed'
        ORDER BY ts
    ''').fetchall()
    if not rows:
        print('No speed data recorded yet.')
        return

    trips = []
    GAP = 300   # 5 min gap = new trip
    trip_start = None
    prev_ts    = None

    for ts, val in rows:
        try:
            speed = float(val)
        except ValueError:
            continue
        if speed > 2:
            if trip_start is None:
                trip_start = ts
            prev_ts = ts
        else:
            if trip_start and prev_ts and (ts - prev_ts) > GAP:
                trips.append((trip_start, prev_ts))
                trip_start = None

    if trip_start and prev_ts:
        trips.append((trip_start, prev_ts))

    if not trips:
        print('No trips detected.')
        return

    print(f"{'#':<4} {'Start':<22} {'End':<22} {'Duration':<12} Start SOC  End SOC")
    print('-' * 85)
    for i, (start, end) in enumerate(trips, 1):
        duration = end - start
        h, m = divmod(duration // 60, 60)

        def nearest_soc(target_ts):
            row = conn.execute('''
                SELECT value FROM metrics
                WHERE metric='v/b/soc' AND ABS(ts - ?) < 300
                ORDER BY ABS(ts - ?) LIMIT 1
            ''', (target_ts, target_ts)).fetchone()
            return f"{float(row[0]):.1f}%" if row else '--'

        print(f'{i:<4} {fmt_ts(start):<22} {fmt_ts(end):<22} {h}h {m:02d}m       '
              f'{nearest_soc(start):<10} {nearest_soc(end)}')

def main():
    if not os.path.exists(DB_PATH):
        print(f'No database found at {DB_PATH}')
        print('Start ovms_logger.py first to begin recording.')
        return

    conn = sqlite3.connect(DB_PATH)
    args = sys.argv[1:]

    if not args or args[0] == 'last':
        cmd_last(conn)
    elif args[0] == 'trips':
        cmd_trips(conn)
    elif args[0] == 'metric' and len(args) > 1:
        cmd_metric(conn, args[1])
    elif args[0] == 'since' and len(args) > 1:
        cmd_since(conn, args[1])
    else:
        print(__doc__)

    conn.close()

if __name__ == '__main__':
    main()

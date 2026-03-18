#!/usr/bin/env python3
"""
Heat Pump local proxy server.

Serves the webapp and:
  - Proxies /api/<ip>/...  -> http://<ip>/...          (Daikin local HTTP)
  - Handles /toshiba/state -> Toshiba cloud API (read)
  - Handles /toshiba/set   -> Toshiba cloud API (write, needs toshiba-ac package)

Usage:
    pip install toshiba-ac     # required for Toshiba control (on Pi)
    python server.py
    Then open http://localhost:8765
"""

import http.server
import urllib.request
import urllib.parse
import json
import os
import sys
import threading
import time

PORT     = 8765
SERVE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Toshiba credentials ────────────────────────────────────────────────────
SECRETS_FILE = os.path.join(SERVE_DIR, 'toshiba_secrets.json')
TOSHIBA_BASE = 'https://mobileapi.toshibahomeaccontrols.com'
TOSHIBA_HEADERS = {
    'Content-Type':  'application/json',
    'User-Agent':    'Dalvik/2.1.0 (Linux; Android 10)',
    'Application-Id': 'TOSHIBA',
}

_toshiba_token      = None
_toshiba_token_time = 0
_token_lock         = threading.Lock()
TOKEN_TTL           = 3600   # refresh token after 1 hour

def _load_secrets():
    if not os.path.exists(SECRETS_FILE):
        return None, None
    with open(SECRETS_FILE) as f:
        s = json.load(f)
    return s.get('username'), s.get('password')

def _get_token():
    global _toshiba_token, _toshiba_token_time
    with _token_lock:
        if _toshiba_token and (time.time() - _toshiba_token_time) < TOKEN_TTL:
            return _toshiba_token

        username, password = _load_secrets()
        if not username:
            return None

        body = json.dumps({'Username': username, 'Password': password}).encode()
        req  = urllib.request.Request(
            TOSHIBA_BASE + '/api/Consumer/Login',
            data=body, headers=TOSHIBA_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())

        if not resp.get('IsSuccess'):
            raise RuntimeError('Toshiba login failed: ' + resp.get('Message', ''))

        _toshiba_token      = resp['ResObj']['access_token']
        _toshiba_token_time = time.time()
        return _toshiba_token

def _toshiba_get_state(ac_id):
    token = _get_token()
    headers = {**TOSHIBA_HEADERS, 'Authorization': f'Bearer {token}'}
    url = TOSHIBA_BASE + f'/api/AC/GetCurrentACState?ACId={ac_id}'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
        resp = json.loads(r.read())
    if not resp.get('IsSuccess'):
        raise RuntimeError(resp.get('Message', 'Unknown error'))
    return resp['ResObj']

def _decode_state(raw_hex):
    """Decode Toshiba ACStateData hex string into readable dict."""
    data = bytes.fromhex(raw_hex)
    # 0x30 = ON, 0x31 = OFF (confirmed: API OnOff field returns "30" when unit is on)
    POWER = {0x30: 'on', 0x31: 'off'}
    MODE  = {0x41: 'auto', 0x42: 'cool', 0x43: 'heat', 0x44: 'dry', 0x45: 'fan'}
    FAN   = {0x31: 'quiet', 0x32: '1', 0x33: '2', 0x34: '3',
             0x35: '4',     0x36: '5',  0x41: 'auto'}
    return {
        'power':    POWER.get(data[0], 'unknown'),
        'mode':     MODE.get(data[1],  'unknown'),
        'setpoint': data[2],      # target temperature (°C)
        'roomTemp': data[8],      # actual room sensor reading (°C)
        'fan':      FAN.get(data[3], 'unknown'),
        'raw':      raw_hex,
    }

def _encode_state(current_hex, changes):
    """Patch a Toshiba ACStateData hex string with changes dict."""
    data = bytearray(bytes.fromhex(current_hex))
    POWER = {'off': 0x30, 'on': 0x31}
    MODE  = {'auto': 0x41, 'cool': 0x42, 'heat': 0x43, 'dry': 0x44, 'fan': 0x45}
    FAN   = {'quiet': 0x31, '1': 0x32, '2': 0x33, '3': 0x34,
             '4': 0x35,     '5': 0x36, 'auto': 0x41}
    if 'power' in changes:
        data[0] = POWER[changes['power']]
    if 'mode' in changes:
        data[1] = MODE[changes['mode']]
    if 'setpoint' in changes:
        data[2] = int(changes['setpoint'])
    if 'fan' in changes:
        data[3] = FAN[changes['fan']]
    return data.hex()


# ── HTTP request handler ────────────────────────────────────────────────────

class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path.startswith('/api/'):
            self._proxy_daikin()
        elif self.path.startswith('/toshiba/state'):
            self._toshiba_state()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/toshiba/set'):
            self._toshiba_set()
        else:
            self.send_error(404)

    # ── Daikin local proxy ──────────────────────────────────────────────────

    def _proxy_daikin(self):
        remainder = self.path[5:]           # strip '/api/'
        slash = remainder.find('/')
        if slash == -1:
            self.send_error(400, 'Missing path after IP')
            return
        ip   = remainder[:slash]
        rest = remainder[slash + 1:]
        target = f'http://{ip}/{rest}'
        try:
            with urllib.request.urlopen(target, timeout=6) as resp:
                body = resp.read()
            self._ok('text/plain', body)
        except Exception as e:
            self.send_error(502, str(e))

    # ── Toshiba state (GET) ─────────────────────────────────────────────────

    def _toshiba_state(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ac_id  = (params.get('acId') or [''])[0]
        if not ac_id:
            self.send_error(400, 'Missing acId')
            return
        try:
            raw  = _toshiba_get_state(ac_id)
            state = _decode_state(raw['ACStateData'])
            state['updatedAt'] = raw.get('UpdatedDate', '')
            self._ok('application/json', json.dumps(state).encode())
        except Exception as e:
            self.send_error(502, str(e))

    # ── Toshiba set state (POST) ────────────────────────────────────────────

    def _toshiba_set(self):
        length  = int(self.headers.get('Content-Length', 0))
        body    = json.loads(self.rfile.read(length))
        ac_id   = body.get('acId', '')
        changes = body.get('changes', {})

        if not ac_id or not changes:
            self.send_error(400, 'Missing acId or changes')
            return

        try:
            # Get current cloud state, apply changes optimistically, send via AMQP
            raw       = _toshiba_get_state(ac_id)
            new_hex   = _encode_state(raw['ACStateData'], changes)
            new_state = _decode_state(new_hex)
            _toshiba_send(ac_id, changes)   # fire AMQP command
            # Return optimistic state immediately — don't wait for cloud to update
            self._ok('application/json', json.dumps(new_state).encode())
        except Exception as e:
            self.send_error(502, str(e))

    # ── Helper ─────────────────────────────────────────────────────────────

    def _ok(self, content_type, body: bytes):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Show API calls and errors, suppress static file noise
        if len(args) > 0 and ('/api/' in str(args[0]) or '/toshiba' in str(args[0])):
            super().log_message(fmt, *args)
        elif len(args) > 1 and str(args[1]) >= '400':
            super().log_message(fmt, *args)


# ── Toshiba AMQP control (requires toshiba-ac package) ─────────────────────

def _toshiba_send(ac_id, changes):
    """
    Send state changes to Toshiba unit via Azure IoT Hub (AMQP).
    Requires: pip install toshiba-ac
    """
    import asyncio
    from toshiba_ac.device_manager import ToshibaAcDeviceManager
    from toshiba_ac.device.properties import (
        ToshibaAcStatus, ToshibaAcMode, ToshibaAcFanMode,
    )

    MODE_MAP = {
        'auto': ToshibaAcMode.AUTO, 'cool': ToshibaAcMode.COOL,
        'heat': ToshibaAcMode.HEAT, 'dry':  ToshibaAcMode.DRY,
        'fan':  ToshibaAcMode.FAN,
    }
    FAN_MAP = {
        'auto':  ToshibaAcFanMode.AUTO,  'quiet': ToshibaAcFanMode.QUIET,
        '1':     ToshibaAcFanMode.LOW,   '2':     ToshibaAcFanMode.MEDIUM_LOW,
        '3':     ToshibaAcFanMode.MEDIUM,'4':     ToshibaAcFanMode.MEDIUM_HIGH,
        '5':     ToshibaAcFanMode.HIGH,
    }

    username, password = _load_secrets()

    async def _send():
        mgr = ToshibaAcDeviceManager(username=username, password=password)
        await mgr.connect()
        devices = await mgr.get_devices()
        dev = next((d for d in devices if str(d.ac_id).lower() == ac_id.lower()), None)
        if not dev:
            raise RuntimeError(f'Device {ac_id} not found')
        await dev.connect()

        if 'power' in changes:
            await dev.set_ac_status(
                ToshibaAcStatus.ON if changes['power'] == 'on' else ToshibaAcStatus.OFF)
        if 'mode' in changes:
            await dev.set_ac_mode(MODE_MAP[changes['mode']])
        if 'setpoint' in changes:
            await dev.set_ac_temperature(int(changes['setpoint']))
        if 'fan' in changes:
            await dev.set_ac_fan_mode(FAN_MAP[changes['fan']])

        await mgr.shutdown()

    asyncio.run(_send())


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    os.chdir(SERVE_DIR)

    # Warm up Toshiba token if secrets present
    username, _ = _load_secrets()
    if username:
        try:
            _get_token()
            print('Toshiba: logged in OK')
        except Exception as e:
            print(f'Toshiba: login failed ({e}) — check toshiba_secrets.json')
    else:
        print('Toshiba: no secrets file, cloud API disabled')

    server = http.server.HTTPServer(('', PORT), ProxyHandler)
    print(f'Heat Pump dashboard -> http://localhost:{PORT}')
    print('Press Ctrl+C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
        sys.exit(0)

"""
OVMS MQTT Bridge
Connects to Dexter-web MQTT broker (TCP) and proxies messages
to the browser via WebSocket on ws://localhost:9001
"""
import asyncio
import json
import logging
import threading
import http.server
import socketserver
import os
import webbrowser
import paho.mqtt.client as mqtt
import websockets

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('ovms-bridge')

# --- Config (mirrors config.js) ---
MQTT_HOST     = 'ovms.dexters-web.de'
MQTT_PORT     = 1883
MQTT_USER     = 'EV88283'
MQTT_PASS     = 'WsR@RQqp%4VVn'
VEHICLE_ID    = 'EV88283'
WS_PORT       = 9001
HTTP_PORT     = 8080

TOPIC_PREFIX  = f'ovms/{MQTT_USER}/{VEHICLE_ID}'

# Connected WebSocket clients
ws_clients: set = set()
loop: asyncio.AbstractEventLoop = None

# --- MQTT callbacks (paho-mqtt v2 API) ---
def on_connect(client, userdata, flags, reason_code, properties=None):
    # reason_code is a ReasonCode object in paho v2; .is_failure checks != 0
    if not reason_code.is_failure:
        log.info('Connected to MQTT broker')
        client.subscribe(f'{TOPIC_PREFIX}/metric/#')
        client.subscribe(f'{TOPIC_PREFIX}/notify/#')
        broadcast({'type': 'status', 'connected': True})
    else:
        err = str(reason_code)
        log.error(f'MQTT connect failed: {err}')
        broadcast({'type': 'status', 'connected': False, 'error': err})

def on_disconnect(client, userdata, flags, reason_code=None, properties=None):
    log.warning(f'Disconnected: {reason_code}')
    broadcast({'type': 'status', 'connected': False})

def on_message(client, userdata, msg):
    topic   = msg.topic
    payload = msg.payload.decode('utf-8', errors='replace')
    prefix  = f'{TOPIC_PREFIX}/metric/'
    if topic.startswith(prefix):
        metric_key = topic[len(prefix):].replace('/', '.')
        broadcast({'type': 'metric', 'key': metric_key, 'value': payload})

def broadcast(data: dict):
    if not ws_clients or loop is None:
        return
    msg = json.dumps(data)
    asyncio.run_coroutine_threadsafe(_broadcast(msg), loop)

async def _broadcast(msg: str):
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)

# --- WebSocket server ---
async def ws_handler(websocket):
    ws_clients.add(websocket)
    log.info(f'Browser connected ({len(ws_clients)} clients)')
    # Send current connection status immediately
    await websocket.send(json.dumps({'type': 'status', 'connected': mqtt_client.is_connected()}))
    try:
        async for _ in websocket:
            pass  # No commands from browser for now
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.discard(websocket)
        log.info(f'Browser disconnected ({len(ws_clients)} clients)')

# --- HTTP server (serves the webapp) ---
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

def run_http():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with socketserver.TCPServer(('', HTTP_PORT), QuietHandler) as httpd:
        log.info(f'Webapp: http://localhost:{HTTP_PORT}')
        httpd.serve_forever()

# --- Main ---
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='ovms-bridge')
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.on_connect    = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message    = on_message

async def main():
    global loop
    loop = asyncio.get_running_loop()

    # Start HTTP server in background thread
    t = threading.Thread(target=run_http, daemon=True)
    t.start()

    # Connect MQTT in background thread
    def mqtt_thread():
        log.info(f'Connecting to MQTT {MQTT_HOST}:{MQTT_PORT}...')
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        mqtt_client.loop_forever()

    mt = threading.Thread(target=mqtt_thread, daemon=True)
    mt.start()

    # Start WebSocket server
    log.info(f'WebSocket bridge on ws://localhost:{WS_PORT}')
    async with websockets.serve(ws_handler, 'localhost', WS_PORT):
        webbrowser.open(f'http://localhost:{HTTP_PORT}')
        log.info('Bridge running. Press Ctrl+C to stop.')
        await asyncio.Future()  # run forever

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info('Stopped.')

#!/usr/bin/env python3
"""
Flexit UNI4 / CI66 Modbus → MQTT bridge
Runs on Raspberry Pi, polls registers every 10 s and publishes to HiveMQ.

Hardware: Waveshare USB-RS485 → CI66 → UNI4
CI66 Modbus RTU settings: 56000 baud, 8E1, slave address 21
"""

import json
import time
import logging
import sys
import struct
import threading

from pymodbus.client import ModbusSerialClient
import paho.mqtt.client as mqtt

from flexit_config import MODBUS_PORT, MODBUS_SLAVE, MQTT_BROKER, MQTT_PORT, \
                          MQTT_USERNAME, MQTT_PASSWORD, MQTT_TOPIC_BASE, POLL_INTERVAL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('flexit')

# ---------------------------------------------------------------------------
# Register map (CI66 — K2/C2/UNI edition)
# ---------------------------------------------------------------------------

# Input registers (FC04, read-only)
IR = {
    'filter_hours':      8,
    'supply_temp':       9,   # /10 → °C
    'extract_temp':     10,   # /10 → °C
    'outdoor_temp':     11,   # /10 → °C
    'cooling_pct':      13,   # 0-100 %
    'heat_recovery':    14,   # 0-100 %
    'heating_pct':      15,   # 0-100 %
    'alarm_supply':     19,   # bool
    'alarm_extract':    20,   # bool
    'alarm_outdoor':    21,   # bool
    'alarm_fire_therm': 23,   # bool
    'alarm_fire_smoke': 24,   # bool
    'alarm_rotor':      26,   # bool
    'alarm_filter':     27,   # bool
    'actual_setpoint':  47,   # /10 → °C
    'actual_speed_mode': 48,  # 0=stop 1=min 2=normal 3=max 4=forced
}

# Holding registers (FC03, read/write)
HR = {
    'supply_speed1':    0,   # % level 1 (min)
    'supply_speed2':    1,   # % level 2 (normal)
    'supply_speed3':    2,   # % level 3 (max)
    'extract_speed1':   4,
    'extract_speed2':   5,
    'extract_speed3':   6,
    'set_temperature':  8,   # write value × 10
    'supply_min_temp':  9,   # min supply air temp × 10
    'supply_max_temp': 10,   # max supply air temp × 10
    'regulation_type': 14,   # 0=temp control, 1=speed control
    'cooling_active':  15,   # bool
    'forced_vent':     16,   # bool on/off
    'set_speed_mode':  17,   # 0=stop 1=min 2=normal 3=max
}

SPEED_MODE_NAMES = {0: 'stop', 1: 'min', 2: 'normal', 3: 'max', 4: 'forced'}


# ---------------------------------------------------------------------------
# Modbus helpers
# ---------------------------------------------------------------------------

def read_input_registers(client, address, count=1):
    result = client.read_input_registers(address, count=count, device_id=MODBUS_SLAVE)
    if result.isError():
        raise IOError(f'FC04 error at address {address}')
    return result.registers


def read_holding_registers(client, address, count=1):
    result = client.read_holding_registers(address, count=count, device_id=MODBUS_SLAVE)
    if result.isError():
        raise IOError(f'FC03 error at address {address}')
    return result.registers


def write_register(client, address, value):
    result = client.write_register(address, value, device_id=MODBUS_SLAVE)
    if result.isError():
        raise IOError(f'FC06 error writing address {address} = {value}')
    log.info(f'Wrote holding register {address} = {value}')


def signed16(val):
    """Convert uint16 to signed int16 (for negative temperatures)."""
    return val if val < 0x8000 else val - 0x10000


def poll_all(client):
    """Read all registers and return a dict ready for JSON publish."""
    data = {}

    # Read input registers 8–48 in one shot (41 registers)
    ir_raw = read_input_registers(client, 8, 41)

    def ir(name):
        return ir_raw[IR[name] - 8]

    data['filter_hours']       = ir('filter_hours')
    data['supply_temp']        = signed16(ir('supply_temp'))  / 10.0
    data['extract_temp']       = signed16(ir('extract_temp')) / 10.0
    data['outdoor_temp']       = signed16(ir('outdoor_temp')) / 10.0
    data['cooling_pct']        = ir('cooling_pct')
    data['heat_recovery']      = ir('heat_recovery')
    data['heating_pct']        = ir('heating_pct')
    data['alarm_supply']       = bool(ir('alarm_supply'))
    data['alarm_extract']      = bool(ir('alarm_extract'))
    data['alarm_outdoor']      = bool(ir('alarm_outdoor'))
    data['alarm_fire_therm']   = bool(ir('alarm_fire_therm'))
    data['alarm_fire_smoke']   = bool(ir('alarm_fire_smoke'))
    data['alarm_rotor']        = bool(ir('alarm_rotor'))
    data['alarm_filter']       = bool(ir('alarm_filter'))
    data['actual_setpoint']    = signed16(ir('actual_setpoint')) / 10.0
    data['actual_speed_mode']  = ir('actual_speed_mode')
    data['speed_mode_name']    = SPEED_MODE_NAMES.get(data['actual_speed_mode'], '?')

    # Read holding registers 0–15 (fan speeds + temp limits + regulation type)
    hr_raw = read_holding_registers(client, 0, 16)
    data['supply_speed1']    = hr_raw[0]
    data['supply_speed2']    = hr_raw[1]
    data['supply_speed3']    = hr_raw[2]
    data['extract_speed1']   = hr_raw[4]
    data['extract_speed2']   = hr_raw[5]
    data['extract_speed3']   = hr_raw[6]
    data['supply_min_temp']  = signed16(hr_raw[9])  / 10.0
    data['supply_max_temp']  = signed16(hr_raw[10]) / 10.0
    data['regulation_type']  = hr_raw[14]   # 0=temp, 1=speed
    data['cooling_active']   = bool(hr_raw[15])

    data['timestamp'] = int(time.time())
    return data


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------

mqtt_client = None
mqtt_connected = threading.Event()


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info('MQTT connected')
        mqtt_connected.set()
        # Subscribe to command topics
        client.subscribe(f'{MQTT_TOPIC_BASE}/cmd/#')
    else:
        log.error(f'MQTT connect failed: rc={rc}')
        mqtt_connected.clear()


def on_disconnect(client, userdata, rc, properties=None):
    log.warning(f'MQTT disconnected: rc={rc}')
    mqtt_connected.clear()


def on_message(client, userdata, msg):
    """Handle incoming command messages."""
    topic = msg.topic
    try:
        payload = msg.payload.decode().strip()
        log.info(f'CMD {topic}: {payload}')
    except Exception:
        return

    modbus = userdata.get('modbus')
    if modbus is None or not modbus.is_socket_open():
        log.warning('Modbus not connected — ignoring command')
        return

    try:
        cmd = topic.split('/')[-1]
        if cmd == 'set_speed':
            # payload: 0-3 (stop/min/normal/max)
            mode = int(payload)
            if 0 <= mode <= 3:
                write_register(modbus, HR['set_speed_mode'], mode)
        elif cmd == 'set_temp':
            # payload: temperature in °C (e.g. "19.5" or "20")
            temp = float(payload)
            write_register(modbus, HR['set_temperature'], int(temp * 10))
        elif cmd == 'forced_vent':
            # payload: "1" or "0"
            write_register(modbus, HR['forced_vent'], int(bool(int(payload))))
        elif cmd == 'set_supply_speed1':
            write_register(modbus, HR['supply_speed1'], max(0, min(100, int(payload))))
        elif cmd == 'set_supply_speed2':
            write_register(modbus, HR['supply_speed2'], max(0, min(100, int(payload))))
        elif cmd == 'set_supply_speed3':
            write_register(modbus, HR['supply_speed3'], max(0, min(100, int(payload))))
        elif cmd == 'set_extract_speed1':
            write_register(modbus, HR['extract_speed1'], max(0, min(100, int(payload))))
        elif cmd == 'set_extract_speed2':
            write_register(modbus, HR['extract_speed2'], max(0, min(100, int(payload))))
        elif cmd == 'set_extract_speed3':
            write_register(modbus, HR['extract_speed3'], max(0, min(100, int(payload))))
        elif cmd == 'set_min_temp':
            temp = float(payload)
            if 5.0 <= temp <= 20.0:
                write_register(modbus, HR['supply_min_temp'], int(temp * 10))
        elif cmd == 'set_max_temp':
            temp = float(payload)
            if 15.0 <= temp <= 40.0:
                write_register(modbus, HR['supply_max_temp'], int(temp * 10))
        elif cmd == 'set_regulation_type':
            # 0 = temperature control, 1 = speed control
            write_register(modbus, HR['regulation_type'], int(payload) & 1)
        elif cmd == 'set_cooling':
            write_register(modbus, HR['cooling_active'], int(bool(int(payload))))
        else:
            log.warning(f'Unknown command: {cmd}')
    except Exception as e:
        log.error(f'Command error: {e}')


def setup_mqtt():
    global mqtt_client
    client = mqtt.Client(
        client_id=f'flexit-daemon-pi',
        protocol=mqtt.MQTTv5
    )
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.tls_set()
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    mqtt_client = client
    return client


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    log.info('Flexit UNI4 daemon starting')
    log.info(f'Modbus port: {MODBUS_PORT}, slave: {MODBUS_SLAVE}')
    log.info(f'MQTT broker: {MQTT_BROKER}:{MQTT_PORT}')

    # Connect MQTT
    client = setup_mqtt()
    log.info('Waiting for MQTT connection…')
    if not mqtt_connected.wait(timeout=15):
        log.error('MQTT connect timeout — check credentials/broker')
        sys.exit(1)

    # Wait for USB serial port (adapter may not be plugged in yet)
    import os
    while not os.path.exists(MODBUS_PORT):
        log.warning(f'Serial port {MODBUS_PORT} not found — waiting for Waveshare adapter…')
        time.sleep(10)

    # Connect Modbus
    modbus = ModbusSerialClient(
        port=MODBUS_PORT,
        baudrate=56000,
        bytesize=8,
        parity='E',       # Even parity
        stopbits=1,
        timeout=2,
    )
    client.user_data_set({'modbus': modbus})

    if not modbus.connect():
        log.error(f'Cannot open serial port {MODBUS_PORT}')
        sys.exit(1)
    log.info(f'Modbus serial open: {MODBUS_PORT} 56000 8E1 slave={MODBUS_SLAVE}')

    consecutive_errors = 0
    while True:
        try:
            data = poll_all(modbus)
            payload = json.dumps(data)
            client.publish(f'{MQTT_TOPIC_BASE}/status', payload, retain=True)
            log.info(
                f"supply={data['supply_temp']}°C  extract={data['extract_temp']}°C  "
                f"outdoor={data['outdoor_temp']}°C  HR={data['heat_recovery']}%  "
                f"mode={data['speed_mode_name']}  filter={data['filter_hours']}h"
            )
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            log.error(f'Poll error ({consecutive_errors}): {e}')
            if consecutive_errors >= 5:
                log.warning('5 consecutive errors — reconnecting Modbus')
                modbus.close()
                time.sleep(2)
                modbus.connect()
                consecutive_errors = 0

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()

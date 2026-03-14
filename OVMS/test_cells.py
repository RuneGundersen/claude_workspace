"""
Scan for cell/bank level battery metrics from OVMS FT5E.
Run this while the car is ON for best results.
"""
import paho.mqtt.client as mqtt, ssl, time

BROKER   = 'e15ab5a391184740942bb3aa44acb808.s1.eu.hivemq.cloud'
PORT     = 8883
USERNAME = 'EV88283'
PASSWORD = 'hm$lKN3Q3J6^B'

all_metrics = {}

def on_connect(c, u, f, rc, p=None):
    if not rc.is_failure:
        print('Tilkoblet — samler data i 30 sekunder...\n')
        c.subscribe('EV88283metric/#')

def on_message(c, u, msg):
    all_metrics[msg.topic] = msg.payload.decode()

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set(USERNAME, PASSWORD)
c.on_connect = on_connect
c.on_message = on_message
c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
c.connect(BROKER, PORT, 10)
c.loop_start()
time.sleep(30)
c.loop_stop()

def section(title, keys):
    matches = {k: v for k, v in all_metrics.items() if any(x in k for x in keys)}
    if matches:
        print(f'\n=== {title} ===')
        for k, v in sorted(matches.items()):
            print(f'  {k.replace("EV88283metric/", "")} = {v}')
    else:
        print(f'\n=== {title} === (ingen data)')

section('CELLE-NIVÅ (v/b/c/)',     ['/b/c/'])
section('BANK/MODUL-NIVÅ (v/b/p/)', ['/b/p/'])
section('CELLE MIN/MAX',            ['c.volt', 'c.temp', 'voltage.min', 'voltage.max',
                                     'temp.min', 'temp.max', 'b/c/v', 'b/c/t'])
section('XSE BATTERI (Fiat-spesifikt)', ['xse/v/b'])
section('ALLE BATTERI (v/b/)',      ['/v/b/'])

print(f'\nTotalt {len(all_metrics)} metrikker mottatt.')
print('Bil på:', all_metrics.get('EV88283metric/v/e/on', 'ukjent'))

import paho.mqtt.client as mqtt, ssl, time

BROKER   = 'e15ab5a391184740942bb3aa44acb808.s1.eu.hivemq.cloud'
PORT     = 8883
USERNAME = 'EV88283'
PASSWORD = 'hm$lKN3Q3J6^B'

metrics = {}

def on_connect(c, u, f, rc, p=None):
    if not rc.is_failure:
        print('Tilkoblet — henter nettverksinfo...\n')
        c.subscribe('EV88283metric/#')

def on_message(c, u, msg):
    topic = msg.topic
    val   = msg.payload.decode()
    metrics[topic] = val

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set(USERNAME, PASSWORD)
c.on_connect = on_connect
c.on_message = on_message
c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
c.connect(BROKER, PORT, 10)
c.loop_start()
time.sleep(12)
c.loop_stop()

print("=== NETTVERKSMETRIKKER ===")
for k, v in sorted(metrics.items()):
    key = k.replace('EV88283metric/', '')
    if any(x in key for x in ['net', 'wifi', 'ip', 'modem', 'sq', 'provider']):
        print(f"  {key} = {v}")

print("\n=== ALLE METRIKKER (for referanse) ===")
for k, v in sorted(metrics.items()):
    print(f"  {k.replace('EV88283metric/','')} = {v}")

import paho.mqtt.client as mqtt, ssl, time

BROKER   = 'e15ab5a391184740942bb3aa44acb808.s1.eu.hivemq.cloud'
PORT     = 8883
USERNAME = 'EV88283'
PASSWORD = 'hm$lKN3Q3J6^B'

metrics = {}

def on_connect(c, u, f, rc, p=None):
    if not rc.is_failure:
        print('Tilkoblet - samler batterimetrikker...\n')
        c.subscribe('EV88283metric/#')

def on_message(c, u, msg):
    topic = msg.topic
    val   = msg.payload.decode()
    if any(x in topic for x in ['/b/', '/c/', '/e/', 'xse', '/p/']):
        metrics[topic] = val

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set(USERNAME, PASSWORD)
c.on_connect = on_connect
c.on_message = on_message
c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
c.connect(BROKER, PORT, 10)
c.loop_start()
time.sleep(20)
c.loop_stop()

print("=== BATTERIMETRIKKER ===")
for k in sorted(metrics):
    print(f"  {k.replace('EV88283metric/','')} = {metrics[k]}")

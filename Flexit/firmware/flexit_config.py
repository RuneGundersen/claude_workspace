# Flexit daemon configuration
# Copy this file and fill in your values.

# --- Modbus / Serial ---
MODBUS_PORT  = '/dev/ttyUSB0'   # Waveshare USB-RS485 adapter on Pi
MODBUS_SLAVE = 21               # CI66 default slave address (DIP switches)

# --- MQTT (HiveMQ Cloud — same broker as OVMS) ---
MQTT_BROKER     = 'e15ab5a391184740942bb3aa44acb808.s1.eu.hivemq.cloud'
MQTT_PORT       = 8883
MQTT_USERNAME   = 'EV88283'     # reuse OVMS account, or create a second one
MQTT_PASSWORD   = 'CHANGE_ME'   # set this — never commit the real password

MQTT_TOPIC_BASE = 'flexit/UNI4'

# --- Poll interval ---
POLL_INTERVAL = 10   # seconds

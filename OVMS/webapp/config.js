// OVMS Connection Configuration — no secrets stored here
const OVMS_CONFIG = {
  // HiveMQ Cloud (private, TLS)
  broker:    'wss://e15ab5a391184740942bb3aa44acb808.s1.eu.hivemq.cloud:8884/mqtt',
  username:  'EV88283',
  // password read from localStorage — set via the in-app setup screen
  vehicleId: 'EV88283',
  clientId:  'ovms-webapp-' + Math.random().toString(16).substr(2, 8),

  // Direct local access (home network)
  ovmsIp:    '192.168.55.247',

  // Vehicle info
  vin:       '3C3CFFGE4FT741123',
  carName:   'Fiat 500e',
  carYear:   '2015',
};

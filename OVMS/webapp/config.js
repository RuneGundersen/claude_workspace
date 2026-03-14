// OVMS Connection Configuration
// Edit these values to match your setup
const OVMS_CONFIG = {
  // Dexter-web MQTT broker (WebSocket)
  broker:    'wss://ovms.dexters-web.de:9001/mqtt',
  username:  'EV88283',
  password:  'WsR@RQqp%4VVn',
  vehicleId: 'EV88283',        // Usually same as username for single-vehicle accounts
  clientId:  'ovms-webapp-' + Math.random().toString(16).substr(2, 8),

  // Vehicle info
  vin:       '3C3CFFGE4FT741123',
  carName:   'Fiat 500e',
  carYear:   '2015',

  // Future: switch to your own MQTT broker here
  // broker: 'wss://your-own-broker.com:9001/mqtt',
};

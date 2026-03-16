// Flexit webapp configuration — no secrets stored here
const FLEXIT_CONFIG = {
  broker:    'wss://e15ab5a391184740942bb3aa44acb808.s1.eu.hivemq.cloud:8884/mqtt',
  username:  'EV88283',
  // password read from localStorage — set via the in-app setup screen
  clientId:  'flexit-webapp-' + Math.random().toString(16).substr(2, 8),

  topicBase: 'flexit/UNI4',
  unitName:  'Flexit UNI4',
};

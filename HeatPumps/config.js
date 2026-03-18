// Heat Pump Unit Configuration
const HP_UNITS = [
  {
    id:   'floor1',
    name: 'Ground Floor',
    ip:   '192.168.55.122',
    icon: '🏠',
  },
  {
    id:   'floor2',
    name: 'Second Floor',
    ip:   '192.168.55.126',
    icon: '🛏',
  },
  {
    id:   'flat1',
    name: 'Flat 1',
    ip:   '192.168.55.173',
    icon: '🏢',
  },
  {
    id:   'garage',
    name: 'Garage',
    icon: '🚗',
    type: 'toshiba',                           // uses cloud API, not local HTTP
    acId: 'f6b3f09f-9dee-4197-9920-82e7d1211275',
  },
];

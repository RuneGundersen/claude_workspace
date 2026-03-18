// Heat Pump Unit Configuration
const HP_UNITS = [
  {
    id:   'floor1',
    name: 'Ground Floor',
    ip:   '192.168.55.130',
    icon: '🏠',
  },
  {
    id:   'floor2',
    name: 'Second Floor',
    ip:   '192.168.55.131',
    icon: '🛏',
  },
  {
    id:   'flat1',
    name: 'Flat 1',
    ip:   '192.168.55.132',
    icon: '🏢',
  },
  {
    id:   'basement_l2',
    name: 'Basement L2',
    ip:   '192.168.55.133',
    icon: '🏗',
  },
  {
    id:   'garage',
    name: 'Garage',
    icon: '🚗',
    type: 'toshiba',                           // uses cloud API, not local HTTP
    acId: 'f6b3f09f-9dee-4197-9920-82e7d1211275',
  },
];

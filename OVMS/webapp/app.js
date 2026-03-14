// OVMS Dashboard App Logic

let ovms;
let map = null;
let marker = null;
let updateInterval = null;

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  ovms = new OVMSService(OVMS_CONFIG);
  setupEventHandlers();
  updateStaticInfo();
  connect();
});

function connect() {
  setStatus('connecting');
  ovms.connect();
}

function setupEventHandlers() {
  ovms.on('connected', () => {
    setStatus('online');
    updateInterval = setInterval(refreshUI, 2000);
  });

  ovms.on('disconnected', () => {
    setStatus('offline');
    clearInterval(updateInterval);
  });

  ovms.on('reconnecting', () => setStatus('connecting'));

  ovms.on('error', msg => {
    setStatus('offline');
    showToast('Tilkoblingsfeil: ' + msg);
  });

  ovms.on('metric', ({ key }) => {
    // Live refresh on key metrics
    if (['v.b.soc', 'v.c.charging', 'v.p.latitude', 'v.p.longitude'].includes(key)) {
      refreshUI();
    }
  });

  // Reconnect button
  document.getElementById('btnReconnect').addEventListener('click', () => {
    ovms.disconnect();
    setTimeout(connect, 500);
  });

  // Nav tabs
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
      if (tab.dataset.tab === 'map') initMap();
    });
  });
}

// --- UI Update ---
function refreshUI() {
  updateBattery();
  updateCharging();
  updateVehicle();
  updateEnvironment();
  updateLocation();
}

function updateStaticInfo() {
  document.getElementById('carName').textContent = OVMS_CONFIG.carName;
  document.getElementById('carYear').textContent = OVMS_CONFIG.carYear;
  document.getElementById('vin').textContent     = OVMS_CONFIG.vin;
}

function updateBattery() {
  const soc      = ovms.getFloat('v.b.soc', 1);
  const range    = ovms.getFloat('v.b.range.est', 0) ?? ovms.getFloat('v.b.range', 0);
  const voltage  = ovms.getFloat('v.b.voltage', 1);
  const current  = ovms.getFloat('v.b.current', 1);
  const temp     = ovms.getFloat('v.b.temp', 1);
  const health   = ovms.getFloat('v.b.health', 0);
  const power    = (voltage && current) ? Math.abs(voltage * current / 1000).toFixed(2) : null;

  // SOC gauge
  const pct = soc ?? 0;
  document.getElementById('socValue').textContent  = soc !== null ? `${soc}%` : '--';
  document.getElementById('socBar').style.width     = `${Math.min(pct, 100)}%`;
  document.getElementById('socBar').className       = 'soc-fill ' + socColor(pct);
  document.getElementById('rangeValue').textContent = range !== null ? `${range} km` : '--';

  // Stats
  setText('battVoltage', voltage, 'V');
  setText('battCurrent', current, 'A');
  setText('battTemp',    temp,    '°C');
  setText('battHealth',  health,  '%');
  setText('battPower',   power,   'kW');
}

function updateCharging() {
  const isCharging  = ovms.getBool('v.c.charging');
  const state       = ovms.get('v.c.state') ?? '--';
  const chgPower    = ovms.getFloat('v.c.power', 2);
  const chgVoltage  = ovms.getFloat('v.c.voltage', 0);
  const chgCurrent  = ovms.getFloat('v.c.current', 1);
  const chgType     = ovms.get('v.c.type') ?? '--';
  const duration    = ovms.get('v.c.duration') ?? '--';
  const efficiency  = ovms.getFloat('v.c.efficiency', 1);

  const badge = document.getElementById('chargeBadge');
  badge.textContent  = isCharging ? '⚡ Lader' : state;
  badge.className    = 'charge-badge ' + (isCharging ? 'charging' : 'idle');

  setText('chgPower',      chgPower,    'kW');
  setText('chgVoltage',    chgVoltage,  'V');
  setText('chgCurrent',    chgCurrent,  'A');
  setText('chgType',       chgType,     '');
  setText('chgDuration',   duration,    '');
  setText('chgEfficiency', efficiency,  '%');
}

function updateVehicle() {
  const speed    = ovms.getFloat('v.p.speed', 0);
  const odometer = ovms.getFloat('v.p.odometer', 0);
  const gear     = ovms.get('v.e.gear') ?? '--';
  const locked   = ovms.getBool('v.e.locked');
  const on       = ovms.getBool('v.e.on');
  const cabinTemp = ovms.getFloat('v.e.cabintemp', 1);
  const ambientTemp = ovms.getFloat('v.e.temp', 1);
  const v12      = ovms.getFloat('v.b.12v.voltage', 2);

  setText('vSpeed',    speed,    'km/h');
  setText('vOdo',      odometer !== null ? odometer.toLocaleString('no-NO') : null, 'km');
  setText('vGear',     gear,     '');
  setText('vCabin',    cabinTemp,'°C');
  setText('vAmbient',  ambientTemp, '°C');
  setText('v12v',      v12,      'V');

  const lockIcon = document.getElementById('vLocked');
  if (locked !== null) {
    lockIcon.textContent = locked ? '🔒 Låst' : '🔓 Ulåst';
    lockIcon.className   = locked ? 'badge locked' : 'badge unlocked';
  }
  const onIcon = document.getElementById('vOn');
  if (on !== null) {
    onIcon.textContent = on ? '🟢 På' : '🔴 Av';
  }
}

function updateEnvironment() {
  const lat = ovms.get('v.p.latitude');
  const lon = ovms.get('v.p.longitude');
  if (lat && lon) {
    document.getElementById('gpsCoords').textContent = `${parseFloat(lat).toFixed(5)}, ${parseFloat(lon).toFixed(5)}`;
    if (map && marker) {
      const ll = [parseFloat(lat), parseFloat(lon)];
      marker.setLatLng(ll);
      map.setView(ll, map.getZoom());
    }
  }
}

function updateLocation() {
  updateEnvironment();
}

// --- Map ---
function initMap() {
  if (map) return;
  const lat = parseFloat(ovms.get('v.p.latitude') || '59.9139');
  const lon = parseFloat(ovms.get('v.p.longitude') || '10.7522');

  map = L.map('mapContainer').setView([lat, lon], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
  }).addTo(map);

  const icon = L.divIcon({
    className: 'car-icon',
    html: '<div style="font-size:28px">🚗</div>',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });

  marker = L.marker([lat, lon], { icon }).addTo(map)
    .bindPopup(`${OVMS_CONFIG.carName} ${OVMS_CONFIG.carYear}`);
}

// --- Helpers ---
function setText(id, value, unit) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value !== null && value !== undefined && value !== '--'
    ? `${value}${unit ? ' ' + unit : ''}`
    : '--';
}

function setStatus(state) {
  const dot  = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  const labels = { online: 'Tilkoblet', offline: 'Frakoblet', connecting: 'Kobler til...' };
  dot.className  = 'status-dot ' + state;
  text.textContent = labels[state] || state;
}

function socColor(pct) {
  if (pct > 60) return 'green';
  if (pct > 25) return 'yellow';
  return 'red';
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 4000);
}

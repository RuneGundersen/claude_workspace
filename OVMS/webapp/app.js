// OVMS Dashboard App Logic

let ovms;
window._ovms = null;   // exposed for diagnostics.js
let map = null;
let marker = null;
let updateInterval = null;
let logger  = null;
let alerts  = null;
let _lastVehicleOn = null;
let _lastCharging  = null;

// --- Init ---
// ── Credential helpers ─────────────────────────────────────────────────────
const PASS_KEY = 'ovms_password';

function getSavedPassword() { return localStorage.getItem(PASS_KEY); }
function savePassword(pw)   { localStorage.setItem(PASS_KEY, pw); }
function clearPassword()    { localStorage.removeItem(PASS_KEY); }

function showSetupModal(onSave) {
  const modal = document.getElementById('setupModal');
  const input = document.getElementById('setupPassword');
  const btn   = document.getElementById('setupSave');
  const err   = document.getElementById('setupError');
  if (!modal) return;
  input.value = '';
  err.style.display = 'none';
  modal.style.display = 'flex';
  input.focus();

  const save = () => {
    const pw = input.value.trim();
    if (!pw) { err.textContent = 'Skriv inn passordet'; err.style.display = ''; return; }
    savePassword(pw);
    modal.style.display = 'none';
    onSave(pw);
  };
  btn.onclick = save;
  input.onkeydown = e => { if (e.key === 'Enter') save(); };
}

document.addEventListener('DOMContentLoaded', () => {
  const savedPw = getSavedPassword();
  OVMS_CONFIG.password = savedPw || '';

  ovms = new OVMSService(OVMS_CONFIG);
  window._ovms = ovms;

  const shell = new OVMSShell(ovms);

  logger = new OVMSLogger();
  logger.init().catch(e => showDebug('Logger-feil: ' + e));
  logger.onTripStart   = () => updateRecordingBadge();
  logger.onTripEnd     = () => { updateRecordingBadge(); if (_historyTabActive()) refreshHistory(); };
  logger.onChargeStart = () => updateRecordingBadge();
  logger.onChargeEnd   = () => { updateRecordingBadge(); if (_historyTabActive()) refreshHistory(); };

  alerts = new OVMSAlerts();
  if (alerts.permission === 'granted') alerts.enabled = true;

  initHistoryUI(logger);
  setupNotifUI(alerts);
  initDiagnostics();
  setupEventHandlers();
  setupCommandButtons();
  updateStaticInfo();
  connect();
});

function connect() {
  const pw = getSavedPassword();
  if (!pw) {
    showSetupModal(savedPw => {
      ovms.config.password = savedPw;
      setStatus('connecting');
      ovms.connect();
    });
    return;
  }
  ovms.config.password = pw;
  setStatus('connecting');
  ovms.connect();
}

function setupEventHandlers() {
  ovms.on('connected', () => {
    setStatus('online');
    showDebug('Tilkoblet: ' + OVMS_CONFIG.broker);
    updateInterval = setInterval(refreshUI, 2000);
  });

  ovms.on('disconnected', () => {
    setStatus('offline');
    clearInterval(updateInterval);
  });

  ovms.on('reconnecting', () => {
    setStatus('connecting');
    showDebug('Kobler til: ' + OVMS_CONFIG.broker);
  });

  ovms.on('error', msg => {
    setStatus('offline');
    showToast('Feil: ' + msg);
    showDebug('ERROR: ' + msg);
  });

  ovms.on('metric', ({ key, value }) => {
    if (['v.b.soc', 'v.c.charging', 'v.p.latitude', 'v.p.longitude'].includes(key)) {
      refreshUI();
    }
    alerts?.check(key, value, ovms);
  });

  // Auto-start/stop trip logging
  ovms.on('metric:v.e.on', val => {
    const isOn = val === '1' || val === 'yes' || val === 'true';
    if (isOn === _lastVehicleOn) return;
    _lastVehicleOn = isOn;
    if (isOn) {
      logger.startTrip(ovms);
      showDebug('Tur startet — logger aktivert');
    } else {
      logger.endTrip(ovms).then(t => t && showDebug(`Tur avsluttet: ${t.points?.length ?? 0} punkter`));
    }
  });

  // Auto-start/stop charge logging
  ovms.on('metric:v.c.charging', val => {
    const isCharging = val === '1' || val === 'yes' || val === 'true';
    if (isCharging === _lastCharging) return;
    _lastCharging = isCharging;
    if (isCharging) {
      logger.startCharge(ovms);
      showDebug('Ladeøkt startet — logger aktivert');
    } else {
      logger.endCharge(ovms).then(c => c && showDebug(`Lading avsluttet: SOC ${c.startSOC}% → ${c.endSOC}%`));
    }
  });

  // Reconnect button
  document.getElementById('btnReconnect').addEventListener('click', () => {
    ovms.disconnect();
    setTimeout(connect, 500);
  });

  // Change password button
  document.getElementById('btnChangePassword')?.addEventListener('click', () => {
    ovms.disconnect();
    clearPassword();
    showSetupModal(pw => {
      ovms.config.password = pw;
      setStatus('connecting');
      ovms.connect();
    });
  });

  // Nav tabs
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
      if (tab.dataset.tab === 'map')     initMap();
      if (tab.dataset.tab === 'history') refreshHistory();
      if (tab.dataset.tab === 'diag')    updateDiagOvmsAlerts(ovms);
    });
  });
}

// --- UI Update ---
function refreshUI() {
  updateBattery();
  updateCharging();
  updateVehicle();
  updateTpms();
  updateEnvironment();
  updateLocation();
}

function updateStaticInfo() {
  document.getElementById('carName').textContent   = OVMS_CONFIG.carName;
  document.getElementById('carYear').textContent   = OVMS_CONFIG.carYear;
  document.getElementById('vin').textContent       = OVMS_CONFIG.vin;
  document.getElementById('brokerUrl').textContent = OVMS_CONFIG.broker;
}

function updateBattery() {
  // SOC & range
  const soc        = ovms.getFloat('v.b.soc', 1);
  const rangeEst   = ovms.getFloat('v.b.range.est', 0) ?? ovms.getFloat('v.b.range', 0);
  const rangeFull  = ovms.getFloat('v.b.range.full', 0);

  const pct = soc ?? 0;
  document.getElementById('socValue').textContent = soc !== null ? `${soc}%` : '--%';
  document.getElementById('socBar').style.width   = `${Math.min(pct, 100)}%`;
  document.getElementById('socBar').className     = 'soc-fill ' + socColor(pct);
  setText('rangeValue', rangeEst, '');
  setText('rangeFull',  rangeFull, '');

  // Electrical
  const voltage = ovms.getFloat('v.b.voltage', 1);
  const current = ovms.getFloat('v.b.current', 1);
  let   power   = ovms.getFloat('v.b.power', 2);
  if (power === null && voltage !== null && current !== null)
    power = parseFloat((voltage * current / 1000).toFixed(2));

  setText('battVoltage', voltage, 'V');
  setText('battCurrent', current, 'A');
  setText('battPower',   power !== null ? (power < 0 ? power : '+' + power) : null, 'kW');

  // Health & capacity
  const health   = ovms.getFloat('v.b.soh', 1) ?? ovms.getFloat('v.b.health', 1);
  const cac      = ovms.getFloat('v.b.cac', 1);
  const capacity = ovms.getFloat('v.b.capacity', 1);
  const cycles   = ovms.get('v.b.cycles');

  setText('battHealth',   health,   '%');
  setText('battCac',      cac,      'Ah');
  setText('battCapacity', capacity, 'kWh');
  setText('battCycles',   cycles,   '');

  // Temperature
  const temp    = ovms.getFloat('v.b.temp', 1);
  const tempMin = ovms.getFloat('v.b.temp.min', 1);
  const tempMax = ovms.getFloat('v.b.temp.max', 1);
  const mTemp   = ovms.getFloat('v.m.temp', 1);

  setText('battTemp',    temp,    '°C');
  setText('battTempMin', tempMin, '°C');
  setText('battTempMax', tempMax, '°C');
  setText('motorTemp',   mTemp,   '°C');

  // Energy statistics
  const eUsed  = ovms.getFloat('v.b.energy.used', 2);
  const eRecd  = ovms.getFloat('v.b.energy.recd', 2);
  const cUsed  = ovms.getFloat('v.b.coulomb.used', 1);
  const cRecd  = ovms.getFloat('v.b.coulomb.recd', 1);

  setText('battEnergyUsed',   eUsed,  'kWh');
  setText('battEnergyRecd',   eRecd,  'kWh');
  setText('battCoulombUsed',  cUsed,  'Ah');
  setText('battCoulombRecd',  cRecd,  'Ah');

  // 12V aux battery
  const v12v    = ovms.getFloat('v.b.12v.voltage', 2);
  const i12v    = ovms.getFloat('v.b.12v.current', 2);
  const s12v    = ovms.get('v.b.12v.state');

  setText('batt12vVoltage', v12v, 'V');
  setText('batt12vCurrent', i12v, 'A');
  setText('batt12vState',   s12v, '');

  // Cell heatmap
  updateCellHeatmap(ovms);
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

  setText('chgPower',      isCharging ? chgPower   : null, 'kW');
  setText('chgVoltage',    isCharging ? chgVoltage : null, 'V');
  setText('chgCurrent',    isCharging ? chgCurrent : null, 'A');
  setText('chgType',       chgType,     '');
  setText('chgDuration',   duration,    '');
  setText('chgEfficiency', efficiency,  '%');
}

function updateTpms() {
  const keys = {
    FL: 'v.tp.fl.p', FR: 'v.tp.fr.p',
    RL: 'v.tp.rl.p', RR: 'v.tp.rr.p',
  };
  const LOW = 207, CRIT = 172;  // kPa thresholds
  let anyLow = false, anyCrit = false;

  Object.entries(keys).forEach(([pos, key]) => {
    const kPa  = ovms.getFloat(key, 0);
    const tile  = document.getElementById('tpms' + pos);
    const valEl = document.getElementById('tpms' + pos + 'val');
    if (!tile || !valEl) return;

    if (kPa === null) {
      valEl.textContent = '--';
      tile.className = 'tpms-tire';
      return;
    }

    valEl.textContent = kPa;
    if (kPa < CRIT) {
      tile.className = 'tpms-tire tpms-crit';
      anyCrit = true;
    } else if (kPa < LOW) {
      tile.className = 'tpms-tire tpms-low';
      anyLow = true;
    } else {
      tile.className = 'tpms-tire tpms-ok';
    }
  });

  const alert = document.getElementById('tpmsAlert');
  if (alert) {
    if (anyCrit) {
      alert.style.display = '';
      alert.className = 'tpms-alert tpms-alert--crit';
      alert.textContent = '🚨 Kritisk lavt dekktrykk — stopp bilen';
    } else if (anyLow) {
      alert.style.display = '';
      alert.className = 'tpms-alert tpms-alert--low';
      alert.textContent = '⚠️ Lavt dekktrykk — sjekk dekkene';
    } else {
      alert.style.display = 'none';
    }
  }
}

function updateVehicle() {
  const speed    = ovms.getFloat('v.p.speed', 0);
  const odometer = ovms.getFloat('v.p.odometer', 0);
  const gear     = ovms.get('v.e.gear') ?? '--';
  const locked   = ovms.getBool('v.e.locked');
  const on       = ovms.getBool('v.e.on');
  const cabinTemp = ovms.getFloat('v.e.cabintemp', 2) / 100;  // FT5E reports in hundredths of °C
  const ambientTemp = ovms.getFloat('v.e.temp', 1);
  const v12      = ovms.getFloat('v.b.12v.voltage', 2);

  setText('vSpeed',    speed,    'km/h');
  setText('vOdo',      odometer !== null ? odometer.toLocaleString('no-NO') : null, 'km');
  setText('vGear',     gear,     '');
  setText('vCabin',    cabinTemp,'°C');
  setText('vAmbient',  ambientTemp, '°C');
  setText('v12v',      v12,      'V');

  // Driving overview card
  const soc      = ovms.getFloat('v.b.soc', 1);
  const rangeEst = ovms.getFloat('v.b.range.est', 0) ?? ovms.getFloat('v.b.range', 0);
  const power    = ovms.getFloat('v.b.power', 1);

  const dvSOC  = document.getElementById('dvSOC');
  const dvRng  = document.getElementById('dvRange');
  const dvSpd  = document.getElementById('dvSpeed');
  const dvCons = document.getElementById('dvConsumption');

  if (dvSOC)  dvSOC.innerHTML  = soc      !== null ? `${soc}<small>%</small>`       : '--%';
  if (dvRng)  dvRng.innerHTML  = rangeEst !== null ? `${rangeEst} <small>km</small>` : '-- <small>km</small>';
  if (dvSpd)  dvSpd.innerHTML  = speed    !== null ? `${speed} <small>km/h</small>`  : '-- <small>km/h</small>';

  if (dvCons) {
    let cons = null;
    if (power !== null && speed !== null && speed > 3)
      cons = parseFloat((power / speed * 100).toFixed(1));
    if (cons !== null) {
      dvCons.textContent = cons < 0 ? cons : '+' + cons;
      dvCons.style.color = cons < 0 ? 'var(--green)'
                         : cons < 15 ? 'var(--text)'
                         : cons < 22 ? 'var(--yellow)'
                         : 'var(--orange)';
    } else {
      dvCons.textContent = '--';
      dvCons.style.color = '';
    }
  }

  updateDragCard(ovms);

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

// --- Notifications ---
function setupNotifUI(alerts) {
  const btn    = document.getElementById('btnEnableNotif');
  const status = document.getElementById('notifStatus');
  const rules  = document.getElementById('notifRules');

  function updatePermUI() {
    const p = alerts.permission;
    if (p === 'granted') {
      status.textContent = '🔔 Varsler er aktivert';
      status.style.color = 'var(--green)';
      btn.style.display  = 'none';
      rules.style.display = '';
      loadNotifSettings(alerts);
    } else if (p === 'denied') {
      status.textContent = '🔕 Varsler blokkert i nettleseren';
      status.style.color = 'var(--red)';
      btn.style.display  = 'none';
    } else if (p === 'unsupported') {
      status.textContent = 'Varsler støttes ikke av denne nettleseren';
    } else {
      status.textContent = 'Trykk for å aktivere push-varsler';
    }
  }

  btn.addEventListener('click', async () => {
    const ok = await alerts.requestPermission();
    updatePermUI();
    if (ok) showToast('Varsler aktivert!');
  });

  document.getElementById('btnSaveNotif')?.addEventListener('click', () => {
    saveNotifSettings(alerts);
    showToast('Varselinnstillinger lagret');
  });

  updatePermUI();
}

function loadNotifSettings(alerts) {
  const r = alerts.rules;
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.checked = val; };
  const setN = (id, val) => { const el = document.getElementById(id); if (el) el.value  = val; };
  set('ruleChargeStart',   r.chargeStart?.enabled  ?? true);
  set('ruleChargeDone',    r.chargeDone?.enabled    ?? true);
  set('ruleSocLow',        r.socLow?.enabled        ?? true);
  set('ruleSocCritical',   r.socCritical?.enabled   ?? true);
  set('ruleBattTempHigh',  r.battTempHigh?.enabled  ?? false);
  set('ruleCarUnlocked',   r.carUnlocked?.enabled   ?? false);
  setN('threshChargeDone', r.chargeDone?.threshold  ?? 80);
  setN('threshSocLow',     r.socLow?.threshold      ?? 20);
  setN('threshSocCritical',r.socCritical?.threshold ?? 10);
  setN('threshBattTempHigh',r.battTempHigh?.threshold ?? 42);
}

function saveNotifSettings(alerts) {
  const get  = id => document.getElementById(id)?.checked ?? false;
  const getN = id => parseInt(document.getElementById(id)?.value ?? '0');
  alerts.rules.chargeStart.enabled         = get('ruleChargeStart');
  alerts.rules.chargeDone.enabled          = get('ruleChargeDone');
  alerts.rules.chargeDone.threshold        = getN('threshChargeDone');
  alerts.rules.socLow.enabled              = get('ruleSocLow');
  alerts.rules.socLow.threshold            = getN('threshSocLow');
  alerts.rules.socCritical.enabled         = get('ruleSocCritical');
  alerts.rules.socCritical.threshold       = getN('threshSocCritical');
  alerts.rules.battTempHigh.enabled        = get('ruleBattTempHigh');
  alerts.rules.battTempHigh.threshold      = getN('threshBattTempHigh');
  alerts.rules.carUnlocked.enabled         = get('ruleCarUnlocked');
  alerts.saveRules();
}

// --- Commands ---
function setupCommandButtons() {
  document.querySelectorAll('.cmd-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const cmd     = btn.dataset.cmd;
      const label   = btn.dataset.label || cmd;
      const confirm = btn.dataset.confirm;

      if (confirm && !window.confirm(confirm)) return;

      if (!ovms.connected) {
        showCmdResponse('error', 'Ikke tilkoblet — kan ikke sende kommando');
        return;
      }

      // Disable buttons, show spinner
      document.querySelectorAll('.cmd-btn').forEach(b => b.disabled = true);
      btn.classList.add('loading');
      showCmdResponse('pending', `Sender: ${label}...`);

      try {
        const response = await ovms.sendCommand(cmd);
        const msg = response?.trim() || 'OK';
        showCmdResponse('success', msg);
        logCommand(label, 'success', msg);
        showDebug(`Kommando OK [${label}]: ${msg}`);
      } catch (e) {
        showCmdResponse('error', e.message);
        logCommand(label, 'error', e.message);
        showDebug(`Kommando feil [${label}]: ${e.message}`);
      } finally {
        document.querySelectorAll('.cmd-btn').forEach(b => b.disabled = false);
        btn.classList.remove('loading');
      }
    });
  });
}

function showCmdResponse(type, msg) {
  const el = document.getElementById('cmdResponse');
  el.style.display = '';
  el.className = 'cmd-response cmd-response--' + type;
  const icons = { pending: '⏳', success: '✅', error: '❌' };
  el.textContent = (icons[type] || '') + ' ' + msg;
  if (type === 'success') setTimeout(() => { el.style.display = 'none'; }, 6000);
}

function logCommand(label, status, msg) {
  const log = document.getElementById('cmdLog');
  if (!log) return;
  const ts   = new Date().toLocaleTimeString('no-NO');
  const row  = document.createElement('div');
  row.className = 'cmd-log-row ' + status;
  row.innerHTML = `<span class="cmd-log-time">${ts}</span>
                   <span class="cmd-log-label">${label}</span>
                   <span class="cmd-log-result">${msg}</span>`;
  log.prepend(row);
  // Keep max 20 entries
  while (log.children.length > 20) log.removeChild(log.lastChild);
}

function updateRecordingBadge() {
  const badge = document.getElementById('recBadge');
  if (!badge || !logger) return;
  if (logger.isRecordingTrip) {
    badge.textContent = '● REC';
    badge.className   = 'rec-badge trip';
    badge.style.display = '';
  } else if (logger.isRecordingCharge) {
    badge.textContent = '● CHG';
    badge.className   = 'rec-badge charge';
    badge.style.display = '';
  } else {
    badge.style.display = 'none';
  }
}

function _historyTabActive() {
  return document.getElementById('panel-history')?.classList.contains('active');
}

function showDebug(msg) {
  const d = document.getElementById('debugLog');
  if (!d) return;
  const ts = new Date().toLocaleTimeString('no-NO');
  d.textContent = `[${ts}] ${msg}\n` + d.textContent;
}

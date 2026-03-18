// Heat Pump Dashboard — Daikin BRP069 local + Toshiba cloud API

// --- Toshiba API helpers ---

async function toshibaGetState(acId) {
  const resp = await fetch(`/toshiba/state?acId=${acId}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return resp.json();   // { power, mode, temp, fan, raw, updatedAt }
}

async function toshibaSet(acId, changes) {
  const resp = await fetch('/toshiba/set', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ acId, changes }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

// --- Daikin API helpers ---

function apiUrl(ip, path) {
  return `/api/${ip}/${path}`;
}

async function daikinGet(ip, path) {
  const resp = await fetch(apiUrl(ip, path));
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const text = await resp.text();
  return parseKV(text);
}

async function daikinSet(ip, params) {
  const qs = new URLSearchParams(params).toString();
  const resp = await fetch(apiUrl(ip, `aircon/set_control_info?${qs}`));
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const text = await resp.text();
  const kv = parseKV(text);
  if (kv.ret !== 'OK') throw new Error('Unit rejected command: ' + text);
  return kv;
}

function parseKV(text) {
  const obj = {};
  text.trim().split(',').forEach(pair => {
    const eq = pair.indexOf('=');
    if (eq === -1) return;
    obj[pair.slice(0, eq)] = pair.slice(eq + 1);
  });
  return obj;
}

// --- Mode / fan maps ---

const MODES = {
  '1': 'Auto',
  '2': 'Dry',
  '3': 'Cool',
  '4': 'Heat',
  '6': 'Fan',
};

const MODE_ICONS = {
  '1': '🔄',
  '2': '💧',
  '3': '❄️',
  '4': '🔥',
  '6': '💨',
};

const FAN_RATES = {
  'A': 'Auto',
  'B': 'Silent',
  '3': '1',
  '4': '2',
  '5': '3',
  '6': '4',
  '7': '5',
};

const FAN_DIRS = {
  '0': 'Fixed',
  '1': '↑',
  '2': '↗',
  '3': '→',
  '4': '↘',
  '5': '↓',
  'S': 'Swing',
};

// --- State per unit ---

const unitState = {};   // ip → { control, sensor }

// --- Polling ---

let pollTimer = null;

async function pollAll() {
  for (const unit of HP_UNITS) {
    await pollUnit(unit);
  }
}

async function pollUnit(unit) {
  const card = document.getElementById('card-' + unit.id);
  if (!card) return;
  try {
    if (unit.type === 'toshiba') {
      const state = await toshibaGetState(unit.acId);
      unitState[unit.id] = { toshiba: state };
      renderToshibaCard(unit, state);
    } else {
      const [ctrl, sensor] = await Promise.all([
        daikinGet(unit.ip, 'aircon/get_control_info'),
        daikinGet(unit.ip, 'aircon/get_sensor_info'),
      ]);
      unitState[unit.id] = { ctrl, sensor };
      renderCard(unit, ctrl, sensor);
    }
    card.classList.remove('card--error');
    card.querySelector('.card-status').textContent = '';
  } catch (e) {
    card.classList.add('card--error');
    card.querySelector('.card-status').textContent = '⚠️ Unreachable';
  }
}

// --- Render ---

function renderCard(unit, ctrl, sensor) {
  const isOn    = ctrl.pow === '1';
  const mode    = ctrl.mode;
  const stemp   = parseFloat(ctrl.stemp);
  const fRate   = ctrl.f_rate;
  const fDir    = ctrl.f_dir;
  const htemp   = parseFloat(sensor.htemp);
  const otemp   = sensor.otemp !== '-' ? parseFloat(sensor.otemp) : null;

  const card = document.getElementById('card-' + unit.id);

  // Power class
  card.classList.toggle('card--on', isOn);
  card.classList.toggle('card--off', !isOn);

  // Power button
  card.querySelector('.btn-power').textContent = isOn ? '⏻ On' : '⏻ Off';
  card.querySelector('.btn-power').classList.toggle('active', isOn);

  // Room temp
  card.querySelector('.room-temp').textContent =
    isNaN(htemp) ? '--' : htemp.toFixed(1) + '°C';

  // Outdoor temp (not all units expose this)
  const otEl = card.querySelector('.outdoor-temp');
  otEl.textContent = otemp !== null ? `Outside: ${otemp.toFixed(1)}°C` : '';

  // Mode buttons
  card.querySelectorAll('.btn-mode').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });

  // Set temp
  card.querySelector('.stemp-val').textContent = isNaN(stemp) ? '--' : stemp.toFixed(1) + '°C';

  // Fan rate buttons
  card.querySelectorAll('.btn-fan').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.fan === fRate);
  });

  // Fan dir
  card.querySelector('.fdir-val').textContent = FAN_DIRS[fDir] ?? fDir;
}

// --- Send command ---

async function sendControl(unit, changes) {
  const card = document.getElementById('card-' + unit.id);
  card.querySelector('.card-status').textContent = '⏳ Sending…';

  try {
    if (unit.type === 'toshiba') {
      const newState = await toshibaSet(unit.acId, changes);
      unitState[unit.id].toshiba = newState;
      renderToshibaCard(unit, newState);
    } else {
      const state = unitState[unit.id];
      const ctrl  = state.ctrl;
      const params = {
        pow:    ctrl.pow,
        mode:   ctrl.mode,
        stemp:  ctrl.stemp,
        shum:   ctrl.shum || '0',
        f_rate: ctrl.f_rate,
        f_dir:  ctrl.f_dir,
        ...changes,
      };
      await daikinSet(unit.ip, params);
      Object.assign(state.ctrl, params);
      renderCard(unit, state.ctrl, state.sensor);
    }
    card.querySelector('.card-status').textContent = '✅ Done';
    setTimeout(() => { card.querySelector('.card-status').textContent = ''; }, 2000);
  } catch (e) {
    card.querySelector('.card-status').textContent = '❌ ' + e.message;
  }
}

// --- Toshiba card ---

function renderToshibaCard(unit, state) {
  const card = document.getElementById('card-' + unit.id);
  const isOn = state.power === 'on';

  card.classList.toggle('card--on',  isOn);
  card.classList.toggle('card--off', !isOn);

  card.querySelector('.btn-power').textContent = isOn ? '⏻ On' : '⏻ Off';
  card.querySelector('.btn-power').classList.toggle('active', isOn);
  card.querySelector('.room-temp').textContent    = state.roomTemp != null ? `${state.roomTemp}°C` : '--';
  card.querySelector('.outdoor-temp').textContent = '';
  card.querySelector('.stemp-val').textContent    = state.setpoint != null ? `${state.setpoint}°C` : '--';

  card.querySelectorAll('.btn-mode').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === state.mode);
  });
  card.querySelectorAll('.btn-fan').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.fan === state.fan);
  });
  card.querySelector('.fdir-val').textContent = '--';
}

// --- Build cards ---

function buildCards() {
  const container = document.getElementById('units');
  container.innerHTML = '';
  HP_UNITS.forEach(unit => {
    container.insertAdjacentHTML('beforeend', cardHTML(unit));
    attachCardListeners(unit);
  });
}

function cardHTML(unit) {
  const modeButtons = Object.entries(MODES).map(([key, label]) =>
    `<button class="btn btn-mode" data-mode="${key}">${MODE_ICONS[key]} ${label}</button>`
  ).join('');

  const fanButtons = Object.entries(FAN_RATES).map(([key, label]) =>
    `<button class="btn btn-fan" data-fan="${key}">${label}</button>`
  ).join('');

  return `
  <div class="card card--off" id="card-${unit.id}">
    <div class="card-header">
      <span class="card-icon">${unit.icon}</span>
      <span class="card-name">${unit.name}</span>
      <span class="card-status"></span>
      <button class="btn btn-power btn-power--toggle">⏻ Off</button>
    </div>

    <div class="temps-row">
      <div class="room-temp-wrap">
        <div class="temp-label">Room</div>
        <div class="room-temp">--</div>
        <div class="outdoor-temp"></div>
      </div>
      <div class="settemp-wrap">
        <div class="temp-label">Set</div>
        <div class="settemp-row">
          <button class="btn btn-adj" data-adj="-0.5">−</button>
          <span class="stemp-val">--</span>
          <button class="btn btn-adj" data-adj="+0.5">+</button>
        </div>
      </div>
    </div>

    <div class="section-label">Mode</div>
    <div class="btn-row">${modeButtons}</div>

    <div class="section-label">Fan speed</div>
    <div class="btn-row">${fanButtons}</div>

    <div class="section-label">Fan direction</div>
    <div class="fdir-row">
      <button class="btn btn-fdir" data-dir="S">Swing</button>
      <button class="btn btn-fdir" data-dir="1">↑</button>
      <button class="btn btn-fdir" data-dir="2">↗</button>
      <button class="btn btn-fdir" data-dir="3">→</button>
      <button class="btn btn-fdir" data-dir="4">↘</button>
      <button class="btn btn-fdir" data-dir="5">↓</button>
      <button class="btn btn-fdir" data-dir="0">Fixed</button>
    </div>
    <div class="fdir-current">Direction: <span class="fdir-val">--</span></div>
  </div>`;
}

function attachCardListeners(unit) {
  const card = document.getElementById('card-' + unit.id);

  // Power toggle
  card.querySelector('.btn-power').addEventListener('click', () => {
    const isOn = unitState[unit.ip]?.ctrl?.pow === '1';
    sendControl(unit, { pow: isOn ? '0' : '1' });
  });

  // Mode
  card.querySelectorAll('.btn-mode').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = unit.type === 'toshiba' ? 'mode' : 'mode';
      sendControl(unit, { [key]: btn.dataset.mode });
    });
  });

  // Temperature
  card.querySelectorAll('.btn-adj').forEach(btn => {
    btn.addEventListener('click', () => {
      const s = unitState[unit.id];
      const curr = unit.type === 'toshiba'
        ? (s?.toshiba?.setpoint ?? 20)
        : parseFloat(s?.ctrl?.stemp ?? '20');
      const delta = parseFloat(btn.dataset.adj);
      const next  = Math.min(30, Math.max(16, Math.round((curr + delta) * 2) / 2));
      const key   = unit.type === 'toshiba' ? 'setpoint' : 'stemp';
      sendControl(unit, { [key]: unit.type === 'toshiba' ? next : next.toFixed(1) });
    });
  });

  // Fan speed
  card.querySelectorAll('.btn-fan').forEach(btn => {
    btn.addEventListener('click', () => sendControl(unit, { f_rate: btn.dataset.fan }));
  });

  // Fan direction
  card.querySelectorAll('.btn-fdir').forEach(btn => {
    btn.addEventListener('click', () => sendControl(unit, { f_dir: btn.dataset.dir }));
  });
}

// --- Init ---

document.addEventListener('DOMContentLoaded', () => {
  buildCards();
  pollAll();
  pollTimer = setInterval(pollAll, 15000);   // refresh every 15s

  document.getElementById('btnRefresh').addEventListener('click', pollAll);
});

'use strict';

// ── MQTT password (localStorage) ──────────────────────────────────────────
const PASS_KEY = 'flexit_password';
const getSavedPassword = () => localStorage.getItem(PASS_KEY);
const savePassword     = pw => localStorage.setItem(PASS_KEY, pw);
const clearPassword    = () => localStorage.removeItem(PASS_KEY);

// ── State ─────────────────────────────────────────────────────────────────
let mqttClient = null;
let lastStatus = null;

const SPEED_NAMES  = ['Stop', 'Min', 'Normal', 'Max', 'Forced'];
const SPEED_ICONS  = ['⏹', '🌬️', '💨', '🌀', '⚡'];

// ── DOM helpers ───────────────────────────────────────────────────────────
const $  = id => document.getElementById(id);
const el = (tag, cls, txt) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt !== undefined) e.textContent = txt;
  return e;
};

// ── Connection status ─────────────────────────────────────────────────────
function setStatus(state) {
  const dot   = $('statusDot');
  const label = $('statusLabel');
  dot.className = 'status-dot ' + state;
  label.textContent = state === 'online' ? 'Tilkoblet' :
                      state === 'connecting' ? 'Kobler til…' : 'Frakoblet';
}

// ── Setup modal ───────────────────────────────────────────────────────────
function showSetupModal(onSave) {
  const modal = $('setupModal');
  const input = $('setupPassword');
  const btn   = $('setupSave');
  const err   = $('setupError');
  modal.style.display = 'flex';
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

// ── Connect ───────────────────────────────────────────────────────────────
function connect() {
  const pw = getSavedPassword();
  if (!pw) {
    showSetupModal(savedPw => doConnect(savedPw));
    return;
  }
  doConnect(pw);
}

function doConnect(password) {
  setStatus('connecting');
  mqttClient = new Paho.Client(FLEXIT_CONFIG.broker, FLEXIT_CONFIG.clientId);

  mqttClient.onConnectionLost = () => {
    setStatus('offline');
    setTimeout(connect, 5000);
  };
  mqttClient.onMessageArrived = onMessage;

  mqttClient.connect({
    userName: FLEXIT_CONFIG.username,
    password: password,
    useSSL: true,
    keepAliveInterval: 30,
    onSuccess: () => {
      setStatus('online');
      mqttClient.subscribe(`${FLEXIT_CONFIG.topicBase}/status`);
    },
    onFailure: (err) => {
      setStatus('offline');
      console.error('MQTT connect failed:', err.errorMessage);
      setTimeout(connect, 8000);
    },
  });
}

// ── MQTT message handler ──────────────────────────────────────────────────
function onMessage(msg) {
  if (msg.destinationName === `${FLEXIT_CONFIG.topicBase}/status`) {
    try {
      lastStatus = JSON.parse(msg.payloadString);
      render(lastStatus);
    } catch (e) {
      console.error('JSON parse error:', e);
    }
  }
}

// ── Commands ──────────────────────────────────────────────────────────────
function publish(subtopic, payload) {
  if (!mqttClient || !mqttClient.isConnected()) return;
  const msg = new Paho.Message(String(payload));
  msg.destinationName = `${FLEXIT_CONFIG.topicBase}/cmd/${subtopic}`;
  mqttClient.send(msg);
}

function setSpeedMode(mode) {
  publish('set_speed', mode);
  // optimistic UI update
  const btns = document.querySelectorAll('.speed-btn');
  btns.forEach((b, i) => b.classList.toggle('active', i === mode));
}

function setTemperature(temp) {
  publish('set_temp', temp);
}

// ── Render ────────────────────────────────────────────────────────────────
function render(d) {
  // Temperatures
  setVal('supplyTemp',  d.supply_temp.toFixed(1)  + ' °C');
  setVal('extractTemp', d.extract_temp.toFixed(1) + ' °C');
  setVal('outdoorTemp', d.outdoor_temp.toFixed(1) + ' °C');

  // Heat recovery
  setVal('heatRecovery', d.heat_recovery + ' %');
  $('hrBar').style.width = d.heat_recovery + '%';
  $('hrBar').className   = 'bar-fill ' + (d.heat_recovery >= 70 ? 'bar-green' : d.heat_recovery >= 40 ? 'bar-yellow' : 'bar-orange');

  // Heating / cooling
  setVal('heatingPct', d.heating_pct + ' %');
  setVal('coolingPct', d.cooling_pct + ' %');

  // Fan speed mode
  const mode = d.actual_speed_mode;
  setVal('speedMode', SPEED_ICONS[mode] + ' ' + SPEED_NAMES[mode]);
  document.querySelectorAll('.speed-btn').forEach((b, i) => {
    b.classList.toggle('active', i === mode);
  });

  // Setpoint
  const sp = d.actual_setpoint;
  $('setpointDisplay').textContent = sp.toFixed(1) + ' °C';
  if ($('tempSlider').dataset.dragging !== 'true') {
    $('tempSlider').value = Math.round(sp * 2) / 2; // 0.5 steps
  }

  // Filter
  setVal('filterHours', d.filter_hours + ' t');
  $('filterHoursBar').style.width = Math.min(d.filter_hours / 2000 * 100, 100) + '%';
  $('filterHoursBar').className   = 'bar-fill ' + (d.filter_hours > 1800 ? 'bar-red' : d.filter_hours > 1200 ? 'bar-yellow' : 'bar-green');

  // Alarms
  renderAlarms(d);

  // Fan speed config
  setVal('s1Supply',  d.supply_speed1  + '%');
  setVal('s2Supply',  d.supply_speed2  + '%');
  setVal('s3Supply',  d.supply_speed3  + '%');
  setVal('s1Extract', d.extract_speed1 + '%');
  setVal('s2Extract', d.extract_speed2 + '%');
  setVal('s3Extract', d.extract_speed3 + '%');

  // Last update
  const ts = new Date(d.timestamp * 1000);
  $('lastUpdate').textContent = 'Sist oppdatert: ' + ts.toLocaleTimeString('nb-NO');
}

function setVal(id, text) {
  const e = $(id);
  if (e) e.textContent = text;
}

function renderAlarms(d) {
  const alarmMap = {
    alarm_supply:      'Tilluft-sensor feil',
    alarm_extract:     'Avtrekk-sensor feil',
    alarm_outdoor:     'Uteluft-sensor feil',
    alarm_fire_therm:  'Branntermostat aktiv',
    alarm_fire_smoke:  'Brann-/røyksensor aktiv',
    alarm_rotor:       'Rotorvarmer feil',
    alarm_filter:      'Bytt filter!',
  };
  const container = $('alarmList');
  container.innerHTML = '';
  let any = false;
  for (const [key, label] of Object.entries(alarmMap)) {
    if (d[key]) {
      any = true;
      const row = el('div', 'alarm-row');
      row.innerHTML = `<span class="alarm-icon">⚠️</span><span>${label}</span>`;
      container.appendChild(row);
    }
  }
  $('alarmCard').style.display = any ? 'block' : 'none';
}

// ── Temperature slider ─────────────────────────────────────────────────────
function initSlider() {
  const slider = $('tempSlider');
  slider.addEventListener('input', () => {
    $('setpointDisplay').textContent = parseFloat(slider.value).toFixed(1) + ' °C';
  });
  slider.addEventListener('touchstart', () => slider.dataset.dragging = 'true');
  slider.addEventListener('mousedown',  () => slider.dataset.dragging = 'true');
  slider.addEventListener('change', () => {
    slider.dataset.dragging = 'false';
    setTemperature(parseFloat(slider.value));
  });
}

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initSlider();

  // Speed buttons
  document.querySelectorAll('.speed-btn').forEach((btn, i) => {
    btn.addEventListener('click', () => setSpeedMode(i));
  });

  // Change password button
  const chgBtn = $('btnChangePassword');
  if (chgBtn) {
    chgBtn.addEventListener('click', () => {
      clearPassword();
      if (mqttClient && mqttClient.isConnected()) mqttClient.disconnect();
      setStatus('offline');
      showSetupModal(pw => doConnect(pw));
    });
  }

  connect();
});

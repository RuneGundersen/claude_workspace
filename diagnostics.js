// OVMS Diagnostics — DTC read / clear
// Sends OBD-II Mode 03 / 07 / 04 via OVMS command channel

// ── DTC description lookup ─────────────────────────────────────────────────
// P0/P1/P2/P3 = Powertrain, B = Body, C = Chassis, U = Network
// P0Axx / P0Bxx = Hybrid/EV specific (SAE J1979)
const DTC_DESC = {
  // Generic EV / hybrid powertrain
  'P0A00': 'Elektrisk drivverk: strøm for høy',
  'P0A01': 'Elektrisk drivverk: strøm for lav',
  'P0A02': 'Elektrisk motor A: ytelse',
  'P0A03': 'Elektrisk motor A: overtemperatur',
  'P0A04': 'Elektrisk motor A: undertemperatur',
  'P0A09': 'DC/DC-omformer: kretsfeil',
  'P0A0A': 'DC/DC-omformer: ytelse',
  'P0A0B': 'Høyspenningsbatteri: isolasjonsfeil',
  'P0A0C': 'Høyspenningsbatteri: undertemperatur',
  'P0A0D': 'Høyspenningsbatteri: overtemperatur',
  'P0A0F': 'Batterisystemets ytelse degradert',
  'P0A1A': 'Ladekrets: spenning for høy',
  'P0A1B': 'Ladekrets: spenning for lav',
  'P0A1E': 'Ladetemperatur for høy',
  'P0A3F': 'Traksjonsmotor: overtemperatur',
  'P0A7A': 'Batteristyringssystem: kommunikasjonsfeil',
  'P0A7B': 'Batteristyringssystem: ytelse',
  'P0A7E': 'Batteripakke: kontaktorfeil',
  'P0A7F': 'Høyspenningsbatteri: SOH under grense',
  'P0A80': 'Batteripakke: kapasitet kraftig redusert',
  'P0A81': 'Batterisytungssystem: intern feil',
  'P0A82': 'Batteripakke: spenningsavvik',
  'P0A9C': 'Elektrisk motor B: overtemperatur',
  'P0AC0': 'Drivelinekontroll: kommunikasjonsfeil',
  'P0B00': 'Batteripakke: cellespenning for høy',
  'P0B24': 'Batteripakke: cellespenning for lav',
  'P0B30': 'Batteripakke: strøm for høy',
  'P0B36': 'Batteripakke: temperaturavvik',
  'P0B3A': 'Batteripakke: intern isolasjonsfeil',
  'P0B6F': 'Lader: kommunikasjonsfeil',
  // Generic OBD-II (P0xxx)
  'P0010': 'Variable ventiltiming: kretsfeil A',
  'P0030': 'Oksygensensor (foran): varmer kretsfeil',
  'P0100': 'Luftmasseflow: kretsfeil',
  'P0110': 'Inntakslufttemperatur: kretsfeil',
  'P0115': 'Kjølevæsketemperatur: kretsfeil',
  'P0120': 'Gassspjeld: stillingssensor kretsfeil',
  'P0130': 'Oksygensensor bank 1: krets',
  'P0133': 'Oksygensensor bank 1: treg respons',
  'P0171': 'Blandingeforhold bank 1: for mager',
  'P0172': 'Blandingeforhold bank 1: for rik',
  'P0300': 'Tenningsfeil: tilfeldig',
  'P0420': 'Katalysatoreffektivitet bank 1: for lav',
  'P0500': 'Hastighetsensorhastighet: kretsfeil',
  'P0562': '12V batterispenning: for lav',
  'P0563': '12V batterispenning: for høy',
  'P0600': 'CAN-bus: kommunikasjonsfeil',
  'P0601': 'Styrings-ECU: internt minne-feil',
  'P0602': 'Styrings-ECU: programmeringsfeil',
  'P0605': 'Styrings-ECU: ROM-feil',
  'P0606': 'Styrings-ECU: prosessorfeil',
  'P0615': 'Starterrelé: kretsfeil',
  'P0620': 'Generator: kretsfeil',
  'P0700': 'Girkasse styringssystem: feil (MIL)',
  // Network/communication
  'U0001': 'CAN-bus: høyhastighets kommunikasjonsfeil',
  'U0100': 'Tap av kommunikasjon med motor-ECU',
  'U0101': 'Tap av kommunikasjon med girkasse-ECU',
  'U0121': 'Tap av kommunikasjon med ABS',
  'U0155': 'Tap av kommunikasjon med kombiinstrument',
  'U0164': 'Tap av kommunikasjon med klima-ECU',
  'U0401': 'Ugyldig data mottatt fra motor-ECU',
  // Body
  'B1001': 'Airbag styringsenhet: intern feil',
  'B1004': 'Airbag styringsenhet: spenningsfeil',
  // Chassis
  'C0031': 'Bremsekraft-forsterker: kretsfeil',
  'C0034': 'ABS: bakre venstre sensor kretsfeil',
  'C0040': 'ABS: foran høyre sensor kretsfeil',
  'C0110': 'ABS hydraulisk pumpe: motor kretsfeil',
  'C0561': 'Stabilitets- og trekkontroll: funksjonsfeil',
};

function dtcDescription(code) {
  return DTC_DESC[code.toUpperCase()] || 'Ukjent feilkode';
}

// ── OBD-II response parser ──────────────────────────────────────────────────
// Mode 03/07 response: "43 NN B1 B2 B3 B4 ..." (space-separated hex bytes)
// "43" = positive response to mode 03; "47" = response to mode 07
// NN  = number of DTCs
// Each DTC = 2 bytes: [type+first] [last two digits]
function parseDTCResponse(raw) {
  if (!raw) return [];
  const bytes = raw.trim().split(/\s+/).map(b => parseInt(b, 16));
  if (bytes.length < 2) return [];

  const responseId = bytes[0];
  if (responseId !== 0x43 && responseId !== 0x47) {
    // Negative response or unexpected
    return null;
  }

  const count = bytes[1];
  const dtcs = [];

  for (let i = 0; i < count; i++) {
    const idx = 2 + i * 2;
    if (idx + 1 >= bytes.length) break;

    const hi = bytes[idx];
    const lo = bytes[idx + 1];

    // Skip null DTCs (00 00)
    if (hi === 0 && lo === 0) continue;

    const type = (hi >> 6) & 0x03;
    const prefix = ['P', 'C', 'B', 'U'][type];
    const d2 = (hi >> 4) & 0x03;
    const d3 = hi & 0x0F;
    const d4 = (lo >> 4) & 0x0F;
    const d5 = lo & 0x0F;

    const code = `${prefix}${d2}${d3.toString(16).toUpperCase()}${d4.toString(16).toUpperCase()}${d5.toString(16).toUpperCase()}`;
    dtcs.push(code);
  }
  return dtcs;
}

// ── Main diagnostics controller ────────────────────────────────────────────
class Diagnostics {
  constructor() {
    this.storedDTCs  = [];
    this.pendingDTCs = [];
    this.lastScan    = null;
    this.scanning    = false;
  }

  async readStored(ovms) {
    return this._scan(ovms, 'obdii request standard 03', 'stored');
  }

  async readPending(ovms) {
    return this._scan(ovms, 'obdii request standard 07', 'pending');
  }

  async clearDTCs(ovms) {
    const raw = await ovms.sendCommand('obdii request standard 04');
    // Mode 04 positive response is "44"
    const ok = raw && raw.trim().startsWith('44');
    if (ok) {
      this.storedDTCs  = [];
      this.pendingDTCs = [];
      this.lastScan    = new Date();
    }
    return ok;
  }

  async _scan(ovms, cmd, type) {
    this.scanning = true;
    try {
      const raw  = await ovms.sendCommand(cmd);
      const dtcs = parseDTCResponse(raw);
      if (type === 'stored')  this.storedDTCs  = dtcs ?? [];
      if (type === 'pending') this.pendingDTCs = dtcs ?? [];
      this.lastScan = new Date();
      return { dtcs: dtcs ?? [], raw };
    } finally {
      this.scanning = false;
    }
  }
}

// ── UI ─────────────────────────────────────────────────────────────────────
let _diag = null;

function initDiagnostics() {
  _diag = new Diagnostics();

  document.getElementById('btnReadDTC').addEventListener('click', () => scanDTCs('stored'));
  document.getElementById('btnReadPending').addEventListener('click', () => scanDTCs('pending'));
  document.getElementById('btnClearDTC').addEventListener('click', clearDTCs);
}

async function scanDTCs(type) {
  if (!window._ovms?.connected) {
    showDiagStatus('error', 'Ikke tilkoblet — kan ikke lese feilkoder');
    return;
  }

  const btnId = type === 'stored' ? 'btnReadDTC' : 'btnReadPending';
  const btn   = document.getElementById(btnId);
  btn.disabled = true;
  btn.classList.add('loading');
  showDiagStatus('pending', type === 'stored' ? 'Leser lagrede feilkoder...' : 'Leser ventende feilkoder...');

  try {
    const result = type === 'stored'
      ? await _diag.readStored(window._ovms)
      : await _diag.readPending(window._ovms);

    if (result.dtcs === null) {
      showDiagStatus('error', 'Ukjent svar fra kjøretøy — OBD-II støttes kanskje ikke');
    } else {
      renderDTCList(type, result.dtcs);
      updateDiagTimestamp();
      const n = result.dtcs.length;
      if (n === 0) {
        showDiagStatus('ok', type === 'stored' ? 'Ingen lagrede feilkoder' : 'Ingen ventende feilkoder');
      } else {
        showDiagStatus('warn', `${n} feilkode${n > 1 ? 'r' : ''} funnet`);
      }
    }
  } catch (e) {
    showDiagStatus('error', 'Feil: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
  }
}

async function clearDTCs() {
  if (!window._ovms?.connected) {
    showDiagStatus('error', 'Ikke tilkoblet — kan ikke slette feilkoder');
    return;
  }
  if (!confirm('Slett alle lagrede og ventende feilkoder?\n\nDette vil tilbakestille feilminnet til alle ECU-er.')) return;

  const btn = document.getElementById('btnClearDTC');
  btn.disabled = true;
  btn.classList.add('loading');
  showDiagStatus('pending', 'Sletter feilkoder...');

  try {
    const ok = await _diag.clearDTCs(window._ovms);
    if (ok) {
      renderDTCList('stored',  []);
      renderDTCList('pending', []);
      updateDiagTimestamp();
      showDiagStatus('ok', 'Feilkoder slettet');
    } else {
      showDiagStatus('error', 'Kjøretøy bekreftet ikke sletting');
    }
  } catch (e) {
    showDiagStatus('error', 'Feil: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
  }
}

function renderDTCList(type, dtcs) {
  const listId = type === 'stored' ? 'dtcStoredList' : 'dtcPendingList';
  const el = document.getElementById(listId);
  if (!el) return;

  if (dtcs.length === 0) {
    el.innerHTML = `<div class="dtc-empty">Ingen feilkoder</div>`;
    return;
  }

  el.innerHTML = dtcs.map(code => {
    const desc     = dtcDescription(code);
    const typeChar = code[0];
    const typeLabel = { P: 'Drivlinje', C: 'Chassis', B: 'Karosseri', U: 'Nettverk' }[typeChar] || typeChar;
    return `
      <div class="dtc-row">
        <span class="dtc-code">${code}</span>
        <span class="dtc-type dtc-type--${typeChar.toLowerCase()}">${typeLabel}</span>
        <span class="dtc-desc">${desc}</span>
      </div>`;
  }).join('');
}

function showDiagStatus(type, msg) {
  const el = document.getElementById('diagStatus');
  if (!el) return;
  el.style.display = '';
  const icon = { ok: '✅', warn: '⚠️', error: '❌', pending: '⏳' }[type] || '';
  el.className = `diag-status diag-status--${type}`;
  el.textContent = `${icon} ${msg}`;
  if (type === 'ok') setTimeout(() => { el.style.display = 'none'; }, 6000);
}

function updateDiagTimestamp() {
  const el = document.getElementById('diagLastScan');
  if (!el || !_diag?.lastScan) return;
  el.textContent = 'Sist skannet: ' + _diag.lastScan.toLocaleTimeString('no-NO');
}

function updateDiagOvmsAlerts(ovms) {
  const el = document.getElementById('diagOvmsAlerts');
  if (!el) return;

  const alarm   = ovms.get('v.e.alarm');
  const chState = ovms.get('v.c.state');
  const bFaults = ovms.get('xse.b.faults') ?? ovms.get('v.b.faults');

  const rows = [];
  if (alarm && alarm !== '0' && alarm !== 'false' && alarm !== 'no') {
    rows.push({ label: 'Kjøretøysalarm', value: alarm, warn: true });
  }
  if (chState && chState.toLowerCase().includes('fail')) {
    rows.push({ label: 'Ladefeil', value: chState, warn: true });
  }
  if (bFaults && bFaults !== '0') {
    rows.push({ label: 'Batterifeil (OVMS)', value: bFaults, warn: true });
  }

  if (rows.length === 0) {
    el.innerHTML = '<div class="dtc-empty">Ingen aktive OVMS-varsler</div>';
  } else {
    el.innerHTML = rows.map(r => `
      <div class="dtc-row ${r.warn ? 'dtc-row--warn' : ''}">
        <span class="dtc-code">${r.label}</span>
        <span class="dtc-desc">${r.value}</span>
      </div>`).join('');
  }
}

// OVMS History UI

let historyLogger = null;
let historyMap    = null;

function initHistoryUI(logger) {
  historyLogger = logger;

  // Subtab switching
  document.querySelectorAll('.subtab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.subtab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.subtab-panel').forEach(p => p.style.display = 'none');
      btn.classList.add('active');
      document.getElementById('subtab-' + btn.dataset.subtab).style.display = '';
      if (btn.dataset.subtab === 'stats') renderStats();
    });
  });

  // Modal close
  document.getElementById('historyModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeHistoryModal();
  });
  document.getElementById('modalClose').addEventListener('click', closeHistoryModal);
}

async function refreshHistory() {
  if (!historyLogger) return;
  const [trips, charges] = await Promise.all([
    historyLogger.getTrips(),
    historyLogger.getCharges(),
  ]);
  renderTripsList(trips);
  renderChargesList(charges);
}

// --- Trip list ---
function renderTripsList(trips) {
  const el = document.getElementById('tripsList');
  if (!trips.length) {
    el.innerHTML = '<div class="history-empty">Ingen turer registrert ennå.<br>Logger automatisk når bilen slås på.</div>';
    return;
  }
  el.innerHTML = trips.map(tripCardHTML).join('');
  el.querySelectorAll('.history-card').forEach(card => {
    card.addEventListener('click', async () => {
      const trip = await historyLogger.getTrip(Number(card.dataset.id));
      showTripDetail(trip);
    });
  });
  el.querySelectorAll('.btn-export').forEach(btn => {
    btn.addEventListener('click', e => { e.stopPropagation(); exportTrip(Number(btn.dataset.id)); });
  });
  el.querySelectorAll('.btn-delete').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      if (confirm('Slett denne turen?')) {
        await historyLogger.deleteTrip(Number(btn.dataset.id));
        refreshHistory();
      }
    });
  });
}

// --- Charge list ---
function renderChargesList(charges) {
  const el = document.getElementById('chargesList');
  if (!charges.length) {
    el.innerHTML = '<div class="history-empty">Ingen ladinger registrert ennå.<br>Logger automatisk ved tilkobling av lader.</div>';
    return;
  }
  el.innerHTML = charges.map(chargeCardHTML).join('');
  el.querySelectorAll('.history-card').forEach(card => {
    card.addEventListener('click', async () => {
      const charge = await historyLogger.getCharge(Number(card.dataset.id));
      showChargeDetail(charge);
    });
  });
  el.querySelectorAll('.btn-export').forEach(btn => {
    btn.addEventListener('click', e => { e.stopPropagation(); exportCharge(Number(btn.dataset.id)); });
  });
  el.querySelectorAll('.btn-delete').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      if (confirm('Slett denne ladingen?')) {
        await historyLogger.deleteCharge(Number(btn.dataset.id));
        refreshHistory();
      }
    });
  });
}

// --- Card HTML ---
function tripCardHTML(t) {
  const dur    = fmtDuration((t.endTime ?? Date.now()) - t.startTime);
  const dist   = t.distance != null ? `${Math.round(t.distance)} km` : '--';
  const socStr = (t.startSOC != null && t.endSOC != null) ? `${t.startSOC}% → ${t.endSOC}%` : '';
  const pts    = t.points?.length ?? 0;
  const maxSpd = t.points?.reduce((m, p) => Math.max(m, p.speed ?? 0), 0) ?? 0;
  return `
  <div class="history-card" data-id="${t.id}">
    <div class="hcard-icon">🚗</div>
    <div class="hcard-body">
      <div class="hcard-title">${fmtDate(t.startTime)}</div>
      <div class="hcard-meta">${dur} &nbsp;•&nbsp; ${dist}${maxSpd ? ' &nbsp;•&nbsp; topp ' + maxSpd + ' km/h' : ''}</div>
      ${socStr ? `<div class="hcard-soc">${socStr} &nbsp;•&nbsp; ${pts} punkter</div>` : ''}
    </div>
    <div class="hcard-actions">
      <button class="btn-icon btn-export" data-id="${t.id}" title="Eksporter CSV">⬇</button>
      <button class="btn-icon btn-delete" data-id="${t.id}" title="Slett">🗑</button>
    </div>
  </div>`;
}

function chargeCardHTML(c) {
  const dur    = fmtDuration((c.endTime ?? Date.now()) - c.startTime);
  const energy = c.energyAdded != null ? `+${c.energyAdded} kWh` : '--';
  const peak   = c.peakPower  ? ` &nbsp;•&nbsp; topp ${c.peakPower} kW` : '';
  const socStr = (c.startSOC != null && c.endSOC != null) ? `${c.startSOC}% → ${c.endSOC}%` : '';
  const type   = (c.finalType ?? c.chgType ?? '').replace('--', '').toUpperCase();
  return `
  <div class="history-card" data-id="${c.id}">
    <div class="hcard-icon">⚡</div>
    <div class="hcard-body">
      <div class="hcard-title">${fmtDate(c.startTime)}${type ? ` <span class="hcard-badge">${type}</span>` : ''}</div>
      <div class="hcard-meta">${dur} &nbsp;•&nbsp; ${energy}${peak}</div>
      ${socStr ? `<div class="hcard-soc">${socStr}</div>` : ''}
    </div>
    <div class="hcard-actions">
      <button class="btn-icon btn-export" data-id="${c.id}" title="Eksporter CSV">⬇</button>
      <button class="btn-icon btn-delete" data-id="${c.id}" title="Slett">🗑</button>
    </div>
  </div>`;
}

// --- Trip detail modal ---
function showTripDetail(trip) {
  const dur    = fmtDuration((trip.endTime ?? Date.now()) - trip.startTime);
  const dist   = trip.distance != null ? `${trip.distance.toFixed(1)} km` : '--';
  const soc    = (trip.startSOC != null && trip.endSOC != null) ? `${trip.startSOC}% → ${trip.endSOC}%` : '--';
  const maxSpd = trip.points?.reduce((m, p) => Math.max(m, p.speed ?? 0), 0) ?? 0;
  const pwrPts = (trip.points || []).filter(p => p.power != null);
  const avgPwr = pwrPts.length
    ? (pwrPts.reduce((s, p) => s + Math.abs(p.power), 0) / pwrPts.length).toFixed(1)
    : '--';
  const tempPts = (trip.points || []).filter(p => p.ambTemp != null);
  const avgAmb  = tempPts.length
    ? (tempPts.reduce((s, p) => s + p.ambTemp, 0) / tempPts.length).toFixed(1)
    : '--';

  document.getElementById('modalTitle').textContent = '🚗 ' + fmtDate(trip.startTime);
  document.getElementById('modalContent').innerHTML = `
    <div class="modal-stats">
      <div class="mstat"><span>Varighet</span><strong>${dur}</strong></div>
      <div class="mstat"><span>Distanse</span><strong>${dist}</strong></div>
      <div class="mstat"><span>SOC</span><strong>${soc}</strong></div>
      <div class="mstat"><span>Maks hastighet</span><strong>${maxSpd} km/h</strong></div>
      <div class="mstat"><span>Snitt effekt</span><strong>${avgPwr} kW</strong></div>
      <div class="mstat"><span>Snitt utetemperatur</span><strong>${avgAmb} °C</strong></div>
    </div>
    <div id="tripDetailMap"></div>
  `;
  document.getElementById('historyModal').classList.add('show');
  setTimeout(() => initTripMap(trip), 150);
}

function initTripMap(trip) {
  if (historyMap) { historyMap.remove(); historyMap = null; }
  const pts = (trip.points || []).filter(p => p.lat && p.lon);
  const el  = document.getElementById('tripDetailMap');
  if (!pts.length) {
    el.innerHTML = '<div class="no-gps">Ingen GPS-data for denne turen</div>';
    return;
  }
  const latlngs = pts.map(p => [p.lat, p.lon]);
  historyMap = L.map(el);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap'
  }).addTo(historyMap);

  const track = L.polyline(latlngs, { color: '#4a90d9', weight: 3, opacity: 0.9 }).addTo(historyMap);

  // Start marker (green)
  L.circleMarker(latlngs[0], { radius: 8, color: '#2ecc71', fillColor: '#2ecc71', fillOpacity: 1 })
    .bindPopup(`Start ${new Date(pts[0].t).toLocaleTimeString('no-NO')}`)
    .addTo(historyMap);

  // End marker (red)
  const last = latlngs[latlngs.length - 1];
  L.circleMarker(last, { radius: 8, color: '#e74c3c', fillColor: '#e74c3c', fillOpacity: 1 })
    .bindPopup(`Slutt ${new Date(pts[pts.length - 1].t).toLocaleTimeString('no-NO')}`)
    .addTo(historyMap);

  historyMap.fitBounds(track.getBounds(), { padding: [16, 16] });
}

// --- Charge detail modal ---
function showChargeDetail(charge) {
  const dur    = fmtDuration((charge.endTime ?? Date.now()) - charge.startTime);
  const soc    = (charge.startSOC != null && charge.endSOC != null)
    ? `${charge.startSOC}% → ${charge.endSOC}%` : '--';
  const type   = (charge.finalType ?? charge.chgType ?? '').replace('--', '') || '--';

  const tableRows = (charge.points || []).map(p => `
    <tr>
      <td>${new Date(p.t).toLocaleTimeString('no-NO')}</td>
      <td>${p.soc ?? '--'}%</td>
      <td>${p.power ?? '--'} kW</td>
      <td>${p.voltage ?? '--'} V</td>
      <td>${p.current ?? '--'} A</td>
      <td>${p.battTemp ?? '--'} °C</td>
    </tr>`).join('');

  document.getElementById('modalTitle').textContent = '⚡ ' + fmtDate(charge.startTime);
  document.getElementById('modalContent').innerHTML = `
    <div class="modal-stats">
      <div class="mstat"><span>Varighet</span><strong>${dur}</strong></div>
      <div class="mstat"><span>Energi tilsatt</span><strong>${charge.energyAdded != null ? charge.energyAdded + ' kWh' : '--'}</strong></div>
      <div class="mstat"><span>SOC</span><strong>${soc}</strong></div>
      <div class="mstat"><span>Topp effekt</span><strong>${charge.peakPower ?? '--'} kW</strong></div>
      <div class="mstat"><span>Type</span><strong>${type.toUpperCase()}</strong></div>
    </div>
    ${tableRows ? `
    <div class="charge-table-wrap">
      <table class="charge-table">
        <thead><tr><th>Tid</th><th>SOC</th><th>Effekt</th><th>Spenning</th><th>Strøm</th><th>Batttemp</th></tr></thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>` : '<div class="no-gps">Ingen datapunkter</div>'}
  `;
  document.getElementById('historyModal').classList.add('show');
}

function closeHistoryModal() {
  document.getElementById('historyModal').classList.remove('show');
  if (historyMap) { historyMap.remove(); historyMap = null; }
}

// --- Export ---
async function exportTrip(id) {
  const trip = await historyLogger.getTrip(id);
  downloadCSV(`tur_${fmtDateFile(trip.startTime)}.csv`, historyLogger.exportTripCSV(trip));
}

async function exportCharge(id) {
  const charge = await historyLogger.getCharge(id);
  downloadCSV(`lading_${fmtDateFile(charge.startTime)}.csv`, historyLogger.exportChargeCSV(charge));
}

function downloadCSV(filename, content) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], { type: 'text/csv' }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// --- Formatters ---
function fmtDate(ts) {
  return new Date(ts).toLocaleString('no-NO', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}
function fmtDateFile(ts) {
  return new Date(ts).toISOString().slice(0, 16).replace(/[T:]/g, '-');
}
function fmtDuration(ms) {
  const min = Math.floor(ms / 60000);
  const h   = Math.floor(min / 60);
  const m   = min % 60;
  return h > 0 ? `${h}t ${m}min` : `${m}min`;
}

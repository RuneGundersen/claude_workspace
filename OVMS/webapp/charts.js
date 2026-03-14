// OVMS Statistics Charts — Chart.js powered

let _charts = {};

async function renderStats() {
  if (!historyLogger) return;
  const [trips, charges] = await Promise.all([
    historyLogger.getTrips(30),
    historyLogger.getCharges(20),
  ]);
  renderSummary(trips, charges);
  renderTripChart(trips);
  renderChargeChart(charges);
  renderSocTrend(trips);
}

// --- Summary cards ---
function renderSummary(trips, charges) {
  const totalKm     = trips.reduce((s, t) => s + (t.distance ?? 0), 0);
  const avgRange    = trips.filter(t => t.startSOC && t.distance)
    .map(t => (t.distance / (t.startSOC - (t.endSOC ?? 0))) * 100)
    .filter(v => v > 0 && v < 600);
  const avgRangeVal = avgRange.length
    ? Math.round(avgRange.reduce((a, b) => a + b, 0) / avgRange.length)
    : null;
  const totalEnergy = charges.reduce((s, c) => s + (c.energyAdded ?? 0), 0);
  const avgCharge   = charges.filter(c => c.energyAdded).length
    ? (totalEnergy / charges.filter(c => c.energyAdded).length).toFixed(1)
    : null;

  setStatText('statTotalKm',   Math.round(totalKm),    'km');
  setStatText('statAvgRange',  avgRangeVal,             'km');
  setStatText('statTotalChg',  totalEnergy.toFixed(1),  'kWh');
  setStatText('statAvgChg',    avgCharge,               'kWh');
  setStatText('statTrips',     trips.length,            'turer');
  setStatText('statCharges',   charges.length,          'ladinger');

  function setStatText(id, val, unit) {
    const el = document.getElementById(id);
    if (el) el.textContent = val != null ? `${val} ${unit}` : '--';
  }
}

// --- Trip bar chart: distance + SOC used ---
function renderTripChart(trips) {
  const canvas = document.getElementById('chartTrips');
  if (!canvas) return;

  if (!trips.length) {
    showEmpty('chartTripsWrap', 'Ingen turer å vise ennå');
    return;
  }

  const data = trips.slice().reverse().slice(-20); // last 20, chronological
  const labels   = data.map(t => fmtShortDate(t.startTime));
  const distances = data.map(t => t.distance ? +t.distance.toFixed(1) : 0);
  const socUsed   = data.map(t =>
    t.startSOC != null && t.endSOC != null ? Math.max(0, t.startSOC - t.endSOC) : null
  );

  if (_charts.trips) _charts.trips.destroy();
  _charts.trips = new Chart(canvas, {
    data: {
      labels,
      datasets: [
        {
          type: 'bar',
          label: 'Distanse (km)',
          data: distances,
          backgroundColor: 'rgba(74,144,217,.75)',
          borderRadius: 5,
          yAxisID: 'y',
        },
        {
          type: 'line',
          label: 'SOC brukt (%)',
          data: socUsed,
          borderColor: 'rgba(231,76,60,.85)',
          backgroundColor: 'rgba(231,76,60,.1)',
          pointRadius: 4,
          tension: 0.3,
          yAxisID: 'y1',
        },
      ],
    },
    options: mkOptions('km', '%'),
  });
}

// --- Charge bar chart: energy added + end SOC ---
function renderChargeChart(charges) {
  const canvas = document.getElementById('chartCharges');
  if (!canvas) return;

  if (!charges.length) {
    showEmpty('chartChargesWrap', 'Ingen ladeøkter å vise ennå');
    return;
  }

  const data   = charges.slice().reverse().slice(-20);
  const labels  = data.map(c => fmtShortDate(c.startTime));
  const energy  = data.map(c => c.energyAdded ?? 0);
  const endSoc  = data.map(c => c.endSOC ?? null);

  if (_charts.charges) _charts.charges.destroy();
  _charts.charges = new Chart(canvas, {
    data: {
      labels,
      datasets: [
        {
          type: 'bar',
          label: 'Energi tilsatt (kWh)',
          data: energy,
          backgroundColor: 'rgba(46,204,113,.75)',
          borderRadius: 5,
          yAxisID: 'y',
        },
        {
          type: 'line',
          label: 'Slutt-SOC (%)',
          data: endSoc,
          borderColor: 'rgba(241,196,15,.9)',
          backgroundColor: 'rgba(241,196,15,.1)',
          pointRadius: 4,
          tension: 0.3,
          yAxisID: 'y1',
        },
      ],
    },
    options: mkOptions('kWh', '%'),
  });
}

// --- SOC trend over trips ---
function renderSocTrend(trips) {
  const canvas = document.getElementById('chartSocTrend');
  if (!canvas || trips.length < 2) {
    showEmpty('chartSocWrap', trips.length < 2 ? 'Trenger minst 2 turer for trend' : 'Ingen data');
    return;
  }

  const data     = trips.slice().reverse().slice(-20);
  const labels   = data.map(t => fmtShortDate(t.startTime));
  const startSoc = data.map(t => t.startSOC ?? null);
  const endSoc   = data.map(t => t.endSOC   ?? null);

  if (_charts.socTrend) _charts.socTrend.destroy();
  _charts.socTrend = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'SOC ved start (%)',
          data: startSoc,
          borderColor: 'rgba(46,204,113,.8)',
          backgroundColor: 'rgba(46,204,113,.1)',
          pointRadius: 4,
          tension: 0.3,
          fill: false,
        },
        {
          label: 'SOC ved slutt (%)',
          data: endSoc,
          borderColor: 'rgba(231,76,60,.8)',
          backgroundColor: 'rgba(231,76,60,.1)',
          pointRadius: 4,
          tension: 0.3,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8888aa', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#8888aa', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.05)' } },
        y: { min: 0, max: 100, ticks: { color: '#8888aa', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.05)' } },
      },
    },
  });
}

// --- Helpers ---
function mkOptions(yLabel, y1Label) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: '#8888aa', font: { size: 11 } } } },
    scales: {
      x:  { ticks: { color: '#8888aa', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.05)' } },
      y:  { position: 'left',  title: { display: true, text: yLabel,  color: '#8888aa', font: {size:10} }, ticks: { color: '#8888aa', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.05)' } },
      y1: { position: 'right', title: { display: true, text: y1Label, color: '#8888aa', font: {size:10} }, ticks: { color: '#8888aa', font: { size: 10 } }, grid: { drawOnChartArea: false }, min: 0, max: 100 },
    },
  };
}

function showEmpty(wrapperId, msg) {
  const wrap = document.getElementById(wrapperId);
  if (wrap) wrap.innerHTML = `<div class="chart-empty">${msg}</div>`;
}

function fmtShortDate(ts) {
  const d = new Date(ts);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

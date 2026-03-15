// Cell voltage heatmap — reads v.b.c.voltage.0 … .95 from OVMS metrics
// Called from updateBattery() in app.js every 2 seconds.
// Colors each cell by deviation from the pack average (mV):
//   < 10 mV  → green      (well balanced)
//   10–25 mV → lime       (minor imbalance)
//   25–50 mV → yellow     (moderate)
//   50–100 mV→ orange     (notable)
//   ≥ 100 mV → red        (bad cell)

const CELL_COUNT    = 96;
const CELLS_PER_ROW = 12;

function updateCellHeatmap(ovms) {
  const voltages = [];
  for (let i = 0; i < CELL_COUNT; i++) {
    const v = ovms.getFloat(`v.b.c.voltage.${i}`, 3);
    voltages.push(v);
  }

  const valid  = voltages.filter(v => v !== null && v > 1.0);
  const noData = document.getElementById('cellNoData');
  const grid   = document.getElementById('cellGrid');
  const stats  = document.getElementById('cellStats');
  const ts     = document.getElementById('cellTimestamp');

  if (valid.length === 0) {
    if (noData) noData.style.display = '';
    if (grid)   grid.style.display   = 'none';
    if (stats)  stats.style.display  = 'none';
    if (ts)     ts.textContent       = '';
    return;
  }

  const min    = Math.min(...valid);
  const max    = Math.max(...valid);
  const avg    = valid.reduce((a, b) => a + b, 0) / valid.length;
  const spread = max - min;

  // ── Stats row ─────────────────────────────────────────────────────────────
  if (stats) {
    const spreadCls = spread > 0.050 ? 'cell-stat-warn'
                    : spread > 0.020 ? 'cell-stat-caution'
                    : '';
    stats.innerHTML = `
      <span class="cell-stat-item">
        <span class="cell-stat-lbl">Min</span>
        <span class="cell-stat-val cell-stat-lo">${(min * 1000).toFixed(0)} mV</span>
      </span>
      <span class="cell-stat-item">
        <span class="cell-stat-lbl">Snitt</span>
        <span class="cell-stat-val">${(avg * 1000).toFixed(0)} mV</span>
      </span>
      <span class="cell-stat-item">
        <span class="cell-stat-lbl">Maks</span>
        <span class="cell-stat-val cell-stat-hi">${(max * 1000).toFixed(0)} mV</span>
      </span>
      <span class="cell-stat-item">
        <span class="cell-stat-lbl">Spread</span>
        <span class="cell-stat-val ${spreadCls}">${(spread * 1000).toFixed(0)} mV</span>
      </span>
    `;
    stats.style.display = '';
  }

  // ── Grid ─────────────────────────────────────────────────────────────────
  if (grid) {
    // Build cells once
    if (grid.children.length !== CELL_COUNT) {
      grid.innerHTML = '';
      for (let i = 0; i < CELL_COUNT; i++) {
        const el = document.createElement('div');
        el.className = 'cell-item';
        grid.appendChild(el);
      }
    }
    // Update colors + tooltips
    for (let i = 0; i < CELL_COUNT; i++) {
      const el = grid.children[i];
      const v  = voltages[i];
      el.className = 'cell-item ' + _cellClass(v, avg);
      el.title = v !== null && v > 1.0
        ? `#${i + 1}: ${(v * 1000).toFixed(0)} mV (Δ${((v - avg) * 1000).toFixed(0)} mV)`
        : `#${i + 1}: --`;
    }
    grid.style.display = '';
  }

  if (noData) noData.style.display = 'none';
  if (ts) ts.textContent = 'Oppdatert: ' + new Date().toLocaleTimeString('no-NO');
}

function _cellClass(v, avg) {
  if (v === null || v <= 1.0) return 'cell-v-none';
  const d = Math.abs(v - avg) * 1000; // mV
  if (d <  10) return 'cell-v-ok';
  if (d <  25) return 'cell-v-warn-lo';
  if (d <  50) return 'cell-v-warn';
  if (d < 100) return 'cell-v-low';
  return 'cell-v-crit';
}

// Drag force estimation for Fiat 500e (2015)
// Aerodynamic drag + tire rolling resistance on flat road, no wind.
//
// Sources / references:
//   Cd 0.311, A 2.13 m²   — SAE wind-tunnel test, Fiat 500e (2013-2019)
//   Cr 0.011              — Michelin Energy Saver+ 185/65 R15 (OE tyre)
//   Mass 1450 kg          — curb 1360 kg + 90 kg driver
//   Air density           — adjusted for ambient temperature via ideal gas law

const FT5E_PHYSICS = {
  Cd:   0.311,      // aerodynamic drag coefficient
  A:    2.13,       // frontal area (m²)
  Cr:   0.011,      // rolling resistance coefficient
  mass: 1450,       // vehicle + driver mass (kg)
  g:    9.81,       // gravitational acceleration (m s⁻²)
  rho0: 1.293,      // air density at 0 °C, sea level (kg m⁻³)
};

/**
 * Estimate drag forces at a given speed and ambient temperature.
 *
 * @param {number} speedKmh   - Vehicle speed (km/h)
 * @param {number} tempC      - Ambient air temperature (°C), default 15
 * @returns {{ F_aero, F_roll, F_total, P_kw, v_ms, rho }}
 *   All forces in Newtons; power in kW; speed in m/s.
 */
function estimateDrag(speedKmh, tempC = 15) {
  const v   = speedKmh / 3.6;                                   // m/s
  const rho = FT5E_PHYSICS.rho0 * (273.15 / (273.15 + tempC)); // kg/m³

  const F_aero  = 0.5 * rho * FT5E_PHYSICS.Cd * FT5E_PHYSICS.A * v * v;
  const F_roll  = FT5E_PHYSICS.Cr * FT5E_PHYSICS.mass * FT5E_PHYSICS.g;
  const F_total = F_aero + F_roll;
  const P_kw    = F_total * v / 1000;

  return { F_aero, F_roll, F_total, P_kw, v_ms: v, rho };
}

// ── UI update ──────────────────────────────────────────────────────────────

function updateDragCard(ovms) {
  const speedKmh = ovms.getFloat('v.p.speed', 1);
  const tempC    = ovms.getFloat('v.e.temp',  1) ?? 15;

  const card = document.getElementById('dragCard');
  if (!card) return;

  // Hide card when stopped (< 2 km/h)
  if (speedKmh === null || speedKmh < 2) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  const d = estimateDrag(speedKmh, tempC);

  // Progress bar: scale so that 100 % = 1000 N (well above highway max)
  const pct = v => Math.min(v / 1000 * 100, 100);

  _dragBar('dragAero',  d.F_aero,  pct(d.F_aero));
  _dragBar('dragRoll',  d.F_roll,  pct(d.F_roll));
  _dragBar('dragTotal', d.F_total, pct(d.F_total));

  _setText('dragPower', d.P_kw.toFixed(1) + ' kW');
  _setText('dragSpeed', speedKmh.toFixed(0) + ' km/h');
  _setText('dragRho',   d.rho.toFixed(3)   + ' kg/m³');

  // Fraction labels
  const aeroFrac = d.F_aero / d.F_total * 100;
  const rollFrac = d.F_roll / d.F_total * 100;
  _setText('dragAeroFrac', aeroFrac.toFixed(0) + '%');
  _setText('dragRollFrac', rollFrac.toFixed(0) + '%');
}

function _dragBar(id, forceN, pct) {
  const row = document.getElementById(id);
  if (!row) return;
  const valEl = row.querySelector('.drag-val');
  const barEl = row.querySelector('.drag-bar-fill');
  if (valEl) valEl.textContent = Math.round(forceN) + ' N';
  if (barEl) barEl.style.width = pct.toFixed(1) + '%';
}

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

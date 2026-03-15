// Drag + grade force estimation for Fiat 500e (2015)
//
// Forces on flat road:
//   F_aero  = ½ · ρ(T) · Cd · A · v²
//   F_roll  = Cr · m · g
//   F_grade = m · g · sin(atan(Δh / Δd))   ← new; > 0 uphill, < 0 downhill
//   F_total = F_aero + F_roll + F_grade
//
// Sources:
//   Cd 0.311, A 2.13 m²  — SAE tunnel test, Fiat 500e 2013-2019
//   Cr 0.011             — Michelin Energy Saver+ 185/65 R15 (OE)
//   m  1450 kg           — curb 1360 kg + 90 kg driver

const FT5E_PHYSICS = {
  Cd:   0.311,
  A:    2.13,
  Cr:   0.011,
  mass: 1450,
  g:    9.81,
  rho0: 1.293,   // air density at 0 °C, sea level (kg m⁻³)
};

// ── Grade estimator ────────────────────────────────────────────────────────
//
// GPS altitude is noisy (±3–10 m). Strategy:
//   1. EMA-smooth the raw altitude samples (α = 0.15 → heavy smoothing).
//   2. Accumulate horizontal distance by integrating speed × dt each call.
//   3. Keep a 30-second sliding window of {dist, alt} pairs.
//   4. grade = Δalt / Δdist over that window.
//   5. Only report when Δdist ≥ MIN_DIST and speed ≥ MIN_SPEED.
//
// The horizontal distance integral via speed × dt is far more accurate
// than using the odometer (which is integer km) at this time scale.

const _GRADE = {
  ALPHA:    0.15,   // EMA factor — smaller = smoother but more lag
  WIN_MS:   30000,  // sliding window (ms)
  MIN_DIST: 80,     // minimum window distance (m) before reporting
  MIN_KMH:  12,     // ignore grade below this speed
};

class GradeEstimator {
  constructor() {
    this._buf      = [];      // [{t, dist, alt}]
    this._cumDist  = 0;       // integrated distance (m)
    this._lastT    = null;
    this._altEma   = null;    // EMA-smoothed altitude (m)
    this.gradeRaw  = null;    // dimensionless (m/m); null = not available
    this.altSmooth = null;    // current smoothed altitude (m)
  }

  /** Call once per refresh cycle.
   *  @param {number|null} altRaw  - GPS altitude (m), or null if unavailable
   *  @param {number}      speedKmh
   *  @returns {number|null}  grade (m/m), positive = uphill
   */
  update(altRaw, speedKmh) {
    const now = Date.now();

    // Accumulate horizontal distance (always, even when alt unavailable)
    if (this._lastT !== null) {
      const dt = (now - this._lastT) / 1000;          // s
      this._cumDist += Math.max(0, speedKmh / 3.6) * dt;  // m
    }
    this._lastT = now;

    if (altRaw === null) {
      this.gradeRaw  = null;
      this.altSmooth = null;
      return null;
    }

    // EMA smooth altitude
    if (this._altEma === null) {
      this._altEma = altRaw;
    } else {
      this._altEma = _GRADE.ALPHA * altRaw + (1 - _GRADE.ALPHA) * this._altEma;
    }
    this.altSmooth = this._altEma;

    // Push sample
    this._buf.push({ t: now, dist: this._cumDist, alt: this._altEma });

    // Trim samples older than the window
    const cutoff = now - _GRADE.WIN_MS;
    while (this._buf.length > 2 && this._buf[0].t < cutoff) {
      this._buf.shift();
    }

    // Need enough distance and minimum speed
    if (this._buf.length < 2 || speedKmh < _GRADE.MIN_KMH) {
      this.gradeRaw = null;
      return null;
    }

    const old   = this._buf[0];
    const cur   = this._buf[this._buf.length - 1];
    const dDist = cur.dist - old.dist;
    const dAlt  = cur.alt  - old.alt;

    if (dDist < _GRADE.MIN_DIST) {
      this.gradeRaw = null;
      return null;
    }

    this.gradeRaw = dAlt / dDist;
    return this.gradeRaw;
  }

  get gradePct() {
    return this.gradeRaw !== null ? this.gradeRaw * 100 : null;
  }

  reset() {
    this._buf     = [];
    this._cumDist = 0;
    this._lastT   = null;
    this._altEma  = null;
    this.gradeRaw  = null;
    this.altSmooth = null;
  }
}

// Module-level singleton — persists across refresh cycles
const _gradeEst = new GradeEstimator();


// ── Physics calculation ────────────────────────────────────────────────────

/**
 * @param {number} speedKmh
 * @param {number} tempC       ambient temperature (°C)
 * @param {number} gradeRaw    Δh/Δd, dimensionless; 0 if unknown
 * @returns {{ F_aero, F_roll, F_grade, F_total, P_kw, v_ms, rho, gradeRaw }}
 */
function estimateDrag(speedKmh, tempC = 15, gradeRaw = 0) {
  const v   = speedKmh / 3.6;
  const rho = FT5E_PHYSICS.rho0 * (273.15 / (273.15 + tempC));

  const F_aero  = 0.5 * rho * FT5E_PHYSICS.Cd * FT5E_PHYSICS.A * v * v;
  const F_roll  = FT5E_PHYSICS.Cr * FT5E_PHYSICS.mass * FT5E_PHYSICS.g;
  // Exact formula (no small-angle assumption) — matters above ~10% grade
  const F_grade = FT5E_PHYSICS.mass * FT5E_PHYSICS.g * Math.sin(Math.atan(gradeRaw));
  const F_total = F_aero + F_roll + F_grade;
  const P_kw    = F_total * v / 1000;

  return { F_aero, F_roll, F_grade, F_total, P_kw, v_ms: v, rho, gradeRaw };
}


// ── UI update ──────────────────────────────────────────────────────────────

function updateDragCard(ovms) {
  const speedKmh = ovms.getFloat('v.p.speed',   1);
  const tempC    = ovms.getFloat('v.e.temp',     1) ?? 15;
  const altRaw   = ovms.getFloat('v.p.altitude', 1);

  const card = document.getElementById('dragCard');
  if (!card) return;

  if (speedKmh === null || speedKmh < 2) {
    // Still update the estimator so it accumulates distance while stopped
    _gradeEst.update(altRaw, 0);
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  const grade    = _gradeEst.update(altRaw, speedKmh);
  const gradeRaw = grade ?? 0;
  const d        = estimateDrag(speedKmh, tempC, gradeRaw);

  // ── Summary row ──────────────────────────────────────────────────────────
  _setText('dragSpeed', speedKmh.toFixed(0) + ' km/h');
  _setText('dragPower', d.P_kw.toFixed(1)   + ' kW');
  _setText('dragRho',   d.rho.toFixed(3)     + ' kg/m³');

  // Altitude
  const altEl = document.getElementById('dragAlt');
  if (altEl) {
    altEl.textContent = _gradeEst.altSmooth !== null
      ? Math.round(_gradeEst.altSmooth) + ' m'
      : '--';
  }

  // Grade indicator in summary
  const gradeEl  = document.getElementById('dragGradePct');
  const gradeRow = document.getElementById('dragGradeRow');
  if (gradeEl) {
    if (grade !== null) {
      const pct  = (gradeRaw * 100).toFixed(1);
      const sign = gradeRaw > 0 ? '+' : '';
      const arrow = gradeRaw >  0.002 ? ' ⬆' :
                    gradeRaw < -0.002 ? ' ⬇' : ' ➡';
      gradeEl.textContent  = sign + pct + '%' + arrow;
      gradeEl.className    = 'drag-summary-val ' +
        (gradeRaw >  0.005 ? 'drag-grade-up' :
         gradeRaw < -0.005 ? 'drag-grade-dn' : '');
    } else {
      gradeEl.textContent = '-- (beregner…)';
      gradeEl.className   = 'drag-summary-val';
    }
  }

  // ── Force bars ────────────────────────────────────────────────────────────
  // Scale: 100 % bar = 1200 N
  const SCALE = 1200;
  _dragBar('dragAero',  d.F_aero, Math.abs(d.F_aero)  / SCALE * 100, false);
  _dragBar('dragRoll',  d.F_roll, Math.abs(d.F_roll)  / SCALE * 100, false);

  // Grade bar — uphill = orange, downhill = green
  if (gradeRow) {
    if (grade !== null) {
      gradeRow.style.display = '';
      const isDown = d.F_grade < 0;
      _dragBar('dragGrade', d.F_grade,
               Math.abs(d.F_grade) / SCALE * 100, isDown);
      // Override bar colour class
      const fill = document.querySelector('#dragGrade .drag-bar-fill');
      if (fill) {
        fill.className = 'drag-bar-fill ' + (isDown ? 'drag-bar-grade-dn' : 'drag-bar-grade-up');
      }
      // Label
      const nameEl = document.querySelector('#dragGrade .drag-name');
      if (nameEl) nameEl.textContent = isDown ? 'Bakke (assistanse)' : 'Bakkeresistans';
    } else {
      gradeRow.style.display = 'none';
    }
  }

  // Total: colour changes when gravity net-assists (F_total < 0)
  const totalValEl = document.querySelector('#dragTotal .drag-val');
  _dragBar('dragTotal', d.F_total,
           Math.min(Math.abs(d.F_total) / SCALE * 100, 100),
           d.F_total < 0);
  if (totalValEl) {
    totalValEl.className = 'drag-val ' + (d.F_total < 0 ? 'drag-grade-dn' : 'drag-total-color');
    totalValEl.textContent = (d.F_total >= 0 ? '' : '−') +
                             Math.abs(Math.round(d.F_total)) + ' N';
  }

  // Fractions (only aero and roll relative to total resistance, excluding grade)
  const F_res = d.F_aero + d.F_roll;  // always positive
  _setText('dragAeroFrac', (d.F_aero / F_res * 100).toFixed(0) + '%');
  _setText('dragRollFrac', (d.F_roll / F_res * 100).toFixed(0) + '%');

  // Footnote: show "(+ bakke)" or "(− bakke)" when grade is active
  const noteEl = document.getElementById('dragNote');
  if (noteEl) {
    const base = 'Modell: Cd 0.311 · A 2.13 m² · Cr 0.011 · m 1450 kg · ingen vind';
    noteEl.textContent = grade !== null
      ? base + ' · bakke fra GPS-høyde'
      : base + ' · flat vei (venter på GPS-høydedata)';
  }
}

function _dragBar(id, forceN, pct, invert) {
  const row = document.getElementById(id);
  if (!row) return;
  const valEl = row.querySelector('.drag-val');
  const barEl = row.querySelector('.drag-bar-fill');
  if (valEl && id !== 'dragTotal') {   // total val handled separately
    const sign = forceN < 0 ? '−' : '';
    valEl.textContent = sign + Math.abs(Math.round(forceN)) + ' N';
  }
  if (barEl) barEl.style.width = Math.max(0, pct).toFixed(1) + '%';
}

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// OVMS Alert & Notification System

class OVMSAlerts {
  constructor() {
    this.enabled     = false;
    this.rules       = this._loadRules();
    this._states     = {};  // last known states for edge detection
  }

  // --- Default rules ---
  _defaultRules() {
    return {
      socLow:       { enabled: true,  threshold: 20, label: 'Lavt batteri' },
      socCritical:  { enabled: true,  threshold: 10, label: 'Kritisk lavt batteri' },
      chargeDone:   { enabled: true,  threshold: 80, label: 'Lading fullført' },
      chargeStart:  { enabled: true,  label: 'Lading startet' },
      battTempHigh: { enabled: false, threshold: 42, label: 'Høy batteritemperatur' },
      battTempLow:  { enabled: false, threshold: 0,  label: 'Lav batteritemperatur' },
      carUnlocked:  { enabled: false, label: 'Bilen låst opp' },
    };
  }

  _loadRules() {
    try {
      const s = localStorage.getItem('ovms_alerts');
      return s ? { ...this._defaultRules(), ...JSON.parse(s) } : this._defaultRules();
    } catch { return this._defaultRules(); }
  }

  saveRules() {
    localStorage.setItem('ovms_alerts', JSON.stringify(this.rules));
  }

  // --- Permission ---
  async requestPermission() {
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') { this.enabled = true; return true; }
    if (Notification.permission === 'denied')  return false;
    const res = await Notification.requestPermission();
    this.enabled = (res === 'granted');
    return this.enabled;
  }

  get permission() {
    if (!('Notification' in window)) return 'unsupported';
    return Notification.permission;
  }

  // --- Check metric for alert conditions ---
  check(key, value, ovms) {
    switch (key) {

      case 'v.b.soc': {
        const soc = parseFloat(value);
        if (isNaN(soc)) break;
        const r = this.rules;
        if (r.socCritical.enabled && soc <= r.socCritical.threshold
            && this._risingEdge('socCritical', soc <= r.socCritical.threshold)) {
          this._fire('🚨 Kritisk lavt batteri!', `SOC er ${soc}% — lad bilen snarest!`, true);
        } else if (r.socLow.enabled && soc <= r.socLow.threshold
            && this._risingEdge('socLow', soc <= r.socLow.threshold)) {
          this._fire('🔋 Lavt batteri', `SOC er ${soc}% — husk å lade`);
        }
        if (soc > (r.socLow.threshold + 5)) {
          this._states.socLow = false;
          this._states.socCritical = false;
        }
        break;
      }

      case 'v.c.charging': {
        const now = value === '1' || value === 'yes' || value === 'true';
        const was = this._states.charging;
        if (was !== undefined && was !== now) {
          const soc = ovms?.getFloat('v.b.soc', 1);
          if (now && this.rules.chargeStart.enabled) {
            this._fire('⚡ Lading startet', `SOC: ${soc ?? '--'}%`);
          }
          if (!now && this.rules.chargeDone.enabled) {
            if (soc != null && soc >= this.rules.chargeDone.threshold) {
              this._fire('✅ Lading fullført', `Batteriet er ladet til ${soc}%`);
            } else if (soc != null) {
              this._fire('⏹ Lading stoppet', `SOC: ${soc}%`);
            }
          }
        }
        this._states.charging = now;
        break;
      }

      case 'v.b.temp': {
        const t = parseFloat(value);
        if (isNaN(t)) break;
        if (this.rules.battTempHigh.enabled && t >= this.rules.battTempHigh.threshold
            && this._risingEdge('battTempHigh', t >= this.rules.battTempHigh.threshold)) {
          this._fire('🌡️ Høy batteritemperatur', `${t}°C — unngå hurtiglading nå`);
        }
        if (this.rules.battTempLow.enabled && t <= this.rules.battTempLow.threshold
            && this._risingEdge('battTempLow', t <= this.rules.battTempLow.threshold)) {
          this._fire('🥶 Lav batteritemperatur', `${t}°C — forvarming anbefales`);
        }
        break;
      }

      case 'v.e.locked': {
        const locked = value === '1' || value === 'yes' || value === 'true';
        if (this.rules.carUnlocked.enabled
            && this._states.locked === true && !locked) {
          this._fire('🔓 Bilen er låst opp', 'Fiat 500e ble nettopp låst opp');
        }
        this._states.locked = locked;
        break;
      }
    }
  }

  // --- Internal ---
  _risingEdge(key, state) {
    const prev = this._states[key] ?? false;
    this._states[key] = state;
    return state && !prev;
  }

  _fire(title, body, critical = false) {
    // In-app toast always shown
    if (typeof showToast === 'function') showToast(title + ' — ' + body);

    if (!this.enabled || Notification.permission !== 'granted') return;
    try {
      new Notification(title, {
        body,
        icon:              'icons/icon.svg',
        badge:             'icons/icon.svg',
        tag:               title,
        requireInteraction: critical,
        vibrate:           critical ? [300, 100, 300, 100, 300] : [200],
      });
    } catch (e) { console.warn('Notification error:', e); }
  }
}

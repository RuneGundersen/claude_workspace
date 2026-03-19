// OVMS Data Logger — IndexedDB-backed trip & charge session recording

class OVMSLogger {
  constructor() {
    this.db           = null;
    this.activeTrip   = null;
    this.activeCharge = null;
    this._tripTimer   = null;
    this._chgTimer    = null;
    this.onTripStart   = null;
    this.onTripEnd     = null;
    this.onChargeStart = null;
    this.onChargeEnd   = null;
  }

  // --- Init ---
  async init() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open('ovms_log', 1);
      req.onupgradeneeded = e => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains('trips')) {
          const s = db.createObjectStore('trips', { keyPath: 'id', autoIncrement: true });
          s.createIndex('startTime', 'startTime');
        }
        if (!db.objectStoreNames.contains('charges')) {
          const s = db.createObjectStore('charges', { keyPath: 'id', autoIncrement: true });
          s.createIndex('startTime', 'startTime');
        }
      };
      req.onsuccess = e => { this.db = e.target.result; resolve(); };
      req.onerror   = e => reject(e.target.error);
    });
  }

  get isRecordingTrip()   { return !!this.activeTrip; }
  get isRecordingCharge() { return !!this.activeCharge; }

  // --- Trip recording ---
  startTrip(ovms) {
    if (this.activeTrip) return;
    const lat = parseFloat(ovms.get('v.p.latitude'));
    const lon = parseFloat(ovms.get('v.p.longitude'));
    this.activeTrip = {
      startTime: Date.now(),
      startSOC:  ovms.getFloat('v.b.soc', 1),
      startOdo:  ovms.getFloat('v.p.odometer', 0),
      startLat:  isNaN(lat) ? null : lat,
      startLon:  isNaN(lon) ? null : lon,
      points:    [],
    };
    this._snapTripPoint(ovms);
    this._tripTimer = setInterval(() => this._snapTripPoint(ovms), 10000);
    if (this.onTripStart) this.onTripStart();
  }

  _snapTripPoint(ovms) {
    if (!this.activeTrip) return;
    const lat = parseFloat(ovms.get('v.p.latitude'));
    const lon = parseFloat(ovms.get('v.p.longitude'));
    this.activeTrip.points.push({
      t:         Date.now(),
      lat:       isNaN(lat) ? null : lat,
      lon:       isNaN(lon) ? null : lon,
      speed:     ovms.getFloat('v.p.speed', 0),
      soc:       ovms.getFloat('v.b.soc', 1),
      power:     ovms.getFloat('v.b.power', 2),
      battTemp:  ovms.getFloat('v.b.temp', 1),
      ambTemp:   ovms.getFloat('v.e.temp', 1),
      cabinTemp: ovms.getFloat('v.e.cabintemp', 1),
    });
  }

  async endTrip(ovms) {
    if (!this.activeTrip) return null;
    clearInterval(this._tripTimer);
    this._tripTimer = null;
    this._snapTripPoint(ovms);
    const endOdo = ovms.getFloat('v.p.odometer', 0);
    const record = {
      ...this.activeTrip,
      endTime:  Date.now(),
      endSOC:   ovms.getFloat('v.b.soc', 1),
      endOdo,
      distance: (endOdo != null && this.activeTrip.startOdo != null)
                  ? Math.max(0, endOdo - this.activeTrip.startOdo)
                  : null,
    };
    this.activeTrip = null;
    const id = await this._add('trips', record);
    record.id = id;
    if (this.onTripEnd) this.onTripEnd(record);
    return record;
  }

  // --- Charge recording ---
  startCharge(ovms) {
    if (this.activeCharge) return;
    const lat = parseFloat(ovms.get('v.p.latitude'));
    const lon = parseFloat(ovms.get('v.p.longitude'));
    this.activeCharge = {
      startTime:        Date.now(),
      startSOC:         ovms.getFloat('v.b.soc', 1),
      chgType:          ovms.get('v.c.type') ?? '--',
      lat:              isNaN(lat) ? null : lat,
      lon:              isNaN(lon) ? null : lon,
      peakPower:        0,
      _startEnergyRecd: parseFloat(ovms.get('v.b.energy.recd') ?? '0') || 0,
      points:           [],
    };
    this._snapChargePoint(ovms);
    this._chgTimer = setInterval(() => this._snapChargePoint(ovms), 30000);
    if (this.onChargeStart) this.onChargeStart();
  }

  _snapChargePoint(ovms) {
    if (!this.activeCharge) return;
    const power = ovms.getFloat('v.c.power', 2) ?? 0;
    if (power > this.activeCharge.peakPower) this.activeCharge.peakPower = power;
    this.activeCharge.points.push({
      t:        Date.now(),
      soc:      ovms.getFloat('v.b.soc', 1),
      power,
      voltage:  ovms.getFloat('v.c.voltage', 0),
      current:  ovms.getFloat('v.c.current', 1),
      battTemp: ovms.getFloat('v.b.temp', 1),
    });
  }

  async endCharge(ovms) {
    if (!this.activeCharge) return null;
    clearInterval(this._chgTimer);
    this._chgTimer = null;
    this._snapChargePoint(ovms);

    const endEnergyRecd = parseFloat(ovms.get('v.b.energy.recd') ?? '0') || 0;
    const energyDelta   = Math.max(0, endEnergyRecd - this.activeCharge._startEnergyRecd);
    const energyMetric  = ovms.getFloat('v.c.kwh', 2);

    const { _startEnergyRecd, ...rest } = this.activeCharge;
    const record = {
      ...rest,
      endTime:     Date.now(),
      endSOC:      ovms.getFloat('v.b.soc', 1),
      energyAdded: energyMetric ?? (energyDelta > 0.01 ? parseFloat(energyDelta.toFixed(2)) : null),
      finalType:   ovms.get('v.c.type') ?? this.activeCharge.chgType,
    };
    this.activeCharge = null;
    const id = await this._add('charges', record);
    record.id = id;
    if (this.onChargeEnd) this.onChargeEnd(record);
    return record;
  }

  // --- Retrieval ---
  getTrips(limit = 100)   { return this._getAll('trips',   limit); }
  getCharges(limit = 100) { return this._getAll('charges', limit); }
  getTrip(id)             { return this._get('trips',   id); }
  getCharge(id)           { return this._get('charges', id); }
  deleteTrip(id)          { return this._delete('trips',   id); }
  deleteCharge(id)        { return this._delete('charges', id); }

  // --- CSV export ---
  exportTripCSV(trip) {
    const rows = ['time,lat,lon,speed_kmh,soc_pct,power_kw,batt_temp_c,amb_temp_c,cabin_temp_c'];
    for (const p of (trip.points || [])) {
      rows.push([
        new Date(p.t).toISOString(),
        p.lat ?? '', p.lon ?? '', p.speed ?? '', p.soc ?? '', p.power ?? '',
        p.battTemp ?? '', p.ambTemp ?? '', p.cabinTemp ?? '',
      ].join(','));
    }
    return rows.join('\n');
  }

  exportChargeCSV(charge) {
    const rows = ['time,soc_pct,power_kw,voltage_v,current_a,batt_temp_c'];
    for (const p of (charge.points || [])) {
      rows.push([
        new Date(p.t).toISOString(),
        p.soc ?? '', p.power ?? '', p.voltage ?? '', p.current ?? '', p.battTemp ?? '',
      ].join(','));
    }
    return rows.join('\n');
  }

  // --- DB helpers ---
  _add(store, record) {
    return new Promise((res, rej) => {
      const tx  = this.db.transaction(store, 'readwrite');
      const req = tx.objectStore(store).add(record);
      req.onsuccess = () => res(req.result);
      req.onerror   = e => rej(e.target.error);
    });
  }

  _getAll(store, limit) {
    return new Promise((res, rej) => {
      const tx  = this.db.transaction(store, 'readonly');
      const idx = tx.objectStore(store).index('startTime');
      const out = [];
      const req = idx.openCursor(null, 'prev'); // newest first
      req.onsuccess = e => {
        const c = e.target.result;
        if (c && out.length < limit) { out.push(c.value); c.continue(); }
        else res(out);
      };
      req.onerror = e => rej(e.target.error);
    });
  }

  _get(store, id) {
    return new Promise((res, rej) => {
      const req = this.db.transaction(store, 'readonly').objectStore(store).get(id);
      req.onsuccess = () => res(req.result);
      req.onerror   = e => rej(e.target.error);
    });
  }

  _delete(store, id) {
    return new Promise((res, rej) => {
      const req = this.db.transaction(store, 'readwrite').objectStore(store).delete(id);
      req.onsuccess = () => res();
      req.onerror   = e => rej(e.target.error);
    });
  }
}

// OVMS MQTT Service — direct WebSocket MQTT via mqtt.js

class OVMSService {
  constructor(config) {
    this.config = config;
    this.client = null;
    this.connected = false;
    this.metrics = {};
    this.listeners = {};
    this.topicPrefix = `ovms/${config.username}/${config.vin}/`;  // OVMS v3 format: ovms/EV88283/VIN/
    this._pendingCmds = {};               // cmdId -> { resolve, reject, timer }
  }

  on(event, fn) {
    this.listeners[event] = this.listeners[event] || [];
    this.listeners[event].push(fn);
  }

  emit(event, data) {
    (this.listeners[event] || []).forEach(fn => fn(data));
  }

  connect() {
    const opts = {
      clientId:        this.config.clientId,
      username:        this.config.username,
      password:        this.config.password,
      clean:           true,
      reconnectPeriod: 5000,
      connectTimeout:  15000,
    };

    this.emit('reconnecting');
    this.client = mqtt.connect(this.config.broker, opts);

    this.client.on('connect', () => {
      this.connected = true;
      this.emit('connected');
      this.client.subscribe(`${this.topicPrefix}metric/#`);
      this.client.subscribe(`${this.topicPrefix}event/#`);
      this.client.subscribe(`${this.topicPrefix}client/${this.config.clientId}/response/#`);
      this._startHeartbeat();
    });

    this.client.on('close',     () => { this.connected = false; this.emit('disconnected'); });
    this.client.on('reconnect', () => this.emit('reconnecting'));
    this.client.on('error',     e  => this.emit('error', e.message || String(e)));

    this.client.on('message', (topic, payload) => {
      const value = payload.toString();

      // Command response
      const respPrefix = `${this.topicPrefix}client/${this.config.clientId}/response/`;
      if (topic.startsWith(respPrefix)) {
        const cmdId   = topic.slice(respPrefix.length);
        const pending = this._pendingCmds[cmdId];
        if (pending) {
          clearTimeout(pending.timer);
          delete this._pendingCmds[cmdId];
          pending.resolve(value);
        }
        return;
      }

      // Metric
      const key = this._topicToMetric(topic);
      if (!key) return;
      this.metrics[key] = value;
      this.emit('metric', { key, value, topic });
      this.emit(`metric:${key}`, value);
    });
  }

  disconnect() {
    this._stopHeartbeat();
    if (this.client) this.client.end(true);
  }

  _startHeartbeat() {
    const topic = `${this.topicPrefix}/client/${this.config.clientId}/active`; // keepalive
    const ping = () => { if (this.connected) this.client.publish(topic, '1'); };
    ping();
    this._hb = setInterval(ping, 55000);
  }

  _stopHeartbeat() {
    if (this._hb) { clearInterval(this._hb); this._hb = null; }
  }

  _topicToMetric(topic) {
    const prefix = `${this.topicPrefix}metric/`;
    if (!topic.startsWith(prefix)) return null;
    return topic.slice(prefix.length).replace(/\//g, '.');
  }

  sendCommand(cmd, timeoutMs = 12000) {
    if (!this.connected) return Promise.reject(new Error('Not connected to car'));
    return new Promise((resolve, reject) => {
      const cmdId    = Date.now().toString();
      const cmdTopic = `${this.topicPrefix}client/${this.config.clientId}/command/${cmdId}`;
      const timer = setTimeout(() => {
        delete this._pendingCmds[cmdId];
        reject(new Error('Timeout — car did not respond'));
      }, timeoutMs);
      this._pendingCmds[cmdId] = { resolve, reject, timer };
      // Subscribe to specific response topic (already covered by wildcard, but be explicit)
      this.client.publish(cmdTopic, cmd);
    });
  }

  get(key)              { return this.metrics[key] ?? null; }
  getFloat(key, dec=1)  { const v=parseFloat(this.metrics[key]); return isNaN(v)?null:parseFloat(v.toFixed(dec)); }
  getBool(key)          { const v=this.metrics[key]; if(v==null)return null; return v==='1'||v==='yes'||v==='true'; }
}

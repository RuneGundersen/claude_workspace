// OVMS MQTT Service — direct WebSocket MQTT via mqtt.js

class OVMSService {
  constructor(config) {
    this.config = config;
    this.client = null;
    this.connected = false;
    this.metrics = {};
    this.listeners = {};
    this.topicPrefix = config.vehicleId;  // OVMS v2 format: EV88283metric/...
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
      this._startHeartbeat();
    });

    this.client.on('close',     () => { this.connected = false; this.emit('disconnected'); });
    this.client.on('reconnect', () => this.emit('reconnecting'));
    this.client.on('error',     e  => this.emit('error', e.message || String(e)));

    this.client.on('message', (topic, payload) => {
      const value = payload.toString();
      const key   = this._topicToMetric(topic);
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

  get(key)              { return this.metrics[key] ?? null; }
  getFloat(key, dec=1)  { const v=parseFloat(this.metrics[key]); return isNaN(v)?null:parseFloat(v.toFixed(dec)); }
  getBool(key)          { const v=this.metrics[key]; if(v==null)return null; return v==='1'||v==='yes'||v==='true'; }
}

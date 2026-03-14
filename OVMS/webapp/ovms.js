// OVMS MQTT Service
// Handles connection to OVMS broker and metric subscriptions

class OVMSService {
  constructor(config) {
    this.config = config;
    this.client = null;
    this.connected = false;
    this.metrics = {};
    this.listeners = {};
    this.heartbeatInterval = null;
    this.topicPrefix = `ovms/${config.username}/${config.vehicleId}`;
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
      clientId:  this.config.clientId,
      username:  this.config.username,
      password:  this.config.password,
      clean:     true,
      reconnectPeriod: 5000,
      connectTimeout:  10000,
    };

    this.client = mqtt.connect(this.config.broker, opts);

    this.client.on('connect', () => {
      this.connected = true;
      this.emit('connected');
      this._subscribe();
      this._startHeartbeat();
    });

    this.client.on('disconnect', () => {
      this.connected = false;
      this.emit('disconnected');
      this._stopHeartbeat();
    });

    this.client.on('reconnect', () => this.emit('reconnecting'));

    this.client.on('error', err => this.emit('error', err.message));

    this.client.on('message', (topic, payload) => {
      const value = payload.toString();
      const metricKey = this._topicToMetric(topic);
      if (metricKey) {
        this.metrics[metricKey] = value;
        this.emit('metric', { key: metricKey, value, topic });
        this.emit(`metric:${metricKey}`, value);
      }
    });
  }

  disconnect() {
    this._stopHeartbeat();
    if (this.client) this.client.end();
  }

  _subscribe() {
    const prefix = this.topicPrefix;
    // Subscribe to all metrics
    this.client.subscribe(`${prefix}/metric/#`);
    // Subscribe to notifications
    this.client.subscribe(`${prefix}/notify/#`);
  }

  _startHeartbeat() {
    // OVMS requires a heartbeat every ~60s to keep client alive
    const prefix = this.topicPrefix;
    const clientTopic = `${prefix}/client/${this.config.clientId}/active`;
    const ping = () => this.client.publish(clientTopic, '1', { retain: false });
    ping();
    this.heartbeatInterval = setInterval(ping, 55000);
  }

  _stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  // Convert MQTT topic back to metric key (slashes → dots)
  // ovms/user/vehicle/metric/v/b/soc → v.b.soc
  _topicToMetric(topic) {
    const prefix = `${this.topicPrefix}/metric/`;
    if (!topic.startsWith(prefix)) return null;
    return topic.slice(prefix.length).replace(/\//g, '.');
  }

  get(key) {
    return this.metrics[key] ?? null;
  }

  getFloat(key, decimals = 1) {
    const v = parseFloat(this.metrics[key]);
    return isNaN(v) ? null : parseFloat(v.toFixed(decimals));
  }

  getBool(key) {
    const v = this.metrics[key];
    if (v === null || v === undefined) return null;
    return v === '1' || v === 'yes' || v === 'true';
  }
}

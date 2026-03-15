// OVMS Shell — send commands via MQTT and display responses

class OVMSShell {
  constructor(ovmsService) {
    this.ovms    = ovmsService;
    this.output  = document.getElementById('shellOutput');
    this.input   = document.getElementById('shellInput');
    this.sendBtn = document.getElementById('shellSend');
    this.history = [];
    this.histIdx = -1;

    this.sendBtn.addEventListener('click', () => this._send());
    this.input.addEventListener('keydown', e => {
      if (e.key === 'Enter')     { this._send(); return; }
      if (e.key === 'ArrowUp')   { this._histNav(1); e.preventDefault(); return; }
      if (e.key === 'ArrowDown') { this._histNav(-1); e.preventDefault(); return; }
    });

    this._print('OVMS Shell — skriv en kommando og trykk Enter', 'info');
    this._print('Tips: prøv  network status  eller  ota status', 'info');
    this._print('', '');
  }

  _print(text, type) {
    const line = document.createElement('div');
    line.textContent = text;
    line.style.color = type === 'cmd'   ? '#7ec8e3'
                     : type === 'error' ? '#f87171'
                     : type === 'info'  ? '#888'
                     : '#d4d4d4';
    this.output.appendChild(line);
    this.output.scrollTop = this.output.scrollHeight;
  }

  _send() {
    const cmd = this.input.value.trim();
    if (!cmd) return;

    this.input.value = '';
    this.history.unshift(cmd);
    this.histIdx = -1;

    this._print('> ' + cmd, 'cmd');

    if (!this.ovms.connected) {
      this._print('Ikke tilkoblet — venter på MQTT-tilkobling', 'error');
      return;
    }

    this.sendBtn.disabled = true;
    this.input.disabled   = true;

    this.ovms.sendCommand(cmd, 15000)
      .then(response => {
        response.split('\n').forEach(line => this._print(line, 'out'));
      })
      .catch(err => {
        this._print('Feil: ' + err.message, 'error');
      })
      .finally(() => {
        this.sendBtn.disabled = false;
        this.input.disabled   = false;
        this.input.focus();
        this._print('', '');
      });
  }

  _histNav(dir) {
    const newIdx = this.histIdx + dir;
    if (newIdx < -1 || newIdx >= this.history.length) return;
    this.histIdx = newIdx;
    this.input.value = this.histIdx === -1 ? '' : this.history[this.histIdx];
    // move cursor to end
    const len = this.input.value.length;
    this.input.setSelectionRange(len, len);
  }
}

// Initialised in app.js after ovmsService is ready

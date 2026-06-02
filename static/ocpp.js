// ─── State ───────────────────────────────────────────────────────────────────
const MAX_MESSAGES = 1000;
let allMessages = [];
let filteredMessages = [];
let paused = false;
let pendingMessages = [];
let sseSource = null;

// Rate tracking
let recentTimestamps = [];

// ─── Event type classification ────────────────────────────────────────────────
function classifyType(type) {
  if (!type) return { css: 'type-boot', label: type || 'unknown', dir: 'from' };

  const toCharger = type.startsWith('ops.') || type.startsWith('remote.');
  const dir = toCharger ? 'to' : 'from';

  let css = 'type-boot';
  const t = type.toLowerCase();
  if (t.includes('boot') || t.includes('heartbeat')) css = 'type-boot';
  else if (t.includes('online')) css = 'type-boot';
  else if (t.includes('offline')) css = 'type-error';
  else if (t.includes('status')) css = 'type-status';
  else if (t.includes('meter')) css = 'type-meter';
  else if (t.includes('start')) css = 'type-start';
  else if (t.includes('stop') || t.includes('cdr')) css = 'type-stop';
  else if (t.includes('auth')) css = 'type-auth';
  else if (t.includes('alert') || t.includes('error')) css = 'type-error';
  else if (t.includes('pki') || t.includes('cert')) css = 'type-pki';

  return { css, label: type, dir };
}

function getDirection(evt) {
  if (evt.direction) return evt.direction;
  const { dir } = classifyType(evt.type);
  return dir;
}

function highlightJSON(obj) {
  const str = JSON.stringify(obj, null, 2);
  return str
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function(match) {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) return '<span class="json-key">' + match + '</span>';
        return '<span class="json-str">' + match + '</span>';
      }
      if (/true|false/.test(match)) return '<span class="json-bool">' + match + '</span>';
      if (/null/.test(match)) return '<span class="json-null">' + match + '</span>';
      return '<span class="json-num">' + match + '</span>';
    });
}

function fmtTime(ts) {
  if (!ts) return '--:--:--.---';
  const d = new Date(ts);
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  const ms = String(d.getMilliseconds()).padStart(3, '0');
  return `${h}:${m}:${s}.${ms}`;
}

function humanizeType(type) {
  const map = {
    'charger.boot': 'Boot',
    'charger.online': 'Online',
    'charger.offline': 'Offline',
    'charger.status': 'Status',
    'charger.heartbeat': 'Heartbeat',
    'session.start': 'Session started',
    'session.stop': 'Session stopped',
    'session.meter': 'Meter values',
    'session.cdr': 'Session summary',
    'auth.result': 'Authorization',
    'ops.alert': 'Alert',
    'BootNotification': 'Boot',
    'Heartbeat': 'Heartbeat',
    'StatusNotification': 'Status',
    'MeterValues': 'Meter values',
    'StartTransaction': 'Session started',
    'StopTransaction': 'Session stopped',
    'Authorize': 'Authorization',
    'RemoteStartTransaction': 'Remote start',
    'RemoteStopTransaction': 'Remote stop',
    'Reset': 'Reset',
    'FirmwareStatusNotification': 'Firmware',
  };
  return map[type] || type || 'Unknown';
}

function formatValue(v, suffix = '') {
  if (v === null || v === undefined || v === '') return null;
  return `${v}${suffix}`;
}

function summarizeEvent(evt) {
  const data = evt.data || {};
  const type = evt.type || '';

  if (type.includes('heartbeat') || type === 'Heartbeat') {
    return 'Heartbeat received';
  }

  if (type.includes('boot') || type === 'BootNotification') {
    const vendor = data.chargePointVendor || data.vendor || data.vendor_name;
    const model = data.chargePointModel || data.model || data.model_name;
    return [vendor, model].filter(Boolean).join(' ') || 'Charger booted';
  }

  if (type.includes('status') || type === 'StatusNotification') {
    const status = data.status || data.connector_status;
    const connector = data.connectorId ?? data.connector_id;
    const error = data.errorCode || data.error_code;
    const parts = [];
    if (status) parts.push(status);
    if (connector !== undefined && connector !== null) parts.push(`connector ${connector}`);
    if (error && error !== 'NoError') parts.push(error);
    return parts.join(' • ') || 'Status updated';
  }

  if (type.includes('meter') || type === 'MeterValues') {
    const power = data.power_kw ?? data.power;
    const energy = data.energy_wh ?? data.energy_wh;
    const soc = data.soc ?? data.state_of_charge;
    const parts = [];
    if (power !== undefined) parts.push(`${Number(power).toFixed(1)} kW`);
    if (energy !== undefined) parts.push(`${Math.round(Number(energy))} Wh`);
    if (soc !== undefined) parts.push(`${soc}% SoC`);
    return parts.join(' • ') || 'Meter update';
  }

  if (type.includes('start') || type === 'StartTransaction') {
    const connector = data.connectorId ?? data.connector_id;
    const idTag = data.idTag || data.id_tag;
    const tx = data.transactionId || data.transaction_id;
    const parts = ['Charging started'];
    if (connector !== undefined) parts.push(`connector ${connector}`);
    if (idTag) parts.push(idTag);
    if (tx) parts.push(`tx ${tx}`);
    return parts.join(' • ');
  }

  if (type.includes('stop') || type === 'StopTransaction') {
    const reason = data.reason;
    const tx = data.transactionId || data.transaction_id;
    const parts = ['Charging stopped'];
    if (reason) parts.push(reason);
    if (tx) parts.push(`tx ${tx}`);
    return parts.join(' • ');
  }

  if (type.includes('auth') || type === 'Authorize') {
    const status = data.status || data.idTagInfo?.status;
    const tag = data.idTag || data.id_tag;
    const parts = [];
    if (status) parts.push(status);
    if (tag) parts.push(tag);
    return parts.join(' • ') || 'Authorization checked';
  }

  if (type.includes('remote.start')) return 'Remote start command sent';
  if (type.includes('remote.stop')) return 'Remote stop command sent';
  if (type.includes('reset') || type === 'Reset') return 'Reset command';

  const entries = Object.entries(data).slice(0, 3).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`);
  return entries.join(' • ') || 'Event received';
}

function renderRow(evt, idx) {
  const { css } = classifyType(evt.type);
  const dir = getDirection(evt);
  const dirArrow = dir === 'to' ? '→' : '←';
  const dirClass = dir === 'to' ? 'msg-dir-to' : 'msg-dir-from';
  const cp = evt.charge_point || '';
  const cpShort = cp.startsWith('FARM-ENC-DCL120B-16-') ? cp.replace('FARM-ENC-DCL120B-16-', 'Farm #') : cp;
  const typeLabel = humanizeType(evt.type);
  const preview = summarizeEvent(evt);
  const cpLink = cp ? `<a href="/remote/${encodeURIComponent(cp)}" onclick="event.stopPropagation()">${escapeHtml(cpShort)}</a>` : '—';

  return `<div class="msg-row" onclick="showDetail(${idx})" data-idx="${idx}">
    <span class="msg-ts">${fmtTime(evt.timestamp)}</span>
    <span class="msg-dir ${dirClass}">${dirArrow}</span>
    <span class="msg-cp" title="${escapeHtml(cp)}">${cpLink}</span>
    <span class="msg-type ${css}">${escapeHtml(typeLabel)}</span>
    <span class="msg-preview">${escapeHtml(preview)}</span>
  </div>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function renderLog() {
  const log = document.getElementById('msg-log');
  const empty = document.getElementById('msg-empty');

  if (filteredMessages.length === 0) {
    log.innerHTML = '';
    empty.style.display = 'block';
    log.appendChild(empty);
    empty.textContent = allMessages.length === 0 ? 'Waiting for events…' : 'No messages match current filters.';
    return;
  }

  empty.style.display = 'none';
  const frag = document.createDocumentFragment();
  const tmp = document.createElement('div');
  tmp.innerHTML = filteredMessages.map((evt, i) => renderRow(evt, allMessages.indexOf(evt))).join('');
  while (tmp.firstChild) frag.appendChild(tmp.firstChild);
  log.innerHTML = '';
  log.appendChild(frag);

  if (document.getElementById('auto-scroll').checked) log.scrollTop = log.scrollHeight;
  updateCounters();
}

function appendRow(evt) {
  const log = document.getElementById('msg-log');
  const empty = document.getElementById('msg-empty');
  if (empty.style.display !== 'none') empty.style.display = 'none';
  const idx = allMessages.indexOf(evt);
  const div = document.createElement('div');
  div.innerHTML = renderRow(evt, idx);
  log.appendChild(div.firstElementChild);
  if (document.getElementById('auto-scroll').checked) log.scrollTop = log.scrollHeight;
  while (log.children.length > MAX_MESSAGES) log.removeChild(log.firstChild);
}

function addMessage(evt) {
  allMessages.push(evt);
  if (allMessages.length > MAX_MESSAGES) allMessages.shift();
  const now = Date.now();
  recentTimestamps.push(now);
  recentTimestamps = recentTimestamps.filter(t => now - t < 5000);
  if (paused) {
    pendingMessages.push(evt);
    updateCounters();
    return;
  }
  if (passesFilter(evt)) {
    filteredMessages.push(evt);
    if (filteredMessages.length > MAX_MESSAGES) filteredMessages.shift();
    appendRow(evt);
    updateCounters();
  }
}

function passesFilter(evt) {
  const cpFilter = document.getElementById('filter-charger').value;
  const typeFilter = document.getElementById('filter-type').value;
  const dirFilter = document.getElementById('filter-direction').value;
  const searchFilter = document.getElementById('filter-search').value.trim().toLowerCase();
  if (cpFilter && evt.charge_point !== cpFilter) return false;
  if (typeFilter && evt.type !== typeFilter) return false;
  if (dirFilter) {
    const dir = getDirection(evt);
    if (dirFilter === 'from' && dir !== 'from') return false;
    if (dirFilter === 'to' && dir !== 'to') return false;
  }
  if (searchFilter) {
    const payload = JSON.stringify(evt).toLowerCase();
    if (!payload.includes(searchFilter)) return false;
  }
  return true;
}

function applyFilters() {
  filteredMessages = allMessages.filter(passesFilter);
  renderLog();
}

function updateCounters() {
  const total = allMessages.length;
  const rate = (recentTimestamps.length / 5).toFixed(1);
  document.getElementById('msg-counter').textContent = `${total.toLocaleString()} events`;
  document.getElementById('msg-rate').textContent = `${rate} /sec`;
  const shown = filteredMessages.length;
  const fc = document.getElementById('filter-count');
  fc.textContent = shown !== total ? `${shown.toLocaleString()} shown` : '';
  if (paused && pendingMessages.length > 0) {
    document.getElementById('btn-pause').textContent = `Resume (${pendingMessages.length})`;
  }
}

function togglePause() {
  paused = !paused;
  const btn = document.getElementById('btn-pause');
  if (paused) {
    btn.textContent = 'Resume (0)';
    btn.style.color = '#eab308';
    btn.style.borderColor = '#78350f';
  } else {
    btn.textContent = 'Pause';
    btn.style.color = '#c0cdd8';
    btn.style.borderColor = '#1e3450';
    pendingMessages.forEach(e => {
      if (passesFilter(e)) {
        filteredMessages.push(e);
        appendRow(e);
      }
    });
    pendingMessages = [];
    updateCounters();
  }
}

function clearLog() {
  allMessages = [];
  filteredMessages = [];
  pendingMessages = [];
  recentTimestamps = [];
  const log = document.getElementById('msg-log');
  log.innerHTML = '';
  const empty = document.getElementById('msg-empty');
  empty.textContent = 'Cleared. Waiting for new events…';
  empty.style.display = 'block';
  log.appendChild(empty);
  updateCounters();
}

function exportMessages() {
  const data = JSON.stringify(filteredMessages, null, 2);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `ocpp-messages-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

let detailEvt = null;
function showDetail(idx) {
  const evt = allMessages[idx];
  if (!evt) return;
  detailEvt = evt;
  document.getElementById('detail-title').textContent = humanizeType(evt.type || 'unknown');
  document.getElementById('detail-cp').textContent = evt.charge_point || '';
  const dir = getDirection(evt);
  const dirLabel = dir === 'to' ? '→ To charger' : '← From charger';
  const ts = evt.timestamp ? new Date(evt.timestamp).toLocaleString() : '—';
  const meta = [
    `Time: ${ts}`,
    `Direction: ${dirLabel}`,
    evt.event_id ? `Event ID: ${evt.event_id}` : null,
    evt.session_id ? `Session: ${evt.session_id}` : null,
    evt.connector != null && evt.connector !== '' ? `Connector: ${evt.connector}` : null,
    evt.simulated ? 'Simulated: true' : null,
  ].filter(Boolean).join('   |   ');
  document.getElementById('detail-meta').textContent = meta;
  document.getElementById('detail-json').innerHTML = highlightJSON(evt);
  document.getElementById('detail-panel').style.display = 'flex';
  document.getElementById('detail-backdrop').style.display = 'block';
}

function closeDetail() {
  document.getElementById('detail-panel').style.display = 'none';
  document.getElementById('detail-backdrop').style.display = 'none';
  detailEvt = null;
}

function copyDetail() {
  if (!detailEvt) return;
  navigator.clipboard.writeText(JSON.stringify(detailEvt, null, 2)).then(() => {
    const btn = document.getElementById('btn-copy');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
  });
}

async function loadHistory() {
  try {
    const resp = await fetch('/partials/ocpp-messages?limit=200');
    const data = await resp.json();
    const events = (data.events || []).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    events.forEach(addMessage);
    if (events.length === 0) document.getElementById('msg-empty').textContent = 'No historical events found. Waiting for live events…';
  } catch (e) {
    console.warn('Failed to load history:', e);
  }
}

function connectSSE() {
  const url = '/api/events/stream';
  if (sseSource) sseSource.close();
  sseSource = new EventSource(url);
  const statusEl = document.getElementById('conn-status');
  sseSource.onopen = () => {
    statusEl.textContent = '● Connected';
    statusEl.style.color = '#84BD00';
  };
  sseSource.onerror = () => {
    statusEl.textContent = '● Disconnected';
    statusEl.style.color = '#ef4444';
    sseSource.close();
    setTimeout(connectSSE, 4000);
  };
  sseSource.onmessage = (e) => { try { addMessage(JSON.parse(e.data)); } catch {} };
  const eventTypes = [
    'charger.boot', 'charger.online', 'charger.offline', 'charger.status', 'charger.heartbeat',
    'session.start', 'session.meter', 'session.stop', 'session.cdr',
    'auth.result', 'pki.cert.issued', 'ops.alert',
    'BootNotification', 'Heartbeat', 'StatusNotification', 'MeterValues',
    'StartTransaction', 'StopTransaction', 'Authorize',
    'RemoteStartTransaction', 'RemoteStopTransaction', 'Reset',
    'TriggerMessage', 'DataTransfer', 'FirmwareStatusNotification',
  ];
  eventTypes.forEach(type => {
    sseSource.addEventListener(type, (e) => { try { addMessage(JSON.parse(e.data)); } catch {} });
  });
}

loadHistory().then(() => { connectSSE(); });

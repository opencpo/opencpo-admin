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

  // Direction heuristic: ops/remote commands go TO the charger; everything else FROM
  const toCharger = type.startsWith('ops.') || type.startsWith('remote.');
  const dir = toCharger ? 'to' : 'from';

  let css = 'type-boot';
  const t = type.toLowerCase();
  if (t.includes('boot') || t.includes('heartbeat'))          css = 'type-boot';
  else if (t.includes('online'))                               css = 'type-boot';
  else if (t.includes('offline'))                              css = 'type-error';
  else if (t.includes('status'))                               css = 'type-status';
  else if (t.includes('meter'))                                css = 'type-meter';
  else if (t.includes('start'))                                css = 'type-start';
  else if (t.includes('stop') || t.includes('cdr'))           css = 'type-stop';
  else if (t.includes('auth'))                                 css = 'type-auth';
  else if (t.includes('alert') || t.includes('error'))        css = 'type-error';
  else if (t.includes('pki') || t.includes('cert'))           css = 'type-pki';

  return { css, label: type, dir };
}

// ─── Direction from event (override via classify) ─────────────────────────────
function getDirection(evt) {
  // Use direction field if present (from ocpp_messages table data)
  if (evt.direction) return evt.direction; // 'inbound' | 'outbound'
  // Infer from event type
  const { dir } = classifyType(evt.type);
  return dir;
}

// ─── JSON syntax highlighting ─────────────────────────────────────────────────
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

// ─── Timestamp formatting ─────────────────────────────────────────────────────
function fmtTime(ts) {
  if (!ts) return '--:--:--.---';
  const d = new Date(ts);
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  const ms = String(d.getMilliseconds()).padStart(3, '0');
  return `${h}:${m}:${s}.${ms}`;
}

// ─── Render a single message row ──────────────────────────────────────────────
function renderRow(evt, idx) {
  const { css, label } = classifyType(evt.type);
  const dir = getDirection(evt);
  const dirArrow = dir === 'to' ? '→' : '←';
  const dirClass = dir === 'to' ? 'msg-dir-to' : 'msg-dir-from';
  const cp = evt.charge_point || '';

  // Build preview from data
  const data = evt.data || {};
  const dataStr = JSON.stringify(data);
  const preview = dataStr.length > 85
    ? dataStr.slice(0, 85).replace(/[{,]$/, '') + '…'
    : dataStr;

  const cpLink = cp ? `<a href="/remote/${encodeURIComponent(cp)}" onclick="event.stopPropagation()">${cp}</a>` : '—';

  return `<div class="msg-row" onclick="showDetail(${idx})" data-idx="${idx}">
    <span class="msg-ts">${fmtTime(evt.timestamp)}</span>
    <span class="msg-dir ${dirClass}">${dirArrow}</span>
    <span class="msg-cp" title="${cp}">${cpLink}</span>
    <span class="msg-type ${css}">${label}</span>
    <span class="msg-preview">${escapeHtml(preview)}</span>
  </div>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ─── Render the full filtered list ───────────────────────────────────────────
function renderLog() {
  const log = document.getElementById('msg-log');
  const empty = document.getElementById('msg-empty');

  if (filteredMessages.length === 0) {
    log.innerHTML = '';
    empty.style.display = 'block';
    log.appendChild(empty);
    empty.textContent = allMessages.length === 0
      ? 'Waiting for events…'
      : 'No messages match current filters.';
    return;
  }

  empty.style.display = 'none';

  // Re-render only — batch as fragment
  const frag = document.createDocumentFragment();
  const tmp = document.createElement('div');
  tmp.innerHTML = filteredMessages.map((evt, i) => renderRow(evt, allMessages.indexOf(evt))).join('');
  while (tmp.firstChild) frag.appendChild(tmp.firstChild);

  log.innerHTML = '';
  log.appendChild(frag);

  if (document.getElementById('auto-scroll').checked) {
    log.scrollTop = log.scrollHeight;
  }

  updateCounters();
}

// ─── Append a single new row (efficient for live stream) ─────────────────────
function appendRow(evt) {
  const log = document.getElementById('msg-log');
  const empty = document.getElementById('msg-empty');

  if (empty.style.display !== 'none') {
    empty.style.display = 'none';
  }

  const idx = allMessages.indexOf(evt);
  const div = document.createElement('div');
  div.innerHTML = renderRow(evt, idx);
  const row = div.firstElementChild;
  log.appendChild(row);

  if (document.getElementById('auto-scroll').checked) {
    log.scrollTop = log.scrollHeight;
  }

  // Trim rendered rows if too many
  while (log.children.length > MAX_MESSAGES) {
    log.removeChild(log.firstChild);
  }
}

// ─── Add message to buffer ────────────────────────────────────────────────────
function addMessage(evt) {
  allMessages.push(evt);
  if (allMessages.length > MAX_MESSAGES) allMessages.shift();

  // Rate tracking
  const now = Date.now();
  recentTimestamps.push(now);
  recentTimestamps = recentTimestamps.filter(t => now - t < 5000);

  if (paused) {
    pendingMessages.push(evt);
    updateCounters();
    return;
  }

  // Check if this event passes current filters
  if (passesFilter(evt)) {
    filteredMessages.push(evt);
    if (filteredMessages.length > MAX_MESSAGES) filteredMessages.shift();
    appendRow(evt);
    updateCounters();
  }
}

// ─── Filter logic ─────────────────────────────────────────────────────────────
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

// ─── Counters ─────────────────────────────────────────────────────────────────
function updateCounters() {
  const total = allMessages.length;
  const rate = (recentTimestamps.length / 5).toFixed(1);
  document.getElementById('msg-counter').textContent = `${total.toLocaleString()} events`;
  document.getElementById('msg-rate').textContent = `${rate} /sec`;

  const shown = filteredMessages.length;
  const fc = document.getElementById('filter-count');
  if (shown !== total) {
    fc.textContent = `${shown.toLocaleString()} shown`;
  } else {
    fc.textContent = '';
  }

  if (paused && pendingMessages.length > 0) {
    document.getElementById('btn-pause').textContent = `Resume (${pendingMessages.length})`;
  }
}

// ─── Pause / Resume ───────────────────────────────────────────────────────────
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
    // Flush pending
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

// ─── Clear ────────────────────────────────────────────────────────────────────
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

// ─── Export ───────────────────────────────────────────────────────────────────
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

// ─── Detail panel ─────────────────────────────────────────────────────────────
let detailEvt = null;

function showDetail(idx) {
  const evt = allMessages[idx];
  if (!evt) return;
  detailEvt = evt;

  document.getElementById('detail-title').textContent = evt.type || 'unknown';
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

// ─── Load historical events ───────────────────────────────────────────────────
async function loadHistory() {
  try {
    const resp = await fetch('/partials/ocpp-messages?limit=200');
    const data = await resp.json();
    const events = (data.events || []).sort((a, b) =>
      new Date(a.timestamp) - new Date(b.timestamp)
    );
    events.forEach(addMessage);
    if (events.length === 0) {
      document.getElementById('msg-empty').textContent = 'No historical events found. Waiting for live events…';
    }
  } catch (e) {
    console.warn('Failed to load history:', e);
  }
}

// ─── SSE connection ───────────────────────────────────────────────────────────
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

  // Generic message handler
  sseSource.onmessage = (e) => {
    try { addMessage(JSON.parse(e.data)); } catch {}
  };

  // Listen for both old event-bus types and raw OCPP action names
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
    sseSource.addEventListener(type, (e) => {
      try { addMessage(JSON.parse(e.data)); } catch {}
    });
  });
}

// ─── Boot ─────────────────────────────────────────────────────────────────────
loadHistory().then(() => {
  connectSSE();
});

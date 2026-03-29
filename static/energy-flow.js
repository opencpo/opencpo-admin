/**
 * OpenCPO Energy Flow Diagram — Shared Component
 * initEnergyFlow(containerId, dataUrl, options)
 *
 * options: {
 *   pollInterval: 3000,      // ms between polls
 *   showPhaseTable: false,   // show per-phase data table
 *   showDetailCards: false,  // show detail cards below diagram
 *   gridLimitKw: 86,         // grid connection limit for utilization bar
 * }
 *
 * Data format (EMS API):
 *   grid_kw, solar_kw, battery_power_w, inverter_power_w,
 *   ess_soc_pct, ev_total_kw, building_kw, ems_mode,
 *   ems_control_reason, battery_state, battery_voltage_v,
 *   battery_temp_c, frequency_hz, grid_limit_kw, available_kw,
 *   profiles[], chint_v_a/b/c, chint_i_a/b/c, fresh
 *
 * Also accepts client-portal format:
 *   charging_kw (= ev_total_kw), battery_kw (= battery_power_w/1000),
 *   battery_soc (= ess_soc_pct), active_sessions, today_kwh
 */

(function () {
  'use strict';

  // ── SVG markup ─────────────────────────────────────────────────────────

  function buildSVG(id) {
    return `
<style>
  @keyframes emsDashFwd-${id} { to { stroke-dashoffset: -24; } }
  @keyframes emsDashRev-${id} { to { stroke-dashoffset: 24; } }
  .fl-fwd-${id} { animation: emsDashFwd-${id} 1.2s linear infinite; }
  .fl-rev-${id} { animation: emsDashRev-${id} 1.2s linear infinite; }
</style>
<svg id="flow-svg-${id}" viewBox="0 0 920 430" style="width:100%;display:block;">
  <defs>
    <filter id="glow-${id}" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3"/>
    </filter>
  </defs>

  <!-- Flow lines -->
  <path id="fl-grid-${id}"  d="M 130,215 L 320,215"
    stroke="#1e3a5f" stroke-width="2" fill="none" stroke-dasharray="4,8" stroke-linecap="round" opacity="0.35"/>
  <path id="fl-solar-${id}" d="M 460,100 L 460,175"
    stroke="#1e3a5f" stroke-width="2" fill="none" stroke-dasharray="4,8" stroke-linecap="round" opacity="0.35"/>
  <path id="fl-batt-${id}"  d="M 460,255 L 460,325"
    stroke="#1e3a5f" stroke-width="2" fill="none" stroke-dasharray="4,8" stroke-linecap="round" opacity="0.35"/>
  <path id="fl-bld-${id}"   d="M 600,200 L 720,200 Q 755,200 755,165 L 755,110"
    stroke="#1e3a5f" stroke-width="2" fill="none" stroke-dasharray="4,8" stroke-linecap="round" opacity="0.35"/>
  <path id="fl-ev-${id}"    d="M 600,235 L 720,235 Q 755,235 755,270 L 755,325"
    stroke="#1e3a5f" stroke-width="2" fill="none" stroke-dasharray="4,8" stroke-linecap="round" opacity="0.35"/>

  <!-- Dots (JS-driven via rAF — no animateMotion) -->
  <circle id="dot-grid-${id}"  r="4" cx="130" cy="215" fill="#10b981" opacity="0" filter="url(#glow-${id})"/>
  <circle id="dot-grid2-${id}" r="4" cx="225" cy="215" fill="#10b981" opacity="0" filter="url(#glow-${id})"/>
  <circle id="dot-solar-${id}" r="4" cx="460" cy="100" fill="#fbbf24" opacity="0" filter="url(#glow-${id})"/>
  <circle id="dot-batt-${id}"  r="4" cx="460" cy="255" fill="#10b981" opacity="0" filter="url(#glow-${id})"/>
  <circle id="dot-bld-${id}"   r="4" cx="600" cy="200" fill="#94a3b8" opacity="0" filter="url(#glow-${id})"/>
  <circle id="dot-ev-${id}"    r="4" cx="600" cy="235" fill="#00B0E4"  opacity="0" filter="url(#glow-${id})"/>

  <!-- ── Node: Grid ── -->
  <rect x="15" y="170" width="115" height="90" rx="10" fill="#0d2137" stroke="#1a3a5c"/>
  <text x="72" y="193" text-anchor="middle" fill="#64748b"
    font-size="9" font-family="monospace" font-weight="700">GRID</text>
  <text id="fv-grid-${id}" x="72" y="225" text-anchor="middle" fill="#10b981"
    font-size="20" font-family="monospace" font-weight="800">0,0 kW</text>
  <text id="fv-grid-dir-${id}" x="72" y="246" text-anchor="middle" fill="#64748b"
    font-size="10" font-family="monospace">import</text>

  <!-- ── Node: Inverter / Hub (center) ── -->
  <rect x="328" y="175" width="264" height="80" rx="10" fill="#0d2137" stroke="#00B0E4" stroke-opacity="0.5"/>
  <text x="460" y="200" text-anchor="middle" fill="#00B0E4"
    font-size="9" font-family="monospace" font-weight="700">INVERTER</text>
  <text id="fv-inv-${id}"  x="400" y="232" text-anchor="middle" fill="#e2e8f0"
    font-size="18" font-family="monospace" font-weight="700">0 W</text>
  <text id="fv-mode-${id}" x="536" y="232" text-anchor="middle" fill="#10b981"
    font-size="11" font-family="monospace" font-weight="600">—</text>

  <!-- ── Node: Solar ── -->
  <rect x="400" y="15" width="120" height="82" rx="10" fill="#0d2137" stroke="#1a3a5c"/>
  <text x="460" y="40" text-anchor="middle" fill="#64748b"
    font-size="9" font-family="monospace" font-weight="700">SOLAR</text>
  <text id="fv-solar-${id}" x="460" y="74" text-anchor="middle" fill="#64748b"
    font-size="22" font-family="monospace" font-weight="800">0,0 kW</text>

  <!-- ── Node: Battery ── -->
  <rect x="378" y="325" width="164" height="92" rx="10" fill="#0d2137" stroke="#1a3a5c"/>
  <text x="460" y="350" text-anchor="middle" fill="#64748b"
    font-size="9" font-family="monospace" font-weight="700">BATTERY · 140 kWh</text>
  <text id="fv-batt-${id}" x="460" y="383" text-anchor="middle" fill="#8b5cf6"
    font-size="20" font-family="monospace" font-weight="800">— kW</text>
  <text id="fv-soc-${id}"  x="460" y="404" text-anchor="middle" fill="#8b5cf6"
    font-size="12" font-family="monospace">—%</text>

  <!-- ── Node: Building ── -->
  <rect x="692" y="22" width="120" height="82" rx="10" fill="#0d2137" stroke="#1a3a5c"/>
  <text x="752" y="47" text-anchor="middle" fill="#64748b"
    font-size="9" font-family="monospace" font-weight="700">BUILDING</text>
  <text id="fv-bld-${id}" x="752" y="81" text-anchor="middle" fill="#94a3b8"
    font-size="22" font-family="monospace" font-weight="800">0,0 kW</text>

  <!-- ── Node: EV Chargers ── -->
  <rect x="692" y="325" width="120" height="82" rx="10" fill="#0d2137" stroke="#1a3a5c"/>
  <text x="752" y="350" text-anchor="middle" fill="#64748b"
    font-size="9" font-family="monospace" font-weight="700">CHARGERS</text>
  <text id="fv-ev-${id}" x="752" y="384" text-anchor="middle" fill="#64748b"
    font-size="22" font-family="monospace" font-weight="800">0,0 kW</text>
</svg>`;
  }

  // ── Normalize incoming data ─────────────────────────────────────────────

  function normalize(raw) {
    if (!raw || typeof raw !== 'object') return null;
    // Support both EMS format and client-portal format
    return {
      grid_kw:         typeof raw.grid_kw === 'number' ? raw.grid_kw : 0,
      solar_kw:        typeof raw.solar_kw === 'number' ? raw.solar_kw : 0,
      // battery_power_w (EMS) OR battery_kw*1000 (portal)
      battery_power_w: typeof raw.battery_power_w === 'number' ? raw.battery_power_w
                     : typeof raw.battery_kw === 'number' ? raw.battery_kw * 1000 : 0,
      inverter_power_w: typeof raw.inverter_power_w === 'number' ? raw.inverter_power_w : 0,
      // ess_soc_pct (EMS) OR battery_soc (portal)
      ess_soc_pct:     raw.ess_soc_pct != null ? raw.ess_soc_pct
                     : raw.battery_soc != null ? raw.battery_soc : null,
      // ev_total_kw (EMS) OR charging_kw (portal)
      ev_total_kw:     typeof raw.ev_total_kw === 'number' ? raw.ev_total_kw
                     : typeof raw.charging_kw === 'number' ? raw.charging_kw : 0,
      building_kw:     typeof raw.building_kw === 'number' ? raw.building_kw : 0,
      ems_mode:        raw.ems_mode || null,
      ems_control_reason: raw.ems_control_reason || '',
      battery_state:   raw.battery_state || null,
      battery_voltage_v: raw.battery_voltage_v || null,
      battery_temp_c:  raw.battery_temp_c || null,
      frequency_hz:    raw.frequency_hz || null,
      grid_limit_kw:   raw.grid_limit_kw || null,
      available_kw:    raw.available_kw || null,
      profiles:        Array.isArray(raw.profiles) ? raw.profiles : [],
      chint_v_a: raw.chint_v_a || null, chint_v_b: raw.chint_v_b || null, chint_v_c: raw.chint_v_c || null,
      chint_i_a: raw.chint_i_a || null, chint_i_b: raw.chint_i_b || null, chint_i_c: raw.chint_i_c || null,
      fresh: raw.fresh !== false,
    };
  }

  // ── Dot animation helpers ───────────────────────────────────────────────

  function samplePath(pathEl, numPoints) {
    const len = pathEl.getTotalLength();
    const pts = [];
    for (let i = 0; i <= numPoints; i++) {
      const pt = pathEl.getPointAtLength((i / numPoints) * len);
      pts.push({ x: pt.x, y: pt.y });
    }
    return pts;
  }

  function interpolatePath(points, t) {
    const idx = t * (points.length - 1);
    const i = Math.floor(idx);
    const frac = idx - i;
    const a = points[Math.min(i, points.length - 1)];
    const b = points[Math.min(i + 1, points.length - 1)];
    return { x: a.x + (b.x - a.x) * frac, y: a.y + (b.y - a.y) * frac };
  }

  function kwToSpeed(absKw) {
    // 1 kW → slow (0.3 cycles/sec), 60 kW → fast (1.2 cycles/sec)
    return Math.max(0.3, Math.min(1.2, 0.3 + (absKw / 60) * 0.9));
  }

  // ── Per-instance dot registry ───────────────────────────────────────────
  // Maps id → { dots: {...}, rafId: number }

  const dotRegistry = {};

  function initDots(id) {
    const byId = eid => document.getElementById(eid + '-' + id);

    const bldEl = byId('fl-bld');
    const evEl  = byId('fl-ev');

    const gridPath  = [{ x: 130, y: 215 }, { x: 320, y: 215 }];
    const solarPath = [{ x: 460, y: 100 }, { x: 460, y: 175 }];
    const battPath  = [{ x: 460, y: 255 }, { x: 460, y: 325 }];
    const bldPath   = bldEl ? samplePath(bldEl, 20) : [{ x: 600, y: 200 }, { x: 755, y: 110 }];
    const evPath    = evEl  ? samplePath(evEl, 20)  : [{ x: 600, y: 235 }, { x: 755, y: 325 }];

    const dots = {
      gridDot1: { progress: 0.0, speed: 0.3, direction: 1, active: false, color: '#10b981', el: byId('dot-grid'),  path: gridPath  },
      gridDot2: { progress: 0.5, speed: 0.3, direction: 1, active: false, color: '#10b981', el: byId('dot-grid2'), path: gridPath  },
      solarDot: { progress: 0.0, speed: 0.3, direction: 1, active: false, color: '#fbbf24', el: byId('dot-solar'), path: solarPath },
      battDot:  { progress: 0.0, speed: 0.3, direction: 1, active: false, color: '#10b981', el: byId('dot-batt'),  path: battPath  },
      bldDot:   { progress: 0.0, speed: 0.3, direction: 1, active: false, color: '#94a3b8', el: byId('dot-bld'),   path: bldPath   },
      evDot:    { progress: 0.0, speed: 0.3, direction: 1, active: false, color: '#00B0E4', el: byId('dot-ev'),    path: evPath    },
    };

    let lastTime = 0;
    let rafId = null;

    function animate(timestamp) {
      const dt = lastTime ? (timestamp - lastTime) / 1000 : 0;
      lastTime = timestamp;

      for (const dot of Object.values(dots)) {
        if (!dot.el) continue;
        if (!dot.active) {
          dot.el.setAttribute('opacity', '0');
          continue;
        }
        dot.el.setAttribute('opacity', '0.9');
        dot.el.setAttribute('fill', dot.color);

        dot.progress += dot.speed * dot.direction * dt;
        if (dot.progress > 1) dot.progress -= 1;
        if (dot.progress < 0) dot.progress += 1;

        const pos = interpolatePath(dot.path, dot.progress);
        dot.el.setAttribute('cx', pos.x);
        dot.el.setAttribute('cy', pos.y);
      }

      rafId = requestAnimationFrame(animate);
      dotRegistry[id].rafId = rafId;
    }

    rafId = requestAnimationFrame(animate);
    dotRegistry[id] = { dots, rafId };
  }

  function updateDotStates(id, d) {
    const entry = dotRegistry[id];
    if (!entry) return;
    const { dots } = entry;

    const grid     = d.grid_kw || 0;
    const solar    = d.solar_kw || 0;
    const battKw   = (d.battery_power_w || 0) / 1000;
    const building = d.building_kw || 0;
    const ev       = d.ev_total_kw || 0;

    // Grid: active when |grid| > 0.5 kW
    const gridActive = Math.abs(grid) > 0.5;
    dots.gridDot1.active    = gridActive;
    dots.gridDot2.active    = gridActive;
    dots.gridDot1.direction = grid >= 0 ? 1 : -1;
    dots.gridDot2.direction = grid >= 0 ? 1 : -1;
    dots.gridDot1.speed     = kwToSpeed(Math.abs(grid));
    dots.gridDot2.speed     = kwToSpeed(Math.abs(grid));
    dots.gridDot1.color     = grid >= 0 ? '#10b981' : '#ef4444';
    dots.gridDot2.color     = grid >= 0 ? '#10b981' : '#ef4444';

    // Solar: always forward (top → down)
    dots.solarDot.active    = solar > 0.5;
    dots.solarDot.direction = 1;
    dots.solarDot.speed     = kwToSpeed(solar);
    dots.solarDot.color     = '#fbbf24';

    // Battery: charging (battKw < 0) = forward (top → down), discharging = reverse
    dots.battDot.active    = Math.abs(battKw) > 0.5;
    dots.battDot.direction = battKw < 0 ? -1 : 1;  // discharging = upward (batt→inv), charging = downward (inv→batt)
    dots.battDot.speed     = kwToSpeed(Math.abs(battKw));
    dots.battDot.color     = battKw < 0 ? '#f59e0b' : '#10b981';

    // Building: always forward
    dots.bldDot.active    = building > 0.5;
    dots.bldDot.direction = 1;
    dots.bldDot.speed     = kwToSpeed(building);
    dots.bldDot.color     = '#94a3b8';

    // EV: always forward
    dots.evDot.active    = ev > 0.5;
    dots.evDot.direction = 1;
    dots.evDot.speed     = kwToSpeed(ev);
    dots.evDot.color     = '#00B0E4';
  }

  // ── Update SVG with live data ───────────────────────────────────────────

  function updateSVG(id, d) {
    const fmt = n => typeof n === 'number' ? n.toFixed(1) : '—';

    const grid    = d.grid_kw;
    const solar   = d.solar_kw;
    const ev      = d.ev_total_kw;
    const battW   = d.battery_power_w;
    const battKw  = battW / 1000;
    const soc     = d.ess_soc_pct;
    const building = d.building_kw;

    // Helper: get SVG element by suffixed id
    const el = eid => document.getElementById(eid + '-' + id);

    const setTxt = (eid, txt, color) => {
      const e = el(eid); if (!e) return;
      e.textContent = txt;
      if (color) e.setAttribute('fill', color);
    };

    const setLine = (eid, active, color, w, reverse) => {
      const e = el(eid); if (!e) return;
      e.setAttribute('stroke', active ? color : '#1e3a5f');
      e.setAttribute('stroke-width', active ? w : '2');
      e.setAttribute('opacity', active ? '0.85' : '0.35');
      const fwd = 'fl-fwd-' + id, rev = 'fl-rev-' + id;
      e.classList.remove(fwd, rev);
      if (active) e.classList.add(reverse ? rev : fwd);
    };

    const lw = kw => Math.max(2, Math.min(5, 2 + Math.abs(kw || 0) / 30 * 3));

    // Colors
    const gridColor  = grid >= 0 ? '#10b981' : '#ef4444';
    const solarColor = solar > 0.5 ? '#fbbf24' : '#64748b';
    const socColor   = soc == null ? '#8b5cf6' : soc < 20 ? '#ef4444' : soc < 50 ? '#f59e0b' : '#8b5cf6';
    const bState     = d.battery_state || (battKw < -0.5 ? 'charging' : battKw > 0.5 ? 'discharging' : 'idle');
    const battColor  = bState === 'charging' ? '#f59e0b' : bState === 'discharging' ? '#10b981' : '#8b5cf6';
    const bldActive  = building > 0.5;
    const evActive   = ev > 0.5;

    // Active states
    const gridActive  = Math.abs(grid) > 0.5;
    const solarActive = solar > 0.5;
    const battActive  = soc != null;

    // Flow lines
    setLine('fl-grid',  gridActive,  gridColor, lw(grid),          grid < 0);
    setLine('fl-solar', solarActive, '#fbbf24',  lw(solar),         false);
    setLine('fl-batt',  battActive,  battColor,  lw(Math.abs(battKw)), battKw < 0);  // discharging = reverse (upward, batt→inv)
    setLine('fl-bld',   bldActive,   '#94a3b8',  lw(building),      false);
    setLine('fl-ev',    evActive,    '#00B0E4',   lw(ev),            false);

    // Update dot animation state (rAF loop reads these each frame)
    updateDotStates(id, d);

    // Node text values
    setTxt('fv-grid',     fmt(Math.abs(grid)) + ' kW', gridColor);
    setTxt('fv-grid-dir', grid >= 0 ? 'import' : 'export');
    setTxt('fv-solar',    fmt(solar) + ' kW', solarColor);
    const absInv = Math.abs(d.inverter_power_w || 0);
    setTxt('fv-inv', absInv >= 1000 ? (absInv / 1000).toFixed(1) + ' kW' : Math.round(absInv) + ' W');
    setTxt('fv-mode', d.ems_mode || '—',
      d.ems_mode === 'FAILSAFE' ? '#ef4444' : d.ems_mode ? '#10b981' : '#64748b');
    setTxt('fv-batt',     fmt(Math.abs(battKw)) + ' kW', socColor);
    setTxt('fv-soc',      soc != null ? Math.round(soc) + '%' : '—%', socColor);
    setTxt('fv-bld',      fmt(building) + ' kW', bldActive ? '#94a3b8' : '#475569');
    setTxt('fv-ev',       fmt(ev) + ' kW', evActive ? '#00B0E4' : '#64748b');
  }

  // ── Main init function ──────────────────────────────────────────────────

  window.initEnergyFlow = function (containerId, dataUrl, options) {
    options = Object.assign({
      pollInterval: 3000,
      showPhaseTable: false,
      showDetailCards: false,
      gridLimitKw: 86,
    }, options || {});

    const container = document.getElementById(containerId);
    if (!container) {
      console.error('[EnergyFlow] Container not found:', containerId);
      return;
    }

    // Unique id suffix to avoid collisions when used multiple times
    const id = containerId.replace(/[^a-zA-Z0-9]/g, '_');

    // Inject SVG
    container.innerHTML = buildSVG(id);

    // Start rAF animation loop (once per instance)
    initDots(id);

    // Poll loop
    let pollTimer = null;

    async function poll() {
      try {
        const r = await fetch(dataUrl);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const raw = await r.json();
        const d = normalize(raw);
        if (!d) throw new Error('Invalid data');
        updateSVG(id, d);
      } catch (err) {
        console.warn('[EnergyFlow] Poll error:', err);
      }
      pollTimer = setTimeout(poll, options.pollInterval);
    }

    poll();

    // Return a cleanup function
    return function destroy() {
      if (pollTimer) clearTimeout(pollTimer);
      const entry = dotRegistry[id];
      if (entry && entry.rafId) cancelAnimationFrame(entry.rafId);
      delete dotRegistry[id];
    };
  };

})();

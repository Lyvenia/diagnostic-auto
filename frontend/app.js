'use strict';

// ════════════════════════════════════════════════════════
//  STATE
// ════════════════════════════════════════════════════════
const state = {
  connection: { connected: false, simulation: false, port: '' },
  fleet: [],
  selectedVin: null,
  healthScores: {},
  editingVin: null,
  currentDiag: {
    vin: null,
    dtc_codes: [],
    realtime: {},
    freeze_frame: {},
    analyse_ia: null,
    kilometrage: 0,
    savedEntry: null,
    vehicle_manual: null,
    _audio_peaks: null,
    _audio_interps: null,
  },
  diagSaved: false,
  wizardStep: 1,
  session_ralenti: null,
  session_roulant: null,
};

// ════════════════════════════════════════════════════════
//  API HELPERS
// ════════════════════════════════════════════════════════
async function api(method, url, body = null, timeoutMs = 120000) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== null) opts.body = JSON.stringify(body);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  opts.signal = controller.signal;
  try {
    const res = await fetch(url, opts);
    clearTimeout(timer);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || res.statusText);
    }
    return res.json();
  } catch (e) {
    clearTimeout(timer);
    console.error(`[api] ${method} ${url} →`, e.name, e.message, e);
    // WebView2 peut renvoyer "Failed to fetch" au lieu de "AbortError" quand le timeout se déclenche
    if (e.name === 'AbortError' || controller.signal.aborted) throw new Error('Délai dépassé — l\'analyse IA prend trop de temps, réessayez.');
    if (e.message === 'Failed to fetch') throw new Error('Impossible de contacter le serveur. Vérifiez que l\'application est bien lancée.');
    throw e;
  }
}

async function saveFile(url, body, timeoutMs = 120000) {
  const opts = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  opts.signal = controller.signal;
  try {
    const res = await fetch(url, opts);
    clearTimeout(timer);
    const data = await res.json().catch(() => ({ error: res.statusText }));
    if (!res.ok || !data.success) throw new Error(data.error || 'Erreur export');
    return data; // { success, filename, path }
  } catch (e) {
    clearTimeout(timer);
    console.error(`[saveFile] POST ${url} →`, e.name, e.message, e);
    if (e.name === 'AbortError' || controller.signal.aborted) throw new Error('Délai dépassé — la génération du fichier prend trop de temps, réessayez.');
    if (e.message === 'Failed to fetch') throw new Error('Connexion au serveur interrompue pendant la génération. Réessayez dans quelques secondes.');
    throw e;
  }
}

async function openExportsFolder() {
  await fetch('/api/open-exports', { method: 'POST' });
}

async function openExternal(url) {
  try {
    await fetch('/api/open-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
  } catch (err) { console.warn('[openUrl] Échec ouverture URL :', err); }
}

// ════════════════════════════════════════════════════════
//  FOCUS TRAP — accessibilité modales
// ════════════════════════════════════════════════════════
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function trapFocus(modalEl) {
  const focusables = [...modalEl.querySelectorAll(FOCUSABLE)].filter(el => !el.closest('.hidden'));
  if (!focusables.length) return;
  focusables[0].focus();
  function handler(e) {
    if (e.key === 'Tab') {
      const first = focusables[0], last = focusables[focusables.length - 1];
      if (e.shiftKey ? document.activeElement === first : document.activeElement === last) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      }
    }
    if (e.key === 'Escape') {
      modalEl.classList.add('hidden');
      modalEl.removeEventListener('keydown', handler);
    }
  }
  modalEl.addEventListener('keydown', handler);
  // Nettoyer quand la modale se referme
  const obs = new MutationObserver(() => {
    if (modalEl.classList.contains('hidden')) {
      modalEl.removeEventListener('keydown', handler);
      obs.disconnect();
    }
  });
  obs.observe(modalEl, { attributes: true, attributeFilter: ['class'] });
}

function openModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('hidden');
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  trapFocus(el);
}

function closeModal(id) {
  document.getElementById(id)?.classList.add('hidden');
}

// ════════════════════════════════════════════════════════
//  TOAST
// ════════════════════════════════════════════════════════
let _toastTimer = null;
function toast(msg, type = 'info', duration = 3500) {
  const el = document.getElementById('toast');
  el.innerHTML = msg;
  el.className = `toast show ${type}`;
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = 'toast hidden'; }, duration);
}

// ════════════════════════════════════════════════════════
//  CONNECTION & STATUS
// ════════════════════════════════════════════════════════
async function refreshStatus() {
  try {
    const s = await api('GET', '/api/status');
    state.connection = s;
    renderConnectionBadge();
    document.getElementById('simLabel').textContent = s.simulation ? 'ON' : 'OFF';
    if (s.client_build) applyClientBuild();
  } catch (err) { console.warn('[fetchStatus] Impossible de récupérer le statut :', err); }
}

/** Masque tous les éléments liés à la simulation en build client RODIA. */
function applyClientBuild() {
  // Paramètres : bloc mode de fonctionnement
  const simBlock = document.getElementById('simModeBlock');
  if (simBlock) simBlock.style.display = 'none';
  // Topbar : badge simulation
  const simLabel = document.getElementById('simLabel');
  if (simLabel) simLabel.classList.add('hidden');
  // Diagnostic step : tag simulation
  const simTag = document.getElementById('simTag');
  if (simTag) simTag.classList.add('hidden');
  // Écran d'accueil : hint simulation
  const simHint = document.getElementById('simHint');
  if (simHint) simHint.style.display = 'none';
  // Paramètres : bloc clé API Anthropic (inutile en build client, IA via Lyvenia)
  const apiKeyBlock = document.getElementById('apiKeyBlock');
  if (apiKeyBlock) apiKeyBlock.style.display = 'none';
}

function renderConnectionBadge() {
  const dot   = document.getElementById('badgeDot');
  const label = document.getElementById('badgeLabel');
  const { connected, simulation, port } = state.connection;
  if (!connected) {
    dot.className = 'badge-dot disconnected';
    label.textContent = 'Déconnecté';
  } else if (simulation) {
    dot.className = 'badge-dot simulation';
    // Build client : pas de mot "Simulation" (peu pro) → état d'attente adaptateur
    label.textContent = state.connection.client_build ? 'En attente adaptateur' : 'Simulation';
  } else {
    dot.className = 'badge-dot connected';
    label.textContent = `Connecté (${port})`;
  }
}

// ════════════════════════════════════════════════════════
//  FLEET
// ════════════════════════════════════════════════════════
async function loadFleet() {
  try {
    state.fleet = await api('GET', '/api/fleet');
    try {
      state.healthScores = await api('GET', '/api/fleet/health');
    } catch (_) {}
    renderFleet();
    loadPatterns();
    renderNotifBanner();
    // Refresh fleet management if historique tab is visible and no vehicle selected
    const histTab = document.getElementById('tab-historique');
    if (histTab && histTab.classList.contains('active') && !state.selectedVin) {
      renderFleetDashboard();
      renderFleetManagement();
    }
  } catch (e) {
    console.error('Fleet load error:', e);
    // Affiche l'erreur à l'utilisateur pour éviter une liste vide trompeuse.
    const listEl = document.getElementById('fleetList');
    if (listEl) {
      listEl.innerHTML = `<div class="empty-state" style="color:var(--danger)">⚠ Flotte indisponible : ${escHtml(e.message || 'erreur inconnue')}<br><button class="btn-secondary" onclick="loadFleet()" style="margin-top:12px">Réessayer</button></div>`;
    }
  }
}

function renderNotifBanner() {
  const banner = document.getElementById('notifBanner');
  if (!banner) return;
  const isReal = !state.connection?.simulation;
  const fleet = isReal ? state.fleet.filter(v => !v.simulated) : state.fleet;

  const pannes = fleet.filter(v => {
    const statut = v.statut_dernier_diagnostic || 'OK';
    if (statut === 'OK') return false;
    return (v.historique || []).some(h => (h.statut_suivi || 'ouvert') !== 'resolu');
  });

  const alertesKm = fleet.filter(v => {
    const lastKm = v.historique?.[0]?.kilometrage || v.km_manuel || 0;
    return (v.alertes_km || []).some(a => lastKm >= a.km_seuil);
  });

  const items = [];
  if (pannes.length) {
    const names = pannes.slice(0, 3).map(v => v.surnom || v.code || `${v.marque||''} ${v.modele||''}`.trim() || v.vin.slice(-6)).join(', ');
    const more  = pannes.length > 3 ? ` +${pannes.length - 3}` : '';
    items.push(`<span class="notif-item notif-urgent">🔴 ${pannes.length} panne(s) non résolue(s) — <strong>${names}${more}</strong></span>`);
  }
  if (alertesKm.length) {
    const names = alertesKm.slice(0, 3).map(v => v.surnom || v.code || `${v.marque||''} ${v.modele||''}`.trim() || v.vin.slice(-6)).join(', ');
    const more  = alertesKm.length > 3 ? ` +${alertesKm.length - 3}` : '';
    items.push(`<span class="notif-item notif-warn">🔔 ${alertesKm.length} alerte(s) km déclenchée(s) — <strong>${names}${more}</strong></span>`);
  }

  if (!items.length) {
    banner.classList.add('hidden');
    return;
  }
  banner.innerHTML = items.join('');
  banner.classList.remove('hidden');
}

function renderFleet() {
  const el = document.getElementById('fleetList');
  if (!el) return;
  const isReal = !state.connection.simulation;
  const vehicles = isReal ? state.fleet.filter(v => !v.simulated) : state.fleet;

  if (!vehicles.length) {
    el.innerHTML = isReal
      ? '<div class="empty-state">Aucun véhicule réel enregistré.<br><small>Branchez un adaptateur OBD2 et lancez un diagnostic.</small></div>'
      : '<div class="empty-state">Aucun véhicule enregistré</div>';
    return;
  }
  el.innerHTML = vehicles.map(v => {
    const statusDot = statusDotHtml(v.statut_dernier_diagnostic || 'OK');
    const codeLabel = v.code ? `<span class="vehicle-code-badge">[${v.code}]</span> ` : '';
    const displayName = v.surnom || `${v.marque || ''} ${v.modele || ''}`.trim() || 'Véhicule';
    const active = state.selectedVin === v.vin ? ' active' : '';
    const hist = v.historique || [];
    const lastKm = hist.length ? (hist[0].kilometrage || 0) : 0;
    const hasAlert = (v.alertes_km || []).some(a => lastKm >= a.km_seuil);
    const alertBadge = hasAlert ? '<span class="fleet-alert-badge" title="Alerte km déclenchée">🔔</span>' : '';
    const hs = state.healthScores[v.vin];
    const healthBadge = hs ? `<span style="font-size:.7rem;font-weight:700;color:${{'ok':'var(--success)','warn':'var(--warning)','danger':'var(--danger)'}[hs.color]||'var(--accent)'};">${hs.score}</span>` : '';
    return `
      <div class="fleet-item${active}" data-vin="${v.vin}">
        ${statusDot}
        <div class="fleet-item-info">
          <div class="fleet-item-name">${codeLabel}${escHtml(displayName)}${alertBadge}</div>
          <div class="fleet-item-sub">${v.vin}</div>
        </div>
        ${healthBadge}
      </div>`;
  }).join('');
  el.querySelectorAll('.fleet-item').forEach(el => {
    el.addEventListener('click', () => selectVehicle(el.dataset.vin));
  });
}

function statusDotHtml(statut) {
  const cls = { 'URGENT': 'urgent', 'À SURVEILLER': 'surveiller', 'SURVEILLER': 'surveiller', 'OK': 'ok' };
  return `<div class="status-dot ${cls[statut] || 'ok'}"></div>`;
}

async function selectVehicle(vin) {
  state.selectedVin = vin;
  renderFleet(); // met à jour la sidebar globale gauche

  // Si on n'est pas sur l'onglet flotte, y aller
  const fleetTab = document.getElementById('tab-historique');
  if (!fleetTab || !fleetTab.classList.contains('active')) {
    switchTab('historique');
    // switchTab va charger la flotte et renderFleetManagement, attendre
    await new Promise(r => setTimeout(r, 300));
  }

  // Surligner dans la sidebar du panneau flotte
  document.querySelectorAll('.fv-item').forEach(el => {
    el.classList.toggle('active', el.dataset.vin === vin);
  });

  // Afficher le panneau détail
  document.getElementById('fleetEmptyState')?.classList.add('hidden');
  document.getElementById('historyContainer')?.classList.remove('hidden');

  await renderHistory(vin);
}

// ════════════════════════════════════════════════════════
//  TABLEAU DE BORD FLOTTE
// ════════════════════════════════════════════════════════
async function renderFleetDashboard() {
  // Mise à jour de la barre stats en haut (compatibilité)
  const isReal = !state.connection?.simulation;
  const fleet  = isReal ? state.fleet.filter(v => !v.simulated) : state.fleet;
  const urgent     = fleet.filter(v => v.statut_dernier_diagnostic === 'URGENT').length;
  const surveiller = fleet.filter(v => v.statut_dernier_diagnostic === 'SURVEILLER').length;
  const ok         = fleet.filter(v => !['URGENT','SURVEILLER'].includes(v.statut_dernier_diagnostic)).length;
  const setEl = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
  setEl('fstatTotal', fleet.length); setEl('fstatUrgentVal', urgent);
  setEl('fstatWarnVal', surveiller); setEl('fstatOkVal', ok);
  // Le cockpit est rendu dans renderCockpit()
  await renderCockpit();
}

async function renderCockpit() {
  const el = document.getElementById('fleetCockpit');
  if (!el) return;
  try {
    const [dash, patterns, triggered] = await Promise.all([
      api('GET', '/api/dashboard'),
      api('GET', '/api/fleet/patterns'),
      api('GET', '/api/fleet/alerts'),
    ]);

    const isReal  = !state.connection?.simulation;
    const fleet   = isReal ? state.fleet.filter(v => !v.simulated) : state.fleet;
    const urgent  = fleet.filter(v => v.statut_dernier_diagnostic === 'URGENT').length;
    const surv    = fleet.filter(v => v.statut_dernier_diagnostic === 'SURVEILLER').length;
    const ok      = fleet.length - urgent - surv;
    const maint   = dash.maintenance_summary || {};
    const maintU  = (maint.urgent  || []).length;
    const maintW  = (maint.warning || []).length;
    const frauds  = fleet.reduce((n, v) =>
      n + (v.historique || []).filter(h => h.km_alerte_fraude).length, 0);
    const avg     = dash.avg_score ?? null;

    // ── Briefing du matin ──────────────────────────────
    const scoreColor = avg === null ? 'var(--text-muted)'
      : avg >= 80 ? 'var(--success)' : avg >= 50 ? 'var(--warning)' : 'var(--danger)';

    const garage = state._garage || {};
    const garageHdr = garage.nom
      ? `<div class="cockpit-garage-name">${escHtml(garage.nom)}</div>`
      : '';

    let html = `
      <div class="cockpit-wrap">
        ${garageHdr}
        <div class="cockpit-title">☀️ Tableau de bord flotte</div>
        <div class="cockpit-kpi-row">
          <div class="cockpit-kpi cockpit-kpi-urgent" onclick="filterFleetByStatus('URGENT')">
            <div class="cockpit-kpi-val">${urgent}</div>
            <div class="cockpit-kpi-lbl">🔴 Urgences</div>
          </div>
          <div class="cockpit-kpi cockpit-kpi-warn" onclick="filterFleetByStatus('SURVEILLER')">
            <div class="cockpit-kpi-val">${surv}</div>
            <div class="cockpit-kpi-lbl">⚠️ À surveiller</div>
          </div>
          <div class="cockpit-kpi cockpit-kpi-maint${maintU > 0 ? ' cockpit-kpi-alert' : ''}">
            <div class="cockpit-kpi-val">${maintU + maintW}</div>
            <div class="cockpit-kpi-lbl">🔧 Entretiens à faire</div>
          </div>
          <div class="cockpit-kpi cockpit-kpi-ok">
            <div class="cockpit-kpi-val">${ok}</div>
            <div class="cockpit-kpi-lbl">✅ En bon état</div>
          </div>
          ${avg !== null ? `
          <div class="cockpit-kpi" style="cursor:default">
            <div class="cockpit-kpi-val" style="color:${scoreColor}">${avg}</div>
            <div class="cockpit-kpi-lbl">📊 Score moyen</div>
          </div>` : ''}
          ${frauds > 0 ? `
          <div class="cockpit-kpi cockpit-kpi-fraud">
            <div class="cockpit-kpi-val">${frauds}</div>
            <div class="cockpit-kpi-lbl">⚠️ Compteurs suspects</div>
          </div>` : ''}
        </div>`;

    // ── Entretiens urgents ──────────────────────────────
    const allMaint = [...(maint.urgent || []), ...(maint.warning || [])];
    if (allMaint.length) {
      html += `<div class="cockpit-section-title">🔧 Entretiens à traiter</div><div class="cockpit-list">`;
      allMaint.slice(0, 6).forEach(m => {
        const isUrg = (maint.urgent || []).includes(m);
        html += `<div class="cockpit-list-row" onclick="selectVehicle('${escHtml(m.vin)}')">
          <span>${m.icon || '🔧'} <strong>${escHtml(m.label)}</strong></span>
          <span style="font-size:.78rem;color:var(--text-muted)">${escHtml(m.vin?.slice(-6) || '')}</span>
          <span class="cockpit-badge ${isUrg ? 'badge-urgent' : 'badge-warn'}">${isUrg ? 'Dépassé' : 'Bientôt'}</span>
        </div>`;
      });
      html += `</div>`;
    }

    // ── Activité récente ────────────────────────────────
    const recent = (dash.recent_diags || []).slice(0, 6);
    if (recent.length) {
      html += `<div class="cockpit-section-title">🕐 Activité récente</div><div class="cockpit-list">`;
      recent.forEach(d => {
        const vc = fleet.find(v => v.vin === d.vin);
        const code = vc?.code ? `<span class="vehicle-code-badge" style="margin-right:4px">[${escHtml(vc.code)}]</span>` : '';
        const dotCls = { URGENT: 'urgent', SURVEILLER: 'surveiller', OK: 'ok' }[d.statut] || 'ok';
        const codes = d.dtc_codes?.length ? d.dtc_codes.join(', ') : '✅ Aucun défaut';
        html += `<div class="cockpit-list-row" onclick="selectVehicle('${escHtml(d.vin)}')">
          <div class="status-dot ${dotCls}" style="flex-shrink:0;margin-top:2px"></div>
          <span>${code}${escHtml(d.label || d.vin)}</span>
          <span style="font-size:.78rem;color:var(--text-dim);flex:1;text-align:right">${escHtml(codes)}</span>
          <span style="font-size:.75rem;color:var(--text-muted);white-space:nowrap;margin-left:8px">${escHtml(d.date_affichage || '')}</span>
        </div>`;
      });
      html += `</div>`;
    }

    // ── Codes récurrents ────────────────────────────────
    if (patterns.length) {
      html += `<div class="cockpit-section-title">🔍 Codes récurrents dans la flotte</div><div class="cockpit-list">`;
      patterns.slice(0, 5).forEach(p => {
        html += `<div class="cockpit-list-row" style="cursor:default">
          <span style="font-weight:700;color:var(--warning);font-family:monospace">${escHtml(p.code)}</span>
          <span style="font-size:.78rem;color:var(--text-muted)">${p.count} véhicule${p.count > 1 ? 's' : ''}</span>
          <span style="font-size:.75rem;color:var(--text-muted)">${(p.vehicules || []).join(', ')}</span>
        </div>`;
      });
      html += `</div>`;
    }

    html += `<div class="cockpit-hint">Cliquez sur un véhicule dans la liste pour ouvrir son dossier</div></div>`;
    el.innerHTML = html;
  } catch(e) {
    console.error('renderCockpit error', e);
    el.innerHTML = `<div class="cockpit-wrap"><div class="empty-state" style="color:var(--danger)">⚠ Tableau de bord indisponible : ${escHtml(e.message || 'erreur inconnue')}<br><button class="btn-secondary" onclick="renderCockpit()" style="margin-top:12px">Réessayer</button></div></div>`;
  }
}

function filterFleetByStatus(status) {
  const box = document.getElementById('fleetSearchBox');
  if (box) { box.value = ''; }
  // highlight filtered vehicles
  document.querySelectorAll('.fleet-vehicle-item').forEach(el => {
    const vin = el.dataset.vin;
    const v   = state.fleet.find(x => x.vin === vin);
    el.style.display = (!status || v?.statut_dernier_diagnostic === status) ? '' : 'none';
  });
}

// ════════════════════════════════════════════════════════
//  FLEET MANAGEMENT VIEW
// ════════════════════════════════════════════════════════
// Mapping préfixe code → nom de groupe + icône
const CODE_GROUP_MAP = {
  V: { label: 'VSL',          icon: '🚑' },
  T: { label: 'Taxis / VTC',  icon: '🚕' },
  A: { label: 'Ambulances',   icon: '🚨' },
  U: { label: 'Utilitaires',  icon: '🚚' },
  C: { label: 'Camions / PL', icon: '🚛' },
  M: { label: 'Motos',        icon: '🏍️' },
};

function getCodeGroup(v) {
  const prefix = (v.code || '').toUpperCase().match(/^([A-Z]+)/)?.[1] || '';
  return CODE_GROUP_MAP[prefix] || null;
}

async function renderFleetManagement() {
  const listEl = document.getElementById('fleetVehicleList');
  if (!listEl) return;

  const vehicles = state.fleet;
  const query = (document.getElementById('fleetSearchBox')?.value || '').toLowerCase().trim();

  // Grouper par préfixe de code — dérivé automatiquement
  const groups = {};   // key = préfixe (V/T/A…) ou '' pour sans code
  vehicles.forEach(v => {
    const prefix = (v.code || '').toUpperCase().match(/^([A-Z]+)/)?.[1] || '';
    if (!groups[prefix]) groups[prefix] = [];
    groups[prefix].push(v);
  });

  // Ordre : préfixes connus en premier (dans l'ordre du mapping), non classés en dernier
  const knownOrder = Object.keys(CODE_GROUP_MAP);
  const sortedKeys = [
    ...knownOrder.filter(k => groups[k]),
    ...Object.keys(groups).filter(k => k && !CODE_GROUP_MAP[k]).sort(),
    ...(groups[''] ? [''] : []),
  ];

  let html = '';
  for (const prefix of sortedKeys) {
    const groupVehicles = groups[prefix] || [];
    const filtered = query
      ? groupVehicles.filter(v => {
          const name = (v.surnom || `${v.marque || ''} ${v.modele || ''}`).toLowerCase();
          return name.includes(query) || v.vin.toLowerCase().includes(query) ||
                 (v.code || '').toLowerCase().includes(query);
        })
      : groupVehicles;
    if (!filtered.length) continue;

    // Label de groupe
    const grp = CODE_GROUP_MAP[prefix];
    if (grp) {
      html += `<div class="fv-group-label">${grp.icon} ${grp.label} <span class="fv-group-count">${filtered.length}</span></div>`;
    } else if (prefix) {
      html += `<div class="fv-group-label">📁 ${escHtml(prefix)} <span class="fv-group-count">${filtered.length}</span></div>`;
    } else {
      html += `<div class="fv-group-label fv-group-unclassed">— Non classés <span class="fv-group-count">${filtered.length}</span></div>`;
    }
    html += filtered.map(v => renderFleetVehicleItem(v)).join('');
  }

  listEl.innerHTML = html || '<div class="fleet-empty-msg">Aucun véhicule trouvé</div>';

  if (state.selectedVin) {
    listEl.querySelector(`[data-vin="${state.selectedVin}"]`)?.classList.add('active');
  }
  listEl.querySelectorAll('.fv-item').forEach(el => {
    el.addEventListener('click', () => selectVehicle(el.dataset.vin));
  });
}

function renderFleetVehicleItem(v) {
  const health    = state.healthScores?.[v.vin];
  const score     = health?.score ?? null;
  const colorCls  = health ? `fv-${health.color}` : 'fv-unknown';
  const name      = v.surnom || `${v.marque || 'Inconnu'} ${v.modele || ''}`.trim();
  const lastDiag  = v.historique?.[0];
  const lastDate  = lastDiag
    ? new Date(lastDiag.date).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })
    : 'Jamais';
  const isActive  = state.selectedVin === v.vin;
  const urgentDot = v.statut_dernier_diagnostic === 'URGENT'     ? '<span class="fv-urgent-dot"></span>' : '';
  const warnDot   = v.statut_dernier_diagnostic === 'SURVEILLER' ? '<span class="fv-warn-dot"></span>'   : '';
  const codeBadge = v.code ? `<span class="fv-code">${escHtml(v.code)}</span>` : '';
  const yearMake  = [v.marque, v.annee].filter(Boolean).join(' ');

  return `<div class="fv-item ${isActive ? 'active' : ''} ${colorCls}" data-vin="${escHtml(v.vin)}">
    <div class="fv-score-bar ${colorCls}"></div>
    <div class="fv-info">
      <div class="fv-name">${codeBadge}${escHtml(name)}${urgentDot}${warnDot}</div>
      <div class="fv-sub">${escHtml(yearMake)} · ${escHtml(lastDate)}</div>
    </div>
    <div class="fv-item-actions">
      <button class="fv-edit-btn" onclick="event.stopPropagation();openEditVehicleModal('${escHtml(v.vin)}')" title="Modifier">✏️</button>
      <div class="fv-score">${score !== null ? score : '—'}</div>
    </div>
  </div>`;
}

// ── Modal Groupes ─────────────────────────────────────────
// openGroupModal / renderGroupAccordion / renderVehicleCard supprimés —
// les groupes sont désormais dérivés automatiquement du préfixe de code (renderFleetManagement).

// renderVehicleHistoryCompact / toggleGroup / toggleVehicleHistory supprimés —
// remplacés par renderFleetVehicleItem et le panneau détail dossier.

// ── Code builder helpers ──────────────────────────────
const CODE_TYPES = ['V','T','A','U','C','M'];

function updateCodePreview(ctx) {
  const prefix = (document.getElementById(ctx === 'edit' ? 'editVehicleCodeType' : 'assignCodeType')?.value || 'V').toUpperCase();
  const num    = (document.getElementById(ctx === 'edit' ? 'editVehicleCodeNum'  : 'assignCodeNum')?.value  || '').trim();
  const code   = num ? prefix + num : prefix + '?';
  const prev   = document.getElementById(ctx === 'edit' ? 'editCodePreview' : 'assignCodePreview');
  if (prev) prev.textContent = '[' + code + ']';
}

function _parseCode(code) {
  // Split "V3" → { type: 'V', num: '3' } or "T12" → { type: 'T', num: '12' }
  const m = (code || '').toUpperCase().match(/^([A-Z]+)(\d+)$/);
  if (m) return { type: m[1], num: m[2] };
  return { type: 'V', num: code || '' };
}

async function _suggestNum(prefix) {
  try {
    const r = await api('GET', `/api/fleet/next-code?type=${encodeURIComponent(prefix)}`);
    return String(r.next || 1);
  } catch(_) { return '1'; }
}

// ── Modal Modifier véhicule ───────────────────────────
function openEditVehicleModal(vin) {
  const v = state.fleet.find(x => x.vin === vin);
  if (!v) return;
  state.editingVin = vin;
  const { type, num } = _parseCode(v.code || '');
  const typeEl = document.getElementById('editVehicleCodeType');
  const numEl  = document.getElementById('editVehicleCodeNum');
  if (typeEl) typeEl.value = CODE_TYPES.includes(type) ? type : 'V';
  if (numEl)  numEl.value  = num;
  document.getElementById('editVehicleSurnom').value = v.surnom || '';
  updateCodePreview('edit');
  openModal('modalEditVehicle');
}

function closeEditVehicleModal() {
  closeModal('modalEditVehicle');
  state.editingVin = null;
}

async function confirmEditVehicle() {
  if (!state.editingVin) return;
  const prefix = (document.getElementById('editVehicleCodeType')?.value || 'V').toUpperCase();
  const num    = (document.getElementById('editVehicleCodeNum')?.value || '').trim();
  const code   = num ? (prefix + num).toUpperCase() : '';
  const surnom = document.getElementById('editVehicleSurnom').value.trim();

  try {
    await api('PUT', `/api/fleet/vehicle/${encodeURIComponent(state.editingVin)}/info`, { code, surnom });
    closeEditVehicleModal();
    await loadFleet();
    renderFleetManagement();
    toast(`Véhicule mis à jour${code ? ' — Code : [' + code + ']' : ''} ✅`, 'success');
  } catch(e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

// ── Modal Nouveau véhicule — attribution code ─────────
let _assignCodeVin = null;

async function openAssignCodeModal(vin, vehicleLabel) {
  _assignCodeVin = vin;
  const labelEl = document.getElementById('assignCodeVehicleLabel');
  if (labelEl) labelEl.textContent = `Nouveau véhicule : ${vehicleLabel || vin}. Attribuez-lui un code pour le retrouver facilement.`;
  // Suggérer V par défaut puis charger le prochain numéro
  const typeEl = document.getElementById('assignCodeType');
  const numEl  = document.getElementById('assignCodeNum');
  if (typeEl) typeEl.value = 'V';
  if (numEl)  numEl.value  = await _suggestNum('V');
  updateCodePreview('assign');
  document.getElementById('modalAssignCode').classList.remove('hidden');
}

async function onAssignTypeChange() {
  const prefix = document.getElementById('assignCodeType')?.value || 'V';
  const numEl  = document.getElementById('assignCodeNum');
  if (numEl) numEl.value = await _suggestNum(prefix);
  updateCodePreview('assign');
}

async function confirmAssignCode() {
  if (!_assignCodeVin) return;
  const prefix = (document.getElementById('assignCodeType')?.value || 'V').toUpperCase();
  const num    = (document.getElementById('assignCodeNum')?.value || '').trim();
  const code   = num ? (prefix + num).toUpperCase() : prefix + '1';
  try {
    await api('PUT', `/api/fleet/vehicle/${_assignCodeVin}/info`, { code, surnom: '' });
    toast(`Code [${code}] attribué ✅`, 'success');
  } catch(err) { console.warn('[confirmAssignCode] Échec attribution code :', err); }
  closeAssignCodeModal(false);
  await loadFleet();
  renderFleetManagement();
}

function closeAssignCodeModal(skipped) {
  document.getElementById('modalAssignCode').classList.add('hidden');
  _assignCodeVin = null;
  if (skipped) toast('Code non attribué — modifiable dans l\'onglet Infos du véhicule', 'info', 4000);
}

async function deleteVehicle(vin) {
  const v = state.fleet.find(x => x.vin === vin);
  const name = v ? (v.surnom || v.code || `${v.marque || ''} ${v.modele || ''}`.trim() || vin) : vin;
  if (!confirm(`Supprimer le véhicule "${name}" ?\n\nCette action supprime aussi tout l'historique des diagnostics. Cette opération est irréversible.`)) return;
  try {
    await api('DELETE', `/api/fleet/vehicle/${encodeURIComponent(vin)}`);
    if (state.selectedVin === vin) {
      state.selectedVin = null;
      document.getElementById('historyContainer')?.classList.add('hidden');
      document.getElementById('fleetManagement')?.classList.remove('hidden');
    }
    await loadFleet();
    renderFleetManagement();
    toast(`Véhicule supprimé`, 'success');
  } catch(e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  PATTERNS FLOTTE
// ════════════════════════════════════════════════════════
async function loadPatterns() {
  try {
    const patterns = await api('GET', '/api/fleet/patterns');
    renderPatterns(patterns);
  } catch (err) { console.warn('[loadPatterns] Chargement patterns échoué :', err); }
}

function renderPatterns(patterns) {
  const panel = document.getElementById('patternsPanel');
  const list  = document.getElementById('patternsList');
  if (!panel || !list) return;
  if (!patterns || !patterns.length) {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');
  list.innerHTML = patterns.map(p => `
    <div class="pattern-item" title="${escHtml(p.vehicules.join(', '))}">
      <span class="pattern-code">${escHtml(p.code)}</span>
      <span class="pattern-count">${p.count} véhicules</span>
    </div>`).join('');
}

// ════════════════════════════════════════════════════════
//  DIAGNOSTIC FLOW
// ════════════════════════════════════════════════════════
function showStep(name) {
  ['stepWelcome', 'stepReading', 'stepData'].forEach(id => {
    document.getElementById(id).classList.toggle('hidden', id !== name);
  });
}

function applyManualVin() {
  const marque = (document.getElementById('vfMarque')?.value || '').trim();
  const modele = (document.getElementById('vfModele')?.value || '').trim();
  const annee  = (document.getElementById('vfAnnee')?.value  || '').trim();
  const motori = (document.getElementById('vfMotorisation')?.value || '').trim();

  if (!marque && !modele) { toast('Renseignez au minimum la marque ou le modèle', 'warning'); return; }

  // Construire un pseudo-VIN interne si pas de VIN OBD
  if (!state.currentDiag.vin) {
    state.currentDiag.vin = 'MANUEL_' + Date.now();
  }

  // Stocker les infos véhicule manuelles dans l'état
  state.currentDiag.vehicle_manual = { marque, modele, annee, motorisation: motori };

  // Mettre à jour l'affichage bannière
  const label = [marque, modele, annee ? `— ${annee}` : '', motori ? `(${motori})` : '']
    .filter(Boolean).join(' ');
  document.getElementById('vinDisplay').textContent = marque || 'Manuel';
  document.getElementById('vehicleLabel').textContent = label;
  document.getElementById('vinManualZone')?.classList.add('hidden');
  document.getElementById('btnEditVin')?.classList.remove('hidden');
  toast(`Véhicule enregistré : ${label}`, 'success', 3000);
}

/** Caractères VIN valides (ISO 3779 — I, O, Q exclus). */
const _VIN_VALID_RE = /^[A-HJ-NPR-Z0-9]+$/;

/** True si la chaîne est un VIN bien formé (17 caractères, alphabet valide). */
function isValidVinFormat(v) {
  return typeof v === 'string' && v.length === 17 && _VIN_VALID_RE.test(v);
}

/** Nettoie une saisie utilisateur en gardant uniquement les caractères VIN. */
function cleanVinInput(s) {
  return (s || '').toUpperCase().replace(/[^A-HJ-NPR-Z0-9]/g, '');
}

/** Ouvre la modale de saisie manuelle du VIN. Résout avec le VIN propre (17
 *  chars) ou null si l'utilisateur a annulé. Utilisée en filet de sécurité
 *  quand la lecture OBD a échoué ou rend un VIN invalide.
 *  Propose aussi en option : sélection d'un véhicule existant de la flotte. */
function askManualVin() {
  return new Promise((resolve) => {
    const modal  = document.getElementById('modalManualVin');
    const input  = document.getElementById('manualVinInput');
    const btnOk  = document.getElementById('btnManualVinOk');
    const btnCa  = document.getElementById('btnManualVinCancel');
    const hint   = document.getElementById('manualVinHint');
    const fleetRow    = document.getElementById('manualVinFleetRow');
    const fleetSelect = document.getElementById('manualVinFleetSelect');
    if (!modal || !input || !btnOk || !btnCa) { resolve(null); return; }

    input.value = '';
    hint.textContent = '0 / 17 caractères';
    hint.style.color = 'var(--text-muted)';
    btnOk.disabled = true;

    // Peupler la liste des véhicules existants de la flotte (si dispo)
    if (fleetRow && fleetSelect) {
      const fleet = (state.fleet || []).filter(v => v.vin && v.vin.length === 17 && !v.vin.startsWith('MANUEL_'));
      if (fleet.length > 0) {
        fleetSelect.innerHTML = '<option value="">— Choisir un véhicule —</option>' +
          fleet.map(v => {
            const lbl = [v.marque, v.modele, v.annee, v.surnom && `« ${v.surnom} »`].filter(Boolean).join(' ');
            return `<option value="${escHtml(v.vin)}">${escHtml(lbl || v.vin)}</option>`;
          }).join('');
        fleetRow.style.display = '';
      } else {
        fleetRow.style.display = 'none';
      }
    }

    modal.classList.remove('hidden');
    setTimeout(() => input.focus(), 50);

    function updateHint() {
      const v = cleanVinInput(input.value);
      // Resynchronise le champ avec la version nettoyée (au cas où l'utilisateur
      // ait collé du texte avec espaces / tirets)
      if (input.value !== v) input.value = v;
      const ok = isValidVinFormat(v);
      btnOk.disabled = !ok;
      if (ok) {
        hint.textContent = '✓ Format valide';
        hint.style.color = 'var(--success, #2f7a3d)';
      } else {
        hint.textContent = `${v.length} / 17 caractères`;
        hint.style.color = 'var(--text-muted)';
      }
    }
    function close(result) {
      modal.classList.add('hidden');
      btnOk.removeEventListener('click', onOk);
      btnCa.removeEventListener('click', onCancel);
      input.removeEventListener('keydown', onKey);
      input.removeEventListener('input', updateHint);
      // onFleetSelect est défini juste après dans le scope — guard si jamais
      if (typeof onFleetSelect === 'function') {
        fleetSelect?.removeEventListener('change', onFleetSelect);
      }
      resolve(result);
    }
    function onOk() {
      const v = cleanVinInput(input.value);
      if (isValidVinFormat(v)) close(v);
    }
    function onCancel() { close(null); }
    function onKey(e) {
      if (e.key === 'Enter' && !btnOk.disabled) onOk();
      else if (e.key === 'Escape') onCancel();
    }

    // Sélecteur véhicule existant : remplit le champ VIN et valide direct
    const onFleetSelect = () => {
      if (!fleetSelect) return;
      const v = fleetSelect.value;
      if (v) {
        input.value = v;
        updateHint();
        setTimeout(() => btnOk.focus(), 50);  // pour pouvoir valider à l'Entrée
      }
    };

    btnOk.addEventListener('click', onOk);
    btnCa.addEventListener('click', onCancel);
    input.addEventListener('keydown', onKey);
    input.addEventListener('input', updateHint);
    fleetSelect?.addEventListener('change', onFleetSelect);
  });
}

async function startDiagnostic(opts) {
  // ✨ Reset complet de l'état diagnostic AVANT toute lecture. Indispensable
  // pour le bouton "Nouvelle lecture" qui réutilise cette fonction : sinon
  // les résultats du diag précédent (anamnèse, monitoring, IA, audio, etc.)
  // restent à l'écran et le nouveau diag est superposé au-dessus.
  _resetDiagnosticFully();
  // Type de diagnostic : "panne" (défaut) ou "controle" (bilan santé)
  // Lu soit depuis opts.type, soit depuis l'attribut data-diag-type du bouton
  let diagType = (opts && opts.type) || 'panne';
  if (typeof opts === 'object' && opts && opts.target) {
    // Cas où l'event handler passe l'événement directement
    const btn = opts.target.closest && opts.target.closest('[data-diag-type]');
    if (btn) diagType = btn.dataset.diagType || diagType;
  }
  state.currentDiag.type = diagType;

  showStep('stepReading');
  document.getElementById('readingMsg').textContent = diagType === 'controle'
    ? 'Connexion à l\'adaptateur OBD2 (bilan de santé)…'
    : 'Connexion à l\'adaptateur OBD2…';

  try {
    const conn = await api('POST', '/api/connect');

    if (!conn.success) {
      toast('❌ ' + (conn.error || 'Connexion OBD2 impossible'), 'error', 7000);
      showStep('stepWelcome');
      return;
    }

    state.connection.simulation = conn.simulation;
    state.connection.connected  = conn.success;
    document.getElementById('simLabel').textContent = conn.simulation ? 'ON' : 'OFF';
    renderConnectionBadge();

    document.getElementById('readingMsg').textContent = 'Lecture VIN, DTC et données temps réel…';

    const body = state.selectedVin ? { forced_vin: state.selectedVin } : {};
    const data = await api('POST', '/api/read', body);

    // Couche 2 : lecture OBD du VIN incertaine → saisie manuelle.
    // Backend ne renvoie maintenant un VIN que s'il est strictement valide
    // (17 caractères + alphabet ISO 3779) ou null sinon → on demande.
    if (!isValidVinFormat(data.vin)) {
      document.getElementById('readingMsg').textContent = 'VIN non lu — saisie manuelle requise…';
      const manualVin = await askManualVin();
      if (!manualVin) {
        // L'utilisateur a annulé → on abandonne le diagnostic
        showStep('stepWelcome');
        return;
      }
      data.vin = manualVin;
      state.currentDiag.vin_manually_entered = true;
    } else {
      state.currentDiag.vin_manually_entered = false;
    }

    state.currentDiag.vin           = data.vin;
    state.currentDiag.dtc_codes     = data.dtc_codes     || [];
    state.currentDiag.dtc_info      = data.dtc_info      || {};
    state.currentDiag.dtc_families  = data.dtc_families  || {};
    state.currentDiag.mil_on        = !!data.mil_on;
    state.currentDiag.dtc_count_mil = data.dtc_count;
    state.currentDiag.realtime      = data.realtime      || {};
    state.currentDiag.freeze_frame  = data.freeze_frame  || {};
    state.currentDiag.analyse_ia    = null;
    state.diagSaved = false;

    document.getElementById('saveFeedback').classList.add('hidden');
    document.getElementById('actionBar').classList.add('hidden');
    document.getElementById('aiResults').classList.add('hidden');
    document.getElementById('aiResults').innerHTML = '';
    document.getElementById('chatSection').classList.add('hidden');

    renderDiagnosticData(data.simulation);
    showStep('stepData');
    wizardActivateStep(1);

    // Résumé étape 1
    const dtcCount  = (data.dtc_codes || []).length;
    const dtcStatus = data.dtc_status || 'ok';
    const step1SummaryEl = document.getElementById('step1Summary');
    if (step1SummaryEl) {
      if (dtcStatus === 'error' || dtcStatus === 'no_response') {
        step1SummaryEl.innerHTML = '⚠️ Lecture DTC impossible — contact insuffisant ou adaptateur non répondu';
        step1SummaryEl.style.color = '#e8b4a4';
        toast('Lecture DTC échouée — vérifiez que le contact est mis et la valise bien connectée', 'warning', 6000);
      } else if (dtcCount > 0) {
        step1SummaryEl.innerHTML = `✓ ${dtcCount} code(s) DTC détecté(s) : ${(data.dtc_codes||[]).join(', ')}`;
        step1SummaryEl.style.color = '';
      } else {
        step1SummaryEl.innerHTML = '✓ Aucun code DTC — véhicule sain';
        step1SummaryEl.style.color = '';
      }
      step1SummaryEl.classList.remove('hidden');
    }
    wizardSetDotState(1, 'done');
    wizardSetCardState(1, 'done');
    document.getElementById('wizardStep1')?.querySelector('.wizard-card-actions')?.classList?.add('hidden');
    // Afficher l'anamnèse avant le monitoring
    anamneseShow();
    wizardActivateStep(2);
    updateStepContextualHint(2);

    // Lecture kilométrage en arrière-plan (auto si OBD répond, sinon prompt manuel).
    // Async, ne bloque pas l'UI. Persisté dans flotte.json avec garde-fou anti-décroissance.
    if (state.currentDiag.vin) {
      fetchOdometerAuto(state.currentDiag.vin);
    }

    // Décodage VIN immédiat (async, sans bloquer l'UI)
    // Cascade : base partagée Lyvenia → WMI local → IA Claude
    if (state.currentDiag.vin) {
      api('POST', '/api/decode-vin', { vin: state.currentDiag.vin })
        .then(vi => {
          if (!vi || vi.error) return;
          state.currentDiag.vehicle_decoded = vi;  // mémoriser pour contribution
          const label = [vi.marque, vi.modele, vi.annee ? `— ${vi.annee}` : '']
            .filter(s => s && s !== 'Inconnu').join(' ');
          const vehicleLabelEl = document.getElementById('vehicleLabel');
          if (label) {
            // Badge de confiance selon la source
            let badge = '';
            if (vi.source === 'community') {
              const n = vi.shared_contributors || 0;
              if (vi.shared_status === 'verified') {
                badge = `<span class="vin-conf-badge vin-conf-high" title="Vérifié par ${n} garages RODIA — confiance maximale">👥 ✓ vérifié · ${n}</span>`;
              } else if (vi.shared_status === 'disputed') {
                badge = `<span class="vin-conf-badge vin-conf-low" title="Conflit entre contributeurs — à vérifier">👥 ⚠ contesté · ${n}</span>`;
              } else {
                badge = `<span class="vin-conf-badge vin-conf-med" title="Suggéré par ${n} garage(s) RODIA">👥 suggéré · ${n}</span>`;
              }
            } else if (vi.source === 'local') {
              badge = `<span class="vin-conf-badge vin-conf-low" title="Décodage local (table WMI) — à confirmer">🤖 local</span>`;
            }
            vehicleLabelEl.innerHTML = `${escHtml(label)} ${badge}`;
          }
          // Pré-remplir les champs contexte si vides
          const fMarque = document.getElementById('ctxMarque');
          const fModele = document.getElementById('ctxModele');
          const fAnnee  = document.getElementById('ctxAnnee');
          if (fMarque && !fMarque.value && vi.marque && vi.marque !== 'Inconnu') fMarque.value = vi.marque;
          if (fModele && !fModele.value && vi.modele && vi.modele !== 'Inconnu') fModele.value = vi.modele;
          if (fAnnee  && !fAnnee.value  && vi.annee  && vi.annee  !== 'Inconnu') fAnnee.value  = vi.annee;

          // Proposer la contribution à la base partagée IMMÉDIATEMENT après
          // l'identification — c'est le moment où l'utilisateur est concentré
          // sur le véhicule. Plutôt que d'attendre la fin du diagnostic.
          setTimeout(() => maybeProposeVinContribution(), 800);
        })
        .catch(() => {}); // silencieux si erreur
    }

    // Si pas de VIN lu, proposer la saisie manuelle
    if (!state.currentDiag.vin) {
      document.getElementById('vinManualZone')?.classList.remove('hidden');
      document.getElementById('btnEditVin')?.classList.add('hidden');
      toast('VIN non lu par la valise — vous pouvez le saisir manuellement', 'warning', 5000);
    }

  } catch (e) {
    toast('Erreur lecture OBD2 : ' + e.message, 'error');
    showStep('stepWelcome');
  }
}

// Émojis et libellés par famille — utilisés pour le regroupement DTC
const _DTC_FAMILY_ICON = {
  moteur_carburant_air:            '🔧', moteur_allumage_rates:           '⚡',
  moteur_injection_hp:             '💉', moteur_distribution:             '⚙️',
  moteur_lubrification_temperature:'🌡️', antipollution_egr:               '♻️',
  antipollution_fap_dpf:           '🌫️', antipollution_scr_adblue:        '💧',
  antipollution_nox:               '☁️', antipollution_evap:              '⛽',
  antipollution_catalyseur:        '🏭', antipollution_lambda:            '🔬',
  antipollution_air_secondaire:    '💨', turbo_suralimentation:           '🌀',
  prechauffage_diesel:             '🔥', transmission_boite:              '🔁',
  transmission_embrayage:          '🔗', freinage_abs:                    '🛑',
  esp_stabilite_traction:          '🛞', direction_assistee:              '🎯',
  climatisation_chauffage:         '❄️', carrosserie_eclairage_confort:   '💡',
  electronique_ecm_pcm:            '🧠', electronique_reseau_can:         '📡',
  electronique_alimentation:       '🔋', securite_airbags:                '🛡️',
  hybride_batterie_hv:             '🔋', hybride_moteur_electrique:       '⚡',
  hybride_recuperation_freinage:   '♻️', electrique_bms:                  '🧮',
  electrique_charge:               '🔌', electrique_inverter:             '⚡',
  non_classe:                      '❓',
};

function renderDiagnosticData(isSimulation) {
  const { vin, dtc_codes, dtc_info, dtc_families, mil_on, realtime, freeze_frame } = state.currentDiag;

  document.getElementById('vinDisplay').textContent = vin || 'VIN non lu';
  document.getElementById('vehicleLabel').textContent = 'Lecture en cours…';
  document.getElementById('simTag').classList.toggle('hidden', !isSimulation);

  const dtcEl = document.getElementById('dtcList');

  if (!dtc_codes || dtc_codes.length === 0) {
    dtcEl.innerHTML = '<span class="dtc-no-code">✅ Aucun code de défaut détecté</span>';
  } else {
    // ── Bandeau MIL (voyant antipollution allumé) ──
    let html = '';
    if (mil_on) {
      const milCount = dtc_codes.filter(c => dtc_info?.[c]?.mil).length || dtc_codes.length;
      html += `<div class="mil-banner">
        <span class="mil-banner-icon">🚨</span>
        <div class="mil-banner-text">
          <div class="mil-banner-title">Voyant antipollution allumé</div>
          <div class="mil-banner-sub">${milCount} code${milCount>1?'s':''} affectant les émissions</div>
        </div>
      </div>`;
    }

    // ── Regroupement par famille ──
    const byFamily = {};
    for (const code of dtc_codes) {
      const info = dtc_info?.[code] || {};
      const fam  = info.family || 'non_classe';
      (byFamily[fam] = byFamily[fam] || []).push({ code, info });
    }
    // Ordre : critiques d'abord (par nombre de critiques), puis warn, puis info
    const severityRank = { critical: 0, warn: 1, info: 2 };
    const familyKeys = Object.keys(byFamily).sort((a, b) => {
      const sa = Math.min(...byFamily[a].map(x => severityRank[x.info.severity] ?? 1));
      const sb = Math.min(...byFamily[b].map(x => severityRank[x.info.severity] ?? 1));
      if (sa !== sb) return sa - sb;
      return byFamily[b].length - byFamily[a].length;
    });

    for (const fam of familyKeys) {
      const items   = byFamily[fam];
      const famLbl  = (dtc_families && dtc_families[fam]) || (fam === 'non_classe' ? 'Non classé' : fam);
      const icon    = _DTC_FAMILY_ICON[fam] || '🔧';
      const critN   = items.filter(x => x.info.severity === 'critical').length;
      const warnN   = items.filter(x => x.info.severity === 'warn').length;
      const infoN   = items.filter(x => x.info.severity === 'info').length;
      const counts  = [
        critN ? `<span class="dtc-fam-pill dtc-fam-crit">${critN} critique${critN>1?'s':''}</span>` : '',
        warnN ? `<span class="dtc-fam-pill dtc-fam-warn">${warnN} à surveiller</span>` : '',
        infoN ? `<span class="dtc-fam-pill dtc-fam-info">${infoN} info</span>` : '',
      ].filter(Boolean).join(' ');

      html += `<div class="dtc-family">
        <div class="dtc-family-header">
          <span class="dtc-family-icon">${icon}</span>
          <span class="dtc-family-title">${escHtml(famLbl)}</span>
          <span class="dtc-family-counts">${counts}</span>
        </div>
        <div class="dtc-family-codes">`;
      for (const { code, info } of items) {
        const sev = info.severity || 'warn';
        const sevCls = `dtc-${sev}`;
        const fr  = info.fr || 'Description non disponible hors ligne';
        html += `<div class="dtc-row ${sevCls}">
          <span class="dtc-code">${escHtml(code)}</span>
          <span class="dtc-desc">${escHtml(fr)}</span>
        </div>`;
      }
      html += `</div></div>`;
    }
    dtcEl.innerHTML = html;
  }

  const clearBtn = document.getElementById('btnClearDTC');
  if (clearBtn) clearBtn.style.display = (dtc_codes && dtc_codes.length > 0) ? '' : 'none';

  // Freeze frame
  renderFreezeFrame(freeze_frame);
}

function renderFreezeFrame(ff) {
  const section = document.getElementById('freezeFrameSection');
  const grid    = document.getElementById('freezeFrameGrid');
  if (!ff || !Object.keys(ff).length) {
    section.classList.add('hidden');
    return;
  }
  const defs = [
    { key: 'speed_ff',           label: 'Vitesse',        unit: 'km/h' },
    { key: 'rpm_ff',             label: 'Régime',         unit: 'tr/min' },
    { key: 'coolant_temp_ff',    label: 'Température',    unit: '°C' },
    { key: 'engine_load_ff',     label: 'Charge moteur',  unit: '%' },
    { key: 'fuel_trim_short_ff', label: 'Correction CT',  unit: '%' },
    { key: 'fuel_trim_long_ff',  label: 'Correction LT',  unit: '%' },
    { key: 'throttle_ff',        label: 'Papillon',       unit: '%' },
  ];
  grid.innerHTML = defs
    .filter(d => ff[d.key] !== undefined && ff[d.key] !== null)
    .map(d => `
      <div class="ff-card">
        <div class="ff-label">${d.label}</div>
        <div class="ff-value">${ff[d.key]}</div>
        <div class="ff-unit">${d.unit}</div>
      </div>`).join('');
  section.classList.remove('hidden');
}

// ════════════════════════════════════════════════════════
//  AI RESULTS RENDER
// ════════════════════════════════════════════════════════
function renderAIResults(result) {
  const el = document.getElementById('aiResults');
  const statut = result.statut_global || 'OK';
  const emojis  = { 'URGENT': '🔴', 'SURVEILLER': '🟡', 'À SURVEILLER': '🟡', 'OK': '🟢' };
  const badgeCls= { 'URGENT': 'badge-urgent', 'SURVEILLER': 'badge-surveiller', 'À SURVEILLER': 'badge-surveiller', 'OK': 'badge-ok' };

  // Score de confiance global
  const confScore = result.diagnostic_confidence;
  const confHtml = confScore != null ? (() => {
    const pct = Math.max(0, Math.min(100, confScore));
    const confColor = pct >= 80 ? '#22c55e' : pct >= 60 ? '#f59e0b' : '#ef4444';
    const confLabel = pct >= 80 ? 'Diagnostic très fiable' : pct >= 60 ? 'Diagnostic fiable' : 'Incertitude — données insuffisantes';
    const limiteHtml = result.confidence_limite_par
      ? `<div style="font-size:.78rem;color:#64748b;margin-top:4px">⚠️ ${escHtml(result.confidence_limite_par)}</div>` : '';
    return `<div class="diag-confidence-bar">
      <div class="diag-confidence-label">
        <span>🎯 Fiabilité du diagnostic</span>
        <span style="color:${confColor};font-weight:700">${pct}% — ${confLabel}</span>
      </div>
      <div class="diag-confidence-track">
        <div class="diag-confidence-fill" style="width:${pct}%;background:${confColor}"></div>
      </div>
      ${limiteHtml}
    </div>`;
  })() : '';

  // Root cause analysis
  const rootCauseHtml = result.root_cause_analysis
    ? `<div class="root-cause-box">
        <div class="root-cause-title">🔍 Cause racine identifiée</div>
        <div class="root-cause-text">${escHtml(result.root_cause_analysis)}</div>
       </div>` : '';

  // Corrélations + sessions
  const corrHtml = result.correlations
    ? `<div class="correlations-box">📊 <strong>Corrélations :</strong> ${escHtml(result.correlations)}</div>` : '';

  let html = `
    <div class="ai-results-header">
      <div class="global-status">
        <span class="global-status-badge ${badgeCls[statut] || 'badge-ok'}">
          ${emojis[statut] || ''} ${statut}
        </span>
      </div>
      ${confHtml}
      ${rootCauseHtml}
      <p class="resume-text">${escHtml(result.resume || '')}</p>
      ${corrHtml}
    </div>`;

  const analyses = result.analyse || [];
  if (!analyses.length) {
    html += `<p style="color:var(--text-dim);font-size:.9rem;">Analyse non disponible.</p>`;
  }

  analyses.forEach((a, idx) => {
    const niveau   = a.urgence || a.niveau_urgence || '';
    const dtcEmojis= { 'URGENT': '🔴', 'SURVEILLER': '🟡', 'NON URGENT': '🟢' };
    const urgCls   = { 'URGENT': 'badge-urgent', 'SURVEILLER': 'badge-surveiller', 'NON URGENT': 'badge-ok' };
    const actionVal= a.action || a.action_recommandee || '';
    const fpProbable = a.faux_positif_probable !== undefined
      ? a.faux_positif_probable : (a.faux_positif?.probable || false);
    const fpRaison = a.raison_faux_positif || a.faux_positif?.explication || '';
    const defautConnu = a.defaut_constructeur_connu || false;

    // Badge cause principale vs secondaire
    const estPrincipal = a.est_cause_principale;
    const codeSecondaireDe = a.code_secondaire_de;
    const rootBadgeHtml = estPrincipal === true
      ? `<span class="badge-root-cause" title="Cause racine identifiée">🎯 CAUSE RACINE</span>`
      : (estPrincipal === false && codeSecondaireDe
        ? `<span class="badge-secondary-code" title="Code secondaire / conséquence">🔗 Secondaire de ${escHtml(codeSecondaireDe)}</span>`
        : '');

    const fpHtml = fpProbable
      ? `<div class="fp-alert">⚠️ <strong>Faux positif possible :</strong> ${escHtml(fpRaison)}</div>`
      : '';

    const defautHtml = defautConnu && a.detail_defaut_constructeur
      ? `<div class="dtc-section constructeur-known">
           <div class="dtc-section-label">🔧 Défaut constructeur connu</div>
           <div class="dtc-section-content">${escHtml(a.detail_defaut_constructeur)}</div>
         </div>` : '';

    const rappelHtml = a.rappel_constructeur && a.detail_rappel
      ? `<div class="dtc-section rappel-alert">
           <div class="dtc-section-label">📢 Rappel constructeur</div>
           <div class="dtc-section-content">${escHtml(a.detail_rappel)}</div>
         </div>` : '';

    const testHtml = a.test_recommande
      ? `<div class="dtc-section">
           <div class="dtc-section-label">🔁 Test recommandé</div>
           <div class="dtc-section-content">${escHtml(a.test_recommande)}</div>
         </div>` : '';

    const prixHtml = a.fourchette_prix
      ? `<div class="prix-box">
           <div class="prix-label">💶 Estimation réparation</div>
           ${escHtml(a.fourchette_prix)}
         </div>` : '';

    // Causes probables : nouveau format avec score ou ancien format texte
    const rawCauses = Array.isArray(a.causes_probables) && a.causes_probables.length
      ? a.causes_probables
      : (a.cause_probable ? [a.cause_probable] : []);

    let causesHtml = '';
    if (rawCauses.length) {
      const isNewFormat = typeof rawCauses[0] === 'object' && rawCauses[0] !== null && 'score' in rawCauses[0];
      if (isNewFormat) {
        const niveauColors = { 'ROUGE': '#ef4444', 'ORANGE': '#f59e0b', 'JAUNE': '#3b82f6' };
        const niveauEmoji  = { 'ROUGE': '🔴', 'ORANGE': '🟠', 'JAUNE': '🟡' };
        const fallbackColors = ['#ef4444','#f59e0b','#3b82f6','#8b5cf6','#64748b'];
        causesHtml = `<div class="dtc-section">
          <div class="dtc-section-label">Causes probables — probabilité estimée</div>
          <div class="causes-confidence-list">
            ${rawCauses.map((c, ci) => {
              const pct = Math.max(0, Math.min(100, c.score || 0));
              const color = niveauColors[c.niveau] || fallbackColors[ci] || '#64748b';
              const em = niveauEmoji[c.niveau] || (ci === 0 ? '🔴' : ci === 1 ? '🟠' : '🟡');
              const techHtml = c.explication_technique
                ? `<div class="cause-conf-tech">${escHtml(c.explication_technique)}</div>` : '';
              return `<div class="cause-confidence-item">
                <div class="cause-conf-header">
                  <span class="cause-conf-rank">${em}</span>
                  <span class="cause-conf-text">${escHtml(c.cause || '')}</span>
                  <span class="cause-conf-pct" style="color:${color}">${pct}%</span>
                </div>
                <div class="cause-conf-track">
                  <div class="cause-conf-fill" style="width:${pct}%;background:${color}"></div>
                </div>
                ${techHtml}
              </div>`;
            }).join('')}
          </div>
        </div>`;
      } else {
        causesHtml = `<div class="dtc-section">
          <div class="dtc-section-label">Causes probables</div>
          <ul class="causes-list">${rawCauses.map(c => `<li>${escHtml(typeof c === 'string' ? c : c.cause || '')}</li>`).join('')}</ul>
        </div>`;
      }
    }

    html += `
      <div class="dtc-analysis-card${estPrincipal === true ? ' dtc-card-root' : estPrincipal === false ? ' dtc-card-secondary' : ''}" id="card-${idx}">
        <div class="dtc-analysis-header" onclick="toggleCard(${idx})">
          <span class="dtc-code-label">${escHtml(a.code || '')}</span>
          ${rootBadgeHtml}
          <span class="dtc-desc">${escHtml(a.description || '')}</span>
          ${a.systeme ? `<span class="dtc-systeme">${escHtml(a.systeme)}</span>` : ''}
          <span class="urgency-tag ${urgCls[niveau] || 'badge-ok'}">${dtcEmojis[niveau] || ''} ${escHtml(niveau)}</span>
          ${defautConnu ? '<span class="badge-known" title="Défaut constructeur connu">🔧</span>' : ''}
          ${a.rappel_constructeur ? '<span class="badge-recall" title="Rappel constructeur">📢</span>' : ''}
        </div>
        <div class="dtc-analysis-body">
          ${causesHtml}
          ${defautHtml}
          ${rappelHtml}
          ${fpHtml ? `<div class="dtc-section">${fpHtml}</div>` : ''}
          <div class="dtc-section action-box">
            <div class="action-label">Action recommandée</div>
            <div class="action-value">${escHtml(actionVal)}</div>
            ${a.details_action ? `<div class="action-details">${escHtml(a.details_action)}</div>` : ''}
          </div>
          ${testHtml}
          ${prixHtml}
          ${Array.isArray(a.causes_exclues) && a.causes_exclues.length
            ? `<div class="dtc-section excl-section">
                <div class="dtc-section-label">⚫ Causes écartées</div>
                <ul class="excl-list-sm">${a.causes_exclues.map(c => {
                  if (typeof c === 'object' && c !== null && c.cause) {
                    return `<li><strong>${escHtml(c.cause)}</strong>${c.raison ? ` — ${escHtml(c.raison)}` : ''}</li>`;
                  }
                  return `<li>${escHtml(String(c))}</li>`;
                }).join('')}</ul>
               </div>` : ''}
        </div>
      </div>`;
  });

  // Analyse acoustique
  const acou = result.analyse_acoustique;
  if (acou && acou.applicable !== false) {
    html += `<div class="acoustique-box">
      <div class="acoustique-title">🔊 Analyse acoustique</div>
      ${acou.type_bruit ? `<div class="acoustique-row"><span class="acoustique-label">Type de bruit</span><span>${escHtml(acou.type_bruit)}</span></div>` : ''}
      ${acou.interpretation ? `<div class="acoustique-row"><span class="acoustique-label">Interprétation</span><span>${escHtml(acou.interpretation)}</span></div>` : ''}
      ${acou.coherence ? `<div class="acoustique-row"><span class="acoustique-label">Cohérence</span><span>${escHtml(acou.coherence)}</span></div>` : ''}
    </div>`;
  }

  // Plan d'action structuré
  const planAction = result.plan_action;
  if (Array.isArray(planAction) && planAction.length) {
    const prioriteCls = { 'URGENT': 'plan-urgent', 'IMPORTANT': 'plan-important', 'SI NÉCESSAIRE': 'plan-optional' };
    html += `<div class="plan-action-box">
      <div class="plan-action-title">🛠️ Plan d'action recommandé</div>
      <div class="plan-steps">
        ${planAction.map(step => `
          <div class="plan-step">
            <div class="plan-step-header">
              <span class="plan-step-num">Étape ${step.etape || ''}</span>
              ${step.priorite ? `<span class="plan-priorite ${prioriteCls[step.priorite] || ''}">${escHtml(step.priorite)}</span>` : ''}
            </div>
            <div class="plan-step-action">${escHtml(step.action || '')}</div>
            <div class="plan-step-meta">
              ${step.duree_estimee ? `<span>⏱ ${escHtml(step.duree_estimee)}</span>` : ''}
              ${step.cout_estime ? `<span>💶 ${escHtml(step.cout_estime)}</span>` : ''}
            </div>
          </div>`).join('')}
      </div>
    </div>`;
  }

  // Pièces à commander
  const pieces = result.pieces_necessaires;
  if (Array.isArray(pieces) && pieces.length) {
    const typeIcons = {
      capteur: '🔌', filtre: '🔶', pompe: '⚙️', joint: '🔩',
      courroie: '🔗', sonde: '🌡️', vanne: '🔧', injecteur: '💉', autre: '🔧'
    };
    const urgCls  = { 'URGENT': 'part-urgent', 'IMPORTANT': 'part-important', 'SI NÉCESSAIRE': 'part-optional' };
    const badgeCls= { 'URGENT': 'part-badge-urgent', 'IMPORTANT': 'part-badge-important', 'SI NÉCESSAIRE': 'part-badge-optional' };

    const cardsHtml = pieces.map(p => {
      const nom       = escHtml(p.nom || 'Pièce');
      const ref       = p.reference_probable;
      const brands    = p.marques_compatibles;
      const type      = (p.type_piece || 'autre').toLowerCase();
      const urgence   = p.urgence || 'IMPORTANT';
      const icon      = typeIcons[type] || '🔧';
      const cardCls   = urgCls[urgence] || 'part-important';
      const bCls      = badgeCls[urgence] || 'part-badge-important';

      const refHtml    = ref ? `<span class="part-ref">${escHtml(ref)}</span>` : '';
      const brandsHtml = brands ? `<div class="part-brands">Compatible : ${escHtml(brands)}</div>` : '';

      // Construire la requête la plus précise possible avec toutes les données disponibles
      const vehicle = state.fleet.find(v => v.vin === state.currentDiag?.vin) || {};
      // Récupérer motorisation depuis vin_info (analyse IA) ou fiche véhicule
      const vinInfo      = result.vin_info || state.currentDiag?.analyse_ia?.vin_info || {};
      const marque       = vehicle.marque       || vinInfo.marque       || '';
      const modele       = vehicle.modele       || vinInfo.modele       || '';
      const annee        = vehicle.annee        || vinInfo.annee        || '';
      const motorisation = vehicle.motorisation || vinInfo.motorisation || '';
      const carburant    = vinInfo.carburant     || '';

      // Requête Google Shopping : maximale — nom pièce + marque + modèle + motorisation + année + carburant
      const vContext = [marque, modele, motorisation, annee ? `${annee}` : '', carburant]
        .filter(Boolean).join(' ');
      const qGoogle  = [p.nom, vContext, 'pièce auto'].filter(Boolean).join(' ');

      // Requête sites spécialisés : nom pièce + marque + modèle + année (sans motorisation trop longue)
      const vShort   = [marque, modele, annee].filter(Boolean).join(' ');
      const qShops   = [p.nom, vShort].filter(Boolean).join(' ');

      // URLs
      const autodocUrl  = `https://www.autodoc.fr/search?keyword=${encodeURIComponent(qShops)}`;
      const oscaroUrl   = `https://www.oscaro.com/fr/search?q=${encodeURIComponent(qShops)}`;
      const googleUrl   = `https://www.google.fr/search?q=${encodeURIComponent(qGoogle)}&hl=fr&gl=fr&tbm=shop`;

      // Encodage sûr pour onclick inline
      const _esc = url => url.replace(/\\/g,'\\\\').replace(/'/g,"\\'");

      return `
        <div class="part-card ${cardCls}">
          <div class="part-icon">${icon}</div>
          <div class="part-info">
            <div class="part-name">${nom}</div>
            ${refHtml}
            ${brandsHtml}
          </div>
          <div class="part-actions">
            <span class="part-badge ${bCls}">${escHtml(urgence)}</span>
            <button class="btn-shop" onclick="openExternal('${_esc(autodocUrl)}')">🛒 Autodoc</button>
            <button class="btn-shop" onclick="openExternal('${_esc(oscaroUrl)}')">🛒 Oscaro</button>
            <button class="btn-shop" onclick="openExternal('${_esc(googleUrl)}')">🛍️ Shopping</button>
          </div>
        </div>`;
    }).join('');

    html += `
      <div class="parts-box">
        <div class="parts-box-title">🔩 Pièces à commander <span style="font-weight:400;font-size:.78rem;color:var(--text-muted);margin-left:4px">(références indicatives — vérifier la compatibilité avant commande)</span></div>
        <div class="parts-list">${cardsHtml}</div>
      </div>`;
  }

  // Causes globalement exclues
  const excluGlobaux = result.causes_exclues_globales;
  if (Array.isArray(excluGlobaux) && excluGlobaux.length) {
    html += `<div class="excluded-causes-box">
      <div class="excl-title">⚫ Causes écartées par le diagnostic global</div>
      <ul class="excl-list">${excluGlobaux.map(c => {
        if (typeof c === 'object' && c !== null && c.cause) {
          return `<li><strong>${escHtml(c.cause)}</strong>${c.raison ? ` — ${escHtml(c.raison)}` : ''}</li>`;
        }
        return `<li>${escHtml(String(c))}</li>`;
      }).join('')}</ul>
    </div>`;
  }

  // Résumé en bas uniquement si la barre de confiance n'est pas présente (ancien format)
  if (!confScore && result.resume) {
    html += `<div class="ai-summary-bubble">💬 ${escHtml(result.resume)}</div>`;
  }

  el.innerHTML = html;
}

function toggleCard(idx) {
  document.getElementById(`card-${idx}`)?.classList.toggle('expanded');
}

// ════════════════════════════════════════════════════════
//  BASE VIN PARTAGÉE — contribution post-diagnostic
// ════════════════════════════════════════════════════════
/** Constructeurs Renault/PSA/Mercedes/etc. par WMI — pour la vérif de cohérence */
const _WMI_BRANDS = {
  'VF1': 'Renault', 'VF6': 'Renault', 'VF7': 'Citroën',
  'VF3': 'Peugeot', 'VF8': 'Matra',
  'WBA': 'BMW', 'WBS': 'BMW', 'WBY': 'BMW',
  'WDB': 'Mercedes-Benz', 'WDC': 'Mercedes-Benz', 'WDD': 'Mercedes-Benz',
  'WAU': 'Audi', 'WVW': 'Volkswagen', 'WV1': 'Volkswagen', 'WV2': 'Volkswagen',
  'ZFA': 'Fiat', 'ZAR': 'Alfa Romeo', 'ZFF': 'Ferrari',
  'JF1': 'Subaru', 'JTM': 'Toyota', 'JN1': 'Nissan',
  'KMH': 'Hyundai', 'KNA': 'Kia',
  'TMB': 'Škoda', 'VSS': 'SEAT',
};

/** Vérifie que la marque saisie est cohérente avec le WMI (3 premiers chars du VIN). */
function checkVinWmiConsistency(vin, marque) {
  if (!vin || vin.length < 3 || !marque) return { ok: true };
  const wmi = vin.substring(0, 3).toUpperCase();
  const expected = _WMI_BRANDS[wmi];
  if (!expected) return { ok: true };  // WMI inconnu de notre table → on ne bloque pas
  const m = (marque || '').toLowerCase();
  const e = expected.toLowerCase();
  if (m.includes(e.split('-')[0]) || e.includes(m.split(' ')[0])) return { ok: true };
  return { ok: false, expected, given: marque, wmi };
}

/** Propose à l'utilisateur de contribuer à la base VIN partagée, dès la
 *  détection du véhicule. Toast avec champs ÉDITABLES — l'utilisateur peut
 *  corriger/compléter avant de contribuer (utile si décodage local imprécis
 *  ou modèle "Inconnu").
 *
 *  N'apparaît pas si :
 *   - VIN absent ou < 11 caractères
 *   - véhicule déjà confirmé par la communauté (verified)
 *   - toast déjà ouvert pour ce diag (anti-doublon) */
let _vinContribOpen = false;

/* ── Lecture kilométrage ────────────────────────────────────────────
 *
 *  Flow : essai automatique OBD (PID A6, ~2019+) → si KO, prompt manuel.
 *  Persisté dans flotte.json avec garde-fou anti-décroissance.            */

/** Affiche le km dans le bandeau véhicule avec badge source. */
function displayOdometer(km, source) {
  const el = document.getElementById('vehicleOdometer');
  if (!el || !km) return;
  const sourceBadge = source === 'manual'
    ? '✏️ saisi'
    : source === 'simulation'
      ? '🧪 simu'
      : '📡 OBD';
  const fmt = Number(km).toLocaleString('fr-FR');
  el.innerHTML = `📏 <strong>${fmt} km</strong> <span class="odo-badge">${sourceBadge}</span>`;
  el.classList.remove('hidden');
}

/** Tente la lecture OBD ; si échec, bascule sur saisie manuelle. */
async function fetchOdometerAuto(vin) {
  if (!vin) return;
  try {
    const result = await api('POST', '/api/odometer/read', { vin });

    if (result && result.ok) {
      displayOdometer(result.km, result.source);
      return;
    }

    // Cas km < dernier connu : confirmation utilisateur (compteur trafiqué ?
    // Tableau de bord remplacé ? Sinon, erreur de lecture probable).
    if (result && result.reason === 'km_decroissant') {
      const prevFmt = Number(result.previous || 0).toLocaleString('fr-FR');
      const kmFmt   = Number(result.km).toLocaleString('fr-FR');
      const ok = confirm(
        `⚠️ Kilométrage lu (${kmFmt} km) inférieur au dernier connu (${prevFmt} km).\n\n` +
        `Causes possibles :\n` +
        `• Compteur tableau de bord remplacé (légitime)\n` +
        `• Compteur trafiqué\n` +
        `• Erreur de lecture OBD\n\n` +
        `Enregistrer quand même la valeur lue ?`
      );
      if (ok) {
        await api('POST', '/api/odometer/manual',
                  { vin, km: result.km, force: true });
        displayOdometer(result.km, 'obd_pid_a6');
      }
      return;
    }

    // Sinon (not_supported, vehicle_not_found, etc.) → saisie manuelle
    await promptManualOdometer(vin);
  } catch (e) {
    console.warn('Lecture odomètre échouée', e);
  }
}

/** Demande à l'utilisateur de saisir le km manuellement (pré-rempli si connu). */
async function promptManualOdometer(vin) {
  // Pré-remplissage : on cherche le dernier km connu pour ce VIN dans la flotte
  let lastKm = '';
  try {
    const veh = (state.fleet || []).find(v => v.vin === vin);
    if (veh && veh.dernier_km) lastKm = String(veh.dernier_km);
  } catch {}

  const input = prompt(
    `Kilométrage non lisible via OBD pour ce véhicule.\n` +
    `Saisissez le kilométrage actuel (vide pour passer) :`,
    lastKm
  );
  if (input === null || input.trim() === '') return;

  const km = parseInt(input.replace(/[\s ]/g, ''), 10);
  if (isNaN(km) || km < 0 || km > 2_000_000) {
    toast('Kilométrage invalide', 'warning');
    return;
  }

  let result = await api('POST', '/api/odometer/manual', { vin, km });

  if (!result.ok && result.reason === 'km_decroissant') {
    const prevFmt = Number(result.previous || 0).toLocaleString('fr-FR');
    const ok = confirm(
      `⚠️ La valeur saisie (${km.toLocaleString('fr-FR')} km) est inférieure au ` +
      `dernier kilométrage connu (${prevFmt} km).\n\nValider quand même ?`
    );
    if (!ok) return;
    result = await api('POST', '/api/odometer/manual', { vin, km, force: true });
  }

  if (result.ok) {
    displayOdometer(km, 'manual');
    toast(`Kilométrage enregistré : ${km.toLocaleString('fr-FR')} km`, 'success');
  }
}

function maybeProposeVinContribution() {
  try {
    if (_vinContribOpen) return;  // déjà affiché
    const vin = state.currentDiag.vin;
    const vd  = state.currentDiag.vehicle_decoded || {};
    if (!vin || vin.length < 11) return;
    if (vd.source === 'community' && vd.shared_status === 'verified') return;

    const marque = (vd.marque && vd.marque !== 'Inconnu') ? vd.marque : '';
    const modele = (vd.modele && vd.modele !== 'Inconnu') ? vd.modele : '';
    const annee  = (vd.annee  && vd.annee  !== 'Inconnu') ? (vd.annee + '') : '';
    const motori = (vd.motorisation || '');

    // Détecte la marque attendue depuis le WMI pour pré-remplir si vide
    const wmiBrand = _WMI_BRANDS[vin.substring(0, 3).toUpperCase()] || '';
    const suggestedMarque = marque || wmiBrand;

    const id = 'vinContribToast_' + Date.now();
    const html = `
      <div class="vin-contrib-toast vin-contrib-editable" id="${id}">
        <div class="vin-contrib-header">
          <span class="vin-contrib-icon">👥</span>
          <div class="vin-contrib-title">Identifier ce véhicule pour la communauté</div>
          <button class="vin-contrib-close" id="${id}_close" title="Fermer">✕</button>
        </div>
        <div class="vin-contrib-body">
          <div class="vin-contrib-vincheck">
            VIN détecté : <code>${escHtml(vin)}</code>
            <div class="vin-contrib-hint">Vérifier sur la carte grise <strong>champ E</strong></div>
          </div>
          <div class="vin-contrib-fields">
            <div class="vin-contrib-field">
              <label for="${id}_marque">Marque</label>
              <input type="text" id="${id}_marque" value="${escHtml(suggestedMarque)}" placeholder="${escHtml(wmiBrand || 'ex: Renault')}" maxlength="50">
            </div>
            <div class="vin-contrib-field">
              <label for="${id}_modele">Modèle</label>
              <input type="text" id="${id}_modele" value="${escHtml(modele)}" placeholder="ex: Trafic III" maxlength="80">
            </div>
            <div class="vin-contrib-field vin-contrib-field-sm">
              <label for="${id}_annee">Année</label>
              <input type="number" id="${id}_annee" value="${escHtml(annee)}" placeholder="2020" min="1980" max="2050">
            </div>
            <div class="vin-contrib-field vin-contrib-field-lg">
              <label for="${id}_motori">Motorisation</label>
              <input type="text" id="${id}_motori" value="${escHtml(motori)}" placeholder="ex: 2.0 dCi 145" maxlength="120">
            </div>
          </div>
          <div class="vin-contrib-warn-zone" id="${id}_warn"></div>
          <div class="vin-contrib-cg-zone">
            <div class="vin-contrib-sep"><span>OU</span></div>
            <button type="button" class="vin-cg-btn" id="${id}_cg" title="L'image est analysée par Claude — jamais stockée">
              📷 Auto-remplir depuis la carte grise
            </button>
            <input type="file" id="${id}_cg_file" accept="image/jpeg,image/png,image/webp" capture="environment" style="display:none">
            <div class="vin-cg-status" id="${id}_cg_status"></div>
          </div>
        </div>
        <div class="vin-contrib-actions">
          <button class="btn btn-sm btn-outline" id="${id}_no">Plus tard</button>
          <button class="btn btn-sm btn-primary"  id="${id}_yes">✓ Partager</button>
        </div>
      </div>`;

    const host = document.getElementById('toastHost') || document.body;
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    host.appendChild(wrap.firstElementChild);
    _vinContribOpen = true;

    // Auto-dismiss différé : timer désactivable dès qu'on commence à interagir
    // (sélection photo carte grise, saisie dans un champ, etc.)
    let _dismissTimer = setTimeout(() => close(), 60000);
    const _cancelDismiss = () => {
      if (_dismissTimer) { clearTimeout(_dismissTimer); _dismissTimer = null; }
    };

    const close = () => {
      _cancelDismiss();
      document.getElementById(id)?.remove();
      _vinContribOpen = false;
    };

    const updateWmiWarn = () => {
      const mq = document.getElementById(id + '_marque').value.trim();
      const warn = document.getElementById(id + '_warn');
      const check = checkVinWmiConsistency(vin, mq);
      if (!check.ok && mq) {
        warn.innerHTML = `<div class="vin-contrib-warn">⚠️ VIN commence par <strong>${escHtml(check.wmi)}</strong> (généralement <strong>${escHtml(check.expected)}</strong>). Vérifiez la marque.</div>`;
      } else {
        warn.innerHTML = '';
      }
    };
    document.getElementById(id + '_marque').addEventListener('input', updateWmiWarn);
    updateWmiWarn();

    document.getElementById(id + '_close').addEventListener('click', close);
    document.getElementById(id + '_no').addEventListener('click', close);

    // ── Bouton 📷 carte grise : ouvrir le file picker ──
    const cgBtn  = document.getElementById(id + '_cg');
    const cgFile = document.getElementById(id + '_cg_file');
    const cgStat = document.getElementById(id + '_cg_status');
    cgBtn.addEventListener('click', () => {
      _cancelDismiss();    // l'utilisateur interagit : on ne ferme plus tout seul
      cgFile.click();
    });
    // Annule aussi le timer si l'utilisateur tape dans un champ
    ['_marque','_modele','_annee','_motori'].forEach(suffix => {
      document.getElementById(id + suffix)?.addEventListener('input', _cancelDismiss, { once: true });
    });

    cgFile.addEventListener('change', async () => {
      const file = cgFile.files[0];
      if (!file) return;
      // Confirme la non-rétention de l'image avant envoi
      if (!confirm("La photo de la carte grise va être analysée par Claude (Anthropic) :\n\n• Les champs techniques (VIN, marque, modèle, année, motorisation) sont extraits puis pré-remplis dans le formulaire.\n• Les données personnelles (nom, adresse) sont ignorées par l'IA.\n• La photo n'est ni stockée chez Lyvenia ni utilisée pour entraîner Claude.\n\nContinuer ?")) {
        cgFile.value = '';
        return;
      }
      cgStat.innerHTML = '<span class="vin-cg-loading">⏳ Extraction en cours…</span>';
      cgBtn.disabled = true;
      try {
        // Convertir l'image en base64
        const b64 = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result.split(',')[1]);  // strip data:...;base64,
          reader.onerror = () => reject(new Error('Lecture du fichier impossible'));
          reader.readAsDataURL(file);
        });
        const r = await api('POST', '/api/vin/extract-cartegrise', {
          image_base64: b64,
          media_type: file.type || 'image/jpeg',
        });
        if (r && r.ok) {
          // Pré-remplir les champs avec ce qu'a trouvé Claude
          if (r.marque)       document.getElementById(id + '_marque').value = r.marque;
          if (r.modele)       document.getElementById(id + '_modele').value = r.modele;
          if (r.annee)        document.getElementById(id + '_annee').value  = r.annee;
          if (r.motorisation) document.getElementById(id + '_motori').value = r.motorisation;
          // VIN : on vérifie qu'il matche celui détecté par OBD (sinon on alerte)
          if (r.vin && state.currentDiag.vin && r.vin !== state.currentDiag.vin) {
            cgStat.innerHTML = `<span class="vin-cg-warn">⚠️ VIN photo (${r.vin}) ≠ VIN OBD (${state.currentDiag.vin}). Vérifiez.</span>`;
          } else {
            const conf = r.confiance ? ` (confiance ${Math.round(r.confiance * 100)}%)` : '';
            cgStat.innerHTML = `<span class="vin-cg-success">✓ Données extraites${conf} — vérifiez et cliquez Partager</span>`;
          }
          updateWmiWarn();  // re-check WMI cohérence avec les nouvelles valeurs
        } else {
          cgStat.innerHTML = `<span class="vin-cg-error">✗ ${escHtml(r?.error || 'Échec extraction')}</span>`;
        }
      } catch (e) {
        cgStat.innerHTML = `<span class="vin-cg-error">✗ ${escHtml(e.message || 'Erreur réseau')}</span>`;
      } finally {
        cgBtn.disabled = false;
        cgFile.value = '';
      }
    });

    document.getElementById(id + '_yes').addEventListener('click', async () => {
      const mq = document.getElementById(id + '_marque').value.trim();
      const md = document.getElementById(id + '_modele').value.trim();
      const an = document.getElementById(id + '_annee').value.trim();
      const mt = document.getElementById(id + '_motori').value.trim();
      if (!mq || !md) {
        toast('Marque et modèle obligatoires', 'warning');
        return;
      }
      const check = checkVinWmiConsistency(vin, mq);
      if (!check.ok && !confirm(`Incohérence détectée :\nVIN commence par "${check.wmi}" (${check.expected}) mais vous indiquez "${check.given}".\n\nConfirmer quand même la contribution ?`)) {
        return;
      }
      try {
        const r = await api('POST', '/api/vin/contribute', {
          vin, marque: mq, modele: md,
          annee: an ? parseInt(an, 10) : null,
          motorisation: mt || null,
        });
        close();
        if (r && r.ok) {
          const n = r.contributions_count || 1;
          toast(`🙏 Merci ! ${n > 1 ? `Confirmation #${n} pour ce modèle` : '1ère identification de ce modèle'}.`, 'success');
        } else {
          toast('Contribution prise en compte', 'info');
        }
      } catch (e) {
        close();
        toast(`Impossible d'enregistrer : ${e.message || 'erreur réseau'}`, 'warning');
      }
    });

    // (Auto-dismiss déjà armé en début de fonction ; annulé dès interaction.)
  } catch (_) {}
}

// ════════════════════════════════════════════════════════
//  SAVE DIAGNOSTIC
// ════════════════════════════════════════════════════════
async function saveDiagnostic() {
  if (state.diagSaved) { toast('Diagnostic déjà sauvegardé', 'info'); return; }
  const { vin, dtc_codes, realtime, analyse_ia, kilometrage } = state.currentDiag;
  if (!vin || !analyse_ia) { toast('Lancez d\'abord une analyse IA', 'error'); return; }

  openTechModal(async (technicien) => {
    const statut = analyse_ia.statut_global || 'OK';
    const diagType = state.currentDiag.type || 'panne';
    try {
      const res = await api('POST', '/api/fleet/diagnostic', {
        vin, dtc_codes, donnees_temps_reel: realtime, analyse_ia, kilometrage, statut, technicien,
        type: diagType,
        session_ralenti: state.session_ralenti || null,
        session_roulant: state.session_roulant || null,
      });
      state.currentDiag.savedEntry = res.entry;
      state.diagSaved = true;
      document.getElementById('saveFeedback').classList.remove('hidden');
      toast('Diagnostic sauvegardé ✅', 'success');
      // (Le toast de contribution VIN s'affiche au moment de la lecture du
      //  VIN, plus pertinent UX que le moment de save.)
      // ── Alerte régression kilométrique ──
      if (res.entry?.km_alerte_fraude) {
        const prev = (res.entry.km_prev  || 0).toLocaleString('fr');
        const curr = (res.entry.kilometrage || 0).toLocaleString('fr');
        toast(`⚠️ Compteur suspect : ${prev} km → ${curr} km — Régression détectée !`, 'error', 12000);
      }
      // ── Nouveau véhicule → attribuer un code ──
      if (res.is_new) {
        const ai = state.currentDiag.analyse_ia;
        const vi = ai?.vin_info || {};
        const label = [vi.marque, vi.modele, vi.annee].filter(Boolean).join(' ') || vin;
        setTimeout(() => openAssignCodeModal(vin, label), 800);
      }
      await loadFleet();
    } catch (e) {
      toast('Erreur sauvegarde : ' + e.message, 'error');
    }
  });
}

// ════════════════════════════════════════════════════════
//  CLEAR DTC
// ════════════════════════════════════════════════════════
function openClearModal() { document.getElementById('modalClearDTC').classList.remove('hidden'); }
function closeClearModal() { document.getElementById('modalClearDTC').classList.add('hidden'); }

async function confirmClearDTC() {
  closeClearModal();
  try {
    const r = await api('POST', '/api/dtc/clear');
    const cleared   = r.cleared   || [];
    const remaining = r.remaining || [];

    if (r.success && !r.partial) {
      // Tout effacé
      toast(r.message, 'success', 3500);
      state.currentDiag.dtc_codes = [];
      state.currentDiag.freeze_frame = {};
      document.getElementById('dtcList').innerHTML =
        '<span class="dtc-no-code">✅ Aucun code de défaut détecté</span>';
      document.getElementById('freezeFrameSection').classList.add('hidden');

    } else if (r.success && r.partial) {
      // Effacement partiel
      toast(`⚠️ ${r.message}`, 'warning', 6000);
      // Mettre à jour l'état avec seulement les codes restants
      state.currentDiag.dtc_codes = remaining;
      const dtcEl = document.getElementById('dtcList');
      if (dtcEl) {
        let html = '';
        if (cleared.length) {
          html += cleared.map(c =>
            `<span class="dtc-badge dtc-cleared" title="Code effacé">✅ ${escHtml(c)}</span>`
          ).join('');
        }
        html += remaining.map(c =>
          `<span class="dtc-badge dtc-permanent" title="Non effaçable — défaut actif ou code permanent">🔒 ${escHtml(c)}</span>`
        ).join('');
        dtcEl.innerHTML = html +
          `<div class="dtc-permanent-note">🔒 Les codes verrouillés sont permanents (PDTC) ou le défaut est toujours actif. Réparez d'abord le problème physique.</div>`;
      }

    } else {
      // Rien effacé
      toast(`🔒 ${r.message}`, 'error', 6000);
      const dtcEl = document.getElementById('dtcList');
      if (dtcEl && remaining.length) {
        dtcEl.innerHTML = remaining.map(c =>
          `<span class="dtc-badge dtc-permanent" title="Non effaçable">🔒 ${escHtml(c)}</span>`
        ).join('') +
          `<div class="dtc-permanent-note">🔒 Ces codes ne peuvent pas être effacés par l'outil — défaut toujours présent ou code OBD permanent (PDTC). Le calculateur les effacera automatiquement après plusieurs cycles de conduite sans défaut.</div>`;
      }
    }
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  EXPORT PDF
// ════════════════════════════════════════════════════════
async function exportPDF(vin, diagEntry) {
  toast('Génération du PDF…', 'info', 6000);
  try {
    const r = await saveFile('/api/export/pdf', { vin, diagnostic: diagEntry });
    toast(`PDF sauvegardé : ${r.filename} — <button class="toast-btn" onclick="openExportsFolder()">📂 Ouvrir</button>`, 'success', 8000);
  } catch (e) {
    toast('Erreur PDF : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  HISTORY — Vue véhicule tabulée
// ════════════════════════════════════════════════════════
async function renderHistory(vin) {
  const container = document.getElementById('historyContainer');
  try {
    const [vehicle, history, repairs] = await Promise.all([
      api('GET', `/api/fleet/vehicle/${encodeURIComponent(vin)}`),
      api('GET', `/api/fleet/vehicle/${encodeURIComponent(vin)}/history`),
      api('GET', `/api/fleet/vehicle/${encodeURIComponent(vin)}/repairs`),
    ]);

    let healthData = {};
    try { healthData = await api('GET', `/api/fleet/vehicle/${encodeURIComponent(vin)}/health`); } catch(_) {}

    window._currentHistory = { vin, history, vehicle, repairs };

    const label = [vehicle.marque, vehicle.modele, vehicle.annee].filter(Boolean).join(' ');

    // ── Health score ──
    let healthHtml = '';
    if (healthData?.score !== undefined) {
      const hColor = { ok: 'var(--success)', warn: 'var(--warning)', danger: 'var(--danger)' }[healthData.color] || 'var(--accent)';
      healthHtml = `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:16px">
        <div style="position:relative;width:48px;height:48px;flex-shrink:0">
          <svg viewBox="0 0 36 36" style="transform:rotate(-90deg);width:48px;height:48px">
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border)" stroke-width="3"/>
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="${hColor}" stroke-width="3"
              stroke-dasharray="${healthData.score} ${100 - healthData.score}" stroke-dashoffset="0"/>
          </svg>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:.72rem;font-weight:700;color:${hColor}">${healthData.score}</div>
        </div>
        <div>
          <div style="font-weight:700;color:${hColor}">${healthData.label}</div>
          <div style="font-size:.75rem;color:var(--text-muted)">${(healthData.issues || []).join(' · ') || 'Aucun problème détecté'}</div>
        </div>
      </div>`;
    }

    // ── En-tête véhicule ──
    const motori = vehicle.motorisation ? `<span style="margin-left:8px;color:var(--accent)">· ${escHtml(vehicle.motorisation)}</span>` : '';
    const html = `
      <div class="history-header">
        <div>
          <div class="history-title">${escHtml(label || 'Véhicule')}</div>
          <div style="font-size:.78rem;color:var(--text-muted);margin-top:3px">VIN : ${escHtml(vin)}${motori}</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <button class="btn btn-outline btn-sm" onclick="openCompareModal('${vin}', window._currentHistory?.history || [])">🔄 Comparer</button>
          <button class="btn btn-sm" style="background:var(--danger,#e53935);color:#fff;border:none" onclick="deleteVehicle('${escHtml(vin)}')">🗑️</button>
        </div>
      </div>
      ${healthHtml}
      <div class="vtab-bar">
        <button class="vtab active" id="vtab-btn-diagnostics" onclick="switchVTab('diagnostics','${vin}',this)">📋 Diagnostics${history.length ? ` (${history.length})` : ''}</button>
        <button class="vtab" id="vtab-btn-entretiens"  onclick="switchVTab('entretiens','${vin}',this)">🔧 Entretiens</button>
        <button class="vtab" id="vtab-btn-documents"   onclick="switchVTab('documents','${vin}',this)">📁 Documents</button>
        <button class="vtab" id="vtab-btn-infos"       onclick="switchVTab('infos','${vin}',this)">ℹ️ Infos</button>
      </div>
      <div id="vtab-content"></div>`;

    container.innerHTML = html;
    window._currentHistory = { vin, history, vehicle, repairs };
    renderVTabDiagnostics(vin, history);

  } catch (e) {
    container.innerHTML = `<div class="empty-state">Erreur chargement : ${escHtml(e.message)}</div>`;
  }
}

// ── Switching d'onglet ────────────────────────────────
async function switchVTab(tabName, vin, btn) {
  document.querySelectorAll('.vtab').forEach(b => b.classList.remove('active'));
  btn?.classList.add('active');
  const el = document.getElementById('vtab-content');
  if (!el) return;
  const cache = window._currentHistory || {};
  switch (tabName) {
    case 'diagnostics': renderVTabDiagnostics(vin, cache.history || []); break;
    case 'entretiens':  await renderVTabEntretiens(vin, el); break;
    case 'documents':   await renderVTabDocuments(vin, el); break;
    case 'infos':       renderVTabInfos(cache.vehicle || {}, cache.repairs || [], vin, el); break;
  }
}

// ── Tab 1 : Diagnostics ───────────────────────────────
let _diagSort = 'date_desc';

function renderVTabDiagnostics(vin, history) {
  const el = document.getElementById('vtab-content');
  if (!el) return;
  const dotClass  = { 'URGENT': 'dot-urgent', 'SURVEILLER': 'dot-warn', 'À SURVEILLER': 'dot-warn', 'OK': 'dot-ok' };
  const dtcEmojis = { 'URGENT': '🔴', 'SURVEILLER': '🟡', 'À SURVEILLER': '🟡', 'NON URGENT': '🟢' };
  const suiviCfg  = {
    ouvert:   { cls: 'suivi-ouvert',   icon: '🔴', label: 'À traiter' },
    en_cours: { cls: 'suivi-en-cours', icon: '🟡', label: 'En cours' },
    resolu:   { cls: 'suivi-resolu',   icon: '✅', label: 'Résolu' },
  };

  if (!history.length) {
    el.innerHTML = '<div class="empty-state">Aucun diagnostic enregistré pour ce véhicule.</div>';
    return;
  }

  // Trier selon le mode courant
  const graviteOrder = { 'URGENT': 0, 'SURVEILLER': 1, 'À SURVEILLER': 1, 'OK': 2 };
  const suiviOrder   = { 'ouvert': 0, 'en_cours': 1, 'resolu': 2 };
  let sorted = [...history];
  if (_diagSort === 'date_asc')    sorted.sort((a, b) => new Date(a.date) - new Date(b.date));
  else if (_diagSort === 'gravite') sorted.sort((a, b) => (graviteOrder[a.statut||'OK']||2) - (graviteOrder[b.statut||'OK']||2));
  else if (_diagSort === 'statut')  sorted.sort((a, b) => (suiviOrder[a.statut_suivi||'ouvert']||0) - (suiviOrder[b.statut_suivi||'ouvert']||0));
  else sorted.sort((a, b) => new Date(b.date) - new Date(a.date)); // date_desc par défaut

  // Compteur de pannes ouvertes
  const nbOuvertes = history.filter(e => (e.statut_suivi || 'ouvert') !== 'resolu' && (e.statut || 'OK') !== 'OK').length;

  let tlItems = '';
  sorted.forEach((entry, i) => {
    const statut      = entry.statut || 'OK';
    const suiviKey    = entry.statut_suivi || 'ouvert';
    const suivi       = suiviCfg[suiviKey] || suiviCfg.ouvert;
    const dotCls      = dotClass[statut] || 'dot-default';
    const dtcStr      = entry.dtc_codes?.length ? entry.dtc_codes.join(', ') : '✅ Aucun défaut';
    const analyses    = Array.isArray(entry.analyse_ia?.analyse) ? entry.analyse_ia.analyse : [];
    const diagId      = entry.id || i;

    // Km delta — chercher le précédent dans le tableau trié (chronologique)
    const prevEntry   = sorted[i + 1];
    const kmDelta     = prevEntry ? entry.kilometrage - prevEntry.kilometrage : null;
    const kmDeltaHtml = (kmDelta !== null && kmDelta !== 0)
      ? `<div class="tl-gap"><span class="tl-km-delta">${kmDelta > 0 ? '+' : ''}${kmDelta.toLocaleString('fr')} km depuis le précédent</span></div>` : '';
    const fraudHtml   = entry.km_alerte_fraude
      ? `<div class="tl-fraud-banner">⚠️ Régression compteur — ${(entry.km_prev||0).toLocaleString('fr')} km → ${(entry.kilometrage||0).toLocaleString('fr')} km</div>` : '';

    // ── Résumé codes DTC ──
    const analysesHtml = analyses.map(a => {
      const niveau = a.urgence || a.niveau_urgence || '';
      const action = a.action || a.action_recommandee || '';
      const prix   = a.fourchette_prix ? `<span class="doss-prix">💶 ${escHtml(a.fourchette_prix)}</span>` : '';
      return `<div class="doss-dtc-row">
        <span class="doss-dtc-code">${dtcEmojis[niveau]||'⚪'} ${escHtml(a.code||'')}</span>
        <span class="doss-dtc-desc">${escHtml(a.description||'')}</span>
        ${action ? `<span class="doss-dtc-action">→ ${escHtml(action)}</span>` : ''}
        ${prix}
      </div>`;
    }).join('');

    // ── Plan d'action ──
    const plan = entry.plan_action || entry.analyse_ia?.plan_action || [];
    const prioIcon = { 'URGENT': '🔴', 'IMPORTANT': '🟡', 'SI NÉCESSAIRE': '🟢' };
    const planHtml = plan.length ? `
      <div class="doss-section">
        <div class="doss-section-title">🛠️ Plan d'action</div>
        ${plan.map(s => `
          <div class="doss-plan-row">
            <span class="doss-plan-num">Étape ${s.etape||''}</span>
            <span class="doss-plan-prio">${prioIcon[s.priorite]||''} ${escHtml(s.priorite||'')}</span>
            <span class="doss-plan-action">${escHtml(s.action||'')}</span>
            <span class="doss-plan-meta">${s.duree_estimee ? `⏱ ${escHtml(s.duree_estimee)}` : ''} ${s.cout_estime ? `· 💶 ${escHtml(s.cout_estime)}` : ''}</span>
          </div>`).join('')}
      </div>` : '';

    // ── Pièces à commander ──
    const pieces = entry.pieces_necessaires || entry.analyse_ia?.pieces_necessaires || [];
    const typeIcons = { capteur:'🔌', filtre:'🔶', pompe:'⚙️', joint:'🔩', courroie:'🔗', sonde:'🌡️', vanne:'🔧', injecteur:'💉', autre:'🔧' };
    const piecesHtml = pieces.length ? `
      <div class="doss-section">
        <div class="doss-section-title">🔩 Pièces à commander</div>
        ${pieces.map(p => {
          const vehicle   = state.fleet.find(v => v.vin === vin) || {};
          const vinInfo   = entry.analyse_ia?.vin_info || {};
          const marque    = vehicle.marque || vinInfo.marque || '';
          const modele    = vehicle.modele || vinInfo.modele || '';
          const annee     = vehicle.annee  || vinInfo.annee  || '';
          const motorisation = vehicle.motorisation || vinInfo.motorisation || '';
          const vShort    = [marque, modele, annee].filter(Boolean).join(' ');
          const vContext  = [marque, modele, motorisation, annee].filter(Boolean).join(' ');
          const qShops    = encodeURIComponent(`${p.nom} ${vShort}`);
          const qGoogle   = encodeURIComponent(`${p.nom} ${vContext} pièce auto`);
          const autodocUrl = `https://www.autodoc.fr/search?keyword=${qShops}`;
          const oscaroUrl  = `https://www.oscaro.com/fr/search?q=${qShops}`;
          const googleUrl  = `https://www.google.fr/search?q=${qGoogle}&hl=fr&gl=fr&tbm=shop`;
          const _esc = u => u.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
          const icon = typeIcons[(p.type_piece||'autre').toLowerCase()] || '🔧';
          const urgCls = p.urgence === 'URGENT' ? 'part-badge-urgent' : p.urgence === 'SI NÉCESSAIRE' ? 'part-badge-optional' : 'part-badge-important';
          return `<div class="doss-part-row">
            <span class="doss-part-icon">${icon}</span>
            <span class="doss-part-name">${escHtml(p.nom||'')}</span>
            ${p.reference_probable ? `<span class="part-ref">${escHtml(p.reference_probable)}</span>` : ''}
            ${p.marques_compatibles ? `<span class="doss-part-brands">${escHtml(p.marques_compatibles)}</span>` : ''}
            <span class="part-badge ${urgCls}">${escHtml(p.urgence||'')}</span>
            <div class="doss-part-btns">
              <button class="btn-shop" onclick="openExternal('${_esc(autodocUrl)}')">Autodoc</button>
              <button class="btn-shop" onclick="openExternal('${_esc(oscaroUrl)}')">Oscaro</button>
              <button class="btn-shop" onclick="openExternal('${_esc(googleUrl)}')">🛍️</button>
            </div>
          </div>`;
        }).join('')}
      </div>` : '';

    // ── Notes de réparation ──
    const notesVal   = escHtml(entry.notes_reparation || '');
    const notesHtml  = `
      <div class="doss-section">
        <div class="doss-section-title">📝 Notes de réparation</div>
        <textarea class="doss-notes-input" id="notes-${diagId}" placeholder="Décrire les réparations effectuées, pièces montées, observations…">${notesVal}</textarea>
        <button class="btn btn-sm btn-outline" style="margin-top:6px" onclick="saveSuiviNotes('${vin}','${diagId}')">💾 Sauvegarder</button>
      </div>`;

    // ── Header du dossier ──
    const tech = entry.technicien ? `<span class="doss-tech">👤 ${escHtml(entry.technicien)}</span>` : '';
    const rt   = entry.donnees_temps_reel || {};
    const rtStr= [rt.speed!==undefined?`${rt.speed} km/h`:null, rt.rpm!==undefined?`${rt.rpm} tr/min`:null,
      rt.coolant_temp!==undefined?`${rt.coolant_temp}°C`:null].filter(Boolean).join(' · ');

    tlItems += `
    <div class="tl-entry">
      <div class="tl-dot ${dotCls}"></div>
      ${fraudHtml}
      <div class="doss-card${entry.km_alerte_fraude?' fraud-border':''}" id="doss-${i}">

        <div class="doss-header" onclick="toggleDoss(${i})">
          <div class="doss-header-left">
            <span class="doss-date">📅 ${escHtml(entry.date_affichage||'')}</span>
            <span class="doss-km">🛣 ${(entry.kilometrage||0).toLocaleString('fr')} km</span>
            ${entry.km_alerte_fraude ? '<span class="doss-fraud-tag">⚠️ Suspect</span>' : ''}
            ${tech}
          </div>
          <div class="doss-header-right">
            <span class="doss-dtc-badge">${dtcStr}</span>
            <span class="doss-suivi-badge ${suivi.cls}" onclick="event.stopPropagation();cycleSuivi('${vin}','${diagId}',this)">${suivi.icon} ${suivi.label}</span>
            <span class="doss-chevron">▾</span>
          </div>
        </div>

        <div class="doss-body">
          ${rtStr ? `<div class="doss-rt">${rtStr}</div>` : ''}
          ${entry.analyse_ia?.resume ? `<div class="doss-resume">${escHtml(entry.analyse_ia.resume)}</div>` : ''}

          ${analyses.length ? `<div class="doss-section"><div class="doss-section-title">🔍 Codes détectés</div>${analysesHtml}</div>` : ''}
          ${planHtml}
          ${piecesHtml}
          ${notesHtml}

          <div class="doss-actions">
            <button class="btn btn-outline btn-sm" onclick="exportHistoryEntry('${vin}',${i})">📄 PDF Technicien</button>
            <button class="btn btn-outline btn-sm" onclick="exportClientPDFEntry('${vin}',${i})">🧾 Fiche Client</button>
          </div>
        </div>
      </div>
      ${kmDeltaHtml}
    </div>`;
  });

  const nbHtml = nbOuvertes > 0
    ? `<div class="doss-open-count">🔴 ${nbOuvertes} panne${nbOuvertes>1?'s':''} non résolue${nbOuvertes>1?'s':''}</div>` : '';

  const sortBar = `
    <div class="diag-sort-bar">
      <span class="diag-sort-label">Trier :</span>
      <button class="diag-sort-btn${_diagSort==='date_desc'?' active':''}" onclick="setDiagSort('date_desc','${vin}')">📅 Plus récent</button>
      <button class="diag-sort-btn${_diagSort==='date_asc'?' active':''}"  onclick="setDiagSort('date_asc','${vin}')">📅 Plus ancien</button>
      <button class="diag-sort-btn${_diagSort==='gravite'?' active':''}"   onclick="setDiagSort('gravite','${vin}')">🔴 Gravité</button>
      <button class="diag-sort-btn${_diagSort==='statut'?' active':''}"    onclick="setDiagSort('statut','${vin}')">🔄 Statut suivi</button>
    </div>`;

  el.innerHTML = `${nbHtml}${sortBar}<div class="tl-wrap">${tlItems}</div>${renderEvolutionCharts(vin, history)}`;
  initEvolutionCharts(history);
  // Initialiser data-suivi sur chaque badge après injection HTML
  sorted.forEach(entry => {
    const diagId = entry.id || '';
    const badge  = el.querySelector(`.doss-suivi-badge[onclick*="'${diagId}'"]`);
    if (badge) badge.dataset.suivi = entry.statut_suivi || 'ouvert';
  });
}

function setDiagSort(mode, vin) {
  _diagSort = mode;
  const cache = window._currentHistory || {};
  renderVTabDiagnostics(vin, cache.history || []);
}

function toggleDoss(i) {
  document.getElementById(`doss-${i}`)?.classList.toggle('expanded');
}

const _SUIVI_CYCLE = ['ouvert', 'en_cours', 'resolu'];
async function cycleSuivi(vin, diagId, badgeEl) {
  const suiviCfg = {
    ouvert:   { cls: 'suivi-ouvert',   icon: '🔴', label: 'À traiter' },
    en_cours: { cls: 'suivi-en-cours', icon: '🟡', label: 'En cours' },
    resolu:   { cls: 'suivi-resolu',   icon: '✅', label: 'Résolu' },
  };
  const current = badgeEl.dataset.suivi || 'ouvert';
  const nextIdx = (_SUIVI_CYCLE.indexOf(current) + 1) % _SUIVI_CYCLE.length;
  const next    = _SUIVI_CYCLE[nextIdx];
  try {
    await api('PUT', `/api/fleet/vehicle/${encodeURIComponent(vin)}/diagnostic/${diagId}/suivi`, { statut_suivi: next });
    badgeEl.dataset.suivi = next;
    const cfg = suiviCfg[next];
    badgeEl.className = `doss-suivi-badge ${cfg.cls}`;
    badgeEl.textContent = `${cfg.icon} ${cfg.label}`;
    // Mettre à jour en mémoire
    const vehicle = state.fleet.find(v => v.vin === vin);
    if (vehicle) {
      const entry = vehicle.historique?.find(e => (e.id || '') === diagId);
      if (entry) entry.statut_suivi = next;
    }
    // Recalculer le compteur
    const allEntries = document.querySelectorAll('.doss-suivi-badge');
    const nbOuvertes = [...allEntries].filter(b => b.dataset.suivi !== 'resolu' && b.closest('.doss-card')?.querySelector('.tl-dot:not(.dot-ok)')).length;
    const counter = document.querySelector('.doss-open-count');
    if (counter) counter.textContent = nbOuvertes > 0 ? `🔴 ${nbOuvertes} panne${nbOuvertes>1?'s':''} non résolue${nbOuvertes>1?'s':''}` : '';
  } catch(e) { toast('Erreur mise à jour suivi', 'error'); }
}

async function saveSuiviNotes(vin, diagId) {
  const textarea = document.getElementById(`notes-${diagId}`);
  if (!textarea) return;
  try {
    await api('PUT', `/api/fleet/vehicle/${encodeURIComponent(vin)}/diagnostic/${diagId}/suivi`, { notes_reparation: textarea.value.trim() });
    toast('Notes sauvegardées ✅', 'success', 2500);
  } catch(e) { toast('Erreur sauvegarde notes', 'error'); }
}

// ── Tab 2 : Entretiens ────────────────────────────────
async function renderVTabEntretiens(vin, el) {
  el.innerHTML = '<div style="color:var(--text-muted);padding:16px">Chargement…</div>';
  try {
    const cache  = window._currentHistory || {};
    const hist   = cache.history || [];
    const lastKm = cache.vehicle?.km_manuel || hist[0]?.kilometrage || 0;
    const items  = await api('GET', `/api/maintenance/vehicle/${encodeURIComponent(vin)}`);

    const statusCfg = {
      ok:      { cls: 'maint-ok',      icon: '✅', label: 'OK' },
      warning: { cls: 'maint-warning', icon: '⚠️', label: 'Bientôt' },
      urgent:  { cls: 'maint-urgent',  icon: '🔴', label: 'Dépassé / Urgent' },
      unknown: { cls: 'maint-unknown', icon: '❓', label: 'Non renseigné' },
    };

    // Grouper par catégorie
    const cats = {};
    for (const item of items) {
      const cat = item.category || 'Autre';
      if (!cats[cat]) cats[cat] = [];
      cats[cat].push(item);
    }

    let rows = '';
    for (const [cat, catItems] of Object.entries(cats)) {
      rows += `<tr class="maint-cat-header"><td colspan="5">${escHtml(cat)}</td></tr>`;
      for (const item of catItems) {
        const s = statusCfg[item.status] || statusCfg.unknown;
        let infoCol = '', actionCol = '';

        if (item.type === 'scheduled') {
          const lastDone = item.last_km ? `Fait à ${item.last_km.toLocaleString('fr')} km` : 'Jamais enregistré';
          const nextKmStr = item.next_km ? `Prochain : ${item.next_km.toLocaleString('fr')} km` : '—';
          const nextDateStr = item.next_date ? ` · ${item.next_date}` : '';
          const remStr = item.next_km
            ? (item.next_km - lastKm > 0 ? `dans ${(item.next_km - lastKm).toLocaleString('fr')} km` : 'dépassé')
            : '';
          infoCol = `<div style="font-size:.8rem;color:var(--text-muted)">${lastDone}</div>
            <div style="font-size:.78rem;color:var(--text-dim)">${nextKmStr}${nextDateStr} ${remStr?`<em>(${remStr})</em>`:''}</div>`;
          actionCol = `<button class="btn btn-outline btn-sm" onclick="showMaintDoneForm('${vin}','${item.id}',${lastKm},this)">✔ Marquer effectué</button>
            <div id="maint-form-${item.id}" style="display:none" class="maint-done-form">
              <input type="number" id="maint-km-${item.id}" placeholder="km effectué" value="${lastKm}" min="0" step="100"/>
              <input type="date" id="maint-dt-${item.id}" value="${new Date().toISOString().slice(0,10)}"/>
              <button class="btn btn-primary btn-sm" onclick="saveMaintDone('${vin}','${item.id}')">💾 Sauvegarder</button>
            </div>`;
        } else {
          // Wear item
          const states = item.wear_states || ['OK', 'À changer'];
          const opts = states.map(st => `<option value="${st}"${st===item.wear_state?' selected':''}>${escHtml(st)}</option>`).join('');
          const updStr = item.updated_km ? `mis à jour à ${item.updated_km.toLocaleString('fr')} km` : '';
          infoCol = `<div style="font-size:.78rem;color:var(--text-muted)">${updStr}</div>`;
          actionCol = `<select class="maint-wear-select" onchange="saveWearState('${vin}','${item.id}',this.value,${lastKm})">${opts}</select>`;
        }

        rows += `<tr>
          <td style="font-size:1.1rem;text-align:center;width:36px">${item.icon||'🔧'}</td>
          <td><div style="font-weight:600;font-size:.88rem">${escHtml(item.label)}</div>${infoCol}</td>
          <td style="white-space:nowrap">${item.type==='scheduled'&&item.interval_km?`/${item.interval_km.toLocaleString('fr')} km`:(item.interval_months?`/${item.interval_months} mois`:'—')}</td>
          <td><span class="maint-status-badge ${s.cls}">${s.icon} ${s.label}</span></td>
          <td style="min-width:180px">${actionCol}</td>
        </tr>`;
      }
    }

    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px">
        <div style="font-size:.82rem;color:var(--text-muted)">Km actuel : <strong>${lastKm.toLocaleString('fr')} km</strong></div>
        <button class="btn btn-outline btn-sm" onclick="exportMaintenancePDF('${vin}')">📋 Fiche entretien PDF</button>
      </div>
      <div style="overflow-x:auto">
        <table class="maint-table">
          <thead><tr>
            <th></th><th>Opération</th><th>Intervalle</th><th>Statut</th><th>Action</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch(e) {
    el.innerHTML = `<div class="empty-state">Erreur entretiens : ${escHtml(e.message)}</div>`;
  }
}

function showMaintDoneForm(vin, itemId, lastKm, btn) {
  const form = document.getElementById(`maint-form-${itemId}`);
  if (!form) return;
  form.style.display = form.style.display === 'none' ? 'flex' : 'none';
}

async function saveMaintDone(vin, itemId) {
  const kmEl = document.getElementById(`maint-km-${itemId}`);
  const dtEl = document.getElementById(`maint-dt-${itemId}`);
  if (!kmEl) return;
  try {
    await api('POST', `/api/maintenance/vehicle/${encodeURIComponent(vin)}/done/${itemId}`, { km: parseInt(kmEl.value||0), date: dtEl?.value || '' });
    toast('Entretien enregistré ✅', 'success');
    const el = document.getElementById('vtab-content');
    if (el) await renderVTabEntretiens(vin, el);
  } catch(e) { toast('Erreur : ' + e.message, 'error'); }
}

async function saveWearState(vin, itemId, state, km) {
  try {
    await api('PUT', `/api/maintenance/vehicle/${encodeURIComponent(vin)}/wear/${itemId}`, { wear_state: state, km });
    toast('État mis à jour ✅', 'success');
  } catch(e) { toast('Erreur : ' + e.message, 'error'); }
}

// ── Tab 3 : Documents ─────────────────────────────────
async function renderVTabDocuments(vin, el) {
  el.innerHTML = '<div style="color:var(--text-muted);padding:16px">Chargement…</div>';
  try {
    const docs = await api('GET', `/api/export/documents/${vin}`);
    if (!docs.length) {
      el.innerHTML = `<div class="empty-state">
        Aucun PDF enregistré pour ce véhicule.<br>
        <small style="color:var(--text-muted)">Les PDF sont sauvegardés automatiquement à chaque export.</small>
      </div>`;
      return;
    }
    const cards = docs.map(d => `
      <div class="doc-card">
        <div class="doc-card-name">📄 ${escHtml(d.filename)}</div>
        <div class="doc-card-meta">${d.date} · ${d.size_kb} Ko</div>
        <div class="doc-card-actions">
          <button class="btn btn-outline btn-sm" onclick="openDocFile('${escHtml(d.path)}')">📂 Ouvrir</button>
        </div>
      </div>`).join('');
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div style="font-size:.82rem;color:var(--text-muted)">${docs.length} document(s) enregistré(s)</div>
        <button class="btn btn-outline btn-sm" onclick="openVehicleFolder('${vin}')">📁 Ouvrir le dossier</button>
      </div>
      <div class="doc-grid">${cards}</div>`;
  } catch(e) {
    el.innerHTML = `<div class="empty-state">Erreur documents : ${escHtml(e.message)}</div>`;
  }
}

async function openDocFile(path) {
  try {
    await fetch('/api/export/open-exports', { method: 'POST' });
  } catch(err) { console.warn('[openDocFile] Échec ouverture dossier exports :', err); }
}

async function openVehicleFolder(vin) {
  try {
    await api('POST', `/api/export/open-vehicle/${encodeURIComponent(vin)}`, {});
  } catch(err) { console.warn('[openVehicleFolder] Échec ouverture dossier véhicule :', err); }
}

// ── Tab 4 : Infos véhicule ────────────────────────────
function renderVTabInfos(vehicle, repairs, vin, el) {
  const totalCost = repairs.reduce((sum, r) => {
    const c = parseFloat((r.cout||'').toString().replace(',','.'));
    return sum + (isNaN(c) ? 0 : c);
  }, 0);
  const repairsHtml = buildRepairsHtml(vin, repairs);
  const lastKmObd = vehicle.historique?.[0]?.kilometrage || 0;
  const kmManuel  = vehicle.km_manuel != null ? vehicle.km_manuel : lastKmObd;
  el.innerHTML = `
    <div class="km-manuel-row">
      <span style="font-size:.82rem;color:var(--text-muted)">🛣️ Kilométrage actuel :</span>
      <input type="number" id="kmManuelInput" class="km-manuel-input" value="${kmManuel}" min="0" max="9999999" step="100">
      <span style="font-size:.78rem;color:var(--text-muted)">km</span>
      <button class="btn btn-outline btn-sm" onclick="saveKmManuel('${escHtml(vin)}')">💾 Sauvegarder</button>
      ${lastKmObd ? `<span style="font-size:.72rem;color:var(--text-muted);margin-left:4px">Dernier OBD : ${lastKmObd.toLocaleString('fr')} km</span>` : ''}
    </div>
    <div class="infos-grid" style="margin-bottom:20px">
      <div>
        <div class="section-title" style="margin-bottom:10px">🚗 Informations</div>
        <div style="display:flex;flex-direction:column;gap:8px;font-size:.88rem">
          <div><span style="color:var(--text-muted)">Marque :</span> <strong>${escHtml(vehicle.marque||'—')}</strong></div>
          <div><span style="color:var(--text-muted)">Modèle :</span> <strong>${escHtml(vehicle.modele||'—')}</strong></div>
          <div><span style="color:var(--text-muted)">Année :</span> <strong>${escHtml(vehicle.annee||'—')}</strong></div>
          <div><span style="color:var(--text-muted)">Motorisation :</span> <strong>${escHtml(vehicle.motorisation||'—')}</strong></div>
          ${vehicle.code?`<div><span style="color:var(--text-muted)">Code flotte :</span> <strong>${escHtml(vehicle.code)}</strong></div>`:''}
          ${vehicle.surnom?`<div><span style="color:var(--text-muted)">Surnom :</span> <strong>${escHtml(vehicle.surnom)}</strong></div>`:''}
        </div>
      </div>
      <div>
        <div class="section-title" style="margin-bottom:10px">📝 Notes</div>
        <textarea id="vInfoNotes" rows="5" class="settings-input" style="width:100%;resize:vertical;font-size:.85rem">${escHtml(vehicle.notes||'')}</textarea>
        <button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="saveVehicleNotes('${vin}')">💾 Sauvegarder les notes</button>
        <div style="margin-top:16px">
          <button class="btn btn-outline btn-sm" id="btnOpenAlerts" onclick="openAlertsModal('${vin}')">🔔 Alertes km</button>
        </div>
      </div>
    </div>
    ${totalCost > 0 ? `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:.88rem;color:var(--text-dim)">💶 Coût total réparations</span>
      <strong style="color:var(--success)">${totalCost.toLocaleString('fr',{minimumFractionDigits:2})} €</strong>
    </div>` : ''}
    ${repairsHtml}`;
}

async function saveVehicleNotes(vin) {
  const notes = document.getElementById('vInfoNotes')?.value || '';
  try {
    await api('PUT', `/api/fleet/vehicle/${encodeURIComponent(vin)}/notes`, { notes });
    toast('Notes sauvegardées ✅', 'success');
    if (window._currentHistory?.vehicle) window._currentHistory.vehicle.notes = notes;
  } catch(e) { toast('Erreur : ' + e.message, 'error'); }
}

async function saveKmManuel(vin) {
  const val = parseInt(document.getElementById('kmManuelInput')?.value || '0', 10);
  if (isNaN(val) || val < 0) { toast('Kilométrage invalide', 'error'); return; }
  try {
    await api('PUT', `/api/fleet/vehicle/${encodeURIComponent(vin)}/km`, { km_manuel: val });
    if (window._currentHistory?.vehicle) window._currentHistory.vehicle.km_manuel = val;
    await loadFleet();
    toast('Kilométrage mis à jour ✅', 'success');
  } catch(e) { toast('Erreur : ' + e.message, 'error'); }
}

async function exportMaintenancePDF(vin) {
  try {
    toast('Génération de la fiche entretien…', 'info');
    const res = await saveFile(`/api/export/maintenance-pdf/${vin}`, {});
    toast(`Fiche entretien générée : ${res.filename} ✅`, 'success', 5000);
  } catch(e) { toast('Erreur PDF entretien : ' + e.message, 'error'); }
}

function toggleHistItem(idx) {
  document.getElementById(`hist-${idx}`)?.classList.toggle('expanded');
}

function exportHistoryEntry(vin, idx) {
  const h = window._currentHistory;
  if (h && h.vin === vin && h.history[idx]) exportPDF(vin, h.history[idx]);
}

// ════════════════════════════════════════════════════════
//  RÉPARATIONS
// ════════════════════════════════════════════════════════
let _repairVin = null;

function buildRepairsHtml(vin, repairs) {
  let html = `
    <div class="repairs-section">
      <div class="repairs-header">
        <span class="section-title" style="margin:0">🔧 Réparations effectuées</span>
        <button class="btn btn-outline btn-sm" onclick="openRepairModal('${escHtml(vin)}')">+ Ajouter</button>
      </div>`;
  if (!repairs || !repairs.length) {
    html += '<div class="empty-state" style="padding:12px 0">Aucune réparation enregistrée.</div>';
  } else {
    html += repairs.map(r => `
      <div class="repair-item">
        <div class="repair-date">📅 ${escHtml(r.date_affichage || r.date || '')}</div>
        <div class="repair-desc">${escHtml(r.description || '')}</div>
        ${r.pieces     ? `<div class="repair-meta">🔩 Pièces : ${escHtml(r.pieces)}</div>` : ''}
        ${r.cout       ? `<div class="repair-meta">💶 Coût : ${escHtml(r.cout)} €</div>` : ''}
        ${r.technicien ? `<div class="repair-meta">👤 Technicien : ${escHtml(r.technicien)}</div>` : ''}
      </div>`).join('');
  }
  html += '</div>';
  return html;
}

function openRepairModal(vin) {
  _repairVin = vin;
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('repairDate').value  = today;
  document.getElementById('repairDesc').value  = '';
  document.getElementById('repairParts').value = '';
  document.getElementById('repairCost').value  = '';
  document.getElementById('repairTech').value  = '';
  openModal('modalRepair');
}
function closeRepairModal() { document.getElementById('modalRepair').classList.add('hidden'); }

async function confirmAddRepair() {
  if (!_repairVin) return;
  const repair = {
    date:       document.getElementById('repairDate').value,
    description:document.getElementById('repairDesc').value.trim(),
    pieces:     document.getElementById('repairParts').value.trim(),
    cout:       document.getElementById('repairCost').value.trim(),
    technicien: document.getElementById('repairTech').value.trim(),
  };
  if (!repair.description) { toast('Description obligatoire', 'error'); return; }
  try {
    await api('POST', `/api/fleet/vehicle/${_repairVin}/repairs`, repair);
    closeRepairModal();
    toast('Réparation enregistrée ✅', 'success');
    await renderHistory(_repairVin);
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  CHAT IA
// ════════════════════════════════════════════════════════
let _chatHistory = [];

function renderChatMessages() {
  const el = document.getElementById('chatMessages');
  if (!_chatHistory.length) {
    el.innerHTML = '<div class="chat-hint">Posez une question sur le diagnostic en cours…</div>';
    return;
  }
  el.innerHTML = _chatHistory.map(m => `
    <div class="chat-msg chat-msg-${m.role}">
      <div class="chat-msg-content">${escHtml(m.content)}</div>
    </div>`).join('');
  el.scrollTop = el.scrollHeight;
}

async function sendChat() {
  const input   = document.getElementById('chatInput');
  const message = input.value.trim();
  if (!message) return;

  const { vin, analyse_ia } = state.currentDiag;
  _chatHistory.push({ role: 'user', content: message });
  input.value = '';
  renderChatMessages();

  const btnSend = document.getElementById('btnChatSend');
  btnSend.disabled    = true;
  btnSend.textContent = '…';

  try {
    const res = await api('POST', '/api/chat', {
      message,
      vin:     vin || '',
      context: analyse_ia || {},
      history: _chatHistory.slice(-10),
    });
    _chatHistory.push({ role: 'assistant', content: res.response });
    renderChatMessages();
  } catch (e) {
    _chatHistory.push({ role: 'assistant', content: '❌ Erreur : ' + e.message });
    renderChatMessages();
  } finally {
    btnSend.disabled    = false;
    btnSend.textContent = 'Envoyer';
  }
}

// ════════════════════════════════════════════════════════
//  ALERTES KILOMÉTRAGE
// ════════════════════════════════════════════════════════
let _alertsVin = null;

async function loadKmAlerts() {
  try {
    const triggered = await api('GET', '/api/fleet/alerts');
    renderKmAlertsPanel(triggered);
  } catch (err) { console.warn('[loadKmAlerts] Chargement alertes km échoué :', err); }
}

function renderKmAlertsPanel(triggered) {
  // Met à jour le badge d'alerte dans la sidebar et le stat urgent
  const urgentEl = document.getElementById('fstatUrgentVal');
  if (urgentEl && Array.isArray(triggered)) {
    const count = triggered.reduce((n, v) => n + (v.alertes?.length || 0), 0);
    urgentEl.textContent = count;
  }
  // Si un panneau dédié aux alertes km existe, le peupler
  const panel = document.getElementById('kmAlertsPanel') || document.getElementById('kmAlertsList');
  if (!panel || !Array.isArray(triggered)) return;
  if (!triggered.length) {
    panel.innerHTML = '<p style="padding:10px;color:var(--text-muted);text-align:center">Aucune alerte déclenchée</p>';
    return;
  }
  panel.innerHTML = triggered.map(v =>
    `<div class="km-alert-item">
      <strong>${esc(v.marque || v.vin)}</strong>
      ${(v.alertes || []).map(a => `<div class="km-alert-label">⚠️ ${esc(a.label)} — seuil : ${(a.km_seuil||0).toLocaleString()} km</div>`).join('')}
    </div>`
  ).join('');
}

function openAlertsModal(vin) {
  _alertsVin = vin;
  document.getElementById('alertLabel').value = '';
  document.getElementById('alertKm').value = '';
  openModal('modalAlerts');
  refreshAlertsList(vin);
}
function closeAlertsModal() { document.getElementById('modalAlerts').classList.add('hidden'); }

async function refreshAlertsList(vin) {
  try {
    const [alerts, hist] = await Promise.all([
      api('GET', `/api/fleet/vehicle/${encodeURIComponent(vin)}/alerts`),
      api('GET', `/api/fleet/vehicle/${encodeURIComponent(vin)}/history`),
    ]);
    const lastKm = hist.length ? (hist[0].kilometrage || 0) : 0;
    const el = document.getElementById('alertsList');
    if (!alerts.length) {
      el.innerHTML = '<div style="color:var(--text-muted);font-size:.85rem;">Aucune alerte configurée.</div>';
      return;
    }
    el.innerHTML = alerts.map(a => {
      const triggered = lastKm >= a.km_seuil;
      return `
        <div class="alert-row ${triggered ? 'triggered' : ''}">
          <div class="alert-row-info">
            <span class="alert-row-label">${triggered ? '🔔 ' : ''}${escHtml(a.label)}</span>
            <span class="alert-row-km">Seuil : ${a.km_seuil.toLocaleString('fr')} km${triggered ? ` — ⚠️ Dépassé (${lastKm.toLocaleString('fr')} km)` : ''}</span>
          </div>
          <button class="alert-delete-btn" onclick="deleteAlert('${escHtml(vin)}','${escHtml(a.id)}')">🗑</button>
        </div>`;
    }).join('');
  } catch (err) { console.warn('[refreshAlertsList] Chargement alertes véhicule échoué :', err); }
}

async function confirmAddAlert() {
  if (!_alertsVin) return;
  const label   = document.getElementById('alertLabel').value.trim();
  const km_seuil= parseInt(document.getElementById('alertKm').value) || 0;
  if (!label)    { toast('Libellé obligatoire', 'error'); return; }
  if (!km_seuil) { toast('Seuil km obligatoire', 'error'); return; }
  try {
    await api('POST', `/api/fleet/vehicle/${_alertsVin}/alerts`, { label, km_seuil });
    document.getElementById('alertLabel').value = '';
    document.getElementById('alertKm').value    = '';
    toast('Alerte ajoutée ✅', 'success');
    await refreshAlertsList(_alertsVin);
    await loadKmAlerts();
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

async function deleteAlert(vin, alertId) {
  try {
    await api('DELETE', `/api/fleet/vehicle/${encodeURIComponent(vin)}/alerts/${alertId}`);
    toast('Alerte supprimée', 'info');
    await refreshAlertsList(vin);
    await loadKmAlerts();
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  RAPPORT MENSUEL & EXPORT EXCEL
// ════════════════════════════════════════════════════════
function openMonthlyModal() {
  const now = new Date();
  document.getElementById('selectMonth').value = now.getMonth() + 1;
  document.getElementById('selectYear').value  = now.getFullYear();
  document.getElementById('modalMonthly').classList.remove('hidden');
}
function closeMonthlyModal() { document.getElementById('modalMonthly').classList.add('hidden'); }

async function generateMonthlyReport() {
  const month = document.getElementById('selectMonth').value;
  const year  = document.getElementById('selectYear').value;
  closeMonthlyModal();
  toast('Génération du rapport…', 'info', 6000);
  try {
    const res = await fetch(`/api/export/monthly-report?month=${month}&year=${year}`);
    const data = await res.json().catch(() => ({ error: res.statusText }));
    if (!res.ok || !data.success) throw new Error(data.error || res.statusText);
    toast(`Rapport sauvegardé : ${data.filename} — <button class="toast-btn" onclick="openExportsFolder()">📂 Ouvrir</button>`, 'success', 8000);
  } catch (e) {
    toast('Erreur rapport : ' + e.message, 'error');
  }
}

async function exportExcel() {
  toast('Génération du fichier Excel…', 'info', 6000);
  try {
    const res = await fetch('/api/export/excel');
    const data = await res.json().catch(() => ({ error: res.statusText }));
    if (!res.ok || !data.success) throw new Error(data.error || res.statusText);
    toast(`Excel sauvegardé : ${data.filename} — <button class="toast-btn" onclick="openExportsFolder()">📂 Ouvrir</button>`, 'success', 8000);
  } catch (e) {
    toast('Erreur Excel : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  SURVEILLANCE CONTINUE
// ════════════════════════════════════════════════════════
let _monitorInterval = null;
let _monitorStartTime = null;
let _monitorSession = null;


async function refreshMonitoringStatus() {
  try {
    const s = await api('GET', '/api/monitoring/status');
    if (!s.active) return;
    const elapsed = Math.round((Date.now() - _monitorStartTime) / 1000);
    const cur = s.current || {};
    const setVal = (id, val, unit, alertFn) => {
      const el = document.getElementById(id);
      if (!el) return;
      const v = val ? `${val}${unit}` : '—';
      el.querySelector('.mon-val').textContent = v;
      if (alertFn) {
        el.classList.toggle('alert', alertFn === 'alert');
        el.classList.toggle('warn',  alertFn === 'warn');
      }
    };
    setVal('monRpm',   cur.rpm,     '',    null);
    setVal('monTemp',  cur.temp,    '°C',  cur.temp >= 105 ? 'alert' : cur.temp >= 95 ? 'warn' : null);
    setVal('monSpeed', cur.speed,   'km/h',null);
    setVal('monVolt',  cur.voltage, 'V',   cur.voltage <= 11.5 ? 'alert' : null);
    document.getElementById('monTime')?.querySelector('.mon-val')?.textContent && (document.getElementById('monTime').querySelector('.mon-val').textContent = `${elapsed}s`);
    document.getElementById('monAnomalies')?.querySelector('.mon-val')?.textContent && (document.getElementById('monAnomalies').querySelector('.mon-val').textContent = s.anomalies_count || 0);
    // Append new anomalies to feed
    const feed = document.getElementById('monitoringAnomalyFeed');
    if (feed) {
      (s.new_anomalies || []).forEach(a => {
        const cls = a.type.includes('dtc') ? 'dtc' : a.type.includes('critical') ? '' : 'warn';
        const time = a.timestamp ? a.timestamp.substring(11, 19) : '';
        const div = document.createElement('div');
        div.className = `anomaly-item ${cls}`;
        div.innerHTML = `<span class="anomaly-time">${time}</span><span>${a.message}</span>`;
        feed.insertBefore(div, feed.firstChild);
        if (feed.children.length > 20) feed.removeChild(feed.lastChild);
      });
    }
  } catch(e) { /* silently ignore polling errors */ }
}

function renderMonitoringResult(session, analysis) {
  const el = document.getElementById('monitoringResult');
  if (!el) return;
  const res = analysis.result || {};
  const urgence = res.urgence_globale || 'OK';
  const actions = (res.actions || []).map(a =>
    `<li>${a.priorite}. ${a.action} <em style="color:#64748b">[${a.urgence}]</em></li>`
  ).join('');
  const anomaliesHtml = (res.analyse_anomalies || []).map(a =>
    `<div style="margin-bottom:8px"><strong style="color:#fbbf24">${a.anomalie}</strong><br>
     <span style="color:#94a3b8;font-size:0.82rem">${a.interpretation}</span><br>
     <span style="color:#64748b;font-size:0.8rem">Cause : ${a.cause_probable}</span></div>`
  ).join('') || '<p style="color:#64748b;font-size:0.85rem">Aucune anomalie analysée</p>';
  const stats = session.stats || {};
  const fmt = (s, u) => s && s.max > 0 ? `${s.min}–${s.max}${u}` : '—';
  el.innerHTML = `
    <div class="monitoring-result-card">
      <h3>📊 Rapport de session — ${session.duration_seconds || 0}s · ${session.readings_count || 0} relevés</h3>
      <span class="result-urgence ${urgence}">${urgence}</span>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
        <span style="font-size:0.8rem;color:#94a3b8">🔄 RPM: ${fmt(stats.rpm,' tr/min')}</span>
        <span style="font-size:0.8rem;color:#94a3b8">🌡️ Temp: ${fmt(stats.temp,'°C')}</span>
        <span style="font-size:0.8rem;color:#94a3b8">⚡ Batt: ${fmt(stats.voltage,'V')}</span>
        <span style="font-size:0.8rem;color:#94a3b8">🏎️ Vitesse: ${fmt(stats.speed,' km/h')}</span>
      </div>
      <p style="color:#e2e8f0;font-size:0.88rem;margin-bottom:12px">${res.bilan_sante || ''}</p>
      ${anomaliesHtml}
      ${res.correlations ? `<p style="color:#a78bfa;font-size:0.83rem;margin:8px 0"><strong>Corrélations :</strong> ${res.correlations}</p>` : ''}
      ${res.diagnostic_probable ? `<p style="color:#38bdf8;font-size:0.85rem;margin:8px 0"><strong>Diagnostic probable :</strong> ${res.diagnostic_probable}</p>` : ''}
      ${actions ? `<ul class="result-actions">${actions}</ul>` : ''}
      ${res.conseil_conduite ? `<div class="result-conseil">💬 ${res.conseil_conduite}</div>` : ''}
      ${analysis.success === false ? `<p style="color:#f87171">Erreur IA : ${analysis.error}</p>` : ''}
    </div>`;
  el.classList.remove('hidden');
}

// ════════════════════════════════════════════════════════
//  GRAPHIQUES LIVE (Chart.js)
// ════════════════════════════════════════════════════════
let _charts       = {};
let _evoCharts    = {};
let _chartPolling = null;
const _chartData  = { labels: [], rpm: [], temp: [], speed: [] };
const MAX_POINTS  = 40;


// ════════════════════════════════════════════════════════
//  NOTES
// ════════════════════════════════════════════════════════
let _notesVin = null;
function openNotesModal(vehicle, vin) {
  _notesVin = vin;
  document.getElementById('notesTextarea').value = vehicle.notes || '';
  document.getElementById('modalNotes').classList.remove('hidden');
}
function closeNotesModal() { document.getElementById('modalNotes').classList.add('hidden'); }
async function saveNotes() {
  if (!_notesVin) return;
  const notes = document.getElementById('notesTextarea').value;
  try {
    await api('PUT', `/api/fleet/vehicle/${_notesVin}/notes`, { notes });
    closeNotesModal();
    toast('Notes enregistrées ✅', 'success');
    await renderHistory(_notesVin);
  } catch (e) {
    toast('Erreur notes : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  ONGLET PARAMÈTRES
// ════════════════════════════════════════════════════════
async function loadSettingsTab() {
  try {
    const cfg = await api('GET', '/api/config');
    // Mode buttons
    const isSim = cfg.simulation_mode;
    document.getElementById('modeBtnSim').classList.toggle('active', isSim);
    document.getElementById('modeBtnReal').classList.toggle('active', !isSim);
    document.getElementById('modeStatus').textContent =
      isSim ? '🎮 Mode simulation actif — les données sont générées aléatoirement.'
             : '🔌 Mode réel actif — connexion physique OBD2 requise.';
    // Port block visibility
    document.getElementById('settingsPortBlock').style.opacity = isSim ? '0.4' : '1';
    // Config fields
    document.getElementById('cfgPort').value     = cfg.port     || 'COM3';
    document.getElementById('cfgBaudrate').value = cfg.baudrate || 9600;
    document.getElementById('cfgTimeout').value  = cfg.timeout  || 10;
    // System status
    renderSystemStatus(cfg);
    // API key field : show masked preview if already set
    const keyInput = document.getElementById('inputApiKey');
    if (keyInput && cfg.api_key_preview) {
      keyInput.placeholder = cfg.api_key_preview + ' (déjà enregistrée)';
    }
    // Re-applique les masquages CLIENT_BUILD (au cas où le DOM aurait été
    // partiellement reconstruit ou que applyClientBuild() ait été appelé
    // avant le rendu de l'onglet Paramètres)
    if (state.connection && state.connection.client_build) applyClientBuild();
  } catch (err) { console.warn('[loadSettings] Chargement configuration échoué :', err); }
  renderTechList();
  loadGarageSettings();
}

/* ── Garage identity ──────────────────────────────────── */
async function loadGarageSettings() {
  try {
    const g = await api('GET', '/api/config/garage');
    state._garage = g;
    const fields = { garageNom: 'nom', garageAdresse: 'adresse', garageTel: 'tel', garageEmail: 'email', garageSiret: 'siret' };
    for (const [id, key] of Object.entries(fields)) {
      const el = document.getElementById(id);
      if (el) el.value = g[key] || '';
    }
  } catch (err) { console.warn('[loadGarageSettings] Chargement identité garage échoué :', err); }
}

async function saveGarageSettings() {
  const fields = { garageNom: 'nom', garageAdresse: 'adresse', garageTel: 'tel', garageEmail: 'email', garageSiret: 'siret' };
  const data = {};
  for (const [id, key] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (el) data[key] = el.value.trim();
  }
  try {
    await api('PUT', '/api/config/garage', data);
    state._garage = data;
    const status = document.getElementById('garageSaveStatus');
    if (status) { status.textContent = '✅ Sauvegardé'; setTimeout(() => { status.textContent = ''; }, 3500); }
    toast('Identité du garage enregistrée ✅', 'success');
  } catch (e) {
    toast('Erreur sauvegarde garage : ' + e.message, 'error');
  }
}

async function changePassword() {
  const oldP     = document.getElementById('pwdOld').value;
  const newP     = document.getElementById('pwdNew').value;
  const confirmP = document.getElementById('pwdConfirm').value;
  const status   = document.getElementById('pwdStatus');
  const btn      = document.getElementById('btnChangePwd');

  const setStatus = (msg, ok) => {
    if (!status) return;
    status.textContent = msg;
    status.style.color = ok ? 'var(--success, #16a34a)' : 'var(--danger, #dc2626)';
  };

  if (!oldP || !newP || !confirmP) return setStatus('Tous les champs sont requis', false);
  if (newP.length < 8)             return setStatus('8 caractères minimum', false);
  if (newP !== confirmP)           return setStatus('Les mots de passe ne correspondent pas', false);
  if (newP === oldP)               return setStatus('Le nouveau doit différer de l\'ancien', false);

  btn.disabled = true;
  setStatus('Modification…', true);

  try {
    await api('POST', '/api/auth/change-password', { old_password: oldP, new_password: newP });
    setStatus('✅ Mot de passe modifié', true);
    document.getElementById('pwdOld').value = '';
    document.getElementById('pwdNew').value = '';
    document.getElementById('pwdConfirm').value = '';
    toast('Mot de passe modifié avec succès ✅', 'success');
    setTimeout(() => { if (status) status.textContent = ''; }, 5000);
  } catch (e) {
    setStatus('❌ ' + (e.message || 'Échec'), false);
    toast('Échec du changement de mot de passe : ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

/* ── FAQ accordion ─────────────────────────────────────── */
function toggleFaq(btn) {
  const item = btn.closest('.faq-item');
  const isOpen = item.classList.contains('open');
  // Ferme tous les autres
  document.querySelectorAll('.faq-item.open').forEach(el => el.classList.remove('open'));
  if (!isOpen) item.classList.add('open');
}

async function saveApiKey() {
  const key = document.getElementById('inputApiKey').value.trim();
  const status = document.getElementById('apiKeySaveStatus');
  if (!key) { status.textContent = '⚠️ Clé vide'; return; }
  try {
    await api('PUT', '/api/config/apikey', { api_key: key });
    status.textContent = '✅ Clé enregistrée';
    document.getElementById('inputApiKey').value = '';
    await loadSettingsTab();
  } catch (e) {
    status.textContent = '❌ Erreur : ' + e.message;
  }
  setTimeout(() => { status.textContent = ''; }, 4000);
}

function toggleApiKeyVisibility() {
  const inp = document.getElementById('inputApiKey');
  const btn = document.getElementById('btnShowKey');
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = '🙈 Masquer'; }
  else { inp.type = 'password'; btn.textContent = '👁 Afficher'; }
}

function renderSystemStatus(cfg) {
  const el = document.getElementById('systemStatus');
  // En CLIENT_BUILD : l'IA passe par le proxy Lyvenia (pas de clé locale),
  // pas de mode simulation accessible. On adapte les cartes en conséquence.
  const isClient = !!(state.connection && state.connection.client_build);

  const items = [];

  if (isClient) {
    // Carte IA cohérente avec l'archi : analyse via serveur Lyvenia, pas de clé locale
    items.push({
      icon: '🤖',
      label: 'Analyse IA',
      value: 'Connectée au serveur Lyvenia',
      badge: 'ok',
      badgeText: '✅ OK',
    });
  } else {
    // Mode dev : on garde l'affichage classique (clé locale dans config.json)
    items.push({
      icon: '🤖',
      label: 'Clé API Anthropic',
      value: cfg.api_key_ok ? 'Configurée dans config.json ou env' : 'Non configurée — analyses IA indisponibles',
      badge: cfg.api_key_ok ? 'ok' : 'err',
      badgeText: cfg.api_key_ok ? '✅ OK' : '❌ Manquante',
    });
    // En CLIENT_BUILD pas de toggle simulation, donc pas pertinent d'afficher le mode
    items.push({
      icon: '🔌',
      label: 'Mode actuel',
      value: cfg.simulation_mode ? 'Simulation (données fictives)' : 'Réel (connexion OBD2)',
      badge: 'ok',
      badgeText: cfg.simulation_mode ? '🎮 Simulation' : '🔌 Réel',
    });
  }

  // Items toujours utiles (CLIENT comme DEV)
  items.push({
    icon: '🚗',
    label: 'Port OBD2',
    value: cfg.port || 'COM3',
    badge: cfg.simulation_mode && !isClient ? 'warn' : 'ok',
    badgeText: cfg.simulation_mode && !isClient ? 'Non utilisé' : (cfg.port || 'COM3'),
  });
  items.push({
    icon: '📡',
    label: 'Baudrate',
    value: `${cfg.baudrate || 9600} baud — timeout ${cfg.timeout || 10}s`,
    badge: 'ok',
    badgeText: `${cfg.baudrate || 9600}`,
  });

  el.innerHTML = items.map(it => `
    <div class="sys-item">
      <span class="sys-icon">${it.icon}</span>
      <div style="flex:1">
        <div class="sys-label">${it.label}</div>
        <div class="sys-value">${escHtml(it.value)}</div>
      </div>
      <span class="sys-badge ${it.badge}">${it.badgeText}</span>
    </div>`).join('');
}

async function setMode(mode) {
  const enabled = mode === 'simulation';
  try {
    const r = await api('POST', '/api/simulation/toggle', { enabled });
    state.connection.simulation = r.simulation_mode;
    document.getElementById('simLabel').textContent = r.simulation_mode ? 'ON' : 'OFF';
    renderConnectionBadge();
    renderFleet();  // Re-filtrer la liste selon le mode
    toast(`Mode ${r.simulation_mode ? 'simulation' : 'réel'} activé`, 'info');
    await loadSettingsTab();
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

async function detectPort() {
  const btn = document.getElementById('btnDetectPort');
  const status = document.getElementById('detectStatus');
  btn.disabled = true;
  btn.textContent = '⏳ Détection en cours…';
  status.style.display = 'block';
  status.style.color = 'var(--text-dim)';
  status.textContent = 'Scan des ports COM…';
  try {
    const r = await api('POST', '/api/config/detect-port');
    if (r.found) {
      document.getElementById('cfgPort').value = r.port;
      document.getElementById('cfgBaudrate').value = r.baudrate;
      status.style.color = 'var(--success)';
      status.textContent = `✅ Trouvé : ${r.port} à ${r.baudrate} baud (${r.desc})`;
      await loadSettingsTab();
    } else {
      status.style.color = 'var(--danger)';
      status.textContent = '❌ ' + r.message;
    }
  } catch (e) {
    status.style.color = 'var(--danger)';
    status.textContent = '❌ Erreur : ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Détecter automatiquement';
  }
}

async function saveConfig() {
  const port     = document.getElementById('cfgPort').value.trim();
  const baudrate = document.getElementById('cfgBaudrate').value;
  const timeout  = document.getElementById('cfgTimeout').value;
  if (!port) { toast('Port obligatoire', 'error'); return; }
  try {
    await api('PUT', '/api/config', { port, baudrate: parseInt(baudrate), timeout: parseInt(timeout) });
    toast('Configuration sauvegardée ✅', 'success');
    await loadSettingsTab();
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

async function runConnectionTest() {
  const btn = document.getElementById('btnTestConn');
  const res = document.getElementById('testResults');
  btn.disabled = true;
  btn.textContent = '⏳ Test en cours…';
  res.classList.remove('hidden');
  res.innerHTML = '<div class="test-step pending"><span class="test-step-icon">⏳</span><span class="test-step-label">Connexion en cours…</span></div>';

  try {
    const r = await api('POST', '/api/test-connection');
    const icons = { ok: '✅', warning: '⚠️', error: '❌', pending: '⏳' };
    let html = r.steps.map(s => `
      <div class="test-step ${s.status}">
        <span class="test-step-icon">${icons[s.status] || '•'}</span>
        <span class="test-step-label">${escHtml(s.label)}</span>
        <span class="test-step-detail">${escHtml(s.detail || '')}</span>
      </div>`).join('');

    if (r.success) {
      html += `<div class="test-summary ok">✅ Test réussi — ${r.mode === 'simulation' ? 'mode simulation opérationnel' : 'véhicule détecté et lisible'}</div>`;
      if (r.vin) html += `<div class="test-step ok"><span class="test-step-icon">🆔</span><span class="test-step-label">VIN lu</span><span class="test-step-detail" style="font-weight:700">${escHtml(r.vin)}</span></div>`;
    } else {
      html += `<div class="test-summary error">❌ Test échoué — vérifiez la connexion et la configuration</div>`;
    }
    res.innerHTML = html;
  } catch (e) {
    res.innerHTML = `<div class="test-step error"><span class="test-step-icon">❌</span><span class="test-step-label">Erreur</span><span class="test-step-detail">${escHtml(e.message)}</span></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Lancer le test';
  }
}

// ════════════════════════════════════════════════════════
//  SETTINGS (modal legacy — conservé pour la topbar ⚙️)
// ════════════════════════════════════════════════════════
//  THEME TOGGLE
// ════════════════════════════════════════════════════════
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  // Le toggle thème est géré visuellement via CSS ([data-theme="light"])
  savePref('diagTheme', theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ════════════════════════════════════════════════════════
async function openSettings() {
  try {
    const cfg = await api('GET', '/api/config');
    document.getElementById('inputPort').value = cfg.port || 'COM3';
  } catch (err) { console.warn('[openSettings] Chargement config port échoué :', err); }
  openModal('modalSettings');
}
function closeSettings() { document.getElementById('modalSettings').classList.add('hidden'); }
async function saveSettings() {
  const port = document.getElementById('inputPort').value.trim();
  try {
    await api('PUT', '/api/config', { port });
    toast('Configuration sauvegardée ✅', 'success');
    closeSettings();
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  SIMULATION TOGGLE
// ════════════════════════════════════════════════════════
async function toggleSimulation() {
  const next = !state.connection.simulation;
  try {
    const r = await api('POST', '/api/simulation/toggle', { enabled: next });
    state.connection.simulation = r.simulation_mode;
    document.getElementById('simLabel').textContent = r.simulation_mode ? 'ON' : 'OFF';
    toast(`Mode simulation ${r.simulation_mode ? 'activé' : 'désactivé'}`, 'info');
    renderConnectionBadge();
  } catch (e) {
    toast('Erreur : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  TABS
// ════════════════════════════════════════════════════════
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('hidden',  panel.id !== `tab-${name}`);
    panel.classList.toggle('active',  panel.id === `tab-${name}`);
  });

  // (Mini-flotte sidebar masquée en CSS — sidebar = nav pure depuis Phase 3)

  // Nouveau layout deux colonnes pour la flotte
  if (name === 'historique') {
    loadFleet().then(() => {
      renderFleetDashboard();
      renderFleetManagement();
      // Restaurer la sélection active si un véhicule était sélectionné
      if (state.selectedVin) {
        document.querySelectorAll('.fv-item').forEach(el => {
          el.classList.toggle('active', el.dataset.vin === state.selectedVin);
        });
        document.getElementById('fleetEmptyState')?.classList.add('hidden');
        document.getElementById('historyContainer')?.classList.remove('hidden');
      }
    }).catch(err => console.error('Fleet load error:', err));
  }

  // Load settings tab data
  if (name === 'parametres') loadSettingsTab();

  // Load dashboard
  if (name === 'dashboard') loadDashboard();
}

// ════════════════════════════════════════════════════════
//  SEARCH
// ════════════════════════════════════════════════════════
function setupSearch() {
  document.getElementById('searchInput').addEventListener('input', e => {
    const q = e.target.value.trim().toLowerCase();
    if (!q) { renderFleet(); return; }
    const isReal = !state.connection.simulation;
    const base   = isReal ? state.fleet.filter(v => !v.simulated) : state.fleet;
    const filtered = base.filter(v =>
      (v.vin    || '').toLowerCase().includes(q) ||
      (v.marque || '').toLowerCase().includes(q) ||
      (v.modele || '').toLowerCase().includes(q) ||
      (v.historique || []).some(h =>
        (h.dtc_codes || []).some(c => c.toLowerCase().includes(q))
      )
    );
    const el = document.getElementById('fleetList');
    if (!filtered.length) {
      el.innerHTML = '<div class="empty-state">Aucun résultat.</div>';
      return;
    }
    el.innerHTML = filtered.map(v => {
      const statusDot = statusDotHtml(v.statut_dernier_diagnostic || 'OK');
      const label = [v.marque, v.annee].filter(Boolean).join(' ');
      const alertBadge = '';
      return `
        <div class="fleet-item" data-vin="${v.vin}">
          ${statusDot}
          <div class="fleet-item-info">
            <div class="fleet-item-name">${label || 'Véhicule'}</div>
            <div class="fleet-item-sub">${v.vin}</div>
          </div>
        </div>`;
    }).join('');
    el.querySelectorAll('.fleet-item').forEach(el => {
      el.addEventListener('click', () => selectVehicle(el.dataset.vin));
    });
  });
}

// ════════════════════════════════════════════════════════
//  EVOLUTION CHARTS
// ════════════════════════════════════════════════════════
function renderEvolutionCharts(vin, history) {
  if (!history.length) return '';
  return `
    <div class="evo-section">
      <div class="section-title" style="margin-bottom:12px">📈 Évolution dans le temps</div>
      <div class="evo-grid">
        <div class="evo-chart-wrap">
          <div class="evo-chart-title">🔋 Tension batterie (V)</div>
          <canvas id="evoBattery" height="80"></canvas>
        </div>
        <div class="evo-chart-wrap">
          <div class="evo-chart-title">🌡️ Température (°C)</div>
          <canvas id="evoTemp" height="80"></canvas>
        </div>
        <div class="evo-chart-wrap">
          <div class="evo-chart-title">🛣️ Kilométrage</div>
          <canvas id="evoKm" height="80"></canvas>
        </div>
      </div>
    </div>`;
}

function initEvolutionCharts(history) {
  if (!history.length) return;
  const labels   = history.map(h => h.date_affichage?.split(' ')[0] || '').reverse();
  const batteries= history.map(h => h.donnees_temps_reel?.battery_voltage ?? null).reverse();
  const temps    = history.map(h => h.donnees_temps_reel?.coolant_temp ?? null).reverse();
  const kms      = history.map(h => h.kilometrage || 0).reverse();
  const makeOpts = (color) => ({
    type: 'line',
    options: {
      responsive: true, animation: false,
      scales: {
        x: { ticks: { color: '#556070', font: { size: 9 } }, grid: { color: '#2e2e50' } },
        y: { ticks: { color: '#556070', font: { size: 9 } }, grid: { color: '#2e2e50' } },
      },
      plugins: { legend: { display: false } },
      elements: { point: { radius: 3 } },
    },
  });
  const makeDs = (data, color) => ([{
    data, borderColor: color, backgroundColor: color + '22',
    fill: true, tension: 0.3, borderWidth: 2, pointRadius: 3,
  }]);
  // Détruire les anciens graphiques avant d'en créer de nouveaux
  Object.values(_evoCharts).forEach(c => { try { c.destroy(); } catch(_) {} });
  _evoCharts = {};
  const bat = document.getElementById('evoBattery');
  const tmp = document.getElementById('evoTemp');
  const km  = document.getElementById('evoKm');
  if (bat) _evoCharts.battery = new Chart(bat, { ...makeOpts('#4a9eff'), data: { labels, datasets: makeDs(batteries, '#4a9eff') } });
  if (tmp) _evoCharts.temp    = new Chart(tmp, { ...makeOpts('#e53935'), data: { labels, datasets: makeDs(temps,     '#e53935') } });
  if (km)  _evoCharts.km      = new Chart(km,  { ...makeOpts('#4caf50'), data: { labels, datasets: makeDs(kms,       '#4caf50') } });
}

// ════════════════════════════════════════════════════════
//  MAINTENANCE SCHEDULE
// ════════════════════════════════════════════════════════
function renderMaintenanceSchedule(schedule) {
  if (!schedule.length) return '';
  const statusCls = { ok: 'maint-ok', soon: 'maint-soon', overdue: 'maint-overdue' };
  const statusLabel = { ok: '', soon: '⚠️ Bientôt', overdue: '🔴 Dépassé' };
  return `
    <div class="maint-section">
      <div class="section-title" style="margin-bottom:12px">🔧 Calendrier d'entretien</div>
      <div class="maint-grid">
        ${schedule.map(s => `
          <div class="maint-item ${statusCls[s.status] || ''}">
            <span class="maint-icon">${s.icon}</span>
            <div class="maint-info">
              <div class="maint-label">${escHtml(s.label)}</div>
              <div class="maint-km">Prochain : ${s.next_km.toLocaleString('fr')} km
                ${s.km_remaining > 0 ? `(dans ${s.km_remaining.toLocaleString('fr')} km)` : '(dépassé)'}
              </div>
            </div>
            ${s.status !== 'ok' ? `<span class="maint-badge">${statusLabel[s.status]}</span>` : ''}
          </div>`).join('')}
      </div>
    </div>`;
}

// ════════════════════════════════════════════════════════
//  COMPARISON
// ════════════════════════════════════════════════════════
function openCompareModal(vin, history) {
  if (history.length < 2) {
    toast('Au moins 2 diagnostics requis pour comparer', 'info');
    return;
  }
  const sel = (id, label) => `
    <div>
      <label style="font-size:.8rem;color:var(--text-muted)">${label}</label>
      <select id="${id}" class="settings-input" style="width:100%;margin-top:4px">
        ${history.map((h, i) => `<option value="${i}">${h.date_affichage || ''} — ${(h.dtc_codes || []).join(', ') || 'Aucun défaut'} (${(h.kilometrage || 0).toLocaleString('fr')} km)</option>`).join('')}
      </select>
    </div>`;
  document.getElementById('compareContent').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      ${sel('cmpA', 'Diagnostic A')}
      ${sel('cmpB', 'Diagnostic B')}
    </div>
    <button class="btn btn-primary" onclick="runComparison()">🔄 Comparer</button>
    <div id="cmpResult" style="margin-top:16px"></div>`;
  window._cmpHistory = history;
  openModal('modalCompare');
}

function runComparison() {
  const history = window._cmpHistory || [];
  const elA = document.getElementById('cmpA');
  const elB = document.getElementById('cmpB');
  const elResult = document.getElementById('cmpResult');
  if (!elA || !elB || !elResult) { toast('Erreur : modal de comparaison introuvable', 'error'); return; }
  const iA = parseInt(elA.value);
  const iB = parseInt(elB.value);
  const a  = history[iA];
  const b  = history[iB];
  if (!a || !b || iA === iB) { toast('Sélectionnez deux diagnostics différents', 'error'); return; }

  const rtRow = (label, keyA, keyB, unit) => {
    const va = a.donnees_temps_reel?.[keyA];
    const vb = b.donnees_temps_reel?.[keyB];
    const diff = (va != null && vb != null) ? (vb - va).toFixed(1) : null;
    const diffHtml = diff !== null
      ? `<span style="color:${parseFloat(diff) > 0 ? 'var(--warning)' : 'var(--success)'}"> (${parseFloat(diff) > 0 ? '+' : ''}${diff} ${unit})</span>`
      : '';
    return `<tr><td style="color:var(--text-muted);padding:5px 8px">${label}</td>
      <td style="padding:5px 8px">${va ?? '—'} ${unit}</td>
      <td style="padding:5px 8px">${vb ?? '—'} ${unit}${diffHtml}</td></tr>`;
  };

  const codesA = new Set(a.dtc_codes || []);
  const codesB = new Set(b.dtc_codes || []);
  const newCodes      = [...codesB].filter(c => !codesA.has(c));
  const resolvedCodes = [...codesA].filter(c => !codesB.has(c));
  const persistCodes  = [...codesA].filter(c => codesB.has(c));

  elResult.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:.85rem">
      <thead><tr>
        <th style="text-align:left;padding:6px 8px;color:var(--text-muted);border-bottom:1px solid var(--border)">Paramètre</th>
        <th style="padding:6px 8px;color:var(--accent);border-bottom:1px solid var(--border)">${a.date_affichage?.split(' ')[0] || 'A'}</th>
        <th style="padding:6px 8px;color:var(--warning);border-bottom:1px solid var(--border)">${b.date_affichage?.split(' ')[0] || 'B'}</th>
      </tr></thead>
      <tbody>
        <tr><td style="padding:5px 8px;color:var(--text-muted)">Kilométrage</td>
          <td style="padding:5px 8px">${(a.kilometrage||0).toLocaleString('fr')} km</td>
          <td style="padding:5px 8px">${(b.kilometrage||0).toLocaleString('fr')} km</td></tr>
        ${rtRow('Batterie', 'battery_voltage', 'battery_voltage', 'V')}
        ${rtRow('Température', 'coolant_temp', 'coolant_temp', '°C')}
        ${rtRow('RPM', 'rpm', 'rpm', 'tr/min')}
      </tbody>
    </table>
    ${newCodes.length ? `<div style="margin-top:12px;padding:10px;background:rgba(229,57,53,.1);border-radius:6px;border:1px solid rgba(229,57,53,.3)">🔴 <strong>Nouveaux codes :</strong> ${newCodes.join(', ')}</div>` : ''}
    ${resolvedCodes.length ? `<div style="margin-top:8px;padding:10px;background:rgba(76,175,80,.1);border-radius:6px;border:1px solid rgba(76,175,80,.3)">🟢 <strong>Codes résolus :</strong> ${resolvedCodes.join(', ')}</div>` : ''}
    ${persistCodes.length ? `<div style="margin-top:8px;padding:10px;background:rgba(251,140,0,.1);border-radius:6px;border:1px solid rgba(251,140,0,.3)">🟡 <strong>Codes persistants :</strong> ${persistCodes.join(', ')}</div>` : ''}`;
}

// ════════════════════════════════════════════════════════
//  TECHNICIANS
// ════════════════════════════════════════════════════════
let _techniciens = ['Technicien 1'];
let _pendingSaveCb = null;

async function loadTechnicians() {
  try { _techniciens = await api('GET', '/api/config/technicians'); } catch (err) { console.warn('[loadTechnicians] Chargement liste techniciens échoué :', err); }
}

function renderTechList() {
  const el = document.getElementById('techList');
  if (!el) return;
  el.innerHTML = _techniciens.map((t, i) => `
    <div class="tech-item">
      <span>${escHtml(t)}</span>
      <button class="alert-delete-btn" onclick="removeTech(${i})">🗑</button>
    </div>`).join('') || '<div style="color:var(--text-muted);font-size:.85rem">Aucun technicien.</div>';
}

async function addTechnician() {
  const input = document.getElementById('newTechName');
  const name  = input.value.trim();
  if (!name) return;
  _techniciens.push(name);
  input.value = '';
  await saveTechniciansList();
  renderTechList();
}

async function removeTech(idx) {
  _techniciens.splice(idx, 1);
  await saveTechniciansList();
  renderTechList();
}

async function saveTechniciansList() {
  try { await api('PUT', '/api/config/technicians', { technicians: _techniciens }); } catch (err) { console.warn('[saveTechniciansList] Sauvegarde techniciens échouée :', err); }
}

function openTechModal(onConfirm) {
  const sel = document.getElementById('selectTechnicien');
  sel.innerHTML = _techniciens.map(t => `<option>${escHtml(t)}</option>`).join('');
  _pendingSaveCb = onConfirm;
  document.getElementById('modalTechnicien').classList.remove('hidden');
}
function closeTechModal() { document.getElementById('modalTechnicien').classList.add('hidden'); }
function confirmTech() {
  const tech = document.getElementById('selectTechnicien').value;
  closeTechModal();
  if (_pendingSaveCb) { _pendingSaveCb(tech); _pendingSaveCb = null; }
}

// ════════════════════════════════════════════════════════
//  BACKUP
// ════════════════════════════════════════════════════════
async function triggerBackup() {
  const btn = document.getElementById('btnBackup');
  const status = document.getElementById('backupStatus');
  btn.disabled = true;
  try {
    const r = await api('POST', '/api/backup');
    status.textContent = `✅ Sauvegarde créée : ${r.file} (${r.count} fichier(s) conservé(s))`;
    status.style.color = 'var(--success)';
    toast('Sauvegarde créée ✅', 'success');
  } catch (e) {
    status.textContent = '❌ Erreur : ' + e.message;
    status.style.color = 'var(--danger)';
  } finally {
    btn.disabled = false;
  }
}

// ════════════════════════════════════════════════════════
//  CLIENT PDF
// ════════════════════════════════════════════════════════
function exportClientPDFEntry(vin, idx) {
  const h = window._currentHistory;
  if (h && h.vin === vin && h.history[idx]) {
    exportClientPDF(vin, h.history[idx]);
  }
}

async function exportClientPDF(vin, diagEntry) {
  toast('Génération fiche client…', 'info', 5000);
  try {
    const r = await saveFile('/api/export/client-pdf', { vin, diagnostic: diagEntry });
    toast(`Fiche client sauvegardée : ${r.filename} — <button class="toast-btn" onclick="openExportsFolder()">📂 Ouvrir</button>`, 'success', 8000);
  } catch (e) {
    toast('Erreur PDF : ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════
//  UTILS
// ════════════════════════════════════════════════════════
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
const esc = escHtml; // alias utilisé dans le module Dashboard

// ════════════════════════════════════════════════════════
//  TABLEAU DE BORD
// ════════════════════════════════════════════════════════

let _dashData = null;

async function loadDashboard() {
  // Date du jour
  const dateLbl = document.getElementById('dashDateLabel');
  if (dateLbl) {
    dateLbl.textContent = new Date().toLocaleDateString('fr-FR', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
  }
  try {
    _dashData = await api('GET', '/api/dashboard');
    renderDashboardHero(_dashData);
    renderDashboardKPI(_dashData);
    renderDashboardHealth(_dashData);
    renderDashboardDiags(_dashData.recent_diags || []);
    renderDashboardActivity(_dashData);
    renderDashboardChart(_dashData);
    renderDashboardMaintAlerts(_dashData.maintenance_summary || {});
    populateDashVehicleSelect(_dashData.vehicles || []);
    // Index de recherche à jour avec les données fraîches
    if (typeof refreshSearchIndex === 'function') refreshSearchIndex();
    // Auto-charge la maintenance si 1 seul véhicule
    if ((_dashData.vehicles || []).length === 1) {
      renderDashboardMaintenance(_dashData.vehicles[0].vin);
    }
  } catch (e) {
    console.error('loadDashboard error', e);
    const grid = document.getElementById('dashHealthGrid');
    if (grid) {
      grid.innerHTML = `<div class="dash-empty" style="color:var(--danger)">⚠ Tableau de bord indisponible : ${escHtml(e.message || 'erreur inconnue')}<br><button class="btn-secondary" onclick="loadDashboard()" style="margin-top:12px">Réessayer</button></div>`;
    }
  }
}

/**
 * Hero header personnalisé : "Bonjour [user]" + sous-titre dynamique
 *  + bandeau d'alerte critique si une panne urgente est détectée.
 */
function renderDashboardHero(data) {
  const greetEl = document.getElementById('dashGreeting');
  const subEl   = document.getElementById('dashSubtitle');
  if (!greetEl) return;

  // Heure → salutation
  const h = new Date().getHours();
  const hello = h < 5 ? 'Bonsoir' : h < 18 ? 'Bonjour' : 'Bonsoir';

  // Nom : préférer le nom du garage, sinon localStorage, sinon générique
  let userName = (data.garage && data.garage.nom) || localStorage.getItem('rodiaUserName') || '';
  // Si nom long, on prend juste le premier mot
  if (userName.length > 24) userName = userName.split(/\s+/)[0];
  greetEl.textContent = userName ? `${hello} ${userName}` : `${hello}`;

  // Sous-titre dynamique : agrégation alertes
  const vehicles = data.vehicles || [];
  const recentDiags = data.recent_diags || [];
  const maint = data.maintenance_summary || {};

  // Compte les diagnostics urgents (statut URGENT) sur les 7 derniers jours
  const oneWeekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const urgentDiags = recentDiags.filter(d => {
    if ((d.statut || '').toUpperCase() !== 'URGENT') return false;
    const t = Date.parse(d.date || d.date_iso || '') || 0;
    return t >= oneWeekAgo;
  });
  const urgentMaint = (maint.urgent || 0);
  const todayDate = new Date().toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long'
  });

  let parts = [`<span style="text-transform:capitalize">${escHtml(todayDate)}</span>`];
  if (urgentDiags.length) {
    parts.push(`<strong>${urgentDiags.length} alerte${urgentDiags.length > 1 ? 's' : ''} urgente${urgentDiags.length > 1 ? 's' : ''}</strong>`);
  }
  if (urgentMaint) {
    parts.push(`<strong>${urgentMaint} maintenance${urgentMaint > 1 ? 's' : ''} en retard</strong>`);
  }
  if (!urgentDiags.length && !urgentMaint && vehicles.length) {
    parts.push(`<strong>${vehicles.length} véhicule${vehicles.length > 1 ? 's' : ''}</strong> en flotte · aucune alerte critique`);
  }
  subEl.innerHTML = parts.join('  ·  ');

  // Bandeau d'alerte critique : prend le diagnostic urgent le plus récent
  const banner = document.getElementById('dashCriticalAlert');
  if (banner) {
    if (urgentDiags.length > 0) {
      const top = urgentDiags[0];
      const veh = vehicles.find(v => v.vin === top.vin) || {};
      const label = [veh.marque, veh.modele, top.code ? `· ${top.code}` : ''].filter(Boolean).join(' ') || top.vin;
      const codes = (top.dtc_codes && top.dtc_codes.length) ? top.dtc_codes.slice(0, 3).join(', ') : 'Codes DTC critiques';
      const titleEl = document.getElementById('dashCriticalAlertTitle');
      const descEl  = document.getElementById('dashCriticalAlertDesc');
      const ctaEl   = document.getElementById('dashCriticalAlertCta');
      if (titleEl) titleEl.textContent = label;
      if (descEl)  descEl.textContent = `${codes}  ·  intervention urgente recommandée`;
      if (ctaEl) {
        ctaEl.onclick = () => switchTab('historique');
      }
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
    }
  }
}

/* ── KPI cards : flotte / diags ce mois / alertes / score ──────── */
function renderDashboardKPI(data) {
  const vehicles    = data.vehicles || [];
  const recentDiags = data.recent_diags || [];
  const health      = data.health || {};
  const maint       = data.maintenance_summary || {};

  // 1. Flotte active : nombre + sparkline = nombre cumulé sur 7 derniers jours (proxy : tous les véh ajoutés progressivement)
  setKpiText('kpiFleetValue', vehicles.length, ' véhicules');
  setKpiTrend('kpiFleetTrend', vehicles.length > 0 ? +1 : 0, 'count');
  // Sparkline : approximation d'évolution = barres croissantes vers le total actuel
  renderSparkline('kpiFleetSpark', genFleetSpark(vehicles, 7));

  // 2. Diagnostics ce mois
  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
  const lastMonthStart = new Date(now.getFullYear(), now.getMonth() - 1, 1).getTime();
  const diagsThisMonth = recentDiags.filter(d => Date.parse(d.date || d.date_iso || '') >= startOfMonth);
  const diagsLastMonth = recentDiags.filter(d => {
    const t = Date.parse(d.date || d.date_iso || '');
    return t >= lastMonthStart && t < startOfMonth;
  });
  setKpiText('kpiDiagsValue', diagsThisMonth.length);
  const diagsDelta = diagsLastMonth.length > 0
    ? Math.round(((diagsThisMonth.length - diagsLastMonth.length) / diagsLastMonth.length) * 100)
    : (diagsThisMonth.length > 0 ? 100 : 0);
  setKpiTrend('kpiDiagsTrend', diagsDelta, 'percent');
  renderSparkline('kpiDiagsSpark', genDiagsSpark(recentDiags, 7));

  // 3. Alertes urgentes : diagnostics URGENT cette semaine + maintenance dépassée
  const oneWeekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const urgentDiags = recentDiags.filter(d =>
    (d.statut || '').toUpperCase() === 'URGENT' &&
    Date.parse(d.date || d.date_iso || '') >= oneWeekAgo
  );
  const totalAlerts = urgentDiags.length + (maint.urgent || 0);
  setKpiText('kpiAlertsValue', totalAlerts);
  // trend : on inverse — moins d'alertes = vert
  setKpiTrend('kpiAlertsTrend', totalAlerts === 0 ? -1 : (totalAlerts > 3 ? +1 : 0), 'count', /*invert*/ true);
  renderSparkline('kpiAlertsSpark', genAlertsSpark(recentDiags, 7));

  // 4. Score fiabilité moyen
  const avg = data.avg_score ?? 0;
  setKpiText('kpiScoreValue', avg > 0 ? avg : '--', '/100');
  // Trend : comparer au score précédent (proxy : on n'a pas l'historique → estimation via dispersion)
  const scores = vehicles.map(v => (health[v.vin] || {}).score).filter(s => typeof s === 'number');
  const trend = scores.length > 1 ? Math.round((avg - 80)) : 0;
  setKpiTrend('kpiScoreTrend', trend, 'pts');
  renderSparkline('kpiScoreSpark', genScoreSpark(scores, 7));
}

function setKpiText(id, value, suffix = '') {
  const el = document.getElementById(id);
  if (!el) return;
  if (suffix) {
    el.innerHTML = `${value}<span class="kpi-value-suf">${escHtml(suffix)}</span>`;
  } else {
    el.textContent = value;
  }
}

function setKpiTrend(id, delta, unit, invert = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('up', 'down', 'flat');
  if (delta === 0) {
    el.classList.add('flat');
    el.innerHTML = '—';
    return;
  }
  // Sens visuel : si invert=true (alertes), une augmentation est rouge, une baisse est verte
  const positive = invert ? (delta < 0) : (delta > 0);
  el.classList.add(positive ? 'up' : 'down');
  const arrow = positive
    ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m18 9-6-6-6 6"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m6 15 6 6 6-6"/></svg>';
  const sign = delta > 0 ? '+' : '';
  const suffix = unit === 'percent' ? ' %' : unit === 'pts' ? ' pts' : '';
  el.innerHTML = `${arrow}${sign}${delta}${suffix}`;
}

/**
 * Sparkline = N barres flex normalisées entre 8% et 100%.
 * `values` : tableau de N nombres (peuvent être 0).
 */
function renderSparkline(id, values) {
  const el = document.getElementById(id);
  if (!el || !Array.isArray(values) || !values.length) return;
  const max = Math.max(1, ...values);
  el.innerHTML = values.map(v => {
    const h = Math.max(8, Math.round((v / max) * 100));
    return `<span style="height:${h}%"></span>`;
  }).join('');
}

// Sparkline data : approximations heuristiques quand on n'a pas d'historique fin
function genFleetSpark(vehicles, n) {
  // Tous les véhicules existants au moment T, on simule croissance progressive
  const total = vehicles.length;
  if (total === 0) return Array(n).fill(0);
  const step = Math.max(1, Math.ceil(total / n));
  return Array.from({ length: n }, (_, i) => Math.min(total, (i + 1) * step));
}
function genDiagsSpark(diags, n) {
  // Compte des diagnostics par jour sur les n derniers jours
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const buckets = Array(n).fill(0);
  for (const d of diags) {
    const t = Date.parse(d.date || d.date_iso || '');
    if (!t) continue;
    const days = Math.floor((today.getTime() - t) / (24 * 60 * 60 * 1000));
    if (days >= 0 && days < n) buckets[n - 1 - days]++;
  }
  return buckets;
}
function genAlertsSpark(diags, n) {
  // Idem mais seulement les URGENT
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const buckets = Array(n).fill(0);
  for (const d of diags) {
    if ((d.statut || '').toUpperCase() !== 'URGENT') continue;
    const t = Date.parse(d.date || d.date_iso || '');
    if (!t) continue;
    const days = Math.floor((today.getTime() - t) / (24 * 60 * 60 * 1000));
    if (days >= 0 && days < n) buckets[n - 1 - days]++;
  }
  return buckets;
}
function genScoreSpark(scores, n) {
  // Pas d'historique de score → on étale la moyenne sur n points avec une légère variation visuelle
  if (!scores.length) return Array(n).fill(0);
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
  return Array.from({ length: n }, (_, i) => Math.round(avg * (0.85 + (i / n) * 0.3)));
}

/* ── Chart SVG : score fiabilité 30 derniers jours ──────────────── */
function renderDashboardChart(data) {
  const wrap = document.getElementById('dashChartWrap');
  if (!wrap) return;

  // Construit une série de 30 points (1 par jour) à partir des diagnostics
  const series = buildScoreSeries(data, 30);
  if (!series.some(p => p != null)) {
    wrap.innerHTML = '<div class="dash-empty" style="padding:32px;text-align:center;color:var(--text-muted)">Pas assez de données pour tracer la courbe</div>';
    return;
  }

  // Géométrie
  const W = 800, H = 200;
  const padL = 40, padR = 20, padT = 20, padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  // Échelle Y : 0..100
  const yScale = v => padT + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;
  const xScale = i => padL + (i / (series.length - 1)) * innerW;

  // Interpole les points manquants (null) en linéaire entre voisins connus
  const filled = interpolateSeries(series);

  // Path principal
  const points = filled.map((v, i) => `${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`);
  const linePath = 'M' + points.join(' L');
  const areaPath = `${linePath} L${xScale(filled.length - 1).toFixed(1)},${(padT + innerH).toFixed(1)} L${padL.toFixed(1)},${(padT + innerH).toFixed(1)} Z`;

  // Labels X : aujourd'hui, -10j, -20j, -30j
  const today = new Date();
  const fmt = d => d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
  const lbl = (offset) => {
    const d = new Date(today); d.setDate(d.getDate() - offset); return fmt(d);
  };

  const lastVal = filled[filled.length - 1];
  const lastX = xScale(filled.length - 1);
  const lastY = yScale(lastVal);

  wrap.innerHTML = `
    <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="Score fiabilité 30 jours">
      <defs>
        <linearGradient id="chartArea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%"   stop-color="var(--accent)" stop-opacity=".22"/>
          <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <!-- Grid horizontal lignes 70/80/90/100 -->
      <g stroke="var(--border)" stroke-width="1" stroke-opacity=".5">
        <line x1="${padL}" y1="${yScale(100).toFixed(1)}" x2="${W - padR}" y2="${yScale(100).toFixed(1)}"/>
        <line x1="${padL}" y1="${yScale(90).toFixed(1)}"  x2="${W - padR}" y2="${yScale(90).toFixed(1)}"/>
        <line x1="${padL}" y1="${yScale(80).toFixed(1)}"  x2="${W - padR}" y2="${yScale(80).toFixed(1)}"/>
        <line x1="${padL}" y1="${yScale(70).toFixed(1)}"  x2="${W - padR}" y2="${yScale(70).toFixed(1)}"/>
      </g>
      <!-- Y axis labels -->
      <g font-family="Inter" font-size="10" fill="var(--text-muted)">
        <text x="6" y="${(yScale(100) + 4).toFixed(1)}">100</text>
        <text x="6" y="${(yScale(90)  + 4).toFixed(1)}">90</text>
        <text x="6" y="${(yScale(80)  + 4).toFixed(1)}">80</text>
        <text x="6" y="${(yScale(70)  + 4).toFixed(1)}">70</text>
      </g>
      <!-- Area + line -->
      <path d="${areaPath}" fill="url(#chartArea)"/>
      <path d="${linePath}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <!-- Last point + tooltip -->
      <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="5" fill="var(--accent)" stroke="var(--bg-card)" stroke-width="2"/>
      <g transform="translate(${(lastX - 30).toFixed(1)}, ${Math.max(8, lastY - 36).toFixed(1)})">
        <rect width="60" height="26" rx="6" fill="var(--text-main)"/>
        <text x="30" y="17" font-family="Inter" font-size="11" font-weight="600" fill="var(--bg-card)" text-anchor="middle">${Math.round(lastVal)} / 100</text>
      </g>
      <!-- X axis labels -->
      <g font-family="Inter" font-size="10" fill="var(--text-muted)">
        <text x="${padL.toFixed(1)}" y="${(H - 8).toFixed(1)}">${escHtml(lbl(29))}</text>
        <text x="${(padL + innerW * 0.33).toFixed(1)}" y="${(H - 8).toFixed(1)}">${escHtml(lbl(20))}</text>
        <text x="${(padL + innerW * 0.66).toFixed(1)}" y="${(H - 8).toFixed(1)}">${escHtml(lbl(10))}</text>
        <text x="${(W - padR).toFixed(1)}" y="${(H - 8).toFixed(1)}" text-anchor="end">${escHtml(lbl(0))}</text>
      </g>
    </svg>
  `;
}

function buildScoreSeries(data, days) {
  // Pour chaque jour des `days` derniers, on prend le score moyen des diagnostics ce jour-là.
  // Si aucun, retourne null (sera interpolé).
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const buckets = Array(days).fill(null).map(() => []);
  for (const d of (data.recent_diags || [])) {
    const t = Date.parse(d.date || d.date_iso || '');
    if (!t) continue;
    const dayDiff = Math.floor((today.getTime() - t) / (24 * 60 * 60 * 1000));
    if (dayDiff < 0 || dayDiff >= days) continue;
    if (typeof d.score === 'number') {
      buckets[days - 1 - dayDiff].push(d.score);
    }
  }
  return buckets.map(arr => arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null);
}

function interpolateSeries(arr) {
  // Remplace les nulls par interpolation linéaire entre voisins connus
  // Si pas de premier ou dernier point, on les complète avec le score moyen connu (ou 80 par défaut)
  const known = arr.map((v, i) => v == null ? null : { i, v }).filter(Boolean);
  if (!known.length) return arr.map(() => 80);
  const fallback = Math.round(known.reduce((a, b) => a + b.v, 0) / known.length);
  const out = arr.slice();
  // Remplir début et fin avec premier/dernier connu
  for (let i = 0; i < out.length && out[i] == null; i++) out[i] = known[0].v;
  for (let i = out.length - 1; i >= 0 && out[i] == null; i--) out[i] = known[known.length - 1].v;
  // Interpolation entre points connus
  let lastIdx = 0;
  for (let i = 1; i < out.length; i++) {
    if (out[i] != null) {
      const gap = i - lastIdx;
      if (gap > 1) {
        const lv = out[lastIdx], rv = out[i];
        for (let k = 1; k < gap; k++) {
          out[lastIdx + k] = lv + ((rv - lv) * k) / gap;
        }
      }
      lastIdx = i;
    }
  }
  return out.map(v => v == null ? fallback : v);
}

/* ── Activity feed : timeline événements récents ────────────────── */
function renderDashboardActivity(data) {
  const el = document.getElementById('dashActivityFeed');
  if (!el) return;

  const events = buildActivityEvents(data);
  if (!events.length) {
    el.innerHTML = '<div class="dash-empty" style="padding:32px;text-align:center;color:var(--text-muted)">Aucune activité récente</div>';
    return;
  }
  el.innerHTML = events.slice(0, 6).map(ev => `
    <div class="activity-item">
      <div class="activity-dot ${ev.kind}">${ev.icon}</div>
      <div class="activity-body">
        <div class="activity-text">${ev.text}</div>
        <div class="activity-meta">${escHtml(ev.meta)}</div>
      </div>
    </div>
  `).join('');
}

function buildActivityEvents(data) {
  const out = [];
  const vehicles = data.vehicles || [];
  const recentDiags = data.recent_diags || [];
  const maint = data.maintenance_summary || {};

  // SVGs Lucide
  const ICON_CHECK  = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
  const ICON_ALERT  = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';
  const ICON_WRENCH = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>';

  for (const d of recentDiags.slice(0, 8)) {
    const veh = vehicles.find(v => v.vin === d.vin) || {};
    const label = [veh.marque, veh.modele].filter(Boolean).join(' ') || (d.vin || '').slice(-8);
    const plate = veh.code || veh.surnom || '';
    const dateStr = d.date_affichage_relative || d.date_affichage || '';
    const score = (d.score != null) ? `score ${d.score}/100` : '';
    if ((d.statut || '').toUpperCase() === 'URGENT') {
      out.push({
        ts: Date.parse(d.date || d.date_iso || '') || 0,
        kind: 'red', icon: ICON_ALERT,
        text: `Alerte critique sur <strong>${escHtml(label)}${plate ? ' ' + escHtml(plate) : ''}</strong>`,
        meta: [dateStr, score].filter(Boolean).join('  ·  ')
      });
    } else {
      out.push({
        ts: Date.parse(d.date || d.date_iso || '') || 0,
        kind: 'green', icon: ICON_CHECK,
        text: `Diagnostic terminé sur <strong>${escHtml(label)}${plate ? ' ' + escHtml(plate) : ''}</strong>`,
        meta: [dateStr, score].filter(Boolean).join('  ·  ')
      });
    }
  }

  // Maintenance bientôt / dépassée
  if (maint.urgent && maint.urgent > 0) {
    out.push({
      ts: Date.now(),
      kind: 'red', icon: ICON_WRENCH,
      text: `<strong>${maint.urgent}</strong> opération${maint.urgent > 1 ? 's' : ''} de maintenance dépassée${maint.urgent > 1 ? 's' : ''}`,
      meta: 'À traiter sans délai'
    });
  }
  if (maint.warning && maint.warning > 0) {
    out.push({
      ts: Date.now() - 1,
      kind: 'amber', icon: ICON_WRENCH,
      text: `<strong>${maint.warning}</strong> opération${maint.warning > 1 ? 's' : ''} de maintenance bientôt due${maint.warning > 1 ? 's' : ''}`,
      meta: 'Anticiper la prochaine intervention'
    });
  }

  // Tri descendant par timestamp
  out.sort((a, b) => b.ts - a.ts);
  return out;
}

function scoreColor(score) {
  if (score >= 80) return 'ok';
  if (score >= 50) return 'warn';
  return 'danger';
}

function renderDashboardHealth(data) {
  const health   = data.health   || {};
  const vehicles = data.vehicles || [];

  const elGrid  = document.getElementById('dashHealthGrid');
  const elCount = document.getElementById('dashHealthCount');
  if (!elGrid) return;

  if (elCount) elCount.textContent = vehicles.length;

  if (!vehicles.length) {
    elGrid.innerHTML = '<div class="dash-empty" style="padding:32px;text-align:center;color:var(--text-muted)">Aucun véhicule enregistré</div>';
    return;
  }

  // Tri : par score croissant (les + critiques en premier)
  const sorted = [...vehicles].sort((a, b) => {
    const sa = (health[a.vin] || {}).score ?? 999;
    const sb = (health[b.vin] || {}).score ?? 999;
    return sa - sb;
  });

  elGrid.innerHTML = sorted.slice(0, 6).map(v => {
    const h = health[v.vin] || {};
    const s = h.score ?? 0;
    const c = scoreColor(s);
    const name  = [v.marque, v.modele].filter(Boolean).join(' ') || v.vin;
    const plate = v.code || v.surnom || '';
    const lastKm = h.km_actuel ? h.km_actuel.toLocaleString('fr-FR').replace(/,/g, ' ') + ' km' : '—';
    const lastDate = h.last_diag_date_relative || h.last_diag_date_affichage || '';
    const initials = (v.marque || 'V').slice(0, 1).toUpperCase() + (v.modele || '').slice(0, 1).toUpperCase();
    const vinShort = (v.vin || '').slice(-8);

    return `<div class="veh-row" data-vin="${esc(v.vin)}" onclick="switchTab('historique')">
      <div class="veh-icon">${esc(initials || 'V')}</div>
      <div>
        <div class="veh-name">${esc(name)}${plate ? ` <span style="color:var(--text-muted);font-weight:500"> · ${esc(plate)}</span>` : ''}</div>
        <div class="veh-vin">${esc(vinShort || v.vin || '')}</div>
      </div>
      <div class="veh-km">${esc(lastKm)}</div>
      <div class="veh-date">${esc(lastDate)}</div>
      <div class="score ${c}">
        <span class="score-dot"></span>
        ${s > 0 ? s : '--'}
      </div>
      <div class="veh-chev">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
      </div>
    </div>`;
  }).join('');
}

function renderDashboardDiags(diags) {
  const el = document.getElementById('dashRecentDiags');
  if (!el) return;
  if (!diags.length) {
    el.innerHTML = '<div class="dash-empty">Aucun diagnostic enregistré</div>';
    return;
  }
  const rows = diags.map(d => {
    const statut = d.statut || 'OK';
    const cls = statut === 'URGENT' ? 'urgent' : statut === 'SURVEILLER' ? 'warn' : 'ok';
    const dtcCount = (d.dtc_codes || []).length;
    const score = d.analyse_ia?.score_sante ?? '—';
    return `<tr>
      <td>${esc(d.label)}</td>
      <td>${esc(d.date_affichage || '')}</td>
      <td>${d.kilometrage ? d.kilometrage.toLocaleString('fr-FR') + ' km' : '—'}</td>
      <td>${score !== '—' ? score + '/100' : '—'}</td>
      <td>${dtcCount ? `<span class="dtc-badge">${dtcCount} code${dtcCount > 1 ? 's' : ''}</span>` : '✅'}</td>
      <td><span class="diag-status-badge diag-status-${cls}">${esc(statut)}</span></td>
    </tr>`;
  }).join('');
  el.innerHTML = `<table class="dash-diag-table">
    <thead><tr>
      <th>Véhicule</th><th>Date</th><th>Km</th><th>Score</th><th>DTC</th><th>Statut</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderDashboardMaintAlerts(summary) {
  const el = document.getElementById('dashMaintAlerts');
  if (!el) return;
  const urgent  = summary.urgent  || [];
  const warning = summary.warning || [];
  if (!urgent.length && !warning.length) { el.innerHTML = ''; return; }
  const chips = [
    ...urgent.map(a  => `<span class="dash-alert-chip urgent">${a.icon} ${esc(a.label)} <span style="opacity:.7;font-size:.7em">(${esc(a.vin.slice(-6))})</span></span>`),
    ...warning.map(a => `<span class="dash-alert-chip warning">${a.icon} ${esc(a.label)} <span style="opacity:.7;font-size:.7em">(${esc(a.vin.slice(-6))})</span></span>`),
  ].join('');
  el.innerHTML = `<div class="dash-maint-alerts">${chips}</div>`;
}

function populateDashVehicleSelect(vehicles) {
  const sel = document.getElementById('dashVehicleSelect');
  if (!sel) return;
  sel.innerHTML = '<option value="">Tous les véhicules</option>' +
    vehicles.map(v => {
      const name = [v.marque, v.modele].filter(Boolean).join(' ') || v.vin;
      return `<option value="${esc(v.vin)}">${esc(name)}</option>`;
    }).join('');
}

async function renderDashboardMaintenance(vin) {
  const el = document.getElementById('dashMaintList');
  if (!el) return;
  if (!vin) {
    el.innerHTML = '<div class="dash-empty">Sélectionnez un véhicule pour voir sa maintenance</div>';
    return;
  }
  el.innerHTML = '<div class="dash-empty">Chargement…</div>';
  try {
    const items = await api('GET', `/api/maintenance/vehicle/${encodeURIComponent(vin)}`);
    // Grouper par catégorie
    const categories = {};
    for (const item of items) {
      const cat = item.category || 'Autre';
      if (!categories[cat]) categories[cat] = [];
      categories[cat].push(item);
    }
    let html = '';
    for (const [cat, catItems] of Object.entries(categories)) {
      html += `<div class="maint-category">
        <div class="maint-cat-title">${esc(cat)}</div>
        ${catItems.map(item => renderMaintItem(vin, item)).join('')}
      </div>`;
    }
    el.innerHTML = html || '<div class="dash-empty">Aucun item de maintenance</div>';
    // Attach wear select listeners
    el.querySelectorAll('.maint-wear-select').forEach(sel => {
      sel.addEventListener('change', async () => {
        const itemId    = sel.dataset.itemId;
        const wearState = sel.value;
        const km = _dashData?.health?.[vin]?.km_actuel || 0;
        await api('PUT', `/api/maintenance/vehicle/${encodeURIComponent(vin)}/wear/${itemId}`, { wear_state: wearState, km });
        await renderDashboardMaintenance(vin);
        await reloadMaintAlerts();
        toast('État d\'usure mis à jour', 'success', 2000);
      });
    });
    // Attach "mark done" button listeners
    el.querySelectorAll('.btn-done').forEach(btn => {
      btn.addEventListener('click', () => openMarkDoneModal(vin, btn.dataset.itemId, btn.dataset.label));
    });
    // Attach delete custom item listeners
    el.querySelectorAll('.btn-del-maint').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm(`Supprimer "${btn.dataset.label}" ?`)) return;
        await api('DELETE', `/api/maintenance/template/${btn.dataset.itemId}`);
        await renderDashboardMaintenance(vin);
        toast('Item supprimé', 'success', 2000);
      });
    });
  } catch (e) {
    el.innerHTML = '<div class="dash-empty">Erreur de chargement</div>';
  }
}

function renderMaintItem(vin, item) {
  const status = item.status || 'unknown';
  const statusLabels = { ok: 'OK', warning: 'À surveiller', urgent: 'URGENT', unknown: 'Non renseigné' };
  const deleteBtn = item.custom
    ? `<button class="btn-del-maint" data-item-id="${esc(item.id)}" data-label="${esc(item.label)}" title="Supprimer">🗑️</button>`
    : '';

  if (item.type === 'wear') {
    const states = (item.wear_states || []);
    const opts = states.map(s => `<option value="${esc(s)}" ${s === item.wear_state ? 'selected' : ''}>${esc(s)}</option>`).join('');
    const detail = item.updated_date ? `Mis à jour le ${item.updated_date}${item.updated_km ? ' — ' + item.updated_km.toLocaleString('fr-FR') + ' km' : ''}` : 'Non renseigné';
    return `<div class="maint-item status-${status}">
      <div class="maint-item-icon">${item.icon || '🔧'}</div>
      <div class="maint-item-info">
        <div class="maint-item-label">${esc(item.label)}</div>
        <div class="maint-item-detail">${esc(detail)}</div>
      </div>
      <span class="maint-item-status maint-status-${status}">${statusLabels[status] || status}</span>
      <div class="maint-item-action">
        <select class="maint-wear-select" data-item-id="${esc(item.id)}">${opts}</select>
        ${deleteBtn}
      </div>
    </div>`;
  }

  // Scheduled
  let detail = '';
  if (item.next_date || item.next_km) {
    const parts = [];
    if (item.next_date) parts.push('Prochaine : ' + formatDateFr(item.next_date));
    if (item.next_km)   parts.push('ou ' + item.next_km.toLocaleString('fr-FR') + ' km');
    detail = parts.join(' ');
  } else if (item.interval_km || item.interval_months) {
    const parts = [];
    if (item.interval_km)     parts.push('Tous les ' + item.interval_km.toLocaleString('fr-FR') + ' km');
    if (item.interval_months) parts.push('/ ' + item.interval_months + ' mois');
    detail = parts.join(' ') + ' — Non renseigné';
  }
  return `<div class="maint-item status-${status}">
    <div class="maint-item-icon">${item.icon || '🔧'}</div>
    <div class="maint-item-info">
      <div class="maint-item-label">${esc(item.label)}</div>
      <div class="maint-item-detail">${esc(detail)}</div>
    </div>
    <span class="maint-item-status maint-status-${status}">${statusLabels[status] || status}</span>
    <div class="maint-item-action">
      <button class="btn-done" data-item-id="${esc(item.id)}" data-label="${esc(item.label)}">✅ Fait</button>
      ${deleteBtn}
    </div>
  </div>`;
}

function formatDateFr(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('fr-FR');
  } catch { return dateStr; }
}

async function reloadMaintAlerts() {
  try {
    const data = await api('GET', '/api/dashboard');
    renderDashboardMaintAlerts(data.maintenance_summary || {});
  } catch (e) {}
}

// ── Modal : Marquer comme fait ─────────────────────────────────────────────
function openMarkDoneModal(vin, itemId, label) {
  document.getElementById('mdVin').value    = vin;
  document.getElementById('mdItemId').value = itemId;
  document.getElementById('mdDate').value   = new Date().toISOString().slice(0, 10);
  const km = _dashData?.health?.[vin]?.km_actuel || '';
  document.getElementById('mdKm').value = km || '';
  document.getElementById('modalMarkDone').classList.remove('hidden');
}

async function confirmMarkDone() {
  const vin    = document.getElementById('mdVin').value;
  const itemId = document.getElementById('mdItemId').value;
  const date   = document.getElementById('mdDate').value;
  const km     = parseInt(document.getElementById('mdKm').value) || 0;
  if (!date) { toast('Date requise', 'warning'); return; }
  const btn = document.getElementById('mdConfirm');
  if (btn) btn.disabled = true;
  try {
    await api('POST', `/api/maintenance/vehicle/${encodeURIComponent(vin)}/done/${itemId}`, { date, km });
    document.getElementById('modalMarkDone').classList.add('hidden');
    await renderDashboardMaintenance(vin);
    await reloadMaintAlerts();
    toast('Maintenance enregistrée ✅', 'success', 2500);
  } catch (err) {
    toast('Erreur lors de l\'enregistrement', 'error');
    console.error('confirmMarkDone:', err);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Modal : Ajouter item custom ────────────────────────────────────────────
function openAddMaintModal() {
  document.getElementById('amLabel').value = '';
  document.getElementById('amCategory').value = '';
  document.getElementById('amIcon').value = '🔧';
  document.getElementById('amType').value = 'scheduled';
  document.getElementById('amIntervalKm').value = '';
  document.getElementById('amIntervalMonths').value = '';
  document.getElementById('amWearStates').value = 'OK\nÀ surveiller\nÀ changer';
  document.getElementById('amScheduledFields').classList.remove('hidden');
  document.getElementById('amWearFields').classList.add('hidden');
  document.getElementById('modalAddMaint').classList.remove('hidden');
}

async function confirmAddMaint() {
  const label    = document.getElementById('amLabel').value.trim();
  const category = document.getElementById('amCategory').value.trim() || 'Autre';
  const icon     = document.getElementById('amIcon').value.trim() || '🔧';
  const type     = document.getElementById('amType').value;
  if (!label) { toast('Libellé requis', 'warning'); return; }

  const payload = { label, category, icon, type };
  if (type === 'scheduled') {
    const km = parseInt(document.getElementById('amIntervalKm').value) || null;
    const mo = parseInt(document.getElementById('amIntervalMonths').value) || null;
    payload.interval_km = km;
    payload.interval_months = mo;
  } else {
    const raw = document.getElementById('amWearStates').value;
    payload.wear_states = raw.split('\n').map(s => s.trim()).filter(Boolean);
  }
  await api('POST', '/api/maintenance/template', payload);
  document.getElementById('modalAddMaint').classList.add('hidden');

  // Refresh maintenance list for current selected vehicle
  const vin = document.getElementById('dashVehicleSelect').value;
  if (vin) await renderDashboardMaintenance(vin);
  toast('Item ajouté ✅', 'success', 2000);
}

// ════════════════════════════════════════════════════════
//  EVENT LISTENERS
// ════════════════════════════════════════════════════════
function setupEvents() {
  // Tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Diagnostic flow
  document.getElementById('btnStartDiag').addEventListener('click', () => startDiagnostic({ type: 'panne' }));
  document.getElementById('btnStartHealthCheck')?.addEventListener('click', () => startDiagnostic({ type: 'controle' }));
  document.getElementById('btnNewDiag').addEventListener('click', () => {
    // Réinitialisation complète de l'état diagnostic
    state.selectedVin = null;
    state.currentDiag = { vin: null, dtc_codes: [], realtime: {}, freeze_frame: {}, analyse_ia: null, kilometrage: 0, savedEntry: null, vehicle_manual: null, _audio_peaks: null, _audio_interps: null };
    state.diagSaved = false;
    // Reset VIN manuel
    document.getElementById('vinManualZone')?.classList.add('hidden');
    document.getElementById('btnEditVin')?.classList.remove('hidden');
    ['vfMarque','vfModele','vfAnnee','vfMotorisation'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });

    // Réinitialisation complète de l'UI
    document.getElementById('aiResults').classList.add('hidden');
    document.getElementById('aiResults').innerHTML = '';
    document.getElementById('actionBar').classList.add('hidden');
    document.getElementById('chatSection').classList.add('hidden');
    document.getElementById('saveFeedback').classList.add('hidden');
    document.getElementById('historyContainer')?.classList.add('hidden');
    document.getElementById('fleetManagement')?.classList.remove('hidden');

    renderFleet();

    // Activer l'onglet diagnostic et afficher l'écran d'accueil directement
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === 'diagnostic'));
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.classList.toggle('hidden', p.id !== 'tab-diagnostic');
      p.classList.toggle('active', p.id === 'tab-diagnostic');
    });

    _resetDiagnosticFully();
    showStep('stepWelcome');
  });
  document.getElementById('btnNewReadDiag').addEventListener('click', startDiagnostic);

  // VIN manuel
  document.getElementById('btnEditVin')?.addEventListener('click', () => {
    // Peupler le select flotte
    const fleetSelect = document.getElementById('vfFleetSelect');
    const fleetField  = document.getElementById('vfFleetField');
    const realFleet   = state.fleet.filter(v => v.marque || v.modele);
    if (fleetSelect && realFleet.length > 0) {
      fleetSelect.innerHTML = '<option value="">— Choisir un véhicule —</option>';
      realFleet.forEach(v => {
        const label = v.surnom || [v.marque, v.modele, v.annee ? `(${v.annee})` : ''].filter(Boolean).join(' ');
        const opt = document.createElement('option');
        opt.value = v.vin;
        opt.textContent = label;
        fleetSelect.appendChild(opt);
      });
      if (fleetField) fleetField.style.display = '';
    }

    // Pré-remplir si des infos existent déjà
    const vm = state.currentDiag.vehicle_manual;
    if (vm) {
      document.getElementById('vfMarque').value       = vm.marque       || '';
      document.getElementById('vfModele').value       = vm.modele       || '';
      document.getElementById('vfAnnee').value        = vm.annee        || '';
      document.getElementById('vfMotorisation').value = vm.motorisation || '';
    }
    document.getElementById('vinManualZone')?.classList.remove('hidden');
    document.getElementById('btnEditVin')?.classList.add('hidden');
    document.getElementById('vfMarque')?.focus();
  });

  // Sélection d'un véhicule depuis la flotte → pré-remplir les champs + interventions
  document.getElementById('vfFleetSelect')?.addEventListener('change', async function() {
    const vin = this.value;
    if (!vin) return;
    const v = state.fleet.find(x => x.vin === vin);
    if (!v) return;
    document.getElementById('vfMarque').value       = v.marque       || '';
    document.getElementById('vfModele').value       = v.modele       || '';
    document.getElementById('vfAnnee').value        = v.annee        || '';
    document.getElementById('vfMotorisation').value = v.motorisation || '';
    // Stocker le VIN réel
    state.currentDiag.vin = vin;
    document.getElementById('vinDisplay').textContent = vin;

    // Charger les réparations et pré-remplir le champ interventions récentes
    try {
      const repairs = await api('GET', `/api/fleet/vehicle/${encodeURIComponent(vin)}/repairs`);
      if (Array.isArray(repairs) && repairs.length > 0) {
        const lines = repairs.slice(0, 5).map(r => {
          const parts = [r.date_affichage || r.date || ''];
          if (r.description) parts.push(r.description);
          if (r.pieces) parts.push(`(${r.pieces})`);
          return parts.join(' — ');
        });
        const anaInter = document.getElementById('ana_interventions');
        if (anaInter) {
          anaInter.value = lines.join('\n');
          anaInter.style.borderColor = 'var(--primary)';
          // Petit flash pour signaler le pré-remplissage
          setTimeout(() => { anaInter.style.borderColor = ''; }, 2000);
        }
      }
    } catch(e) { /* Pas de réparations enregistrées */ }
  });
  document.getElementById('btnCancelManualVin')?.addEventListener('click', () => {
    document.getElementById('vinManualZone')?.classList.add('hidden');
    document.getElementById('btnEditVin')?.classList.remove('hidden');
  });
  document.getElementById('btnApplyManualVin')?.addEventListener('click', applyManualVin);

  // Wizard buttons
  document.getElementById('btnStartStep2')?.addEventListener('click', startWizardStep2);
  document.getElementById('btnSkipStep2')?.addEventListener('click', () => finishWizardStep2(true));
  document.getElementById('btnStopStep2')?.addEventListener('click', () => finishWizardStep2(false));
  document.getElementById('btnStartStep3')?.addEventListener('click', startWizardStep3);
  document.getElementById('btnSkipStep3')?.addEventListener('click', () => finishWizardStep3(true));
  document.getElementById('btnRunAnalysis')?.addEventListener('click', runFullAnalysis);

  // Multi-ECU scan
  document.getElementById('btnShowECUScan')?.addEventListener('click', ecuScanShow);
  document.getElementById('btnRunECUScan')?.addEventListener('click', runECUScan);
  document.getElementById('btnAnamneseConfirm')?.addEventListener('click', anamneseConfirm);
  document.getElementById('btnAnamneseSkip')?.addEventListener('click', anamneseSkip);
  document.getElementById('btnBilanConfirm')?.addEventListener('click', bilanConfirm);
  document.getElementById('btnBilanSkip')?.addEventListener('click', bilanSkip);
  document.getElementById('btnAudioRecord')?.addEventListener('click', audioRecordStart);
  document.getElementById('btnAudioStop')?.addEventListener('click', audioRecordStop);
  document.getElementById('btnAudioClear')?.addEventListener('click', audioRecordClear);

  // DTC clear
  document.getElementById('btnClearDTC')?.addEventListener('click', openClearModal);
  document.getElementById('btnConfirmClear').addEventListener('click', confirmClearDTC);
  document.getElementById('btnCancelClear').addEventListener('click', closeClearModal);

  // Save & export
  document.getElementById('btnSave').addEventListener('click', saveDiagnostic);
  document.getElementById('btnExportPDF').addEventListener('click', async () => {
    const { vin, dtc_codes, realtime, analyse_ia, kilometrage, savedEntry } = state.currentDiag;
    const diagData = savedEntry || {
      vin, dtc_codes, donnees_temps_reel: realtime, analyse_ia, kilometrage,
      statut: analyse_ia?.statut_global || 'OK',
      date_affichage: new Date().toLocaleString('fr-FR'),
      session_ralenti: state.session_ralenti || null,
      session_roulant: state.session_roulant || null,
    };
    if (analyse_ia?.vin_info) {
      await api('POST', '/api/fleet/vehicle', { vin, vin_info: analyse_ia.vin_info }).catch(() => {});
    }
    await exportPDF(vin, diagData);
  });

  // Chat
  document.getElementById('btnChatSend').addEventListener('click', sendChat);
  document.getElementById('chatInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });

  // Enregistrement audio
  document.getElementById('btnRecordAudio')?.addEventListener('click', startAudioRecord);
  document.getElementById('btnStopRecord')?.addEventListener('click', stopAudioRecord);

  // Theme toggle
  document.getElementById('btnThemeToggle').addEventListener('click', toggleTheme);
  applyTheme(localStorage.getItem('diagTheme') || 'light');

  // Settings (modal legacy — accessible via onglet Paramètres)
  document.getElementById('btnSettings')?.addEventListener('click', openSettings);
  document.getElementById('btnSaveConfig').addEventListener('click', saveSettings);
  document.getElementById('btnCancelSettings').addEventListener('click', closeSettings);

  // Simulation
  document.getElementById('btnSimToggle')?.addEventListener('click', toggleSimulation);

  // Notes
  document.getElementById('btnSaveNotes').addEventListener('click', saveNotes);
  document.getElementById('btnCancelNotes').addEventListener('click', closeNotesModal);

  // Repair
  document.getElementById('btnConfirmRepair').addEventListener('click', confirmAddRepair);
  document.getElementById('btnCancelRepair').addEventListener('click', closeRepairModal);

  // Paramètres tab
  document.getElementById('btnSaveCfg').addEventListener('click', saveConfig);
  document.getElementById('btnDetectPort').addEventListener('click', detectPort);
  document.getElementById('btnTestConn').addEventListener('click', runConnectionTest);
  document.getElementById('btnSaveGarage')?.addEventListener('click', saveGarageSettings);
  document.getElementById('btnChangePwd')?.addEventListener('click', changePassword);

  // Alertes km
  document.getElementById('btnConfirmAlert').addEventListener('click', confirmAddAlert);
  document.getElementById('btnCancelAlerts').addEventListener('click', closeAlertsModal);

  // Rapport mensuel & Excel
  document.getElementById('btnMonthlyReport').addEventListener('click', openMonthlyModal);
  document.getElementById('btnExportExcel').addEventListener('click', exportExcel);
  document.getElementById('btnConfirmMonthly').addEventListener('click', generateMonthlyReport);
  document.getElementById('btnCancelMonthly').addEventListener('click', closeMonthlyModal);

  // Technician modal
  document.getElementById('btnConfirmTech').addEventListener('click', confirmTech);
  document.getElementById('btnCancelTech').addEventListener('click', closeTechModal);

  // Compare modal
  document.getElementById('btnCancelCompare').addEventListener('click', () => {
    document.getElementById('modalCompare').classList.add('hidden');
  });

  // Backup
  document.getElementById('btnBackup').addEventListener('click', triggerBackup);

  // Legal year + version auto
  const legalYear = document.getElementById('legalYear');
  if (legalYear) legalYear.textContent = new Date().getFullYear();
  const legalVersion = document.getElementById('legalVersion');
  if (legalVersion) {
    fetch('/api/version').then(r => r.json()).then(d => {
      if (d.version) legalVersion.textContent = d.version;
    }).catch(() => { legalVersion.textContent = '1.0.0'; });
  }

  // Add technician
  document.getElementById('btnAddTech').addEventListener('click', addTechnician);
  document.getElementById('newTechName').addEventListener('keydown', e => {
    if (e.key === 'Enter') addTechnician();
  });

  // Client PDF in current diagnostic
  document.getElementById('btnExportClientPDF').addEventListener('click', async () => {
    const analyse_ia = state.currentDiag?.analyse_ia;
    if (!state.currentDiag?.vin || !analyse_ia) {
      toast('Lancez d\'abord l\'analyse IA (étape 4)', 'warning');
      return;
    }
    const { vin, dtc_codes, realtime, kilometrage, savedEntry } = state.currentDiag;
    const diagData = savedEntry || {
      vin, dtc_codes, donnees_temps_reel: realtime, analyse_ia, kilometrage,
      statut: analyse_ia?.statut_global || 'OK',
      date_affichage: new Date().toLocaleString('fr-FR'),
    };
    await exportClientPDF(vin, diagData);
  });

  // Edit vehicle modal
  document.getElementById('btnCancelEditVehicle').addEventListener('click', closeEditVehicleModal);
  document.getElementById('btnConfirmEditVehicle').addEventListener('click', confirmEditVehicle);

  // ── Ajouter un véhicule manuellement ──
  document.getElementById('btnAddVehicle')?.addEventListener('click', () => {
    // Reset champs
    ['avMarque','avModele','avAnnee','avKm','avVin','avSurnom'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
    document.getElementById('avMotorisation').value = '';
    document.getElementById('modalAddVehicle').classList.remove('hidden');
    document.getElementById('avMarque')?.focus();
  });

  document.getElementById('btnCancelAddVehicle')?.addEventListener('click', () => {
    document.getElementById('modalAddVehicle').classList.add('hidden');
  });

  document.getElementById('btnConfirmAddVehicle')?.addEventListener('click', async () => {
    const marque = document.getElementById('avMarque').value.trim();
    const modele = document.getElementById('avModele').value.trim();
    if (!marque || !modele) { toast('Marque et modèle obligatoires', 'warning'); return; }

    const annee      = document.getElementById('avAnnee').value.trim();
    const motorisation = document.getElementById('avMotorisation').value;
    const km         = parseInt(document.getElementById('avKm').value) || 0;
    const surnom     = document.getElementById('avSurnom').value.trim();
    let vin          = document.getElementById('avVin').value.trim().toUpperCase();

    // Générer un pseudo-VIN si non fourni
    if (!vin) vin = 'MAN_' + Date.now().toString(36).toUpperCase();

    const vin_info = { marque, modele, annee, motorisation, km };
    try {
      await api('POST', '/api/fleet/vehicle', { vin, vin_info });
      // Appliquer surnom si renseigné
      if (surnom) await api('PUT', `/api/fleet/vehicle/${encodeURIComponent(vin)}/info`, { surnom }).catch(() => {});
      await loadFleet();
      document.getElementById('modalAddVehicle').classList.add('hidden');
      toast(`${marque} ${modele} ajouté à la flotte ✅`, 'success', 3000);
      // Sélectionner le véhicule dans la sidebar
      renderFleetManagement();
    } catch(e) {
      toast('Erreur lors de l\'ajout : ' + e.message, 'error');
    }
  });

  // Recherche dans la sidebar flotte
  document.getElementById('fleetSearchBox')?.addEventListener('input', () => renderFleetManagement());

  // Dashboard
  document.getElementById('dashVehicleSelect')?.addEventListener('change', e => {
    renderDashboardMaintenance(e.target.value);
  });
  document.getElementById('btnAddMaintItem')?.addEventListener('click', openAddMaintModal);
  document.getElementById('mdCancel')?.addEventListener('click', () => document.getElementById('modalMarkDone').classList.add('hidden'));
  document.getElementById('mdConfirm')?.addEventListener('click', confirmMarkDone);
  document.getElementById('amCancel')?.addEventListener('click', () => document.getElementById('modalAddMaint').classList.add('hidden'));
  document.getElementById('amConfirm')?.addEventListener('click', confirmAddMaint);
  document.getElementById('amType')?.addEventListener('change', e => {
    document.getElementById('amScheduledFields').classList.toggle('hidden', e.target.value !== 'scheduled');
    document.getElementById('amWearFields').classList.toggle('hidden', e.target.value !== 'wear');
  });

  // Close modals on overlay click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) overlay.classList.add('hidden');
    });
  });
}

// ════════════════════════════════════════════════════════
//  WIZARD DIAGNOSTIC — 4 ÉTAPES
// ════════════════════════════════════════════════════════

let _wizardMonitorInterval = null;
let _wizardMonitorStartTime = null;
let _wizardStep2CountdownTimer = null;
let _wizardStep3ElapsedTimer = null;

function wizardSetDotState(step, s) { // s = 'active'|'done'|'skipped'|''
  const dot = document.getElementById('wdot' + step);
  if (!dot) return;
  dot.className = 'wizard-step-dot' + (s ? ' ' + s : '');
}

function wizardSetCardState(step, s) { // s = 'active'|'done'|'skipped'|''
  const card = document.getElementById('wizardStep' + step);
  if (!card) return;
  card.className = 'wizard-card' + (s ? ' ' + s : '');
}

function wizardActivateStep(step) {
  state.wizardStep = step;
  for (let i = 1; i <= 4; i++) {
    if (i < step) {
      // already done/skipped — don't change
    } else if (i === step) {
      wizardSetDotState(i, 'active');
      wizardSetCardState(i, 'active');
    } else {
      // future steps stay locked
      const card = document.getElementById('wizardStep' + i);
      if (card && !card.classList.contains('done') && !card.classList.contains('skipped')) {
        card.className = 'wizard-card';
      }
    }
  }
}

function wizardMarkDone(step, summaryHtml, skipped = false) {
  const s = skipped ? 'skipped' : 'done';
  wizardSetDotState(step, skipped ? 'skipped' : 'done');
  wizardSetCardState(step, s);
  const summary = document.getElementById('step' + step + 'Summary');
  if (summary) {
    summary.innerHTML = summaryHtml;
    summary.classList.remove('hidden');
  }
  // Hide actions
  const actions = document.getElementById('step' + step + 'Actions');
  if (actions) actions.classList.add('hidden');
}

// ── STEP 2 : RALENTI ──────────────────────────────────
async function startWizardStep2() {
  try {
    const r = await api('POST', '/api/monitoring/start');
    if (!r.success) { toast(r.message || 'Erreur démarrage', 'warning'); return; }
    _wizardMonitorStartTime = Date.now();

    document.getElementById('btnStartStep2').disabled = true;
    document.getElementById('btnStopStep2').classList.remove('hidden');
    document.getElementById('btnSkipStep2').classList.add('hidden');
    document.getElementById('step2Instruction').classList.add('hidden');
    document.getElementById('step2Monitor').classList.remove('hidden');

    let remaining = 90;
    const cd = document.getElementById('step2Countdown');
    cd.textContent = remaining + 's';

    _wizardStep2CountdownTimer = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(_wizardStep2CountdownTimer);
        cd.textContent = '✓';
        cd.classList.add('done-count');
        finishWizardStep2();
      } else {
        cd.textContent = remaining + 's';
      }
    }, 1000);

    _wizardMonitorInterval = setInterval(() => refreshWizardMonitor(2), 800);
  } catch(e) { toast('Erreur : ' + e.message, 'error'); }
}

async function finishWizardStep2(skipped = false) {
  clearInterval(_wizardStep2CountdownTimer);
  clearInterval(_wizardMonitorInterval);
  _wizardStep2CountdownTimer = null;

  // Reset stop button visibility
  const btnStop2 = document.getElementById('btnStopStep2');
  if (btnStop2) btnStop2.classList.add('hidden');
  const btnSkip2 = document.getElementById('btnSkipStep2');
  if (btnSkip2) btnSkip2.classList.remove('hidden');

  try {
    const r = await api('POST', '/api/monitoring/stop');
    const session = r.session || r;
    if (!skipped && session && session.readings_count > 0) {
      state.session_ralenti = session;
      const stats = session.stats || {};
      const fmt = (k, u) => stats[k]?.max > 0 ? `${stats[k].min}–${stats[k].max}${u}` : '—';
      wizardMarkDone(2, `✓ Ralenti analysé — RPM: ${fmt('rpm',' tr/min')} · Temp: ${fmt('temp','°C')} · ${session.readings_count} mesures`);
    } else {
      state.session_ralenti = null;
      wizardMarkDone(2, skipped ? 'Étape passée' : 'Aucune donnée collectée', skipped);
    }
  } catch(e) {
    state.session_ralenti = null;
    wizardMarkDone(2, 'Étape passée', true);
  }

  wizardActivateStep(3);
  applyStepTriage(3);
  updateStepContextualHint(3);
}

// ── STEP 3 : ROULANT ─────────────────────────────────
async function startWizardStep3() {
  try {
    const r = await api('POST', '/api/monitoring/start');
    if (!r.success) { toast(r.message || 'Erreur démarrage', 'warning'); return; }
    _wizardMonitorStartTime = Date.now();

    document.getElementById('btnStartStep3').classList.add('hidden');
    document.getElementById('btnSkipStep3').classList.add('hidden');
    document.getElementById('step3Instruction').classList.add('hidden');
    document.getElementById('step3Monitor').classList.remove('hidden');

    // Add "J'ai terminé" button dynamically
    const actions = document.getElementById('step3Actions');
    actions.classList.remove('hidden');
    const finBtn = document.createElement('button');
    finBtn.className = 'btn btn-success';
    finBtn.id = 'btnFinishStep3';
    finBtn.textContent = '✓ J\'ai terminé';
    finBtn.onclick = () => finishWizardStep3(false);
    actions.innerHTML = '';
    actions.appendChild(finBtn);

    let elapsed = 0;
    const timer = document.getElementById('step3Timer');
    _wizardStep3ElapsedTimer = setInterval(() => {
      elapsed++;
      timer.textContent = elapsed + 's';
    }, 1000);

    _wizardMonitorInterval = setInterval(() => refreshWizardMonitor(3), 800);
  } catch(e) { toast('Erreur : ' + e.message, 'error'); }
}

async function finishWizardStep3(skipped = false) {
  clearInterval(_wizardStep3ElapsedTimer);
  clearInterval(_wizardMonitorInterval);
  _wizardStep3ElapsedTimer = null;

  try {
    const r = await api('POST', '/api/monitoring/stop');
    const session = r.session || r;
    if (!skipped && session && session.readings_count > 0) {
      state.session_roulant = session;
      const stats = session.stats || {};
      const fmt = (k, u) => stats[k]?.max > 0 ? `${stats[k].min}–${stats[k].max}${u}` : '—';
      wizardMarkDone(3, `✓ Conduite analysée — Vitesse max: ${stats.speed?.max || 0} km/h · RPM max: ${stats.rpm?.max || 0} tr/min · ${session.readings_count} mesures`);
    } else {
      state.session_roulant = null;
      wizardMarkDone(3, skipped ? 'Étape passée' : 'Aucune donnée collectée', skipped);
    }
  } catch(e) {
    state.session_roulant = null;
    wizardMarkDone(3, 'Étape passée', true);
  }

  wizardActivateStep(4);
  updateAnaReminderBanner();
  updateStepContextualHint(4);
}

async function refreshWizardMonitor(step) {
  try {
    const s = await api('GET', '/api/monitoring/status');
    if (!s.active) return;
    const cur = s.current || {};
    const prefix = 'mon' + step;
    const setV = (id, val, unit) => {
      const el = document.getElementById(id);
      if (el) el.querySelector('.mon-val').textContent = val ? `${val}${unit}` : '—';
    };
    setV(prefix + 'Rpm',   cur.rpm,     '');
    setV(prefix + 'Temp',  cur.temp,    '°C');
    setV(prefix + 'Speed', cur.speed,   ' km/h');
    setV(prefix + 'Volt',  cur.voltage, 'V');

    // Feed anomalies
    const feed = document.getElementById('step' + step + 'AnomalyFeed');
    if (feed) {
      (s.new_anomalies || []).forEach(a => {
        const div = document.createElement('div');
        div.className = 'anomaly-item' + (a.type?.includes('critical') ? '' : ' warn');
        div.innerHTML = `<span class="anomaly-time">${(a.timestamp||'').substring(11,19)}</span><span>${a.message}</span>`;
        feed.insertBefore(div, feed.firstChild);
        if (feed.children.length > 10) feed.removeChild(feed.lastChild);
      });
    }
  } catch(e) {}
}

// ── STEP 4 : ANALYSE COMPLÈTE ─────────────────────────
async function runFullAnalysis() {
  const vin = state.currentDiag.vin;
  const km = parseInt(document.getElementById('inputKm')?.value) || 0;
  state.currentDiag.kilometrage = km;

  // Auto-collecter l'anamnèse si le formulaire est rempli mais pas encore confirmé
  const anaCard = document.getElementById('wizardStepAnamnese');
  const anaSkipped = anaCard?.classList.contains('skipped');
  if (!state.currentDiag.anamnese && !anaSkipped) {
    const collected = anamneseCollect();
    const hasData = collected.frequence || collected.symptomes.length > 0 ||
                    collected.depuis_quand || collected.apres_intervention ||
                    collected.sons_decrits || collected.interventions_recentes ||
                    collected.infos_libres;
    if (hasData) {
      state.currentDiag.anamnese = collected;
      const dot = document.getElementById('wdotA');
      if (dot) dot.className = 'wizard-step-dot done';
      if (anaCard) { anaCard.classList.remove('active'); anaCard.classList.add('done'); }
      updateAnaReminderBanner();
      updateStepContextualHint(4);
    }
  }

  document.getElementById('btnRunAnalysis').disabled = true;
  document.getElementById('aiLoading').classList.remove('hidden');
  document.getElementById('aiResults').classList.add('hidden');
  document.getElementById('actionBar').classList.add('hidden');
  document.getElementById('chatSection').classList.add('hidden');

  try {
    const body = {
      vin,
      dtc_codes:      state.currentDiag.dtc_codes    || [],
      realtime:       state.currentDiag.realtime      || {},
      freeze_frame:   state.currentDiag.freeze_frame  || null,
      kilometrage:    km,
      session_ralenti: state.session_ralenti || null,
      session_roulant: state.session_roulant || null,
      anamnese:       state.currentDiag.anamnese      || null,
      vehicle_manual: state.currentDiag.vehicle_manual || null,
    };

    const result = await api('POST', '/api/analyze-full', body, 360000); // 6 min — analyse IA longue
    state.currentDiag.analyse_ia = result;

    const vi = result.vin_info || {};
    const fleetVehicle = state.fleet.find(x => x.vin === vin);
    const codePrefix = fleetVehicle?.code ? `[${fleetVehicle.code}] ` : '';
    const label = [vi.marque, vi.modele, vi.annee ? `— ${vi.annee}` : ''].filter(s => s && s !== 'Inconnu').join(' ');
    document.getElementById('vehicleLabel').textContent = `${codePrefix}${label || 'Véhicule'}`;

    renderAIResults(result);
    document.getElementById('aiLoading').classList.add('hidden');
    document.getElementById('aiResults').classList.remove('hidden');
    document.getElementById('actionBar').classList.remove('hidden');
    document.getElementById('chatSection').classList.remove('hidden');
    document.getElementById('step4Actions').classList.add('hidden');
    _chatHistory = [];
    renderChatMessages();

    await api('POST', '/api/fleet/vehicle', { vin, vin_info: vi });
    await loadFleet();

    wizardSetDotState(4, 'done');
    wizardSetCardState(4, 'done');
    document.getElementById('btnExportPDF').textContent = `📄 Exporter PDF (…${vin ? vin.slice(-6) : '?'})`;
  } catch(e) {
    document.getElementById('aiLoading').classList.add('hidden');
    toast('Erreur analyse IA : ' + e.message, 'error', 5000);
    document.getElementById('btnRunAnalysis').disabled = false;
  }
}

// ════════════════════════════════════════════════════════
//  ANAMNÈSE — Contexte & Symptômes
// ════════════════════════════════════════════════════════

// Skip step 3 automatiquement si le véhicule ne démarre pas
function applyStepTriage(step) {
  if (step !== 3) return;
  const ana = state.currentDiag.anamnese;
  const neDemarre = ana?.demarre === 'non';
  if (!neDemarre) return;

  // Remplacer le contenu de step 3 par un bandeau non-applicable
  const body = document.getElementById('step3Body');
  if (body) {
    body.innerHTML = `<div class="step3-na-banner">
      🚫 <strong>Analyse roulante non applicable</strong> — le véhicule ne démarrant pas,
      cette étape a été ignorée automatiquement.<br>
      <span style="font-size:.82rem;opacity:.8">L'IA tiendra compte de cette contrainte dans son diagnostic.</span>
    </div>`;
  }
  document.getElementById('step3Actions')?.classList.add('hidden');
  state.session_roulant = null;
  wizardMarkDone(3, '🚫 Non applicable — véhicule ne démarrant pas', true);
  // Passer directement à step 4
  wizardActivateStep(4);
  updateAnaReminderBanner();
  updateStepContextualHint(4);
}

// Hint contextuel selon les symptômes, adapté à chaque étape
function updateStepContextualHint(step) {
  const hintEl = document.getElementById('step' + step + 'ContextHint');
  if (!hintEl) return;

  const ana = state.currentDiag.anamnese;
  const dtcs = state.currentDiag.dtc_codes || [];
  let title = '', detail = '', icon = '';

  if (step === 2) {
    icon = '🔑';
    title = 'Démarrez le moteur et laissez-le tourner au ralenti minimum 90 secondes.';
    if (ana?.frequence?.includes('froid')) {
      detail = '⚠️ La panne survient à froid — démarrez sans réchauffer, commencez la mesure immédiatement.';
    } else if (ana?.symptomes?.includes('Régime irrégulier au ralenti')) {
      detail = '💡 Régime irrégulier signalé — observez l\'anomalie RPM dans le moniteur en temps réel.';
    } else if (ana?.symptomes?.includes('Vibrations anormales')) {
      detail = '💡 Vibrations signalées — montez en température et observez les RPM et charge moteur.';
    } else if (dtcs.length > 0) {
      detail = `📡 ${dtcs.length} code(s) DTC détecté(s) — les données au ralenti permettront de corréler les capteurs concernés.`;
    }
  } else if (step === 3) {
    icon = '🛣️';
    title = 'Partez faire un trajet de 2 à 3 minutes sur route normale.';
    if (ana?.moments?.includes('Sous charge (montée, accélération)')) {
      detail = '⚠️ Panne sous charge — accélérez franchement sur un bout de route pour reproduire les conditions.';
    } else if (ana?.moments?.includes('À l\'arrêt / ralenti')) {
      detail = '💡 Panne signalée à l\'arrêt — une courte sortie suffit, revenez vous arrêter 30s moteur tournant.';
    } else if (ana?.symptomes?.includes('Perte de puissance')) {
      detail = '⚠️ Perte de puissance signalée — testez une accélération franche entre 30 et 80 km/h.';
    } else if (ana?.frequence?.includes('chaud')) {
      detail = '🌡️ Panne à chaud — roulez suffisamment longtemps pour atteindre la température normale de fonctionnement.';
    }
  } else if (step === 4) {
    icon = '🤖';
    if (ana?.demarre === 'non') {
      title = 'Analyse sans données roulantes — l\'IA s\'appuie sur les codes DTC, le contexte et les données statiques.';
      detail = '💡 Précisez les interventions récentes et les sons entendus dans le contexte pour maximiser la précision.';
    } else if (!ana) {
      title = 'L\'IA va analyser les codes DTC et les sessions de monitoring.';
      detail = '💡 Remplissez le Contexte & Symptômes ci-dessus pour un diagnostic 3× plus précis.';
    } else {
      const nbSym = (ana.symptomes || []).length;
      title = `Toutes les données sont prêtes${nbSym > 0 ? ` — ${nbSym} symptôme(s) renseigné(s)` : ''}.`;
      detail = '✅ L\'IA va croiser codes DTC, sessions de monitoring et contexte client pour son diagnostic.';
    }
  }

  if (!title) { hintEl.classList.add('hidden'); return; }
  hintEl.innerHTML = `<span class="hint-icon">${icon}</span>
    <div class="hint-body">
      <div class="hint-title">${title}</div>
      ${detail ? `<div class="hint-detail">${detail}</div>` : ''}
    </div>`;
  hintEl.classList.remove('hidden');
}

function anamneseScrollTo() {
  const card = document.getElementById('wizardStepAnamnese');
  if (card) {
    card.classList.remove('hidden', 'skipped');
    card.classList.add('active');
    card.querySelector('.wizard-card-actions')?.classList.remove('hidden');
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const dot = document.getElementById('wdotA');
    if (dot) dot.className = 'wizard-step-dot active';
  }
}

// Affiche ou cache le banner de rappel anamnèse / bilan dans step 4
function updateAnaReminderBanner() {
  const banner = document.getElementById('anaReminderBanner');
  if (!banner) return;
  const cardId = getStep2CardId();
  const card   = document.getElementById(cardId);
  const isDone    = card?.classList.contains('done');
  const isSkipped = card?.classList.contains('skipped');
  if (isDone || isSkipped) {
    banner.classList.add('hidden');
  } else {
    banner.classList.remove('hidden');
    // Adapter le texte selon le mode
    const isControle = cardId === 'wizardStepBilan';
    banner.querySelector('strong')?.replaceChildren(
      document.createTextNode(isControle ? 'Contexte du bilan non renseigné' : 'Contexte & Symptômes non renseigné')
    );
  }
}

/**
 * Retourne l'ID de la carte étape 2 active selon le type de diagnostic :
 *  - "panne"    → wizardStepAnamnese (8 sections : symptômes, fréquence, etc.)
 *  - "controle" → wizardStepBilan    (4 sections : type de bilan, observations…)
 */
function getStep2CardId() {
  return state.currentDiag.type === 'controle' ? 'wizardStepBilan' : 'wizardStepAnamnese';
}

/**
 * Adapte les labels du rail wizard, du dot 5 et du bouton final selon le mode :
 *  - panne    : "Contexte" / "Analyse" / "Lancer l'analyse complète"
 *  - controle : "Bilan"    / "Bilan"   / "Lancer le bilan de santé"
 */
function applyDiagModeLabels() {
  const isControle = state.currentDiag.type === 'controle';
  // Dot rail wizard
  const dotALabel = document.querySelector('#wdotA .wdot-label');
  if (dotALabel) dotALabel.textContent = isControle ? 'Bilan' : 'Contexte';
  // Dot 5 (Analyse / Bilan)
  const dot4Label = document.querySelector('#wdot4 .wdot-label');
  if (dot4Label) dot4Label.textContent = isControle ? 'Bilan' : 'Analyse';
  // Card étape 5 — titre + desc + bouton
  const step4 = document.getElementById('wizardStep4');
  if (step4) {
    const h3 = step4.querySelector('h3');
    const desc = step4.querySelector('.wizard-card-desc');
    const badge = step4.querySelector('.wizard-step-badge');
    if (badge) badge.textContent = 'Étape 5';
    if (h3)    h3.textContent    = isControle ? 'Bilan de santé' : 'Analyse IA complète';
    if (desc)  desc.textContent  = isControle
      ? 'L\'IA évalue l\'état général du véhicule par système et propose un plan de maintenance préventive.'
      : 'L\'IA croise les codes DTC, les données au ralenti et en conduite pour un diagnostic précis.';
  }
  // Bouton final
  const btnAnalyze = document.getElementById('btnRunAnalysis');
  if (btnAnalyze) {
    btnAnalyze.textContent = isControle ? 'Lancer le bilan de santé' : 'Lancer l\'analyse complète';
  }
}

function anamneseShow() {
  applyDiagModeLabels();
  const activeId   = getStep2CardId();
  const otherId    = activeId === 'wizardStepBilan' ? 'wizardStepAnamnese' : 'wizardStepBilan';
  const card       = document.getElementById(activeId);
  const otherCard  = document.getElementById(otherId);
  // Cache l'autre carte (l'app se rappelle peut-être d'un précédent diag)
  if (otherCard) {
    otherCard.classList.add('hidden');
    otherCard.classList.remove('active', 'done', 'skipped');
  }
  if (card) {
    card.classList.remove('hidden', 'done', 'skipped');
    card.classList.add('active');
  }
  const dot = document.getElementById('wdotA');
  if (dot) dot.className = 'wizard-step-dot active';
  // Adapter le label du dot selon mode
  const dotLabel = dot?.querySelector('.wdot-label');
  if (dotLabel) dotLabel.textContent = (activeId === 'wizardStepBilan') ? 'Bilan' : 'Contexte';
  // Reset form de la carte active
  if (card) {
    card.querySelectorAll('input[type=radio], input[type=checkbox]').forEach(i => i.checked = false);
    card.querySelectorAll('select').forEach(s => s.selectedIndex = 0);
    card.querySelectorAll('textarea, input[type=text]').forEach(t => t.value = '');
  }
  document.getElementById('anamneseSummary')?.classList.add('hidden');
  document.getElementById('bilanSummary')?.classList.add('hidden');
  // Re-init l'accordéon de la carte active
  if (typeof setupAnamneseFlow === 'function') setupAnamneseFlow();
  // Bloquer step 2 tant que l'anamnèse n'est pas résolue
  _anamneseLockStep2();
}

function _anamneseLockStep2() {
  const btn = document.getElementById('btnStartStep2');
  const btnSkip = document.getElementById('btnSkipStep2');
  if (btn) {
    btn.disabled = true;
    btn.title = 'Remplissez d\'abord le contexte & symptômes ci-dessus';
  }
  if (btnSkip) {
    btnSkip.disabled = true;
    btnSkip.title = 'Remplissez ou passez d\'abord le contexte & symptômes';
  }
  // Ajouter un bandeau d'attente sous step 2
  const step2Body = document.getElementById('step2Body');
  if (step2Body && !document.getElementById('step2AnaLock')) {
    const lock = document.createElement('div');
    lock.id = 'step2AnaLock';
    lock.className = 'step2-ana-lock';
    lock.innerHTML = '📋 <strong>Remplissez d\'abord le Contexte & Symptômes</strong> ci-dessus — puis revenez ici pour démarrer la mesure.';
    lock.addEventListener('click', () => {
      document.getElementById('wizardStepAnamnese')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    step2Body.insertBefore(lock, step2Body.firstChild);
  }
}

function _anamneseUnlockStep2() {
  const btn = document.getElementById('btnStartStep2');
  const btnSkip = document.getElementById('btnSkipStep2');
  if (btn) { btn.disabled = false; btn.title = ''; }
  if (btnSkip) { btnSkip.disabled = false; btnSkip.title = ''; }
  document.getElementById('step2AnaLock')?.remove();
}

function anamneseHide() {
  // Cache les deux cartes par sécurité (changement de mode entre 2 diags)
  document.getElementById('wizardStepAnamnese')?.classList.add('hidden');
  document.getElementById('wizardStepBilan')?.classList.add('hidden');
}

// ════════════════════════════════════════════════════════
//  ENREGISTREUR AUDIO + SPECTROGRAMME (Web Audio API)
// ════════════════════════════════════════════════════════

const _audio = {
  ctx: null, analyser: null, source: null,
  stream: null, mediaRecorder: null,
  rafId: null, timerInterval: null,
  elapsed: 0, MAX_DURATION: 10,
  freqData: null, peaks: [],
};

// Interprétation mécanique des fréquences dominantes
function _interpretFreqs(peaks, rpm) {
  const interps = [];
  for (const { freq, magnitude } of peaks) {
    if (magnitude < 30) continue; // bruit de fond
    if (freq < 20)        interps.push(`Vibration basse fréquence (${freq} Hz) — possible déséquilibre moteur ou jeu de transmission`);
    else if (freq < 60)   interps.push(`Battement grave (${freq} Hz) — suspect : palier, cardan, rotule`);
    else if (freq < 200)  interps.push(`Grondement (${freq} Hz) — suspect : roulement, vilebrequin, pompe`);
    else if (freq < 500)  interps.push(`Claquement mécanique (${freq} Hz) — suspect : soupapes, chaîne de distribution, injecteurs`);
    else if (freq < 1500) interps.push(`Sifflement modéré (${freq} Hz) — suspect : courroie accessoire, turbo, fuite air admission`);
    else if (freq < 4000) interps.push(`Sifflement aigu (${freq} Hz) — suspect : fuite turbo, joint culasse, courroie serpentine`);
    else                  interps.push(`Fréquence très haute (${freq} Hz) — suspect : frottement métallique, défaut alternateur`);
  }
  return interps.length ? interps : ['Niveau sonore faible — aucune anomalie fréquentielle marquée détectée'];
}

function _drawSpectrogram(canvas, analyser, freqData) {
  const ctx2d = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  analyser.getByteFrequencyData(freqData);

  // Décaler l'image vers la gauche (défilement temporel)
  const imgData = ctx2d.getImageData(1, 0, W - 1, H);
  ctx2d.putImageData(imgData, 0, 0);

  // Dessiner la colonne de droite
  const binCount = freqData.length;
  for (let i = 0; i < H; i++) {
    const binIdx = Math.floor((1 - i / H) * binCount);
    const val = freqData[binIdx] || 0;
    const r = val > 200 ? 255 : val > 100 ? 255 : Math.floor(val * 1.5);
    const g = val > 200 ? 50  : Math.floor(val * 0.8);
    const b = val > 150 ? 50  : Math.floor(255 - val * 2);
    ctx2d.fillStyle = `rgb(${r},${g},${b})`;
    ctx2d.fillRect(W - 1, i, 1, 1);
  }
}

function _extractPeaks(freqData, sampleRate) {
  const binSize = sampleRate / 2 / freqData.length;
  const peaks = [];
  for (let i = 1; i < freqData.length - 1; i++) {
    if (freqData[i] > freqData[i-1] && freqData[i] > freqData[i+1] && freqData[i] > 40) {
      peaks.push({ freq: Math.round(i * binSize), magnitude: freqData[i] });
    }
  }
  peaks.sort((a, b) => b.magnitude - a.magnitude);
  return peaks.slice(0, 5);
}

async function audioRecordStart() {
  try {
    _audio.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch(e) {
    toast('Accès micro refusé — vérifiez les permissions du navigateur', 'error', 4000);
    return;
  }

  _audio.ctx      = new (window.AudioContext || window.webkitAudioContext)();
  _audio.analyser = _audio.ctx.createAnalyser();
  _audio.analyser.fftSize = 2048;
  _audio.freqData = new Uint8Array(_audio.analyser.frequencyBinCount);

  _audio.source = _audio.ctx.createMediaStreamSource(_audio.stream);
  _audio.source.connect(_audio.analyser);

  // UI
  const btn   = document.getElementById('btnAudioRecord');
  const label = document.getElementById('btnAudioLabel');
  const stop  = document.getElementById('btnAudioStop');
  const timer = document.getElementById('audioRecordTimer');
  const canvas = document.getElementById('spectrogramCanvas');
  const result = document.getElementById('audioAnalysisResult');

  btn.classList.add('recording');
  label.textContent = 'Enregistrement…';
  stop.classList.remove('hidden');
  timer.classList.remove('hidden');
  canvas.classList.remove('hidden');
  result.classList.add('hidden');

  // Effacer le canvas
  const ctx2d = canvas.getContext('2d');
  ctx2d.fillStyle = '#0f172a';
  ctx2d.fillRect(0, 0, canvas.width, canvas.height);

  _audio.elapsed = 0;
  _audio.timerInterval = setInterval(() => {
    _audio.elapsed++;
    timer.textContent = `${_audio.elapsed}s / ${_audio.MAX_DURATION}s`;
    if (_audio.elapsed >= _audio.MAX_DURATION) audioRecordStop();
  }, 1000);

  // Boucle d'animation spectrogramme
  function drawLoop() {
    _drawSpectrogram(canvas, _audio.analyser, _audio.freqData);
    _audio.rafId = requestAnimationFrame(drawLoop);
  }
  drawLoop();
}

function audioRecordStop() {
  cancelAnimationFrame(_audio.rafId);
  clearInterval(_audio.timerInterval);

  // Extraire les pics finaux
  if (_audio.analyser && _audio.freqData) {
    _audio.analyser.getByteFrequencyData(_audio.freqData);
    _audio.peaks = _extractPeaks(_audio.freqData, _audio.ctx.sampleRate);
  }

  // Arrêter le flux micro
  _audio.stream?.getTracks().forEach(t => t.stop());
  _audio.source?.disconnect();
  _audio.ctx?.close();

  // UI
  const btn   = document.getElementById('btnAudioRecord');
  const label = document.getElementById('btnAudioLabel');
  const stop  = document.getElementById('btnAudioStop');
  const timer = document.getElementById('audioRecordTimer');
  const clear = document.getElementById('btnAudioClear');
  const result = document.getElementById('audioAnalysisResult');

  btn.classList.remove('recording');
  label.textContent = 'Ré-enregistrer';
  stop.classList.add('hidden');
  timer.classList.add('hidden');
  clear.classList.remove('hidden');

  // Afficher l'interprétation
  const interps = _interpretFreqs(_audio.peaks, null);
  const peakList = _audio.peaks.length
    ? _audio.peaks.map(p => `${p.freq} Hz (intensité ${p.magnitude})`).join(', ')
    : 'Aucun pic détecté';

  result.innerHTML = `
    <div class="freq-title">🎵 Fréquences dominantes : ${peakList}</div>
    <div class="freq-interp">💡 ${interps.join('<br>💡 ')}</div>`;
  result.classList.remove('hidden');

  // Injecter dans ana_sons si vide
  const textarea = document.getElementById('ana_sons');
  if (textarea && !textarea.value.trim()) {
    textarea.value = `Analyse acoustique automatique — Pics : ${peakList}. ${interps.join('. ')}`;
  }

  // Stocker les données audio dans l'état pour l'IA
  state.currentDiag._audio_peaks = _audio.peaks;
  state.currentDiag._audio_interps = interps;
}

function audioRecordClear() {
  const canvas = document.getElementById('spectrogramCanvas');
  const result = document.getElementById('audioAnalysisResult');
  const clear  = document.getElementById('btnAudioClear');
  const label  = document.getElementById('btnAudioLabel');

  const ctx2d = canvas.getContext('2d');
  ctx2d.fillStyle = '#0f172a';
  ctx2d.fillRect(0, 0, canvas.width, canvas.height);
  canvas.classList.add('hidden');
  result.classList.add('hidden');
  clear.classList.add('hidden');
  label.textContent = 'Enregistrer le son moteur';

  document.getElementById('ana_sons').value = '';
  state.currentDiag._audio_peaks  = null;
  state.currentDiag._audio_interps = null;
  _audio.peaks = [];
}

function anamneseCollect() {
  const get = id => (document.getElementById(id)?.value || '').trim();
  const freq = document.querySelector('input[name="ana_freq"]:checked')?.value || '';
  const moments = [...document.querySelectorAll('input[name="ana_moment"]:checked')].map(i => i.value);
  const symptomes = [...document.querySelectorAll('input[name="ana_symptome"]:checked')].map(i => i.value);
  const demarre = document.querySelector('input[name="ana_demarre"]:checked')?.value || '';
  return {
    demarre,
    depuis_quand:            get('ana_depuis'),
    apres_intervention:      get('ana_apres_intervention'),
    frequence:               freq,
    moments,
    symptomes,
    sons_decrits:            get('ana_sons'),
    interventions_recentes:  get('ana_interventions'),
    infos_libres:            get('ana_infos'),
    audio_peaks:             state.currentDiag._audio_peaks  || null,
    audio_interpretations:   state.currentDiag._audio_interps || null,
  };
}

function anamneseConfirm() {
  const data = anamneseCollect();
  state.currentDiag.anamnese = data;
  // Résumé visuel
  const parts = [];
  if (data.frequence)   parts.push(data.frequence);
  if (data.apres_intervention) parts.push(`Après : ${data.apres_intervention}`);
  if (data.symptomes.length)   parts.push(`Symptômes : ${data.symptomes.slice(0,3).join(', ')}${data.symptomes.length > 3 ? '…' : ''}`);
  if (data.sons_decrits)       parts.push('Description acoustique renseignée');
  const summaryEl = document.getElementById('anamneseSummary');
  if (summaryEl) {
    summaryEl.innerHTML = `✅ Contexte enregistré — ${parts.join(' · ') || 'informations saisies'}`;
    summaryEl.classList.remove('hidden');
  }
  // Marquer le dot
  const dot = document.getElementById('wdotA');
  if (dot) dot.className = 'wizard-step-dot done';
  // Masquer les actions, garder la carte en mode "done"
  document.querySelector('#wizardStepAnamnese .wizard-card-actions')?.classList.add('hidden');
  document.getElementById('wizardStepAnamnese')?.classList.remove('active');
  document.getElementById('wizardStepAnamnese')?.classList.add('done');
  _anamneseUnlockStep2();
  toast('Contexte enregistré ✅ — L\'IA utilisera ces informations', 'success', 2500);
  updateAnaReminderBanner();
  updateStepContextualHint(2);
  updateStepContextualHint(3);
  updateStepContextualHint(4);
  if (state.wizardStep === 3) applyStepTriage(3);
  // Scroll vers step 2
  document.getElementById('wizardStep2')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function anamneseSkip() {
  state.currentDiag.anamnese = null;
  const dot = document.getElementById('wdotA');
  if (dot) dot.className = 'wizard-step-dot skipped';
  document.getElementById('wizardStepAnamnese')?.classList.remove('active');
  document.getElementById('wizardStepAnamnese')?.classList.add('skipped');
  document.querySelector('#wizardStepAnamnese .wizard-card-actions')?.classList.add('hidden');
  const summaryEl = document.getElementById('anamneseSummary');
  if (summaryEl) { summaryEl.innerHTML = '⏩ Étape passée'; summaryEl.classList.remove('hidden'); }
  _anamneseUnlockStep2();
  updateAnaReminderBanner();
  document.getElementById('wizardStep2')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ── Bilan de santé : collect + confirm + skip ──────────────────── */

const BILAN_TYPE_LABELS = {
  pre_achat:  'Pré-achat',
  periodique: 'Contrôle périodique',
  pre_ct:     'Avant contrôle technique',
  pre_route:  'Avant longue route',
};

function bilanCollect() {
  const get = (id) => (document.getElementById(id)?.value || '').trim();
  const type = document.querySelector('input[name="bilan_type"]:checked')?.value || '';
  const observations = Array.from(document.querySelectorAll('input[name="bilan_observation"]:checked'))
    .map(i => i.value);
  return {
    type,
    type_label:    BILAN_TYPE_LABELS[type] || '',
    observations,
    notes:         get('bilan_notes'),
    interventions: get('bilan_interventions'),
  };
}

function bilanConfirm() {
  const data = bilanCollect();
  if (!data.type) {
    toast('Choisissez un type de bilan avant de valider', 'warning', 3500);
    return;
  }
  state.currentDiag.bilan = data;
  // Compatibilité : on stocke aussi dans `anamnese` pour que le backend puisse y accéder
  state.currentDiag.anamnese = {
    bilan_mode: true,
    bilan_type: data.type,
    bilan_type_label: data.type_label,
    observations_visuelles: data.observations,
    notes_controle: data.notes,
    interventions_recentes: data.interventions,
  };
  // Résumé visuel
  const parts = [data.type_label || 'Bilan'];
  if (data.observations.length) parts.push(`${data.observations.length} observation(s)`);
  if (data.notes) parts.push('notes saisies');
  const summaryEl = document.getElementById('bilanSummary');
  if (summaryEl) {
    summaryEl.innerHTML = `✅ Contexte enregistré — ${parts.join(' · ')}`;
    summaryEl.classList.remove('hidden');
  }
  // Marquer le dot
  const dot = document.getElementById('wdotA');
  if (dot) dot.className = 'wizard-step-dot done';
  // Card en mode "done"
  document.querySelector('#wizardStepBilan .wizard-card-actions')?.classList.add('hidden');
  document.getElementById('wizardStepBilan')?.classList.remove('active');
  document.getElementById('wizardStepBilan')?.classList.add('done');
  _anamneseUnlockStep2();
  toast('Contexte enregistré ✅ — L\'IA orientera son analyse', 'success', 2500);
  if (typeof updateAnaReminderBanner === 'function') updateAnaReminderBanner();
  if (typeof updateStepContextualHint === 'function') {
    updateStepContextualHint(2);
    updateStepContextualHint(3);
    updateStepContextualHint(4);
  }
  if (state.wizardStep === 3 && typeof applyStepTriage === 'function') applyStepTriage(3);
  // Scroll vers step 2
  document.getElementById('wizardStep2')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function bilanSkip() {
  state.currentDiag.bilan = null;
  state.currentDiag.anamnese = null;
  const dot = document.getElementById('wdotA');
  if (dot) dot.className = 'wizard-step-dot skipped';
  document.getElementById('wizardStepBilan')?.classList.remove('active');
  document.getElementById('wizardStepBilan')?.classList.add('skipped');
  document.querySelector('#wizardStepBilan .wizard-card-actions')?.classList.add('hidden');
  const summaryEl = document.getElementById('bilanSummary');
  if (summaryEl) { summaryEl.innerHTML = '⏩ Étape passée'; summaryEl.classList.remove('hidden'); }
  _anamneseUnlockStep2();
  if (typeof updateAnaReminderBanner === 'function') updateAnaReminderBanner();
  document.getElementById('wizardStep2')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ════════════════════════════════════════════════════════
//  SCAN MULTI-ECU
// ════════════════════════════════════════════════════════

// Mapping constructeur → valeur select
const ECU_MAKE_MAP = {
  RENAULT: 'RENAULT', DACIA: 'RENAULT',
  SKODA: 'SKODA', VOLKSWAGEN: 'SKODA', VW: 'SKODA', AUDI: 'SKODA', SEAT: 'SKODA',
  TOYOTA: 'TOYOTA', LEXUS: 'TOYOTA',
  SUZUKI: 'SUZUKI',
  FIAT: 'FIAT', 'ALFA ROMEO': 'FIAT', ALFA: 'FIAT',
  PEUGEOT: 'PEUGEOT', CITROEN: 'PEUGEOT', CITROËN: 'PEUGEOT', DS: 'PEUGEOT',
  OPEL: 'OPEL', VAUXHALL: 'OPEL',
  FORD: 'FORD', BMW: 'BMW', MERCEDES: 'MERCEDES', 'MERCEDES-BENZ': 'MERCEDES',
};

function ecuScanShow() {
  const section = document.getElementById('ecuScanSection');
  if (section) section.classList.remove('hidden');

  // Auto-détecter le constructeur depuis le VIN info
  const label = document.getElementById('vehicleLabel')?.textContent || '';
  for (const [key, val] of Object.entries(ECU_MAKE_MAP)) {
    if (label.toUpperCase().includes(key)) {
      const sel = document.getElementById('ecuMakeSelect');
      if (sel) sel.value = val;
      break;
    }
  }
}

function ecuScanHide() {
  const section = document.getElementById('ecuScanSection');
  if (section) {
    section.classList.add('hidden');
    document.getElementById('ecuScanResults')?.classList.add('hidden');
    if (document.getElementById('ecuScanResults')) document.getElementById('ecuScanResults').innerHTML = '';
    document.getElementById('ecuScanLoading')?.classList.add('hidden');
  }
}

async function runECUScan() {
  const make = document.getElementById('ecuMakeSelect')?.value || 'GENERIC';
  const loadingEl = document.getElementById('ecuScanLoading');
  const resultsEl = document.getElementById('ecuScanResults');
  const msgEl     = document.getElementById('ecuScanMsg');
  const btn       = document.getElementById('btnRunECUScan');

  if (loadingEl) loadingEl.classList.remove('hidden');
  if (resultsEl) { resultsEl.classList.add('hidden'); resultsEl.innerHTML = ''; }
  if (btn)       { btn.disabled = true; btn.textContent = '⏳ Scan…'; }

  const moduleNames = {
    RENAULT: 9, SKODA: 9, TOYOTA: 8, SUZUKI: 6,
    FIAT: 7, PEUGEOT: 7, OPEL: 5, FORD: 6, BMW: 6, MERCEDES: 5, GENERIC: 6,
  };
  const totalMods = moduleNames[make] || 6;

  // Simuler la progression
  let modIdx = 0;
  const progressInterval = setInterval(() => {
    if (modIdx < totalMods && msgEl) {
      modIdx++;
      msgEl.textContent = `Scan module ${modIdx}/${totalMods}…`;
    }
  }, 2000);

  try {
    const res = await api('POST', '/api/scan-ecus', { make }, 90000);
    clearInterval(progressInterval);

    if (res.error) {
      toast('Erreur scan ECU : ' + res.error, 'error', 7000);
      if (loadingEl) loadingEl.classList.add('hidden');
      return;
    }

    renderECUScanResults(res, resultsEl);
    if (loadingEl) loadingEl.classList.add('hidden');
    if (resultsEl) resultsEl.classList.remove('hidden');

  } catch (e) {
    clearInterval(progressInterval);
    toast('Impossible de scanner les modules : ' + e.message, 'error', 7000);
    if (loadingEl) loadingEl.classList.add('hidden');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🔍 Relancer'; }
  }
}

function renderECUScanResults(data, container) {
  if (!container) return;

  const { modules = [], total_dtcs = 0, modules_found = 0, make = '' } = data;

  // En-tête résumé
  const hasDTCs = total_dtcs > 0;
  const summaryColor = hasDTCs ? '#e53935' : '#4caf50';
  const summaryIcon  = hasDTCs ? '⚠️' : '✅';

  let html = `<div style="padding:10px 14px;border-radius:8px;margin-bottom:12px;background:${hasDTCs ? 'rgba(229,57,53,.1)' : 'rgba(76,175,80,.1)'};border:1px solid ${summaryColor}40">
    <strong style="color:${summaryColor}">${summaryIcon} ${modules_found} module(s) actif(s) — ${total_dtcs} code(s) DTC au total</strong>
  </div>`;

  html += `<div class="ecu-modules-grid">`;
  for (const mod of modules) {
    const isOk      = mod.status === 'ok';
    const hasDtc    = (mod.dtcs || []).length > 0;
    const statusClr = !isOk ? '#888' : (hasDtc ? '#e53935' : '#4caf50');
    const statusLbl = !isOk ? 'Inactif' : (hasDtc ? `${mod.dtcs.length} DTC` : 'OK');
    const icon      = mod.icon || '🔧';
    const dtcBadges = (mod.dtcs || []).map(d => {
      const cat = d[0];
      const catColor = cat === 'P' ? '#e53935' : cat === 'B' ? '#ff9800' : cat === 'C' ? '#2196f3' : '#9c27b0';
      return `<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:700;background:${catColor}20;color:${catColor};border:1px solid ${catColor}50;margin:2px">${d}</span>`;
    }).join('');

    html += `<div style="padding:10px 14px;border-radius:8px;border:1px solid ${isOk ? (hasDtc ? '#e5393530' : '#4caf5030') : 'var(--border)'};background:${isOk ? (hasDtc ? 'rgba(229,57,53,.05)' : 'rgba(76,175,80,.05)') : 'var(--bg-main)'}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span style="font-weight:600;font-size:.85rem">${icon} ${mod.name}</span>
        <span style="font-size:.75rem;font-weight:700;color:${statusClr}">${statusLbl}</span>
      </div>
      <div style="font-size:.72rem;color:var(--text-muted);margin-bottom:${hasDtc ? '6px' : '0'}">Adresse CAN : 0x${mod.address || '—'}</div>
      ${hasDtc ? `<div>${dtcBadges}</div>` : ''}
    </div>`;
  }
  html += `</div>`;

  // Bouton : ajouter les DTC au diagnostic en cours
  if (hasDTCs) {
    const allDtcs = modules.flatMap(m => m.dtcs || []);
    const newDtcs = allDtcs.filter(d => !state.currentDiag.dtc_codes.includes(d));
    if (newDtcs.length > 0) {
      html += `<div style="margin-top:12px">
        <button type="button" class="btn btn-sm btn-primary" id="btnMergeECUDtc" data-dtcs='${JSON.stringify(newDtcs)}'>
          ➕ Ajouter ${newDtcs.length} code(s) au diagnostic en cours
        </button>
      </div>`;
    }
  }

  container.innerHTML = html;

  // Listener pour fusionner les DTCs
  document.getElementById('btnMergeECUDtc')?.addEventListener('click', function() {
    const dtcs = JSON.parse(this.dataset.dtcs || '[]');
    state.currentDiag.dtc_codes = [...new Set([...state.currentDiag.dtc_codes, ...dtcs])];
    const dtcEl = document.getElementById('dtcList');
    if (dtcEl) {
      dtcEl.innerHTML = state.currentDiag.dtc_codes.map(c => `<span class="dtc-badge">${c}</span>`).join('');
    }
    const sumEl = document.getElementById('step1Summary');
    if (sumEl) {
      sumEl.innerHTML = `✓ ${state.currentDiag.dtc_codes.length} code(s) DTC (dont modules constructeur) : ${state.currentDiag.dtc_codes.join(', ')}`;
    }
    this.disabled = true;
    this.textContent = '✅ Codes ajoutés';
    toast(`${dtcs.length} code(s) DTC ajouté(s) au diagnostic`, 'success', 4000);
  });
}

/** Reset COMPLET de l'état diagnostic : appelé par "Nouveau diagnostic"
 *  (retour menu) ET "Nouvelle lecture" (relance sur le même véhicule).
 *  Avant le fix, "Nouvelle lecture" ne réinitialisait que partiellement,
 *  laissant les résultats IA, l'anamnèse et le monitoring du précédent diag
 *  visibles à l'écran. */
function _resetDiagnosticFully() {
  wizardReset();
  // ── State currentDiag : fresh object identique à l'init (cf. ligne 12) ──
  state.currentDiag = {
    vin: null, dtc_codes: [], dtc_info: {}, dtc_families: {},
    mil_on: false, dtc_count_mil: null,
    realtime: {}, freeze_frame: {}, analyse_ia: null,
    kilometrage: 0, savedEntry: null,
    vehicle_manual: null, vehicle_decoded: null,
    anamnese: null,
    _audio_peaks: null, _audio_interps: null,
    vin_manually_entered: false,
  };
  state.diagSaved = false;
  _vinContribOpen = false;

  // ── UI : bandeau véhicule ──
  const vinDisplay     = document.getElementById('vinDisplay');
  const vehicleLabel   = document.getElementById('vehicleLabel');
  const simTag         = document.getElementById('simTag');
  const vehicleOdo     = document.getElementById('vehicleOdometer');
  if (vinDisplay)   vinDisplay.textContent = 'VIN —';
  if (vehicleLabel) vehicleLabel.innerHTML = 'Marque / Année';
  if (simTag)       simTag.classList.add('hidden');
  if (vehicleOdo)   { vehicleOdo.innerHTML = ''; vehicleOdo.classList.add('hidden'); }
  document.getElementById('vinManualZone')?.classList.add('hidden');
  document.getElementById('btnEditVin')?.classList.remove('hidden');

  // ── UI : zones diagnostic (DTC, freeze frame, kilométrage, IA, chat) ──
  const dtcList = document.getElementById('dtcList');
  if (dtcList) dtcList.innerHTML = '';
  document.getElementById('freezeFrameSection')?.classList.add('hidden');
  const inputKm = document.getElementById('inputKm');
  if (inputKm) inputKm.value = '';
  const step1Summary = document.getElementById('step1Summary');
  if (step1Summary) { step1Summary.classList.add('hidden'); step1Summary.style.color = ''; }

  // ── UI : barre d'action + résultats IA + chat + feedback sauvegarde ──
  document.getElementById('actionBar')?.classList.add('hidden');
  document.getElementById('saveFeedback')?.classList.add('hidden');
  const aiResults = document.getElementById('aiResults');
  if (aiResults) { aiResults.classList.add('hidden'); aiResults.innerHTML = ''; }
  document.getElementById('chatSection')?.classList.add('hidden');
}

function wizardReset() {
  clearInterval(_wizardStep2CountdownTimer);
  clearInterval(_wizardStep3ElapsedTimer);
  clearInterval(_wizardMonitorInterval);
  _wizardStep2CountdownTimer = null;
  _wizardStep3ElapsedTimer = null;
  _wizardMonitorInterval = null;
  // Arrêter le monitoring si actif
  fetch('/api/monitoring/stop', { method: 'POST' }).catch(() => {});
  state.wizardStep = 1;
  state.session_ralenti = null;
  state.session_roulant = null;
  for (let i = 1; i <= 4; i++) {
    const card = document.getElementById('wizardStep' + i);
    if (card) card.className = 'wizard-card' + (i === 1 ? ' active' : '');
    wizardSetDotState(i, i === 1 ? 'active' : '');
    const summary = document.getElementById('step' + i + 'Summary');
    if (summary) summary.classList.add('hidden');
    const actions = document.getElementById('step' + i + 'Actions');
    if (actions) actions.classList.remove('hidden');
  }
  // Reset step 2 specific UI
  const s2inst = document.getElementById('step2Instruction');
  if (s2inst) s2inst.classList.remove('hidden');
  const s2mon = document.getElementById('step2Monitor');
  if (s2mon) s2mon.classList.add('hidden');
  const btn2 = document.getElementById('btnStartStep2');
  if (btn2) btn2.disabled = false;
  const btnStop2 = document.getElementById('btnStopStep2');
  if (btnStop2) btnStop2.classList.add('hidden');
  const btnSkip2reset = document.getElementById('btnSkipStep2');
  if (btnSkip2reset) btnSkip2reset.classList.remove('hidden');
  // Reset step 3 specific UI
  const s3inst = document.getElementById('step3Instruction');
  if (s3inst) s3inst.classList.remove('hidden');
  const s3mon = document.getElementById('step3Monitor');
  if (s3mon) s3mon.classList.add('hidden');
  const btn3start = document.getElementById('btnStartStep3');
  const btn3skip = document.getElementById('btnSkipStep3');
  if (btn3start) btn3start.classList.remove('hidden');
  if (btn3skip) btn3skip.classList.remove('hidden');
  // Reset step 4 actions
  const step4actions = document.getElementById('step4Actions');
  if (step4actions) step4actions.classList.remove('hidden');
  const btnRun = document.getElementById('btnRunAnalysis');
  if (btnRun) btnRun.disabled = false;
  const cd = document.getElementById('step2Countdown');
  if (cd) { cd.textContent = '90s'; cd.classList.remove('done-count'); }
  const t3 = document.getElementById('step3Timer');
  if (t3) t3.textContent = '0s';
  // Reset anamnèse
  state.currentDiag.anamnese = null;
  const anaCard = document.getElementById('wizardStepAnamnese');
  if (anaCard) anaCard.classList.add('hidden');
  const dotA = document.getElementById('wdotA');
  if (dotA) dotA.className = 'wizard-step-dot';
  const anaSummary = document.getElementById('anamneseSummary');
  if (anaSummary) anaSummary.classList.add('hidden');
  const anaActions = document.querySelector('#wizardStepAnamnese .wizard-card-actions');
  if (anaActions) anaActions.classList.remove('hidden');
  // Reset audio state + UI
  state.currentDiag._audio_peaks = null;
  state.currentDiag._audio_interps = null;
  const audioResult = document.getElementById('audioAnalysisResult');
  if (audioResult) { audioResult.innerHTML = ''; audioResult.classList.add('hidden'); }
  const spectroCanvas = document.getElementById('spectrogramCanvas');
  if (spectroCanvas) { spectroCanvas.classList.add('hidden'); const ctx2 = spectroCanvas.getContext('2d'); if (ctx2) ctx2.clearRect(0, 0, spectroCanvas.width, spectroCanvas.height); }
  const btnRec = document.getElementById('btnAudioRecord');
  if (btnRec) btnRec.classList.remove('hidden');
  const btnStop = document.getElementById('btnAudioStop');
  if (btnStop) btnStop.classList.add('hidden');
  const btnClear = document.getElementById('btnAudioClear');
  if (btnClear) btnClear.classList.add('hidden');
  const recTimer = document.getElementById('audioRecordTimer');
  if (recTimer) { recTimer.textContent = '0s / 10s'; recTimer.classList.add('hidden'); }
  // Reset ECU scan section
  ecuScanHide();
}

// ════════════════════════════════════════════════════════
//  INIT
// ════════════════════════════════════════════════════════
// ════════════════════════════════════════════════════════
//  ENREGISTREMENT AUDIO + ANALYSE SPECTROGRAMME
// ════════════════════════════════════════════════════════

let _audioCtx = null;
let _audioStream = null;
let _audioSamples = [];
let _audioRecording = false;
let _audioTimerInterval = null;
let _audioProcessor = null;
const AUDIO_SR = 22050;   // sample rate cible
const AUDIO_MAX_S = 8;    // durée max en secondes

/** Encode Float32Array en fichier WAV (PCM 16 bits mono) */
function encodeWav(samples, sampleRate) {
  const numSamples = samples.length;
  const buf = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buf);
  const write = (off, str) => [...str].forEach((c, i) => view.setUint8(off + i, c.charCodeAt(0)));
  write(0, 'RIFF');
  view.setUint32(4, 36 + numSamples * 2, true);
  write(8, 'WAVE');
  write(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);          // PCM
  view.setUint16(22, 1, true);          // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, 'data');
  view.setUint32(40, numSamples * 2, true);
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return buf;
}

async function startAudioRecord() {
  if (_audioRecording) return;
  try {
    _audioStream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: AUDIO_SR, channelCount: 1 } });
  } catch (e) {
    toast('Accès micro refusé : ' + e.message, 'error'); return;
  }

  _audioCtx = new AudioContext({ sampleRate: AUDIO_SR });
  const source = _audioCtx.createMediaStreamSource(_audioStream);
  _audioProcessor = _audioCtx.createScriptProcessor(4096, 1, 1);
  _audioSamples = [];
  _audioRecording = true;

  _audioProcessor.onaudioprocess = (e) => {
    if (!_audioRecording) return;
    const ch = e.inputBuffer.getChannelData(0);
    _audioSamples.push(...ch);
    // Auto-stop à AUDIO_MAX_S secondes
    if (_audioSamples.length >= AUDIO_SR * AUDIO_MAX_S) stopAudioRecord();
  };

  source.connect(_audioProcessor);
  _audioProcessor.connect(_audioCtx.destination);

  // UI
  document.getElementById('audioRecordBar')?.classList.remove('hidden');
  document.getElementById('btnRecordAudio').disabled = true;
  let elapsed = 0;
  _audioTimerInterval = setInterval(() => {
    elapsed++;
    const el = document.getElementById('audioRecTimer');
    if (el) el.textContent = elapsed + 's';
  }, 1000);
}

async function stopAudioRecord() {
  if (!_audioRecording) return;
  _audioRecording = false;
  clearInterval(_audioTimerInterval);

  // Arrêter les ressources
  if (_audioProcessor) { _audioProcessor.disconnect(); _audioProcessor = null; }
  if (_audioStream) { _audioStream.getTracks().forEach(t => t.stop()); _audioStream = null; }
  if (_audioCtx) { await _audioCtx.close(); _audioCtx = null; }

  document.getElementById('audioRecordBar')?.classList.add('hidden');
  document.getElementById('btnRecordAudio').disabled = false;
  const timerEl = document.getElementById('audioRecTimer');
  if (timerEl) timerEl.textContent = '0s';

  const samples = new Float32Array(_audioSamples);
  if (samples.length < AUDIO_SR * 0.5) {
    toast('Enregistrement trop court (min 0.5s)', 'warning'); return;
  }

  await analyzeAudio(samples);
}

async function analyzeAudio(samples) {
  const resultEl = document.getElementById('chatAudioAnalysisResult');
  if (resultEl) {
    resultEl.classList.remove('hidden');
    resultEl.innerHTML = `<div class="audio-analyzing"><span class="spinner"></span> Génération du spectrogramme et analyse IA…</div>`;
  }

  // Encoder en WAV base64
  let wavB64;
  try {
    const wavBuf = encodeWav(samples, AUDIO_SR);
    // btoa sur grands buffers → utiliser chunks pour éviter stack overflow
    const bytes = new Uint8Array(wavBuf);
    let binary = '';
    for (let i = 0; i < bytes.length; i += 8192) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
    }
    wavB64 = btoa(binary);
  } catch (e) {
    if (resultEl) resultEl.innerHTML = `<div class="audio-error">❌ Erreur encodage audio : ${esc(e.message)}</div>`;
    return;
  }

  // Contexte véhicule
  const v = state.fleet.find(v => v.vin === state.selectedVin);
  const vehicleCtx = v
    ? `${v.marque || ''} ${v.modele || ''} ${v.annee || ''} (VIN: ${v.vin})`.trim()
    : (state.selectedVin ? `VIN ${state.selectedVin}` : 'véhicule non identifié');

  try {
    // Timeout 60s pour l'analyse audio (spectrogramme + Claude Vision)
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60000);

    const r = await fetch('/api/audio/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wav: wavB64, vehicle_context: vehicleCtx }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `Erreur serveur (${r.status})`);

    if (resultEl) {
      // Barre des bandes de fréquences
      let bandsHtml = '';
      if (data.bands) {
        const colors = ['#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6'];
        bandsHtml = `<div class="audio-bands">` +
          Object.entries(data.bands).map(([label, pct], i) =>
            `<div class="audio-band-row">
               <span class="audio-band-label">${label}</span>
               <div class="audio-band-bar-wrap">
                 <div class="audio-band-bar" style="width:${pct}%;background:${colors[i] || '#6366f1'}"></div>
               </div>
               <span class="audio-band-pct">${pct}%</span>
             </div>`
          ).join('') + `</div>`;
      }
      const dbInfo = data.db_rms !== undefined
        ? `<span class="audio-result-duration">RMS: ${data.db_rms} dBFS</span>` : '';

      resultEl.innerHTML = `
        <div class="audio-result-header">
          <span class="audio-result-title">🎙️ Analyse du bruit — ${escHtml(vehicleCtx)}</span>
          <span class="audio-result-duration">${data.duration}s</span>
          ${dbInfo}
        </div>
        ${bandsHtml}
        <div class="audio-analysis-text">${marked(data.analysis)}</div>
        <button type="button" class="btn btn-outline btn-sm" style="margin-top:8px"
                onclick="document.getElementById('chatAudioAnalysisResult').classList.add('hidden')">Fermer</button>`;
    }
  } catch (err) {
    const msg = err.name === 'AbortError'
      ? 'Délai dépassé (60s) — le serveur met trop de temps à répondre.'
      : err.message === 'Failed to fetch'
        ? 'Impossible de contacter le serveur.'
        : err.message;
    if (resultEl) resultEl.innerHTML = `<div class="audio-error">❌ ${esc(msg)}</div>`;
  }
}

/** marked() minimal pour rendre le markdown de l'analyse */
function marked(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/^(\d+\.\s)/gm, '<br>$1')
    .replace(/^(#{1,3} )(.*)/gm, '<strong>$2</strong>')
    .replace(/\n/g, '<br>');
}

// ════════════════════════════════════════════════════════
//  AUTHENTIFICATION LYVENIA
// ════════════════════════════════════════════════════════

function showLoginOverlay() {
  const el = document.getElementById('loginOverlay');
  if (el) el.classList.remove('hidden');
}

function hideLoginOverlay() {
  const el = document.getElementById('loginOverlay');
  if (el) el.classList.add('hidden');
}

/** Vérifie la session auprès du backend local. Retourne true si authentifié. */
async function checkAuth() {
  try {
    const status = await api('GET', '/api/auth/status');
    if (status.authenticated) {
      hideLoginOverlay();
      if (status.offline) toast('Mode hors-ligne — session locale valide', 'warn');
      return true;
    }
    showLoginOverlay();
    return false;
  } catch {
    // Serveur injoignable → on ne bloque pas (mode dev sans CLIENT_BUILD)
    hideLoginOverlay();
    return true;
  }
}

function setupAuthEvents() {
  const loginForm = document.getElementById('loginForm');
  if (!loginForm) return;

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email    = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errDiv   = document.getElementById('loginError');
    const btnText  = document.getElementById('loginBtnText');
    const btn      = document.getElementById('btnLoginSubmit');

    errDiv.classList.add('hidden');
    btnText.textContent = 'Connexion…';
    btn.disabled = true;

    try {
      const result = await api('POST', '/api/auth/login', { email, password });
      if (result.success) {
        hideLoginOverlay();
        toast('Connecté avec succès', 'success');
        startAppData();
      } else {
        errDiv.textContent = result.error || 'Identifiants incorrects';
        errDiv.classList.remove('hidden');
      }
    } catch (err) {
      errDiv.textContent = err.message || 'Erreur de connexion';
      errDiv.classList.remove('hidden');
    } finally {
      btnText.textContent = 'Se connecter';
      btn.disabled = false;
    }
  });

  document.getElementById('linkForgotPassword')?.addEventListener('click', async (e) => {
    e.preventDefault();
    const email  = document.getElementById('loginEmail').value.trim();
    const errDiv = document.getElementById('loginError');
    if (!email) {
      errDiv.textContent = 'Entrez votre adresse email d\'abord';
      errDiv.classList.remove('hidden');
      return;
    }
    try {
      await api('POST', '/api/auth/forgot', { email });
      toast('Email de réinitialisation envoyé si ce compte existe', 'info');
    } catch {
      toast('Erreur lors de l\'envoi', 'error');
    }
  });
}

/** Lance le chargement des données et les intervalles de polling. */
async function startAppData() {
  await Promise.all([refreshStatus(), loadFleet(), loadTechnicians()]);
  api('GET', '/api/config/garage').then(g => { state._garage = g; }).catch(() => {});
  renderFleetManagement();
  setInterval(refreshStatus, 10000);
}

// ── Auto-updater ──────────────────────────────────────────────────────────────

let _updateDownloadUrl = '';
let _updateSha256      = '';
let _updateVersion     = '';
let _isUpdating        = false;  // garde anti-doublon
const SNOOZE_KEY       = 'rodia_update_snoozed_until';

async function checkForUpdate() {
  const snoozedUntil = localStorage.getItem(SNOOZE_KEY);
  if (snoozedUntil && Date.now() < parseInt(snoozedUntil)) return;

  try {
    const data = await api('GET', '/api/version-info');
    if (data.update_available && data.download_url) {
      _updateDownloadUrl = data.download_url;
      _updateSha256      = data.sha256 || '';
      _updateVersion     = data.version || '';
      document.getElementById('updateVersion').textContent =
        `Mise à jour v${data.version} disponible`;
      document.getElementById('updateNotes').textContent =
        data.release_notes || '';
      document.getElementById('updateBanner').style.display = 'flex';
    }
  } catch { /* silencieux — pas de connexion ou pas de nouvelle version */ }
}

function snoozeUpdate() {
  localStorage.setItem(SNOOZE_KEY, Date.now() + 24 * 60 * 60 * 1000);
  document.getElementById('updateBanner').style.display = 'none';
}

async function applyUpdate() {
  if (!_updateDownloadUrl || _isUpdating) return;
  _isUpdating = true;

  const btn         = document.getElementById('btnUpdate');
  const countdownEl = document.getElementById('updateCountdown');
  btn.disabled      = true;
  btn.textContent   = 'Préparation…';
  if (countdownEl) countdownEl.textContent = 'Préparation de la mise à jour…';
  document.getElementById('updateProgress').style.display = 'flex';

  try {
    // 1. Backend : lance le PS1 (download + SHA-256 + kill RODIA + install /VERYSILENT
    //    + toast Windows à la fin) puis programme la fermeture de Flask dans 5s.
    await api('POST', '/api/apply-update', {
      download_url: _updateDownloadUrl,
      sha256:       _updateSha256,
      version:      _updateVersion,
    });

    // 2. Compte à rebours visible (mise à jour silencieuse en arrière-plan)
    for (let i = 5; i >= 1; i--) {
      const msg = i > 1
        ? `Fermeture dans ${i} secondes… La mise à jour s'installe en arrière-plan.`
        : `Fermeture dans 1 seconde… RODIA se relancera automatiquement.`;
      if (countdownEl) countdownEl.textContent = msg;
      btn.textContent = `Fermeture dans ${i}s…`;
      await new Promise(r => setTimeout(r, 1000));
    }

    // 3. Message final juste avant que Flask coupe la connexion
    if (countdownEl) countdownEl.textContent = "Mise à jour en cours… RODIA va se relancer dans quelques secondes.";
    btn.textContent = 'Mise à jour…';

  } catch (e) {
    _isUpdating     = false;
    btn.disabled    = false;
    btn.textContent = 'Installer maintenant';
    if (countdownEl) countdownEl.textContent = '';
    alert('Erreur : ' + e.message);
  }
}

/* ══════════════════════════════════════════════════════
   COMMAND PALETTE (recherche globale Ctrl+K)
══════════════════════════════════════════════════════ */

let _searchIndex = null;        // {vehicles, dtcs, technicians, actions}
let _searchActive = -1;         // Index du résultat sélectionné
let _searchResults = [];        // Liste plate des résultats triés
let _searchInputDebounce = null;

/* ── Normalisation pour recherche insensible accents/casse ─────── */
function searchNormalize(s) {
  return (s || '')
    .toString()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}

/* ── Construit l'index de recherche depuis les data dispo ──────── */
function buildSearchIndex(data) {
  const vehicles = (data && data.vehicles) || [];
  const recentDiags = (data && data.recent_diags) || [];

  // 1. Véhicules
  const vehs = vehicles.map(v => {
    const name = [v.marque, v.modele, v.annee].filter(Boolean).join(' ') || (v.vin || '').slice(-8);
    const plate = v.code || v.surnom || '';
    return {
      kind: 'vehicle',
      vin: v.vin,
      label: name,
      plate,
      meta: [plate, v.vin].filter(Boolean).join(' · '),
      // Champs indexés (concat normalisé)
      _haystack: searchNormalize([v.marque, v.modele, v.annee, plate, v.surnom, v.vin].filter(Boolean).join(' ')),
    };
  });

  // 2. DTCs : on parcourt l'historique de chaque véhicule (ou recent_diags si dispo)
  const dtcMap = new Map();
  for (const v of vehicles) {
    const hist = v.historique || [];
    for (const h of hist) {
      const codes = h.dtc_codes || [];
      const vehLabel = [v.marque, v.modele].filter(Boolean).join(' ') || (v.vin || '').slice(-8);
      for (const code of codes) {
        if (!code) continue;
        const key = `${code}::${v.vin}`;
        if (!dtcMap.has(key)) {
          dtcMap.set(key, {
            kind: 'dtc',
            code,
            vin: v.vin,
            vehLabel,
            date: h.date_affichage || h.date || '',
            statut: h.statut || '',
            _haystack: searchNormalize(`${code} ${vehLabel} ${h.statut || ''}`),
          });
        }
      }
    }
  }
  // Aussi depuis recent_diags si infos plus fraîches
  for (const d of recentDiags) {
    const veh = vehicles.find(x => x.vin === d.vin) || {};
    const vehLabel = [veh.marque, veh.modele].filter(Boolean).join(' ') || (d.vin || '').slice(-8);
    for (const code of (d.dtc_codes || [])) {
      const key = `${code}::${d.vin}`;
      if (!dtcMap.has(key)) {
        dtcMap.set(key, {
          kind: 'dtc',
          code,
          vin: d.vin,
          vehLabel,
          date: d.date_affichage || '',
          statut: d.statut || '',
          _haystack: searchNormalize(`${code} ${vehLabel} ${d.statut || ''}`),
        });
      }
    }
  }
  const dtcs = Array.from(dtcMap.values());

  // 3. Techniciens uniques
  const techMap = new Map();
  for (const v of vehicles) {
    for (const h of (v.historique || [])) {
      const t = (h.technicien || '').trim();
      if (!t) continue;
      techMap.set(t, (techMap.get(t) || 0) + 1);
    }
  }
  const technicians = Array.from(techMap.entries()).map(([name, count]) => ({
    kind: 'technician',
    name,
    count,
    _haystack: searchNormalize(name),
  }));

  // 4. Actions rapides (toujours dispo)
  const actions = [
    { kind: 'action', label: 'Aller au tableau de bord', desc: 'Vue d\'ensemble de la flotte', run: () => switchTab('dashboard'), icon: 'dashboard' },
    { kind: 'action', label: 'Lancer un diagnostic', desc: 'Démarrer une lecture OBD2', run: () => switchTab('diagnostic'), icon: 'play' },
    { kind: 'action', label: 'Voir tous les véhicules', desc: 'Liste complète de la flotte', run: () => switchTab('historique'), icon: 'truck' },
    { kind: 'action', label: 'Ouvrir les paramètres', desc: 'Configuration du logiciel', run: () => switchTab('parametres'), icon: 'settings' },
    { kind: 'action', label: 'Basculer mode jour / nuit', desc: 'Changer l\'apparence', run: () => { toggleTheme(); refreshUserDisplay && refreshUserDisplay(); }, icon: 'theme' },
    { kind: 'action', label: 'Modifier mon nom', desc: 'Personnaliser le profil', run: () => {
        const input = document.getElementById('inputUserName');
        if (input) input.value = getUserName();
        openModal('modalEditName');
        setTimeout(() => input && input.focus(), 50);
      }, icon: 'edit' },
    { kind: 'action', label: 'Raccourcis clavier', desc: 'Voir tous les raccourcis', run: () => openModal('modalShortcuts'), icon: 'keyboard' },
    { kind: 'action', label: 'Tour guidé de l\'app', desc: 'Démarrer la visite guidée', run: () => startGuidedTour(), icon: 'play' },
    { kind: 'action', label: 'Signaler un problème', desc: 'Contacter le support', run: () => openBugReportModal(), icon: 'bug' },
  ];
  for (const a of actions) {
    a._haystack = searchNormalize(a.label + ' ' + a.desc);
  }

  return { vehicles: vehs, dtcs, technicians, actions };
}

function refreshSearchIndex() {
  // Préfère l'index complet via /api/fleet, sinon fallback sur _dashData
  fetch('/api/fleet').then(r => r.ok ? r.json() : null).then(vehList => {
    const data = {
      vehicles: vehList || (_dashData && _dashData.vehicles) || [],
      recent_diags: (_dashData && _dashData.recent_diags) || [],
    };
    _searchIndex = buildSearchIndex(data);
  }).catch(() => {
    _searchIndex = buildSearchIndex(_dashData || {});
  });
}

/* ── Recherche : retourne les top résultats par catégorie ──────── */
function performSearch(query) {
  if (!_searchIndex) refreshSearchIndex();
  const q = searchNormalize(query);
  if (!q) {
    // Sans query : montre uniquement les actions par défaut
    return [
      { group: 'Actions rapides', items: (_searchIndex ? _searchIndex.actions : []).slice(0, 6) },
    ];
  }

  const idx = _searchIndex || { vehicles: [], dtcs: [], technicians: [], actions: [] };

  // Score : 100 si match au début, 60 si match au milieu d'un mot, 30 sinon
  const score = (haystack) => {
    if (!haystack.includes(q)) return 0;
    if (haystack.startsWith(q)) return 100;
    // Match au début d'un mot
    const re = new RegExp('(^|[^a-z0-9])' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    if (re.test(haystack)) return 60;
    return 30;
  };

  const filterAndSort = (arr) => arr
    .map(x => ({ x, s: score(x._haystack) }))
    .filter(o => o.s > 0)
    .sort((a, b) => b.s - a.s)
    .map(o => o.x);

  const groups = [
    { group: 'Véhicules',    items: filterAndSort(idx.vehicles).slice(0, 5)    },
    { group: 'Codes DTC',    items: filterAndSort(idx.dtcs).slice(0, 5)        },
    { group: 'Techniciens',  items: filterAndSort(idx.technicians).slice(0, 4) },
    { group: 'Actions',      items: filterAndSort(idx.actions).slice(0, 4)     },
  ];
  return groups.filter(g => g.items.length > 0);
}

/* ── Rendu de la liste de résultats ────────────────────────────── */
function renderSearchResults(query, groups) {
  const wrap = document.getElementById('searchPaletteResults');
  if (!wrap) return;
  _searchResults = [];

  if (!groups.length) {
    wrap.innerHTML = `<div class="search-palette-empty">Aucun résultat pour <strong>« ${escHtml(query)} »</strong></div>`;
    _searchActive = -1;
    return;
  }

  const ICON_VEH  = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>';
  const ICON_DTC  = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';
  const ICON_TECH = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
  const ICON_ACT  = {
    dashboard: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>',
    play:      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>',
    truck:     '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>',
    settings:  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    theme:     '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/></svg>',
    edit:      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
    keyboard:  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="5" rx="2"/><path d="M6 9h.01"/><path d="M10 9h.01"/><path d="M14 9h.01"/><path d="M18 9h.01"/><path d="M10 13h4"/></svg>',
    bug:       '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  };

  // Helper : highlight des matches dans le label
  const highlight = (text, q) => {
    if (!q) return escHtml(text);
    const safe = escHtml(text);
    const norm = searchNormalize(text);
    const idx = norm.indexOf(q);
    if (idx === -1) return safe;
    // On surligne dans la version originale en se basant sur les indices normalisés
    return safe.slice(0, idx) + '<mark>' + safe.slice(idx, idx + q.length) + '</mark>' + safe.slice(idx + q.length);
  };

  let html = '';
  let flatIdx = 0;
  for (const g of groups) {
    html += `<div class="search-group-title">${escHtml(g.group)}</div>`;
    for (const item of g.items) {
      const myIdx = flatIdx++;
      _searchResults.push(item);
      let icon = '', title = '', meta = '';
      if (item.kind === 'vehicle') {
        icon  = ICON_VEH;
        title = highlight(item.label, query);
        meta  = item.meta;
      } else if (item.kind === 'dtc') {
        icon  = ICON_DTC;
        title = highlight(item.code, query) + ' <span style="color:var(--text-muted);font-weight:500"> · ' + escHtml(item.vehLabel) + '</span>';
        meta  = [item.statut, item.date].filter(Boolean).join(' · ');
      } else if (item.kind === 'technician') {
        icon  = ICON_TECH;
        title = highlight(item.name, query);
        meta  = `${item.count} diagnostic${item.count > 1 ? 's' : ''}`;
      } else if (item.kind === 'action') {
        icon  = ICON_ACT[item.icon] || ICON_ACT.settings;
        title = highlight(item.label, query);
        meta  = item.desc;
      }
      html += `<div class="search-result" data-idx="${myIdx}" role="option">
        <div class="search-result-icon">${icon}</div>
        <div class="search-result-body">
          <div class="search-result-title">${title}</div>
          <div class="search-result-meta">${escHtml(meta)}</div>
        </div>
      </div>`;
    }
  }
  wrap.innerHTML = html;

  // Sélectionne le premier résultat
  _searchActive = 0;
  highlightSearchActive();

  // Click handlers
  wrap.querySelectorAll('.search-result').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx, 10);
      activateSearchResult(idx);
    });
    el.addEventListener('mouseenter', () => {
      _searchActive = parseInt(el.dataset.idx, 10);
      highlightSearchActive(false);
    });
  });
}

function highlightSearchActive(autoScroll = true) {
  const wrap = document.getElementById('searchPaletteResults');
  if (!wrap) return;
  wrap.querySelectorAll('.search-result').forEach(el => {
    const idx = parseInt(el.dataset.idx, 10);
    el.classList.toggle('active', idx === _searchActive);
    if (idx === _searchActive && autoScroll) {
      el.scrollIntoView({ block: 'nearest' });
    }
  });
}

function activateSearchResult(idx) {
  const item = _searchResults[idx];
  if (!item) return;
  closeSearchPalette();
  switch (item.kind) {
    case 'vehicle':
      switchTab('historique');
      // Tente d'ouvrir la fiche véhicule via une fonction existante si elle existe
      if (typeof loadVehicleDetail === 'function')      loadVehicleDetail(item.vin);
      else if (typeof openVehicle === 'function')        openVehicle(item.vin);
      else if (typeof showVehicleDetail === 'function')  showVehicleDetail(item.vin);
      break;
    case 'dtc':
      switchTab('historique');
      if (typeof loadVehicleDetail === 'function')       loadVehicleDetail(item.vin);
      else if (typeof openVehicle === 'function')        openVehicle(item.vin);
      if (typeof toast === 'function') toast(`Code ${item.code} — ${item.vehLabel}`, 'info');
      break;
    case 'technician':
      switchTab('historique');
      if (typeof toast === 'function') toast(`${item.count} diagnostic(s) par ${item.name}`, 'info');
      break;
    case 'action':
      try { item.run(); } catch (e) { console.error(e); }
      break;
  }
}

/* ── Open / close palette ──────────────────────────────────────── */

function openSearchPalette() {
  const palette = document.getElementById('searchPalette');
  const input   = document.getElementById('searchPaletteInput');
  if (!palette || !input) return;
  refreshSearchIndex();
  palette.classList.remove('hidden');
  input.value = '';
  setTimeout(() => input.focus(), 30);
  // Affiche par défaut les actions
  renderSearchResults('', performSearch(''));
}

function closeSearchPalette() {
  const palette = document.getElementById('searchPalette');
  if (palette) palette.classList.add('hidden');
}

function setupSearchPalette() {
  const trigger = document.getElementById('globalSearchTrigger');
  const palette = document.getElementById('searchPalette');
  const input   = document.getElementById('searchPaletteInput');

  if (trigger) trigger.addEventListener('click', openSearchPalette);

  // Hotkey Ctrl+K / Cmd+K
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      if (palette && palette.classList.contains('hidden')) openSearchPalette();
      else closeSearchPalette();
    }
  });

  if (palette) {
    // Click outside (sur l'overlay) → close
    palette.addEventListener('click', (e) => {
      if (e.target === palette) closeSearchPalette();
    });
  }

  if (input) {
    input.addEventListener('input', () => {
      if (_searchInputDebounce) clearTimeout(_searchInputDebounce);
      const q = input.value;
      _searchInputDebounce = setTimeout(() => {
        renderSearchResults(q, performSearch(q));
      }, 60);
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeSearchPalette();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (_searchActive < _searchResults.length - 1) _searchActive++;
        else _searchActive = 0;
        highlightSearchActive();
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (_searchActive > 0) _searchActive--;
        else _searchActive = _searchResults.length - 1;
        highlightSearchActive();
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (_searchActive >= 0) activateSearchResult(_searchActive);
        return;
      }
    });
  }
}

/* ══════════════════════════════════════════════════════
   ANAMNÈSE — Accordéon progressif (révélation en cascade)
══════════════════════════════════════════════════════ */

let _anaExpandAll = false;  // Mode "tout déplier" (un seul état pour la session)

/**
 * Initialise le flow d'anamnèse :
 *  - 1ère section ouverte, autres masquées
 *  - À chaque réponse complète : marque la section .done, ferme, ouvre la suivante
 *  - Branche conditionnelle via data-ana-skip-if
 *  - Bouton "Tout déplier" pour les utilisateurs experts
 */
function setupAnamneseFlow() {
  // Initialise les 2 accordéons (panne + bilan). Comme un seul est visible
  // à la fois (#wizardStepAnamnese ou #wizardStepBilan), c'est sans risque.
  ['anamneseAccordion', 'bilanAccordion'].forEach(initAccordion);
}

function initAccordion(accordionId) {
  const accordion = document.getElementById(accordionId);
  if (!accordion) return;
  // Évite de re-binder les listeners en cas d'appel répété
  if (accordion.dataset.flowReady === '1') {
    // Reset état uniquement
    const items = Array.from(accordion.querySelectorAll('.ana-acc-item'));
    items.forEach((it, idx) => {
      it.classList.toggle('open',        idx === 0);
      it.classList.toggle('hidden-step', idx !== 0);
      it.classList.remove('done');
      const sumEl = it.querySelector('.ana-acc-summary');
      if (sumEl) sumEl.textContent = '';
    });
    updateAnamneseProgress();
    return;
  }

  const items = Array.from(accordion.querySelectorAll('.ana-acc-item'));
  if (!items.length) return;

  // État initial : seule la 1ère est révélée et ouverte
  items.forEach((it, idx) => {
    if (idx === 0) {
      it.classList.add('open');
      it.classList.remove('hidden-step', 'done');
    } else {
      it.classList.add('hidden-step');
      it.classList.remove('open', 'done');
    }
  });
  updateAnamneseProgress();

  // Délégation : changement de tout input dans l'accordéon → re-évalue l'item
  accordion.addEventListener('input',  onAnaInputChange);
  accordion.addEventListener('change', onAnaInputChange);

  // Click sur le trigger d'un item → ouvre/ferme (sauf si caché)
  accordion.addEventListener('click', (e) => {
    const trigger = e.target.closest('.ana-acc-trigger');
    if (!trigger) return;
    const item = trigger.closest('.ana-acc-item');
    if (!item || item.classList.contains('hidden-step')) return;
    // Section déjà ouverte ET pas en mode expand-all : on ne ferme pas avec click
    if (item.classList.contains('open') && !_anaExpandAll) return;
    items.forEach(i => i.classList.remove('open'));
    item.classList.add('open');
  });

  // Bouton "Tout déplier" / "Replier" — propre à chaque accordéon
  // (anaExpandAll pour panne, bilanExpandAll pour bilan)
  const btnId = (accordionId === 'bilanAccordion') ? 'bilanExpandAll' : 'anaExpandAll';
  const btn = document.getElementById(btnId);
  if (btn) {
    btn.addEventListener('click', () => {
      _anaExpandAll = !_anaExpandAll;
      if (_anaExpandAll) {
        items.forEach(it => {
          if (!shouldSkipItem(it)) {
            it.classList.remove('hidden-step');
            it.classList.add('open');
          }
        });
        btn.textContent = 'Replier';
      } else {
        const firstUndone = items.find(i =>
          !i.classList.contains('done') &&
          !i.classList.contains('hidden-step') &&
          !shouldSkipItem(i)
        );
        items.forEach((it, idx) => {
          it.classList.remove('open');
          if (idx > 0 && !it.classList.contains('done') && it !== firstUndone) {
            it.classList.add('hidden-step');
          }
        });
        if (firstUndone) firstUndone.classList.add('open');
        btn.textContent = 'Tout déplier';
      }
    });
  }
  accordion.dataset.flowReady = '1';
}

function onAnaInputChange(e) {
  const item = e.target.closest('.ana-acc-item');
  if (!item) return;

  const wasDone = item.classList.contains('done');
  const fields  = (item.dataset.anaFields || '').split(',').map(s => s.trim()).filter(Boolean);
  const filled  = fields.length > 0 && fields.some(name => isAnaFieldFilled(name));

  // Met à jour le résumé compact en permanence
  item.querySelector('.ana-acc-summary').textContent = computeAnaSummary(item);

  if (filled) {
    item.classList.add('done');
    // Si on n'était pas déjà "done", on enchaîne vers la section suivante
    if (!wasDone && !_anaExpandAll) {
      advanceToNextSection(item);
    }
  } else {
    item.classList.remove('done');
  }
  updateAnamneseProgress();
}

function isAnaFieldFilled(name) {
  // Cherche n'importe quel input/select/textarea avec ce name
  const els = document.querySelectorAll(
    `[name="${name}"], #${name}`
  );
  for (const el of els) {
    const tag = (el.tagName || '').toLowerCase();
    const type = (el.type || '').toLowerCase();
    if (type === 'radio' || type === 'checkbox') {
      if (el.checked) return true;
    } else if (tag === 'select' || tag === 'input' || tag === 'textarea') {
      if (el.value && el.value.trim()) return true;
    }
  }
  return false;
}

function advanceToNextSection(currentItem) {
  // Ferme la section courante après un court délai (le temps de voir le check)
  setTimeout(() => {
    // On utilise l'accordéon parent du currentItem (panne ou bilan)
    const accordion = currentItem.closest('.anamnese-accordion');
    if (!accordion) return;
    const items = Array.from(accordion.querySelectorAll('.ana-acc-item'));
    currentItem.classList.remove('open');
    // Cherche la prochaine non-done, non-skipped, non-hidden-step
    let next = null;
    let foundCurrent = false;
    for (const it of items) {
      if (!foundCurrent) {
        if (it === currentItem) foundCurrent = true;
        continue;
      }
      if (shouldSkipItem(it)) {
        // On marque comme done (skipped) pour qu'elle compte dans la progression
        it.classList.add('done');
        it.classList.add('hidden-step');
        const sumEl = it.querySelector('.ana-acc-summary');
        if (sumEl) sumEl.textContent = '— Non applicable';
        continue;
      }
      next = it;
      break;
    }
    if (next) {
      next.classList.remove('hidden-step');
      next.classList.add('open');
      // Scroll smooth dans la card si nécessaire
      setTimeout(() => {
        next.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 50);
    }
    updateAnamneseProgress();
  }, 280);
}

function shouldSkipItem(item) {
  const cond = item.dataset.anaSkipIf;
  if (!cond) return false;
  let parsed;
  try { parsed = JSON.parse(cond); } catch { return false; }
  // Toutes les paires clé:valeur doivent matcher pour skipper
  for (const [name, expected] of Object.entries(parsed)) {
    const els = document.querySelectorAll(`[name="${name}"]:checked, #${name}`);
    let actual = '';
    for (const el of els) {
      if (el.type === 'radio' || el.type === 'checkbox') {
        actual = el.value;
      } else {
        actual = el.value;
      }
      if (actual) break;
    }
    if (actual !== expected) return false;
  }
  return true;
}

function computeAnaSummary(item) {
  const id = item.dataset.anaId;
  switch (id) {
    case 'triage': {
      const v = (document.querySelector('[name="ana_demarre"]:checked') || {}).value;
      if (v === 'oui') return 'Oui, il démarre';
      if (v === 'non') return 'Non, ne démarre pas';
      return '';
    }
    case 'chronologie': {
      const dep = document.getElementById('ana_depuis');
      const itv = document.getElementById('ana_apres_intervention');
      const parts = [];
      if (dep && dep.value) parts.push(dep.options[dep.selectedIndex].text);
      if (itv && itv.value && itv.value.trim()) parts.push('intervention récente');
      return parts.join(' · ');
    }
    case 'frequence': {
      const v = (document.querySelector('[name="ana_freq"]:checked') || {}).value;
      return v || '';
    }
    case 'moment': {
      const checked = Array.from(document.querySelectorAll('[name="ana_moment"]:checked'));
      if (!checked.length) return '';
      if (checked.length <= 2) return checked.map(c => c.value).join(', ');
      return `${checked.length} moments`;
    }
    case 'symptomes': {
      const checked = Array.from(document.querySelectorAll('[name="ana_symptome"]:checked'));
      if (!checked.length) return '';
      return `${checked.length} symptôme${checked.length > 1 ? 's' : ''}`;
    }
    case 'acoustique': {
      const txt = (document.getElementById('ana_sons') || {}).value || '';
      if (!txt.trim()) return '';
      return txt.length > 40 ? txt.slice(0, 38) + '…' : txt;
    }
    case 'interventions': {
      const txt = (document.getElementById('ana_interventions') || {}).value || '';
      if (!txt.trim()) return '';
      return txt.length > 40 ? txt.slice(0, 38) + '…' : txt;
    }
    case 'autres': {
      const txt = (document.getElementById('ana_infos') || {}).value || '';
      if (!txt.trim()) return '';
      return txt.length > 40 ? txt.slice(0, 38) + '…' : txt;
    }
    /* ── Bilan de santé ── */
    case 'bilan_type': {
      const v = (document.querySelector('[name="bilan_type"]:checked') || {}).value;
      return BILAN_TYPE_LABELS[v] || '';
    }
    case 'bilan_observations': {
      const checked = Array.from(document.querySelectorAll('[name="bilan_observation"]:checked'));
      if (!checked.length) return '';
      return `${checked.length} point${checked.length > 1 ? 's' : ''} OK`;
    }
    case 'bilan_notes': {
      const txt = (document.getElementById('bilan_notes') || {}).value || '';
      if (!txt.trim()) return '';
      return txt.length > 40 ? txt.slice(0, 38) + '…' : txt;
    }
    case 'bilan_interventions': {
      const txt = (document.getElementById('bilan_interventions') || {}).value || '';
      if (!txt.trim()) return '';
      return txt.length > 40 ? txt.slice(0, 38) + '…' : txt;
    }
  }
  return '';
}

/**
 * Met à jour les barres de progression des deux accordéons (panne + bilan).
 * Une seule est visible à la fois mais les deux states sont maintenus.
 */
function updateAnamneseProgress() {
  _updateOneProgress('anamneseAccordion', 'anaProgressCurrent', 'anaProgressTotal', 'anaProgressFill');
  _updateOneProgress('bilanAccordion',    'bilanProgressCurrent', 'bilanProgressTotal', 'bilanProgressFill');
}

function _updateOneProgress(accordionId, curId, totId, fillId) {
  const accordion = document.getElementById(accordionId);
  if (!accordion) return;
  const items = Array.from(accordion.querySelectorAll('.ana-acc-item'));
  const eligible = items.filter(it => !shouldSkipItem(it));
  const done = eligible.filter(it => it.classList.contains('done')).length;
  const total = eligible.length;
  const cur = Math.min(done + 1, total);

  const curEl = document.getElementById(curId);
  const totEl = document.getElementById(totId);
  const fillEl = document.getElementById(fillId);
  if (curEl) curEl.textContent = cur;
  if (totEl) totEl.textContent = total;
  if (fillEl) {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    fillEl.style.width = pct + '%';
  }
}

/* ══════════════════════════════════════════════════════
   USER MENU & HELP MENU & MODALES SUPPORT
══════════════════════════════════════════════════════ */

/* ── Préférences UI persistées côté serveur (~/.RODIA/ui_prefs.json) ─────────
 * Le localStorage Edge n'est PAS fiable entre sessions sous --user-data-dir
 * (lock/profil temporaire selon contexte). On utilise /api/prefs comme
 * source de vérité ; localStorage sert juste de cache synchrone en session. */

async function loadPrefs() {
  try {
    const r = await fetch('/api/prefs');
    if (!r.ok) return;
    const prefs = await r.json();
    for (const [k, v] of Object.entries(prefs || {})) {
      if (v == null) { try { localStorage.removeItem(k); } catch {} ; continue; }
      try {
        localStorage.setItem(k, typeof v === 'string' ? v : JSON.stringify(v));
      } catch {}
    }
  } catch {}
}

function savePref(key, value) {
  // 1) Cache local synchrone pour cohérence dans la session courante
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key,
      typeof value === 'string' ? value : JSON.stringify(value));
  } catch {}
  // 2) Persistance serveur (async, best-effort, fire-and-forget)
  fetch('/api/prefs', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ [key]: value }),
  }).catch(() => {});
}

const USER_NAME_KEY = 'rodiaUserName';

function getUserName() {
  return (localStorage.getItem(USER_NAME_KEY) || '').trim();
}
function setUserName(name) {
  const v = (name || '').trim();
  savePref(USER_NAME_KEY, v || null);
  refreshUserDisplay();
  // Re-render le hero du dashboard si chargé
  if (_dashData) renderDashboardHero(_dashData);
}

function computeInitials(name) {
  const clean = (name || '').trim();
  if (!clean) return '--';
  const parts = clean.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function refreshUserDisplay() {
  const name     = getUserName();
  const initials = computeInitials(name);
  const display  = name || 'Utilisateur';

  const avatar      = document.getElementById('userAvatar');
  const userNameEl  = document.getElementById('userName');
  const menuAvatar  = document.getElementById('userMenuAvatar');
  const menuName    = document.getElementById('userMenuName');
  const menuSub     = document.getElementById('userMenuSub');
  const themeMeta   = document.getElementById('menuThemeMeta');

  if (avatar)     avatar.textContent     = initials;
  if (userNameEl) userNameEl.textContent = display;
  if (menuAvatar) menuAvatar.textContent = initials;
  if (menuName)   menuName.textContent   = display;
  if (menuSub)    menuSub.textContent    = name ? 'Profil local' : 'Aucun nom défini';

  // Apparence : reflète le thème actif
  if (themeMeta) {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    themeMeta.textContent = dark ? 'Sombre' : 'Clair';
  }
}

/* ── Dropdown menu : composant générique ──────────────────────── */

const _openDropdowns = new Set();

function setupDropdown(triggerId, menuId) {
  const trigger = document.getElementById(triggerId);
  const menu    = document.getElementById(menuId);
  if (!trigger || !menu) return;

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    if (menu.classList.contains('open')) {
      closeDropdown(menu);
    } else {
      // Fermer les autres dropdowns ouverts
      _openDropdowns.forEach(m => { if (m !== menu) closeDropdown(m); });
      menu.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      _openDropdowns.add(menu);
    }
  });

  // Click outside → close
  document.addEventListener('click', (e) => {
    if (!menu.classList.contains('open')) return;
    if (menu.contains(e.target) || trigger.contains(e.target)) return;
    closeDropdown(menu, trigger);
  });

  // Échap → close
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menu.classList.contains('open')) {
      closeDropdown(menu, trigger);
    }
  });
}

function closeDropdown(menu, trigger = null) {
  menu.classList.remove('open');
  _openDropdowns.delete(menu);
  if (trigger) trigger.setAttribute('aria-expanded', 'false');
  else {
    // Cherche le trigger associé (tous ceux avec aria-controls ou parent menu-host)
    const host = menu.closest('.menu-host');
    if (host) {
      const t = host.querySelector('[aria-haspopup]');
      if (t) t.setAttribute('aria-expanded', 'false');
    }
  }
}

function closeAllDropdowns() {
  _openDropdowns.forEach(m => closeDropdown(m));
}

/* ── Modale : composant générique open/close ─────────────────── */

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('hidden');
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('hidden');
}

/* ── Setup user menu ──────────────────────────────────────────── */

function setupUserMenu() {
  setupDropdown('userChip', 'userMenu');

  const editBtn = document.getElementById('menuEditName');
  if (editBtn) editBtn.addEventListener('click', () => {
    closeAllDropdowns();
    const input = document.getElementById('inputUserName');
    if (input) input.value = getUserName();
    openModal('modalEditName');
    setTimeout(() => input && input.focus(), 50);
  });

  const themeBtn = document.getElementById('menuToggleTheme');
  if (themeBtn) themeBtn.addEventListener('click', () => {
    toggleTheme();
    refreshUserDisplay();
    closeAllDropdowns();
  });

  const resetBtn = document.getElementById('menuResetProfile');
  if (resetBtn) resetBtn.addEventListener('click', () => {
    closeAllDropdowns();
    if (!confirm('Réinitialiser votre profil ? Le nom et les préférences UI seront effacés. La flotte est conservée.')) return;
    savePref(USER_NAME_KEY, null);
    savePref('diagTheme', null);
    refreshUserDisplay();
    if (_dashData) renderDashboardHero(_dashData);
    if (typeof toast === 'function') toast('Profil réinitialisé', 'success');
  });

  // Modale Edit Name
  const saveBtn   = document.getElementById('btnSaveUserName');
  const cancelBtn = document.getElementById('btnCancelUserName');
  const input     = document.getElementById('inputUserName');
  if (saveBtn) saveBtn.addEventListener('click', () => {
    setUserName(input ? input.value : '');
    closeModal('modalEditName');
  });
  if (cancelBtn) cancelBtn.addEventListener('click', () => closeModal('modalEditName'));
  if (input) input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { saveBtn && saveBtn.click(); }
    if (e.key === 'Escape') { closeModal('modalEditName'); }
  });
}

/* Note : la maximisation est gérée côté Python via ctypes ShowWindow
 * (cf. main.py::_maximize_rodia_window_async). Plus besoin de bouton ni de JS. */

/* ── Setup help menu ──────────────────────────────────────────── */

function setupHelpMenu() {
  setupDropdown('btnHelp', 'helpMenu');

  // Affiche la version dans le footer du menu
  fetch('/api/support/diagnostic')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data || !data.summary) return;
      const lbl = document.getElementById('helpVersionLabel');
      if (lbl) lbl.textContent = `RODIA v${data.summary.version} (${data.summary.build})`;
    })
    .catch(() => {});

  const shortcutsBtn = document.getElementById('menuShortcuts');
  if (shortcutsBtn) shortcutsBtn.addEventListener('click', () => {
    closeAllDropdowns();
    openModal('modalShortcuts');
  });
  const closeShortcutsBtn = document.getElementById('btnCloseShortcuts');
  if (closeShortcutsBtn) closeShortcutsBtn.addEventListener('click', () => closeModal('modalShortcuts'));

  const tourBtn = document.getElementById('menuTour');
  if (tourBtn) tourBtn.addEventListener('click', () => {
    closeAllDropdowns();
    startGuidedTour();
  });

  const supportBtn = document.getElementById('menuSupport');
  if (supportBtn) supportBtn.addEventListener('click', () => {
    closeAllDropdowns();
    const subject = encodeURIComponent('RODIA — Question support');
    const body = encodeURIComponent(`Bonjour,\n\n[Décrivez votre demande ici]\n\n--\nUtilisateur : ${getUserName() || '—'}`);
    window.location.href = `mailto:support@lyvenia.fr?subject=${subject}&body=${body}`;
  });

  const bugBtn = document.getElementById('menuReportBug');
  if (bugBtn) bugBtn.addEventListener('click', () => {
    closeAllDropdowns();
    openBugReportModal();
  });
}

/* ── Modale signaler un problème ──────────────────────────────── */

let _bugReport = null; // { report, summary } chargé depuis /api/support/diagnostic

async function openBugReportModal() {
  openModal('modalReportBug');
  const desc = document.getElementById('bugDescription');
  if (desc) { desc.value = ''; setTimeout(() => desc.focus(), 50); }

  const preview = document.getElementById('bugSystemPreview');
  if (preview) preview.textContent = 'Chargement…';

  try {
    const r = await fetch('/api/support/diagnostic');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    _bugReport = await r.json();
    if (preview && _bugReport && _bugReport.summary) {
      const s = _bugReport.summary;
      preview.textContent = `RODIA v${s.version} (${s.build})  ·  ${s.os}  ·  ${s.timestamp}`;
    }
  } catch (e) {
    if (preview) preview.textContent = 'Infos système indisponibles.';
    _bugReport = { report: '', summary: {} };
  }
}

function buildBugMailContent() {
  const desc = (document.getElementById('bugDescription') || {}).value || '';
  const include = (document.getElementById('bugIncludeSystem') || {}).checked;
  const sys = (include && _bugReport && _bugReport.report) ? _bugReport.report : '';
  const lines = [
    'Bonjour,',
    '',
    desc.trim() || '[Décrivez ici ce qui s\'est passé]',
    '',
  ];
  if (sys) {
    lines.push('');
    lines.push(sys);
  }
  return lines.join('\n');
}

function closeBugReportSetup() {
  const sendBtn   = document.getElementById('btnSendBugReport');
  const copyBtn   = document.getElementById('btnCopyBugReport');
  const cancelBtn = document.getElementById('btnCancelBugReport');

  if (sendBtn) sendBtn.addEventListener('click', () => {
    const subject = encodeURIComponent('RODIA — Signalement de problème');
    const body    = encodeURIComponent(buildBugMailContent());
    window.location.href = `mailto:support@lyvenia.fr?subject=${subject}&body=${body}`;
    closeModal('modalReportBug');
  });
  if (copyBtn) copyBtn.addEventListener('click', async () => {
    const content = buildBugMailContent();
    try {
      await navigator.clipboard.writeText(content);
      if (typeof toast === 'function') toast('Rapport copié dans le presse-papier', 'success');
    } catch {
      if (typeof toast === 'function') toast('Impossible de copier — sélectionnez puis Ctrl+C', 'warning');
    }
  });
  if (cancelBtn) cancelBtn.addEventListener('click', () => closeModal('modalReportBug'));
}

/* ── Tour guidé interactif ────────────────────────────────────── */

const TOUR_STEPS = [
  {
    tab: 'diagnostic',
    selector: '.diag-choice-grid',
    title: 'Démarrer un diagnostic',
    text: 'Le cœur de RODIA. Branchez l\'adaptateur OBD2 sur le véhicule, puis choisissez « Diagnostic de panne » si un voyant est allumé, ou « Bilan de santé » pour un contrôle complet.',
    placement: 'bottom',
  },
  {
    tab: 'diagnostic',
    selector: '.sidebar-nav',
    title: 'Naviguer dans RODIA',
    text: 'Tableau de bord pour la vue d\'ensemble de la flotte, Diagnostic pour une lecture OBD2, Véhicules pour l\'historique, Paramètres pour la configuration.',
    placement: 'right',
  },
  {
    tab: 'diagnostic',
    selector: '#globalSearchTrigger',
    title: 'Recherche instantanée',
    text: 'Retrouvez un véhicule, un code défaut ou un technicien en quelques touches. Raccourci clavier : Ctrl + K.',
    placement: 'bottom',
  },
  {
    tab: 'dashboard',
    selector: '#kpiGrid',
    title: 'Vos indicateurs clés',
    text: 'Flotte active, diagnostics du mois, alertes urgentes et score de fiabilité moyen — l\'état de votre parc en un coup d\'œil.',
    placement: 'bottom',
  },
  {
    tab: 'dashboard',
    selector: '#dashHealthCard',
    title: 'Santé de la flotte',
    text: 'Vos véhicules classés par niveau de criticité. Cliquez sur un véhicule pour ouvrir son détail et son historique.',
    placement: 'top',
  },
  {
    tab: 'dashboard',
    selector: '#dashActivityCard',
    title: 'Activité récente',
    text: 'Le journal des événements de votre flotte : diagnostics terminés, alertes déclenchées, maintenances à prévoir.',
    placement: 'left',
  },
  {
    tab: 'dashboard',
    selector: '#btnHelp',
    title: 'Aide & support',
    text: 'Besoin d\'un coup de main ? Le support WhatsApp et la relance de cette visite guidée se trouvent dans ce menu.',
    placement: 'bottom',
  },
  {
    tab: 'dashboard',
    selector: '#btnThemeToggle',
    title: 'Mode jour / nuit',
    text: 'Basculez l\'interface en mode sombre selon vos préférences ou la luminosité de l\'atelier. Votre choix est mémorisé.',
    placement: 'bottom',
  },
];

let _tourIndex = 0;

function startGuidedTour() {
  // Chaque étape bascule sur son propre onglet (cf. showTourStep)
  _tourIndex = 0;
  ensureTourElements();
  const overlay   = document.getElementById('tourOverlay');
  const spotlight = document.getElementById('tourSpotlight');
  const pop       = document.getElementById('tourPopover');
  overlay.classList.remove('hidden');
  spotlight.classList.remove('hidden');
  pop.classList.remove('hidden');
  setTimeout(() => {
    overlay.classList.add('visible');
    pop.classList.add('visible');
    showTourStep(_tourIndex);
  }, 30);
}

function ensureTourElements() {
  if (document.getElementById('tourOverlay')) return;
  const overlay = document.createElement('div');
  overlay.id = 'tourOverlay';
  overlay.className = 'tour-overlay hidden';
  document.body.appendChild(overlay);

  const spotlight = document.createElement('div');
  spotlight.id = 'tourSpotlight';
  spotlight.className = 'tour-spotlight hidden';
  document.body.appendChild(spotlight);

  const pop = document.createElement('div');
  pop.id = 'tourPopover';
  pop.className = 'tour-popover hidden';
  pop.innerHTML = `
    <div class="tour-popover-step" id="tourStepLabel">Étape 1</div>
    <div class="tour-popover-title" id="tourTitle">—</div>
    <div class="tour-popover-text" id="tourText">—</div>
    <div class="tour-popover-actions">
      <button type="button" class="tour-popover-skip" id="tourSkip">Passer</button>
      <div class="tour-popover-nav">
        <span class="tour-popover-progress" id="tourProgress">1/6</span>
        <button type="button" class="tour-popover-btn" id="tourPrev">Précédent</button>
        <button type="button" class="tour-popover-btn primary" id="tourNext">Suivant</button>
      </div>
    </div>
  `;
  document.body.appendChild(pop);

  document.getElementById('tourSkip').addEventListener('click', endGuidedTour);
  document.getElementById('tourPrev').addEventListener('click', () => {
    if (_tourIndex > 0) { _tourIndex--; showTourStep(_tourIndex); }
  });
  document.getElementById('tourNext').addEventListener('click', () => {
    if (_tourIndex < TOUR_STEPS.length - 1) { _tourIndex++; showTourStep(_tourIndex); }
    else endGuidedTour();
  });
  // Échap = fermer
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !document.getElementById('tourOverlay').classList.contains('hidden')) {
      endGuidedTour();
    }
  });
}

function showTourStep(idx) {
  const step = TOUR_STEPS[idx];
  if (!step) return;
  // Bascule sur l'onglet ciblé par l'étape, puis attend le relayout
  // avant de mesurer la cible (sinon getBoundingClientRect = 0).
  const activeBtn = document.querySelector('.tab-btn.active');
  const curTab = activeBtn ? activeBtn.dataset.tab : null;
  if (step.tab && step.tab !== curTab && typeof switchTab === 'function') {
    switchTab(step.tab);
    setTimeout(() => _renderTourStep(idx), 150);
  } else {
    _renderTourStep(idx);
  }
}

function _renderTourStep(idx) {
  const step = TOUR_STEPS[idx];
  if (!step) return;
  const target = document.querySelector(step.selector);
  const spotlight = document.getElementById('tourSpotlight');
  const pop = document.getElementById('tourPopover');
  const stepLabel = document.getElementById('tourStepLabel');
  const titleEl = document.getElementById('tourTitle');
  const textEl  = document.getElementById('tourText');
  const progEl  = document.getElementById('tourProgress');
  const prevBtn = document.getElementById('tourPrev');
  const nextBtn = document.getElementById('tourNext');

  stepLabel.textContent = `Étape ${idx + 1}`;
  titleEl.textContent   = step.title;
  textEl.textContent    = step.text;
  progEl.textContent    = `${idx + 1} / ${TOUR_STEPS.length}`;
  prevBtn.disabled = idx === 0;
  prevBtn.style.visibility = idx === 0 ? 'hidden' : 'visible';
  nextBtn.textContent = idx === TOUR_STEPS.length - 1 ? 'Terminer' : 'Suivant';

  if (!target) {
    // Fallback : centre l'overlay sur l'écran
    spotlight.style.cssText = 'top:50%;left:50%;width:0;height:0;transform:translate(-50%,-50%)';
    pop.style.top  = '50%';
    pop.style.left = '50%';
    pop.style.transform = 'translate(-50%, -50%)';
    return;
  }
  pop.style.transform = '';

  const rect = target.getBoundingClientRect();
  const PAD = 8;
  spotlight.style.top    = (rect.top    - PAD) + 'px';
  spotlight.style.left   = (rect.left   - PAD) + 'px';
  spotlight.style.width  = (rect.width  + PAD * 2) + 'px';
  spotlight.style.height = (rect.height + PAD * 2) + 'px';

  // Place le popover selon `placement`
  positionPopover(pop, rect, step.placement || 'bottom');

  // Scroll si nécessaire
  if (rect.top < 80 || rect.bottom > window.innerHeight - 80) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function positionPopover(pop, rect, placement) {
  const popW = 320;
  const popH = pop.offsetHeight || 180;
  const margin = 16;
  let top = 0, left = 0;

  switch (placement) {
    case 'top':
      top  = rect.top - popH - margin;
      left = rect.left + rect.width / 2 - popW / 2;
      break;
    case 'left':
      top  = rect.top + rect.height / 2 - popH / 2;
      left = rect.left - popW - margin;
      break;
    case 'right':
      top  = rect.top + rect.height / 2 - popH / 2;
      left = rect.right + margin;
      break;
    case 'bottom':
    default:
      top  = rect.bottom + margin;
      left = rect.left + rect.width / 2 - popW / 2;
      break;
  }
  // Clamp dans la viewport
  top  = Math.max(16, Math.min(window.innerHeight - popH - 16, top));
  left = Math.max(16, Math.min(window.innerWidth  - popW - 16, left));
  pop.style.top  = top + 'px';
  pop.style.left = left + 'px';
}

function endGuidedTour() {
  const overlay = document.getElementById('tourOverlay');
  const pop     = document.getElementById('tourPopover');
  const sp      = document.getElementById('tourSpotlight');
  if (overlay) overlay.classList.remove('visible');
  if (pop) pop.classList.remove('visible');
  setTimeout(() => {
    if (overlay) overlay.classList.add('hidden');
    if (pop)     pop.classList.add('hidden');
    if (sp) {
      sp.classList.add('hidden');
      sp.style.cssText = '';
    }
  }, 220);
  savePref('rodiaTourSeen', '1');
}

/* ── Zone danger : effacer toutes les données ─────────────────── */

function setupDangerZone() {
  const btn = document.getElementById('btnEraseAll');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    if (!confirm("ATTENTION : cette action efface TOUTE la flotte, l'historique, la configuration et vos préférences.\n\nCette opération est IRRÉVERSIBLE. Confirmer ?")) return;
    if (!confirm("Êtes-vous absolument certain ?\n\nDernière chance d'annuler.")) return;
    try {
      // 1. Reset côté serveur (flotte, config, logs)
      const r = await fetch('/api/support/erase-all', { method: 'POST' });
      const data = await r.json().catch(() => ({}));
      // 2. Clear localStorage
      ['rodiaUserName', 'diagTheme', 'rodiaTourSeen'].forEach(k => localStorage.removeItem(k));
      const msg = data.errors && data.errors.length
        ? 'Effacement partiel — ' + data.errors.join(', ')
        : 'Toutes les données ont été effacées. Le logiciel va recharger.';
      alert(msg);
      window.location.reload();
    } catch (e) {
      alert('Erreur lors de l\'effacement : ' + (e.message || e));
    }
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  // Préférences serveur d'abord — seed localStorage avant tout le reste
  // (applyTheme, refreshUserDisplay lisent localStorage)
  await loadPrefs();

  setupEvents();
  setupSearch();
  setupAuthEvents();
  setupUserMenu();
  setupHelpMenu();
  setupSearchPalette();
  setupAnamneseFlow();
  closeBugReportSetup();
  setupDangerZone();
  refreshUserDisplay();

  // Heartbeat toujours actif dès le démarrage — maintient le serveur Flask en vie
  // même pendant l'affichage de l'écran de login.
  // On envoie un premier ping immédiat pour éviter la fenêtre de 5s au démarrage.
  // Edge throttle setInterval quand la fenêtre perd le focus → on renvoie aussi
  // un ping sur visibilitychange/focus pour compenser.
  const _sendHeartbeat = () => fetch('/api/heartbeat', { method: 'POST' }).catch(() => {});
  _sendHeartbeat();
  setInterval(_sendHeartbeat, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) _sendHeartbeat(); });
  window.addEventListener('focus', _sendHeartbeat);

  // Vérification silencieuse des mises à jour (ne bloque pas le démarrage)
  checkForUpdate();

  const authenticated = await checkAuth();
  if (authenticated) {
    await startAppData();
  }
  // Si non authentifié, startAppData() sera appelé depuis le handler de login
}

document.addEventListener('DOMContentLoaded', init);

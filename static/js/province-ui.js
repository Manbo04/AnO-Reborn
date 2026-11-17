/* Province page: accessible tabs (URL hash) + building search. Progressive enhancement: without JS every panel is visible. */
(function () {
  'use strict';
  var root = document.querySelector('.province-ui');
  if (!root) return;
  var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
  var panels = tabs.map(function (t) { return document.getElementById(t.getAttribute('aria-controls')); });
  if (!tabs.length) return;
  root.classList.add('js-tabs');

  function select(i, focus, updateHash) {
    tabs.forEach(function (t, j) {
      var on = i === j;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      if (panels[j]) panels[j].hidden = !on;
    });
    if (focus) tabs[i].focus();
    if (updateHash) {
      try { history.replaceState(null, '', '#' + tabs[i].getAttribute('data-tab')); } catch (e) { /* ignore */ }
    }
  }
  function fromHash() {
    var h = (location.hash || '').replace('#', '');
    for (var i = 0; i < tabs.length; i++) if (tabs[i].getAttribute('data-tab') === h) return { i: i, el: null };
    // In-page jump link (e.g. #grp-industry): open the tab that holds the target
    // instead of falling back to Overview, then scroll to it.
    var el = h ? document.getElementById(h) : null;
    var panel = el ? el.closest('.ptabpanel') : null;
    var idx = panel ? panels.indexOf(panel) : -1;
    if (idx >= 0) return { i: idx, el: el };
    return { i: 0, el: null, unknown: !!h };
  }
  function applyHash(isInitial) {
    var r = fromHash();
    // An unrecognised hash on a later hashchange must not yank the user off their tab.
    if (r.unknown && !isInitial) return;
    select(r.i, false, false);
    if (r.el) r.el.scrollIntoView();
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { select(i, false, true); });
    t.addEventListener('keydown', function (ev) {
      var n = null;
      if (ev.key === 'ArrowRight') n = (i + 1) % tabs.length;
      else if (ev.key === 'ArrowLeft') n = (i - 1 + tabs.length) % tabs.length;
      else if (ev.key === 'Home') n = 0;
      else if (ev.key === 'End') n = tabs.length - 1;
      if (n !== null) { ev.preventDefault(); select(n, true, true); }
    });
  });
  applyHash(true);
  window.addEventListener('hashchange', function () { applyHash(false); });

  // Building search: filters rows inside the panel it belongs to; hides empty groups.
  Array.prototype.forEach.call(root.querySelectorAll('.bld-search'), function (input) {
    var panel = input.closest('.ptabpanel');
    var empty = panel.querySelector('.bld-empty');
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      Array.prototype.forEach.call(panel.querySelectorAll('.bld-row'), function (row) {
        var ok = !q || (row.getAttribute('data-bld-name') || '').indexOf(q) !== -1;
        row.hidden = !ok;
        if (ok) shown++;
      });
      Array.prototype.forEach.call(panel.querySelectorAll('.bld-group'), function (g) {
        g.hidden = !g.querySelector('.bld-row:not([hidden])');
      });
      if (empty) empty.hidden = shown !== 0;
    });
  });

  // ---------------------------------------------------------------------------
  // Buy/sell without leaving the page + live cost pre-calculator + live essentials bar.
  // Server stays the authority (purchase_building); this only previews and avoids the
  // full-page redirect that threw players back to the Overview tab (celess mob, 11-15).
  // ---------------------------------------------------------------------------
  var pid = root.getAttribute('data-province');
  if (!pid) return;
  var calc = null;
  var autoSlots = false;
  try { autoSlots = localStorage.getItem('ano_auto_slots') === '1'; } catch (e) { /* storage may be blocked */ }
  Array.prototype.forEach.call(root.querySelectorAll('.auto-slots-cb'), function (cb) { cb.checked = autoSlots; });
  root.addEventListener('change', function (ev) {
    if (!ev.target.classList || !ev.target.classList.contains('auto-slots-cb')) return;
    autoSlots = ev.target.checked;
    try { localStorage.setItem('ano_auto_slots', autoSlots ? '1' : '0'); } catch (e) { /* ignore */ }
    Array.prototype.forEach.call(root.querySelectorAll('.auto-slots-cb'), function (cb) { cb.checked = autoSlots; });
    renderAll();
  });
  // Mirrors the server's capped-linear land/city price (display only; the server re-checks before buying).
  function slotCostFor(slot, n) {
    var s = calc && calc.slots && calc.slots[slot];
    if (!s || n < 1) return 0;
    var unc = Math.max(0, Math.min(n, s.cap - s.owned));
    var raw = unc * s.base + s.inc * (unc * s.owned + unc * (unc - 1) / 2) + (n - unc) * (s.base + s.cap * s.inc);
    return Math.floor(raw * s.factor);
  }
  var nf = new Intl.NumberFormat('en-US');
  function fmt(n) { return nf.format(Math.round(n)); }
  var cf = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 });
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function toast(msg, isError) {
    var box = document.getElementById('toast-container');
    if (!box) { box = el('div', 'toast-container'); box.id = 'toast-container'; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
    var t = el('div', 'toast-item' + (isError ? ' toast-item--error' : ''));
    t.appendChild(el('span', 'toast-message', msg));
    var x = el('button', 'toast-dismiss'); x.type = 'button'; x.setAttribute('aria-label', 'Dismiss notification');
    x.appendChild(el('span', 'material-icons-outlined', 'close'));
    x.addEventListener('click', function () { t.remove(); });
    t.appendChild(x);
    box.appendChild(t);
    if (!isError) setTimeout(function () { if (t.parentNode) t.remove(); }, 4500);
  }

  function setLive(key, text, bad) {
    var item = root.querySelector('.pstick-item[data-live="' + key + '"]');
    if (!item) return;
    var b = item.querySelector('b'); if (b) b.textContent = text;
    if (bad !== undefined && key === 'power') { item.classList.toggle('pstick-item--bad', !!bad); item.classList.toggle('pstick-item--ok', !bad); }
  }
  function renderEssentials() {
    if (!calc) return;
    setLive('power', calc.power.used + '/' + calc.power.total, calc.power.total < calc.power.used);
    setLive('city', calc.city.used + '/' + calc.city.total);
    setLive('land', calc.land.used + '/' + calc.land.total);
    setLive('gold', cf.format(calc.gold));
    var gi = root.querySelector('.pstick-item[data-live="gold"]'); if (gi) gi.title = fmt(calc.gold) + ' gold in your treasury';
  }

  // ---- per-building preview ----
  function previewFor(unit, qty) {
    var c = calc.costs[unit];
    var out = [];
    var short = false;
    if (!c || !qty || qty < 1) return { parts: out, short: false };
    var gold = c.gold * qty;
    var slotDef = 0, slotGold = 0;
    if (autoSlots && c.slot && calc.slots && qty > calc[c.slot].free) {
      slotDef = qty - calc[c.slot].free;
      slotGold = slotCostFor(c.slot, slotDef);
      gold += slotGold;
    }
    var gp = el('span', gold > calc.gold ? 'short' : 'ok', fmt(gold) + ' gold' + (gold > calc.gold ? ' (need ' + fmt(gold - calc.gold) + ' more)' : ''));
    out.push(gp); if (gold > calc.gold) short = true;
    Object.keys(c.resources).forEach(function (r) {
      var need = c.resources[r] * qty, have = calc.stock[r] || 0;
      var low = need > have;
      out.push(el('span', low ? 'short' : 'ok', fmt(need) + ' ' + r.replace(/_/g, ' ') + (low ? ' (need ' + fmt(need - have) + ' more)' : '')));
      if (low) short = true;
    });
    if (slotDef > 0) {
      out.push(el('span', 'ok', 'Includes ' + fmt(slotDef) + ' extra ' + c.slot + ' slot' + (slotDef === 1 ? '' : 's') + ' (' + fmt(slotGold) + ' gold)'));
    } else if (c.slot) {
      var free = calc[c.slot].free;
      if (qty > free) { out.push(el('span', 'short', 'Needs ' + fmt(qty - free) + ' more ' + c.slot + ' slot' + (qty - free === 1 ? '' : 's') + ' (' + fmt(free) + ' free)')); short = true; }
    }
    if (c.jobs) {
      var wf = calc.workforce, needed = wf.jobs_needed + c.jobs * qty;
      if (needed > wf.jobs_available) {
        var eff = Math.max(calc.min_efficiency, wf.jobs_available / needed);
        out.push(el('span', 'short', 'Not enough workers: ' + fmt(needed - wf.jobs_available) + ' jobs unfilled, all production runs at ' + Math.round(eff * 100) + '%'));
        short = true;
      } else {
        out.push(el('span', 'ok', 'Adds ' + fmt(c.jobs * qty) + ' jobs (workers OK)'));
      }
    }
    return { parts: out, short: short };
  }
  function renderRow(input) {
    var unit = input.name;
    var row = input.closest('.bld-row');
    var line = row && row.querySelector('.bld-calc[data-calc-unit]');
    if (!line || !calc) return;
    var q = parseInt(input.value, 10);
    var r = previewFor(unit, q);
    line.textContent = '';
    r.parts.forEach(function (p) { line.appendChild(p); });
    line.hidden = !r.parts.length;
    row.classList.toggle('bld-row--short', r.short);
  }
  root.addEventListener('input', function (ev) {
    var t = ev.target;
    if (t.classList && t.classList.contains('bld-qty')) renderRow(t);
    if (t.id === 'citiesamount' || t.id === 'landamount') setTimeout(function () { renderLandCity(t); }, 0);
  });
  // City / land totals come from the page's own price formulas (output element); we only red it out.
  function renderLandCity(input) {
    if (!calc) return;
    var outId = input.id === 'citiesamount' ? 'citiesoutput' : 'landoutput';
    var line = document.getElementById(input.id === 'citiesamount' ? 'citiesshort' : 'landshort');
    var out = document.getElementById(outId);
    if (!line || !out) return;
    var gold = parseInt((out.textContent || '0').replace(/[^0-9]/g, ''), 10) || 0;
    line.textContent = '';
    if (gold > calc.gold) {
      line.appendChild(el('span', 'short', 'Need ' + fmt(gold - calc.gold) + ' more gold (you have ' + fmt(calc.gold) + ')'));
      line.hidden = false;
    } else line.hidden = true;
    out.classList.toggle('short', gold > calc.gold);
  }
  function renderAll() {
    renderEssentials();
    Array.prototype.forEach.call(root.querySelectorAll('.bld-qty'), renderRow);
    ['citiesamount', 'landamount'].forEach(function (id) { var i = document.getElementById(id); if (i) renderLandCity(i); });
  }

  function loadCalc() {
    return fetch('/api/province/' + encodeURIComponent(pid) + '/build_calc', { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.ok) return;
        calc = d;
        var cc = document.getElementById('cityCount'); if (cc) cc.value = d.city.total;
        var cl = document.getElementById('currentLand'); if (cl) cl.value = d.land.total;
        renderAll();
      })
      .catch(function () { /* preview is optional; buying still works */ });
  }

  // After a purchase: refresh the server-rendered bits (vitals, info table, energy panel, owned counts) in place.
  function refreshFragments() {
    return fetch(location.pathname + '?_=' + Date.now(), { credentials: 'same-origin', headers: { 'Accept': 'text/html' } })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) return;
        var doc = new DOMParser().parseFromString(html, 'text/html');
        ['.vitals-strip', '.province-info-grid', '.energy-balance-panel'].forEach(function (sel) {
          var cur = root.querySelector(sel), nu = doc.querySelector(sel);
          if (cur && nu) cur.innerHTML = nu.innerHTML;
        });
        Array.prototype.forEach.call(root.querySelectorAll('.bld-row[id]'), function (row) {
          var nu = doc.getElementById(row.id); if (!nu) return;
          var a = row.querySelector('.bld-owned'), b = nu.querySelector('.bld-owned');
          if (a && b) { a.textContent = b.textContent; a.title = b.title; }
          row.classList.toggle('bld-row--owned', nu.classList.contains('bld-row--owned'));
        });
      })
      .catch(function () { /* next full load will catch up */ });
  }

  // Auto-buy slots: confirm the exact price first, then buy only the missing slots with the normal routes.
  function buySlots(slot, n, buildingGold) {
    var unit = slot === 'city' ? 'cityCount' : 'land';
    return fetch('/api/province/' + encodeURIComponent(pid) + '/slot_cost?slot=' + slot + '&n=' + n, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (q) {
        if (!q || !q.ok) { toast((q && q.error) || 'Could not price the extra slots.', true); return false; }
        if (q.gold + buildingGold > q.have) {
          toast('Not enough gold for the slots and buildings: need ' + fmt(q.gold + buildingGold - q.have) + ' more. Nothing was bought.', true);
          return false;
        }
        var b = new URLSearchParams(); b.set(unit, String(n));
        return fetch('/buy/' + unit + '/' + encodeURIComponent(pid), { method: 'POST', body: b, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' } })
          .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
          .then(function (res) {
            if (!res.ok) { toast((res.j && res.j.error) || 'Could not buy the extra slots. Nothing was built.', true); return false; }
            toast('Bought ' + fmt(n) + ' ' + slot + ' slot' + (n === 1 ? '' : 's') + ' first.', false);
            return true;
          });
      })
      .catch(function () { toast('Could not reach the server. Nothing was changed; reload and check.', true); return false; });
  }

  // ---- submit via fetch, stay on the same tab ----
  var inflight = false;
  root.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (!form.matches || !form.matches('.bld-form, .province-purchase-grid, form[action="/build_structure"]')) return;
    var btn = ev.submitter;
    var url = (btn && btn.getAttribute('formaction')) || form.getAttribute('action');
    if (!url || !window.fetch) return; // no JS fetch: classic redirect
    ev.preventDefault();
    if (inflight) return; // double-submit guard
    inflight = true;
    Array.prototype.forEach.call(document.querySelectorAll('.toast-item--error'), function (t) { t.remove(); }); // old failures are stale once you act again
    var panel = btn ? btn.closest('.bld-row, .province-purchase-panel, form') : form;
    if (panel) panel.classList.add('purchase-busy');
    var body = new URLSearchParams(new FormData(form));
    var qtyIn = btn && btn.closest('.bld-row') && btn.closest('.bld-row').querySelector('.bld-qty');
    var pre = Promise.resolve(true);
    if (autoSlots && calc && qtyIn && /^\/buy\//.test(url) && calc.costs[qtyIn.name] && calc.costs[qtyIn.name].slot) {
      var c0 = calc.costs[qtyIn.name], q0 = parseInt(qtyIn.value, 10) || 0, def = q0 - calc[c0.slot].free;
      if (def > 0) pre = buySlots(c0.slot, def, c0.gold * q0);
    }
    pre.then(function (go) {
      if (!go) return { skipped: true };
      return fetch(url, { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' } })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); });
    })
      .then(function (res) {
        if (res.skipped) return loadCalc();
        if (res.ok) {
          toast(res.j.message || 'Done', false);
          var qty = btn && btn.closest('.bld-row') && btn.closest('.bld-row').querySelector('.bld-qty');
          if (qty) qty.value = '';
          ['citiesamount', 'landamount'].forEach(function (id) {
            var i = document.getElementById(id);
            if (i && btn && btn.closest('.province-purchase-panel') && btn.closest('.province-purchase-panel').contains(i)) { i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); }
          });
          try { document.dispatchEvent(new CustomEvent("ano:state-changed")); } catch (e) {}
          return Promise.all([loadCalc(), refreshFragments()]);
        }
        toast((res.j && res.j.error) || 'That did not go through.', true);
        return loadCalc();
      })
      .catch(function () { toast('Could not reach the server. Nothing was changed; reload and check.', true); })
      .then(function () { inflight = false; if (panel) panel.classList.remove('purchase-busy'); });
  });

  // keep the essentials bar below the fixed site header
  function placeNav() {
    // Fixed site header + the sticky resource HUD (phones) both sit above the page content.
    var h = 0;
    ['navbarparent'].forEach(function (id) {
      var n = document.getElementById(id);
      if (n && getComputedStyle(n).position === 'fixed') h += Math.round(n.getBoundingClientRect().height);
    });
    var hud = document.querySelector('.game-hud');
    if (hud && getComputedStyle(hud).position === 'sticky' && hud.offsetHeight) h += hud.offsetHeight;
    root.style.setProperty('--pnav-top', h + 'px');
  }
  placeNav();
  window.addEventListener('resize', placeNav);
  loadCalc();
})();

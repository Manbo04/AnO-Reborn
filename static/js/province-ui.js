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
})();

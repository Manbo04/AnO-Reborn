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
    for (var i = 0; i < tabs.length; i++) if (tabs[i].getAttribute('data-tab') === h) return i;
    return 0;
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
  select(fromHash(), false, false);
  window.addEventListener('hashchange', function () { select(fromHash(), false, false); });

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

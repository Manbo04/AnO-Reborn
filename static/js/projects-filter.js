/* Projects page: "Show only available" checkbox (celess mob, vote 9/0). A project is available while it is not researched yet.
   Remembers the choice per browser; with JS off every project simply stays visible. */
(function () {
  'use strict';
  var box = document.getElementById('proj-available-only');
  var grid = document.querySelector('.tech-grid-form');
  if (!box || !grid) return;
  var cards = Array.prototype.slice.call(grid.querySelectorAll('.menudiv'));
  var note = document.getElementById('proj-filter-note');
  var empty = document.getElementById('proj-filter-empty');
  var KEY = 'ano.projects.availableOnly';
  function isResearched(card) { return !!card.querySelector('.researched-badge'); }
  function apply() {
    var only = box.checked, hidden = 0;
    cards.forEach(function (c) {
      var hide = only && isResearched(c);
      c.style.display = hide ? 'none' : '';
      if (hide) hidden++;
    });
    var shown = cards.length - hidden;
    if (note) note.textContent = only ? (shown + ' available, ' + hidden + ' researched hidden') : '';
    if (empty) empty.hidden = !(only && cards.length && shown === 0);
    try { localStorage.setItem(KEY, only ? '1' : '0'); } catch (e) { /* private mode: fine */ }
  }
  try { box.checked = localStorage.getItem(KEY) === '1'; } catch (e) { /* ignore */ }
  box.addEventListener('change', apply);
  apply();
})();

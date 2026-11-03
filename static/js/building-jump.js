/* Jump-to-building bar on the province page (Helios, 2026-10-03: "building
   anything requires pages of scrolling to get to different buildings").
   Lists the buildings in whichever infrastructure tab is open and rebuilds
   when the player switches tab (tabs are class toggles, static/script.js). */
(function () {
    'use strict';

    function slug(text) {
        return 'bld-' + text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    }

    function render(nav) {
        var headers = Array.prototype.filter.call(
            document.querySelectorAll('.menudiv > h2.templatecontentheaderleft'),
            function (h) { return h.offsetParent !== null && h.textContent.trim(); }
        );
        nav.textContent = '';
        if (headers.length < 2) return; // nothing worth jumping between
        var label = document.createElement('span');
        label.className = 'building-jump-label';
        label.textContent = 'Jump to';
        nav.appendChild(label);
        headers.forEach(function (h) {
            var name = h.textContent.trim();
            if (!h.id) h.id = slug(name);
            var a = document.createElement('a');
            a.href = '#' + h.id;
            a.textContent = name;
            a.addEventListener('click', function (e) {
                e.preventDefault();
                h.scrollIntoView({ behavior: 'smooth', block: 'start' });
                if (history.replaceState) history.replaceState(null, '', '#' + h.id);
            });
            nav.appendChild(a);
        });
    }

    function init() {
        var nav = document.querySelector('.building-jump');
        if (!nav) return;
        render(nav);
        // Tab buttons are links inside the .menuflex2 rows; re-render after
        // their onclick has swapped the visible panel.
        document.addEventListener('click', function (e) {
            if (e.target.closest && e.target.closest('.menuflex2 a')) {
                setTimeout(function () { render(nav); }, 0);
            }
        });
    }

    // Deferred scripts run before DOMContentLoaded, i.e. before script.js
    // has opened the default tab, so every building would still look hidden.
    // Render once the page (and its tab state) has finished loading.
    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }
})();

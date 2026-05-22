/**
 * Game shell: HUD expand, tick countdown (bottom tab nav removed).
 */
(function () {
    'use strict';

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function initHudExpand() {
        var btn = qs('[data-game-hud-expand]');
        var drawer = qs('#resourcedivcontent');
        var fab = qs('#resourcediv');
        if (!btn) return;
        btn.addEventListener('click', function () {
            if (typeof resourcedivcontentshow === 'function') {
                resourcedivcontentshow();
                return;
            }
            if (drawer) {
                drawer.classList.toggle('game-hud-drawer-open');
            }
            if (fab) {
                fab.click();
            }
        });
    }

    /** Next hour boundary — aligns with hourly Celery ticks (approximate). */
    function initTickBadge() {
        var el = qs('[data-game-tick-countdown]');
        if (!el) return;

        function pad(n) {
            return n < 10 ? '0' + n : String(n);
        }

        function tick() {
            var now = new Date();
            var next = new Date(now);
            next.setMinutes(0, 0, 0);
            next.setHours(next.getHours() + 1);
            var diff = Math.max(0, Math.floor((next - now) / 1000));
            var m = Math.floor(diff / 60);
            var s = diff % 60;
            el.textContent = 'Tick ~' + pad(m) + ':' + pad(s);
        }

        tick();
        setInterval(tick, 1000);
    }

    function initReducedMotion() {
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        document.body.classList.add('game-reduced-motion');
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.body.classList.contains('game-shell-active')) return;
        initReducedMotion();
        initHudExpand();
        initTickBadge();
    });
})();

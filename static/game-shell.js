/**
 * Game shell: bottom nav active state, more sheet, HUD expand, tick timer hint.
 */
(function () {
    'use strict';

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function qsa(sel, root) {
        return Array.from((root || document).querySelectorAll(sel));
    }

    function setActiveNav() {
        var path = window.location.pathname || '/';
        qsa('.game-bottom-nav .game-nav-item[data-nav-href]').forEach(function (el) {
            var href = el.getAttribute('data-nav-href') || '';
            var active = false;
            if (href === '/provinces' && path.indexOf('/province') === 0) {
                active = true;
            } else if (href && (path === href || path.indexOf(href + '/') === 0)) {
                active = true;
            }
            el.classList.toggle('is-active', active);
        });
    }

    function initMoreSheet() {
        var sheet = qs('#game-more-sheet');
        var openBtn = qs('[data-game-more-open]');
        if (!sheet || !openBtn) return;

        function close() {
            sheet.classList.remove('is-open');
            sheet.setAttribute('aria-hidden', 'true');
        }

        function open() {
            sheet.classList.add('is-open');
            sheet.setAttribute('aria-hidden', 'false');
        }

        openBtn.addEventListener('click', function (e) {
            e.preventDefault();
            if (sheet.classList.contains('is-open')) {
                close();
            } else {
                open();
            }
        });

        qsa('[data-game-more-close]', sheet).forEach(function (el) {
            el.addEventListener('click', close);
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') close();
        });
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
        setActiveNav();
        initMoreSheet();
        initHudExpand();
        initTickBadge();
    });
})();

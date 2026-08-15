/* =====================================================================
 * touch-gestures.js — Affairs and Order
 * A global touch / gesture layer that makes the game genuinely usable on
 * phones and tablets. Everything here is a progressive enhancement: it only
 * activates on touch-capable devices and never changes desktop behaviour.
 *
 * Features
 *   1. Edge-swipe to open/close the nav menu (left edge) and the resource
 *      drawer (right edge).
 *   2. Instant tap feedback (.touch-active) so buttons feel responsive.
 *   3. Long-press tooltips — hover-only tippy content becomes reachable.
 *   4. Swipe left/right to move between prev/next pages on any element that
 *      declares [data-swipe-nav] with data-swipe-prev / data-swipe-next URLs.
 *   5. Generic pinch-to-zoom + drag-to-pan + double-tap-zoom for any element
 *      marked [data-zoomable] (maps, flags, district art). Elements that
 *      manage their own touch (e.g. game_map viewport) are left untouched.
 *   6. Light haptic feedback on meaningful actions (respects a global toggle
 *      and prefers-reduced-motion).
 * ===================================================================== */
(function () {
    'use strict';

    var isTouch = ('ontouchstart' in window) ||
        (navigator.maxTouchPoints > 0) ||
        (navigator.msMaxTouchPoints > 0);
    if (!isTouch) return;

    document.documentElement.classList.add('has-touch');

    var reduceMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // --- haptics ----------------------------------------------------------
    function haptic(ms) {
        if (reduceMotion) return;
        try {
            if (localStorage.getItem('ano-haptics') === 'off') return;
        } catch (e) {}
        if (navigator.vibrate) {
            try { navigator.vibrate(ms || 8); } catch (e) {}
        }
    }

    // --- small helpers ----------------------------------------------------
    function byId(id) { return document.getElementById(id); }
    function closest(el, sel) {
        while (el && el.nodeType === 1) {
            if (el.matches && el.matches(sel)) return el;
            el = el.parentElement;
        }
        return null;
    }

    // =====================================================================
    // 1. Edge swipes: nav menu (left) + resource drawer (right)
    // =====================================================================
    (function edgeSwipes() {
        var EDGE = 28;          // px from screen edge that starts an edge swipe
        var THRESHOLD = 55;     // px of travel to commit
        var startX = 0, startY = 0, tracking = null, t0 = 0;

        function menuIsOpen() {
            var d = byId('menubardiv');
            return !!(d && d.classList.contains('menubardivshow'));
        }
        function toggleMenu() {
            if (typeof window.menubardrop === 'function') window.menubardrop();
        }
        function drawer() { return byId('game-resource-drawer'); }
        function drawerIsOpen() {
            var d = drawer();
            return !!(d && d.classList.contains('is-open'));
        }
        function toggleDrawer() {
            if (typeof window.toggleResourceDrawer === 'function') window.toggleResourceDrawer();
        }

        // Interactive full-bleed content that can legitimately sit right at
        // the screen edge on narrow/portrait phones (e.g. the province
        // district map) -- a tap there with any natural finger micro-drift
        // was crossing the edge-swipe threshold and hijacking the tap as a
        // "open nav menu" gesture instead of the map's own tap-to-select.
        // Real reported bug: tapping the district map's empty/unbuilt
        // ("dark") areas opened the side menu on mobile portrait only,
        // because that's exactly when the map spans edge-to-edge.
        var EDGE_SWIPE_EXCLUDE_SEL = '[data-province-hub], [data-zoomable]';

        document.addEventListener('touchstart', function (e) {
            if (e.touches.length !== 1) { tracking = null; return; }
            var t = e.touches[0];
            startX = t.clientX; startY = t.clientY; t0 = Date.now();
            var w = window.innerWidth;
            if (closest(e.target, EDGE_SWIPE_EXCLUDE_SEL)) { tracking = null; return; }
            if (startX <= EDGE && !menuIsOpen())      tracking = 'menu-open';
            else if (startX >= w - EDGE && !drawerIsOpen()) tracking = 'drawer-open';
            else if (menuIsOpen())                    tracking = 'menu-close';
            else if (drawerIsOpen())                  tracking = 'drawer-close';
            else                                      tracking = null;
        }, { passive: true });

        document.addEventListener('touchend', function (e) {
            if (!tracking) return;
            var t = (e.changedTouches && e.changedTouches[0]) || null;
            if (!t) { tracking = null; return; }
            var dx = t.clientX - startX;
            var dy = t.clientY - startY;
            var dt = Date.now() - t0;
            // must be a mostly-horizontal, reasonably quick gesture
            if (Math.abs(dx) > Math.abs(dy) * 1.4 && Math.abs(dx) > THRESHOLD && dt < 700) {
                if (tracking === 'menu-open'   && dx > 0)  { toggleMenu();   haptic(10); }
                if (tracking === 'menu-close'  && dx < 0)  { toggleMenu();   haptic(6); }
                if (tracking === 'drawer-open' && dx < 0)  { toggleDrawer(); haptic(10); }
                if (tracking === 'drawer-close'&& dx > 0)  { toggleDrawer(); haptic(6); }
            }
            tracking = null;
        }, { passive: true });
    })();

    // =====================================================================
    // 2. Instant tap feedback
    // =====================================================================
    (function tapFeedback() {
        var TAP_SEL = 'button, .button, .btn, a, input[type="submit"], input[type="button"],' +
            '[role="button"], .templatebutton, .navbardropbtn, .card, [data-tap]';
        var active = null;
        function clear() { if (active) { active.classList.remove('touch-active'); active = null; } }
        document.addEventListener('touchstart', function (e) {
            var el = closest(e.target, TAP_SEL);
            if (!el) return;
            clear();
            active = el;
            el.classList.add('touch-active');
        }, { passive: true });
        document.addEventListener('touchend', clear, { passive: true });
        document.addEventListener('touchcancel', clear, { passive: true });
        document.addEventListener('touchmove', clear, { passive: true });
    })();

    // =====================================================================
    // 3. Long-press tooltips (hover content is unreachable on touch)
    // =====================================================================
    (function longPressTooltips() {
        var TIP_SEL = '[data-tippy-content], [title], [data-tooltip], .has-tooltip';
        var timer = null, target = null;
        function cancel() {
            if (timer) { clearTimeout(timer); timer = null; }
            target = null;
        }
        document.addEventListener('touchstart', function (e) {
            var el = closest(e.target, TIP_SEL);
            if (!el) return;
            target = el;
            timer = setTimeout(function () {
                haptic(12);
                // Prefer an already-initialised tippy instance
                if (el._tippy && typeof el._tippy.show === 'function') {
                    el._tippy.show();
                    setTimeout(function () { if (el._tippy) el._tippy.hide(); }, 2600);
                } else if (window.tippy && (el.getAttribute('title') || el.getAttribute('data-tooltip'))) {
                    var content = el.getAttribute('data-tippy-content') ||
                        el.getAttribute('title') || el.getAttribute('data-tooltip');
                    if (el.getAttribute('title')) {
                        el.setAttribute('data-original-title', el.getAttribute('title'));
                        el.removeAttribute('title'); // stop native tooltip fighting us
                    }
                    var inst = window.tippy(el, { content: content, trigger: 'manual', theme: 'ano' });
                    inst.show();
                    setTimeout(function () { inst.hide(); }, 2600);
                }
            }, 420);
        }, { passive: true });
        document.addEventListener('touchend', cancel, { passive: true });
        document.addEventListener('touchmove', cancel, { passive: true });
        document.addEventListener('touchcancel', cancel, { passive: true });
    })();

    // =====================================================================
    // 4. Swipe navigation between prev/next pages
    //    <div data-swipe-nav data-swipe-prev="/url" data-swipe-next="/url">
    // =====================================================================
    (function swipeNav() {
        var zones = document.querySelectorAll('[data-swipe-nav]');
        if (!zones.length) return;
        var THRESHOLD = 70;
        Array.prototype.forEach.call(zones, function (zone) {
            var sx = 0, sy = 0, t0 = 0, ok = false;
            zone.addEventListener('touchstart', function (e) {
                if (e.touches.length !== 1) { ok = false; return; }
                var t = e.touches[0]; sx = t.clientX; sy = t.clientY; t0 = Date.now(); ok = true;
            }, { passive: true });
            zone.addEventListener('touchend', function (e) {
                if (!ok) return; ok = false;
                var t = e.changedTouches[0];
                var dx = t.clientX - sx, dy = t.clientY - sy, dt = Date.now() - t0;
                if (dt > 600 || Math.abs(dx) < THRESHOLD || Math.abs(dx) < Math.abs(dy) * 1.6) return;
                var url = dx < 0 ? zone.getAttribute('data-swipe-next')
                                 : zone.getAttribute('data-swipe-prev');
                if (url) { haptic(10); window.location.href = url; }
            }, { passive: true });
        });
    })();

    // =====================================================================
    // 5. Generic pinch-zoom + pan + double-tap zoom for [data-zoomable]
    //    Skips elements that already manage their own touch handling.
    // =====================================================================
    (function zoomables() {
        var els = document.querySelectorAll('[data-zoomable]');
        if (!els.length) return;

        Array.prototype.forEach.call(els, function (el) {
            var scale = 1, panX = 0, panY = 0;
            var startDist = 0, startScale = 1;
            var startX = 0, startY = 0, startPanX = 0, startPanY = 0;
            var mode = null; // 'pan' | 'pinch'
            var lastTap = 0;
            var MAX = parseFloat(el.getAttribute('data-zoom-max')) || 5;
            var MIN = parseFloat(el.getAttribute('data-zoom-min')) || 1;

            el.style.touchAction = 'none';
            el.style.transformOrigin = '0 0';
            if (!reduceMotion) el.style.transition = 'transform .04s linear';

            function apply() {
                el.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + scale + ')';
                el.classList.toggle('is-zoomed', scale > 1.01);
            }
            function dist(a, b) {
                var dx = a.clientX - b.clientX, dy = a.clientY - b.clientY;
                return Math.sqrt(dx * dx + dy * dy);
            }
            function clampPan() {
                // keep content from drifting entirely off-screen
                var rect = el.getBoundingClientRect();
                var maxX = rect.width * (scale - 1);
                var maxY = rect.height * (scale - 1);
                panX = Math.min(0, Math.max(-maxX, panX));
                panY = Math.min(0, Math.max(-maxY, panY));
            }

            el.addEventListener('touchstart', function (e) {
                if (e.touches.length === 2) {
                    mode = 'pinch';
                    startDist = dist(e.touches[0], e.touches[1]);
                    startScale = scale;
                    e.preventDefault();
                } else if (e.touches.length === 1) {
                    var now = Date.now();
                    if (now - lastTap < 300) { // double tap toggles zoom
                        scale = scale > 1.01 ? 1 : 2.2;
                        if (scale === 1) { panX = 0; panY = 0; }
                        haptic(8); apply(); lastTap = 0; return;
                    }
                    lastTap = now;
                    if (scale > 1.01) {
                        mode = 'pan';
                        startX = e.touches[0].clientX; startY = e.touches[0].clientY;
                        startPanX = panX; startPanY = panY;
                    } else { mode = null; }
                }
            }, { passive: false });

            el.addEventListener('touchmove', function (e) {
                if (mode === 'pinch' && e.touches.length === 2) {
                    var d = dist(e.touches[0], e.touches[1]);
                    scale = Math.max(MIN, Math.min(MAX, startScale * (d / startDist)));
                    clampPan(); apply(); e.preventDefault();
                } else if (mode === 'pan' && e.touches.length === 1) {
                    panX = startPanX + (e.touches[0].clientX - startX);
                    panY = startPanY + (e.touches[0].clientY - startY);
                    clampPan(); apply(); e.preventDefault();
                }
            }, { passive: false });

            el.addEventListener('touchend', function (e) {
                if (e.touches.length === 0) mode = null;
                if (scale <= 1.01) { scale = 1; panX = 0; panY = 0; apply(); }
            }, { passive: true });
        });
    })();

    // Expose a tiny API for other scripts / inline handlers.
    window.AnoTouch = { haptic: haptic, isTouch: isTouch };
})();

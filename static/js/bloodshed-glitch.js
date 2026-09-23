// Glitch text-wall background for the bloodshed nation-page cosmetic
// (templates/country_v2.html, body.nation-bloodshed-theme). No-ops
// everywhere else -- the #bloodshed-glitch-canvas element only exists on
// that one gated page. Same "columns of falling things" technique as
// static/js/cyberpunk-matrix-rain.js and static/js/forge-embers-rain.js,
// re-skinned as a continuously scrolling wall of glyphs from the
// reference image's repeating phrase.
//
// The reference GIF FikusMikus sent (ticket-0033) is a fast full-frame
// strobing loop -- a genuine photosensitive-seizure risk, which is why
// Dede told them he'd add a warning/toggle before shipping it. Two
// safeguards instead of embedding that raw GIF:
//   1. The base scroll is smooth and continuous (no full-frame flashing),
//      so it's safe by default with no toggle needed.
//   2. The flashier RGB-split "glitch" beats are rate-limited to a few
//      hundred ms every 4-8s, and fully gated behind the on-page toggle
//      this script creates (persisted in localStorage), which itself
//      auto-disables under prefers-reduced-motion.
(function () {
    'use strict';

    var PHRASE = 'DEHUMANIZE YOURSELF AND FACE TO BLOODSHED   ';
    var STORAGE_KEY = 'ano-bloodshed-glitch-fx';

    document.addEventListener('DOMContentLoaded', function () {
        var canvas = document.getElementById('bloodshed-glitch-canvas');
        if (!canvas || !canvas.getContext) return;

        var reduceMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduceMotion) return;

        var fxEnabled = true;
        try {
            var stored = window.localStorage.getItem(STORAGE_KEY);
            if (stored !== null) fxEnabled = stored === 'on';
        } catch (e) { /* localStorage unavailable, keep default on */ }

        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'bloodshed-fx-toggle';
        toggle.title = 'Toggle flashing glitch bursts on this page';
        function renderToggle() {
            toggle.setAttribute('aria-pressed', String(fxEnabled));
            toggle.textContent = fxEnabled ? '⚡ Flash FX: On' : '⚡ Flash FX: Off';
        }
        renderToggle();
        toggle.addEventListener('click', function () {
            fxEnabled = !fxEnabled;
            renderToggle();
            try {
                window.localStorage.setItem(STORAGE_KEY, fxEnabled ? 'on' : 'off');
            } catch (e) { /* localStorage unavailable, in-memory only */ }
        });
        document.body.appendChild(toggle);

        var ctx = canvas.getContext('2d');
        var COLUMN_WIDTH = 16;
        var FONT_SIZE = 14;
        var columns = 0;
        var drops = [];
        var timer = null;
        var glitchUntil = 0;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            var newColumns = Math.max(1, Math.floor(canvas.width / COLUMN_WIDTH));
            drops = new Array(newColumns);
            for (var i = 0; i < newColumns; i++) {
                drops[i] = {
                    y: Math.random() * -canvas.height,
                    speed: 1 + Math.random() * 1.5,
                    offset: Math.floor(Math.random() * PHRASE.length)
                };
            }
            columns = newColumns;
        }

        // Opens a short (180-300ms) glitch window every 4-8s, but only
        // if the toggle is on -- this is the one part of the effect that
        // resembles the reference GIF's flashing, so it's the one part
        // the toggle actually controls.
        function scheduleGlitch() {
            window.setTimeout(function () {
                if (fxEnabled) {
                    glitchUntil = Date.now() + 180 + Math.random() * 120;
                }
                scheduleGlitch();
            }, 4000 + Math.random() * 4000);
        }

        function draw() {
            var glitching = Date.now() < glitchUntil;

            ctx.fillStyle = 'rgba(5, 5, 5, 0.15)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            ctx.font = FONT_SIZE + 'px monospace';
            ctx.textBaseline = 'top';

            for (var i = 0; i < columns; i++) {
                var drop = drops[i];
                var ch = PHRASE[(drop.offset + Math.floor(drop.y / FONT_SIZE)) % PHRASE.length];
                var x = i * COLUMN_WIDTH;

                if (glitching && Math.random() < 0.4) {
                    ctx.fillStyle = 'rgba(255, 26, 46, 0.8)';
                    ctx.fillText(ch, x - 1, drop.y);
                    ctx.fillStyle = 'rgba(120, 220, 255, 0.6)';
                    ctx.fillText(ch, x + 1, drop.y);
                }
                ctx.fillStyle = 'rgba(245, 245, 245, 0.75)';
                ctx.fillText(ch, x, drop.y);

                drop.y += drop.speed * (glitching ? 2.2 : 1);
                if (drop.y > canvas.height && Math.random() > 0.985) {
                    drop.y = Math.random() * -100;
                }
            }
        }

        function start() {
            if (timer) return;
            timer = window.setInterval(draw, 60);
        }

        function stop() {
            if (!timer) return;
            window.clearInterval(timer);
            timer = null;
        }

        resize();
        // Mobile browsers fire 'resize' every time the address bar shows or
        // hides during a scroll. resize() reallocates the canvas (wiping it)
        // and restarts every particle, which read as the whole page
        // glitching/tearing mid-scroll (player recording 2026-09-23). Only a
        // real width change (rotation, window resize) re-lays it out.
        var lastWidth = window.innerWidth;
        window.addEventListener('resize', function () {
            if (window.innerWidth === lastWidth) return;
            lastWidth = window.innerWidth;
            resize();
        });

        // Touch devices: pause drawing while the page is scrolling so the
        // canvas repaints don't compete with the scroll itself.
        if (window.matchMedia && window.matchMedia('(hover: none) and (pointer: coarse)').matches) {
            var resumeTimer = null;
            window.addEventListener('scroll', function () {
                stop();
                clearTimeout(resumeTimer);
                resumeTimer = setTimeout(function () {
                    if (!document.hidden) start();
                }, 200);
            }, { passive: true });
        }
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                stop();
            } else {
                start();
            }
        });

        scheduleGlitch();
        start();
    });
})();

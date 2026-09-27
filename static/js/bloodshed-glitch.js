// "Dehumanize yourself and face to bloodshed" background for the bloodshed
// nation-page cosmetic (templates/country_v2.html, body.nation-bloodshed-theme,
// ticket-0033 / FikusMikus). No-ops everywhere else -- the
// #bloodshed-glitch-canvas element only exists on that one gated page.
//
// Recreates the reference GIF's composition rather than a generic "falling
// glyphs" rain: a black sky with a lone radio tower, and a dense wall of the
// phrase in a bitmap font rising up from the bottom of the screen -- rows
// scrolling in alternating directions, double-exposed ghost rows, and
// horizontal tearing where rows jump sideways.
//
// Photosensitivity: the reference GIF is a fast full-frame strobe (black <->
// dense white text), a genuine seizure risk. The base animation here never
// changes overall screen brightness abruptly (motion + displacement only), so
// it is safe by default. The strobe itself is opt-in via the on-page
// "Strobe" toggle this script creates (persisted in localStorage, OFF by
// default for every visitor), and even then is capped at 3 flashes per
// second -- the WCAG 2.3.1 general flash threshold. Everything is skipped
// under prefers-reduced-motion.
(function () {
    'use strict';

    var PHRASE = 'DEHUMANIZE YOURSELF AND FACE TO BLOODSHED ';
    var GLITCH_CHARS = '█▓▒░#%&@$*/\\|_-=';
    var STORAGE_KEY = 'ano-bloodshed-strobe';
    var FONT_FAMILY = "'VT323', 'Courier New', monospace";
    var FPS_INTERVAL = 42;           // ~24fps, matches the GIF's choppy feel
    var STROBE_HALF_PERIOD = 170;    // ms per on/off phase -> < 3 flashes/s

    document.addEventListener('DOMContentLoaded', function () {
        var canvas = document.getElementById('bloodshed-glitch-canvas');
        if (!canvas || !canvas.getContext) return;

        var reduceMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduceMotion) return;

        var strobeEnabled = false;
        try {
            strobeEnabled = window.localStorage.getItem(STORAGE_KEY) === 'on';
        } catch (e) { /* localStorage unavailable, stay off */ }

        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'bloodshed-fx-toggle';
        toggle.title = 'Warning: turning this on enables flashing lights on this page';
        function renderToggle() {
            toggle.setAttribute('aria-pressed', String(strobeEnabled));
            toggle.textContent = strobeEnabled ? '⚠ Strobe: On' : '⚠ Strobe: Off';
            document.body.classList.toggle('bloodshed-strobe-on', strobeEnabled);
        }
        renderToggle();
        toggle.addEventListener('click', function () {
            strobeEnabled = !strobeEnabled;
            if (!strobeEnabled) strobeUntil = 0;
            renderToggle();
            try {
                window.localStorage.setItem(STORAGE_KEY, strobeEnabled ? 'on' : 'off');
            } catch (e) { /* in-memory only */ }
        });
        document.body.appendChild(toggle);

        var ctx = canvas.getContext('2d');
        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        var W = 0, H = 0;
        var fontSize = 22, rowH = 20, charW = 11;
        var rows = [];
        var phraseWidth = 0;
        var timer = null;
        var tick = 0;
        var strobeUntil = 0;
        var strobeStart = 0;

        function randomGlitchString(len) {
            var s = '';
            for (var i = 0; i < len; i++) {
                s += GLITCH_CHARS[Math.floor(Math.random() * GLITCH_CHARS.length)];
            }
            return s;
        }

        function resize() {
            W = window.innerWidth;
            H = window.innerHeight;
            canvas.width = Math.floor(W * dpr);
            canvas.height = Math.floor(H * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            fontSize = Math.round(Math.max(16, Math.min(30, W / 42)));
            rowH = Math.round(fontSize * 0.92);
            ctx.font = fontSize + 'px ' + FONT_FAMILY;
            charW = ctx.measureText('M').width;
            phraseWidth = ctx.measureText(PHRASE).width;

            // Rows cover the full height; density/brightness is decided per
            // frame from each row's position relative to the rising "wall".
            rows = [];
            var count = Math.ceil(H / rowH) + 1;
            for (var i = 0; i < count; i++) {
                var dir = i % 2 === 0 ? 1 : -1;
                rows.push({
                    y: i * rowH,
                    x: Math.random() * phraseWidth,
                    speed: dir * (0.6 + Math.random() * 1.8),
                    ghostOffset: Math.random() * phraseWidth,
                    ghostSpeed: -dir * (0.3 + Math.random() * 1.2),
                    tear: 0,
                    tearFrames: 0,
                    corrupt: null,
                    corruptAt: 0,
                    corruptFrames: 0
                });
            }
        }

        // Draw PHRASE repeated across the full width, starting at offset x.
        function drawPhraseRow(y, x) {
            var start = (x % phraseWidth) - phraseWidth;
            for (var px = start; px < W; px += phraseWidth) {
                ctx.fillText(PHRASE, px, y);
            }
        }

        // The lone tower from the reference image: a thin lattice mast rising
        // out of the text wall, with a slow (1Hz, tiny) red aviation light.
        function drawTower(wallTop) {
            var cx = Math.round(W * 0.38);
            var top = H * 0.14;
            var base = Math.max(wallTop + rowH * 2, H * 0.62);
            ctx.save();
            ctx.globalAlpha = 0.85;
            ctx.fillStyle = '#e9e9e9';
            ctx.fillRect(cx - 1, top, 2, base - top);
            // lattice ticks / antenna segments
            for (var y = top + 10; y < base; y += 14) {
                var w = 2 + Math.floor(((y - top) / (base - top)) * 7);
                ctx.fillRect(cx - w, y, w * 2, 1);
            }
            ctx.fillRect(cx - 4, top + (base - top) * 0.28, 8, 3);
            ctx.fillRect(cx - 6, top + (base - top) * 0.55, 12, 3);
            ctx.restore();

            var blinkOn = Math.floor(Date.now() / 1000) % 2 === 0;
            if (blinkOn) {
                ctx.save();
                ctx.fillStyle = '#ff1a2e';
                ctx.shadowColor = '#ff1a2e';
                ctx.shadowBlur = 10;
                ctx.fillRect(cx - 2, top - 5, 4, 4);
                ctx.restore();
            }
        }

        function scheduleStrobe() {
            window.setTimeout(function () {
                if (strobeEnabled && !document.hidden) {
                    strobeStart = Date.now();
                    strobeUntil = strobeStart + 900 + Math.random() * 700;
                }
                scheduleStrobe();
            }, 5000 + Math.random() * 5000);
        }

        function draw() {
            tick++;
            var now = Date.now();
            var strobing = strobeEnabled && now < strobeUntil;
            // Discrete on/off phases no faster than STROBE_HALF_PERIOD.
            var strobePhaseOn = strobing &&
                Math.floor((now - strobeStart) / STROBE_HALF_PERIOD) % 2 === 0;

            // Partial clear leaves a faint smear of the previous frame --
            // the GIF's double-exposed, VHS-ghosted look.
            ctx.fillStyle = strobePhaseOn ? 'rgba(235, 235, 235, 0.9)' : 'rgba(0, 0, 0, 0.55)';
            ctx.fillRect(0, 0, W, H);

            // The wall's top edge breathes slowly up and down.
            var wallTop = H * (0.42 + 0.06 * Math.sin(tick / 90));
            if (strobing) wallTop = H * 0.05;

            ctx.font = fontSize + 'px ' + FONT_FAMILY;
            ctx.textBaseline = 'top';

            for (var i = 0; i < rows.length; i++) {
                var r = rows[i];
                r.x += r.speed;
                r.ghostOffset += r.ghostSpeed;

                // Brightness ramps up the deeper into the wall a row is; rows
                // above it only flicker in sparsely as stray fragments.
                var depth = (r.y - wallTop) / Math.max(1, H - wallTop);
                var alpha;
                if (depth < 0) {
                    if (Math.random() > 0.04) continue;
                    alpha = 0.18;
                } else {
                    alpha = 0.45 + Math.min(1, depth) * 0.5;
                }

                // Horizontal tearing: a row occasionally snaps sideways for a
                // few frames, like a bad tracking line.
                if (r.tearFrames > 0) {
                    r.tearFrames--;
                } else if (Math.random() < 0.012) {
                    r.tear = (Math.random() - 0.5) * W * 0.3;
                    r.tearFrames = 2 + Math.floor(Math.random() * 6);
                } else {
                    r.tear = 0;
                }

                var x = r.x + r.tear;
                var textColor = strobePhaseOn ? '0, 0, 0' : '240, 240, 240';

                // Ghost (double-exposure) pass, slightly offset vertically.
                if (depth > 0.1) {
                    ctx.fillStyle = 'rgba(' + textColor + ',' + (alpha * 0.35) + ')';
                    drawPhraseRow(r.y + Math.round(rowH * 0.45), r.ghostOffset);
                }

                if (r.tear !== 0) {
                    ctx.fillStyle = 'rgba(255, 26, 46,' + (alpha * 0.7) + ')';
                    drawPhraseRow(r.y, x - 3);
                }

                ctx.fillStyle = 'rgba(' + textColor + ',' + alpha + ')';
                drawPhraseRow(r.y, x);

                // Corrupted block: a few characters of the row replaced with
                // block/noise glyphs, held for a handful of frames.
                if (r.corruptFrames > 0) {
                    r.corruptFrames--;
                    ctx.fillStyle = 'rgba(0, 0, 0, 1)';
                    ctx.fillRect(r.corruptAt, r.y, r.corrupt.length * charW, rowH);
                    ctx.fillStyle = 'rgba(' + textColor + ',' + alpha + ')';
                    ctx.fillText(r.corrupt, r.corruptAt, r.y);
                } else if (depth > 0 && Math.random() < 0.008) {
                    r.corrupt = randomGlitchString(3 + Math.floor(Math.random() * 10));
                    r.corruptAt = Math.random() * W;
                    r.corruptFrames = 3 + Math.floor(Math.random() * 8);
                }
            }

            drawTower(wallTop);

            // Occasional block-slice displacement of the whole canvas: copy a
            // horizontal band and shift it. Pure displacement, no brightness
            // change, so it is part of the safe default.
            if (Math.random() < 0.05) {
                var bandY = Math.random() * H;
                var bandH = 6 + Math.random() * 40;
                var shift = (Math.random() - 0.5) * 60;
                ctx.drawImage(canvas,
                    0, bandY * dpr, canvas.width, bandH * dpr,
                    shift, bandY, W, bandH);
            }
        }

        function start() {
            if (timer) return;
            timer = window.setInterval(draw, FPS_INTERVAL);
        }

        function stop() {
            if (!timer) return;
            window.clearInterval(timer);
            timer = null;
        }

        function init() {
            resize();
            // Mobile browsers fire 'resize' every time the address bar shows or
            // hides during a scroll. resize() reallocates the canvas (wiping it),
            // which read as the whole page tearing mid-scroll (player recording
            // 2026-09-23). Only a real width change re-lays it out.
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
                if (document.hidden) stop(); else start();
            });

            scheduleStrobe();
            start();
        }

        // Canvas text doesn't wait for web fonts; measure/draw only once the
        // pixel font is ready so rows aren't laid out with fallback metrics.
        if (document.fonts && document.fonts.load) {
            document.fonts.load(fontSize + 'px VT323').then(init, init);
        } else {
            init();
        }
    });
})();

// Drifting gold dust for the imperial gold-and-black nation-page cosmetic
// (templates/country_v2.html, body.nation-imperial-theme). No-ops
// everywhere else -- the #imperial-gold-dust-canvas element only exists
// on that one gated page. Same "particles on a canvas" technique as
// static/js/cyberpunk-matrix-rain.js / static/js/forge-embers-rain.js,
// re-skinned as slow upward-drifting gold motes instead of falling code
// or molten drips.
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var canvas = document.getElementById('imperial-gold-dust-canvas');
        if (!canvas || !canvas.getContext) return;

        var reduceMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduceMotion) return;

        var ctx = canvas.getContext('2d');
        var MOTE_COUNT = 90;
        var motes = [];
        var timer = null;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            motes = new Array(MOTE_COUNT);
            for (var i = 0; i < MOTE_COUNT; i++) {
                motes[i] = spawn(Math.random() * canvas.height);
            }
        }

        function spawn(y) {
            return {
                x: Math.random() * canvas.width,
                y: y,
                r: 0.6 + Math.random() * 1.8,
                driftX: (Math.random() - 0.5) * 0.25,
                speed: 0.15 + Math.random() * 0.35,
                twinkle: Math.random() * Math.PI * 2,
                bright: Math.random() < 0.2
            };
        }

        function draw() {
            // Fading trail, same trick as the matrix rain / forge drips: a
            // low-alpha fill over the previous frame instead of a full clear.
            ctx.fillStyle = 'rgba(10, 8, 5, 0.12)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            for (var i = 0; i < motes.length; i++) {
                var m = motes[i];
                m.twinkle += 0.05;
                var alpha = m.bright ? (0.55 + 0.35 * Math.sin(m.twinkle)) : (0.25 + 0.2 * Math.sin(m.twinkle));

                ctx.beginPath();
                ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(255, 215, 0, ' + alpha.toFixed(3) + ')';
                ctx.shadowBlur = m.bright ? 8 : 3;
                ctx.shadowColor = 'rgba(255, 215, 0, 0.8)';
                ctx.fill();

                m.y -= m.speed;
                m.x += m.driftX;

                if (m.y < -5 || m.x < -5 || m.x > canvas.width + 5) {
                    motes[i] = spawn(canvas.height + 5);
                }
            }
            ctx.shadowBlur = 0;
        }

        function start() {
            if (timer) return;
            timer = window.setInterval(draw, 40);
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

        start();
    });
})();

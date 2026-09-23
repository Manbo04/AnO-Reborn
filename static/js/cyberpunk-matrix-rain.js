// Matrix-style falling code rain for the cyberpunk nation-page cosmetic
// (templates/country_v2.html, body.nation-cyberpunk-theme). No-ops
// everywhere else -- the #cyberpunk-matrix-canvas element only exists on
// that one gated page.
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var canvas = document.getElementById('cyberpunk-matrix-canvas');
        if (!canvas || !canvas.getContext) return;

        var reduceMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduceMotion) return;

        var ctx = canvas.getContext('2d');
        var CHARS = '01アカサタナハマヤラワ0123456789ABCDEF{}<>/*&$#%';
        var FONT_SIZE = 16;
        var columns = 0;
        var drops = [];
        var timer = null;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            var newColumns = Math.max(1, Math.floor(canvas.width / FONT_SIZE));
            drops = new Array(newColumns);
            for (var i = 0; i < newColumns; i++) {
                drops[i] = Math.floor(Math.random() * -50);
            }
            columns = newColumns;
        }

        function draw() {
            ctx.fillStyle = 'rgba(5, 2, 15, 0.08)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.font = FONT_SIZE + 'px monospace';

            for (var i = 0; i < columns; i++) {
                var char = CHARS[Math.floor(Math.random() * CHARS.length)];
                var x = i * FONT_SIZE;
                var y = drops[i] * FONT_SIZE;

                ctx.fillStyle = Math.random() < 0.06
                    ? 'rgba(255, 43, 214, 0.9)'
                    : 'rgba(0, 255, 242, 0.85)';
                ctx.fillText(char, x, y);

                if (y > canvas.height && Math.random() > 0.975) {
                    drops[i] = 0;
                }
                drops[i]++;
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

        start();
    });
})();

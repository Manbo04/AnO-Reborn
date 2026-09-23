// Molten-forge falling drips for the fire nation-page cosmetic
// (templates/country_v2.html, body.nation-forge-theme). No-ops
// everywhere else -- the #forge-embers-canvas element only exists on
// that one gated page. Same "columns of falling things" technique as
// static/js/cyberpunk-matrix-rain.js, re-skinned as glowing molten drips
// instead of falling code.
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var canvas = document.getElementById('forge-embers-canvas');
        if (!canvas || !canvas.getContext) return;

        var reduceMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduceMotion) return;

        var ctx = canvas.getContext('2d');
        var COLUMN_WIDTH = 22;
        var columns = 0;
        var drips = [];
        var timer = null;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            var newColumns = Math.max(1, Math.floor(canvas.width / COLUMN_WIDTH));
            drips = new Array(newColumns);
            for (var i = 0; i < newColumns; i++) {
                drips[i] = {
                    y: Math.random() * -canvas.height,
                    len: 30 + Math.random() * 70,
                    speed: 2 + Math.random() * 3,
                    hot: Math.random() < 0.25
                };
            }
            columns = newColumns;
        }

        function draw() {
            // Fading trail, same trick as the matrix rain: a low-alpha
            // fill over the previous frame instead of a full clear.
            ctx.fillStyle = 'rgba(13, 4, 2, 0.16)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            for (var i = 0; i < columns; i++) {
                var drip = drips[i];
                var x = i * COLUMN_WIDTH + COLUMN_WIDTH / 2;

                var gradient = ctx.createLinearGradient(x, drip.y - drip.len, x, drip.y);
                gradient.addColorStop(0, 'rgba(255, 140, 43, 0)');
                gradient.addColorStop(0.7, 'rgba(255, 140, 43, 0.55)');
                gradient.addColorStop(1, drip.hot ? 'rgba(255, 226, 150, 0.95)' : 'rgba(255, 176, 60, 0.9)');

                ctx.strokeStyle = gradient;
                ctx.lineWidth = drip.hot ? 3 : 2;
                ctx.shadowBlur = drip.hot ? 10 : 5;
                ctx.shadowColor = 'rgba(255, 140, 43, 0.8)';
                ctx.beginPath();
                ctx.moveTo(x, drip.y - drip.len);
                ctx.lineTo(x, drip.y);
                ctx.stroke();

                drip.y += drip.speed;
                if (drip.y - drip.len > canvas.height && Math.random() > 0.96) {
                    drip.y = Math.random() * -100;
                    drip.len = 30 + Math.random() * 70;
                    drip.speed = 2 + Math.random() * 3;
                    drip.hot = Math.random() < 0.25;
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

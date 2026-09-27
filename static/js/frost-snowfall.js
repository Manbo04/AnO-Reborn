// Falling snowflakes for the frost nation-page cosmetic
// (templates/country_v2.html, body.nation-frost-theme, ticket-0034).
// No-ops everywhere else -- the #frost-snow-canvas element only exists on
// that one gated page. The flake is Aurelia's own flag emblem (the PNG the
// player attached): a 6-point star core with 6 diamond arms between its
// points. It's rasterised once to an offscreen sprite and stamped with
// drawImage per flake, so each frame is cheap.
(function () {
    'use strict';

    // Proportions measured off the player's emblem PNG, outer radius = 1.
    var CORE_OUTER = 0.52;   // core star points (between the arms)
    var CORE_INNER = 0.36;   // core notches, where each arm meets the core
    var ARM_INNER = 0.38;    // diamond arm: tip nearest the centre
    var ARM_WIDEST = 0.62;   // distance out to the diamond's widest point
    var ARM_HALF_W = 0.17;   // half-width at that widest point
    var ARM_OUTER = 1.0;     // outer tip

    function emblemPath(r) {
        var p = new Path2D();
        var i, a;
        // Core: 6-point star, points offset 30deg from the arms.
        for (i = 0; i < 12; i++) {
            a = -Math.PI / 2 + i * Math.PI / 6;
            var rad = (i % 2 === 0 ? CORE_INNER : CORE_OUTER) * r;
            var px = Math.cos(a) * rad;
            var py = Math.sin(a) * rad;
            if (i === 0) p.moveTo(px, py); else p.lineTo(px, py);
        }
        p.closePath();
        // Arms: a diamond along each of the 6 arm directions.
        for (i = 0; i < 6; i++) {
            a = -Math.PI / 2 + i * Math.PI / 3;
            var c = Math.cos(a);
            var s = Math.sin(a);
            p.moveTo(c * ARM_INNER * r, s * ARM_INNER * r);
            p.lineTo(c * ARM_WIDEST * r - s * ARM_HALF_W * r, s * ARM_WIDEST * r + c * ARM_HALF_W * r);
            p.lineTo(c * ARM_OUTER * r, s * ARM_OUTER * r);
            p.lineTo(c * ARM_WIDEST * r + s * ARM_HALF_W * r, s * ARM_WIDEST * r - c * ARM_HALF_W * r);
            p.closePath();
        }
        return p;
    }

    function makeSprite(size, fill, glow) {
        var pad = Math.ceil(size * 0.35);
        var sprite = document.createElement('canvas');
        sprite.width = sprite.height = size + pad * 2;
        var sctx = sprite.getContext('2d');
        sctx.translate(sprite.width / 2, sprite.height / 2);
        sctx.shadowBlur = pad * 0.8;
        sctx.shadowColor = glow;
        sctx.fillStyle = fill;
        sctx.fill(emblemPath(size / 2));
        return sprite;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var canvas = document.getElementById('frost-snow-canvas');
        if (!canvas || !canvas.getContext || typeof Path2D === 'undefined') return;

        var reduceMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduceMotion) return;

        var ctx = canvas.getContext('2d');
        // Two tints: mostly white flakes, some in Aurelia's ice blue.
        var sprites = [
            makeSprite(64, 'rgba(240, 246, 255, 0.95)', 'rgba(160, 190, 255, 0.9)'),
            makeSprite(64, 'rgba(160, 182, 245, 0.95)', 'rgba(84, 112, 208, 0.9)')
        ];
        var flakes = [];
        var timer = null;
        var tick = 0;

        function newFlake(anywhere) {
            // Bigger flakes fall faster and sit "closer", so the field has depth.
            var depth = Math.random();
            return {
                x: Math.random() * canvas.width,
                y: anywhere ? Math.random() * canvas.height : -40 - Math.random() * 120,
                size: 8 + depth * 22,
                speed: 0.6 + depth * 1.8,
                sway: 0.4 + Math.random() * 1.2,
                phase: Math.random() * Math.PI * 2,
                angle: Math.random() * Math.PI * 2,
                spin: (Math.random() - 0.5) * 0.03,
                alpha: 0.35 + depth * 0.6,
                sprite: sprites[Math.random() < 0.3 ? 1 : 0]
            };
        }

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            // Density scales with screen area, capped so phones stay light.
            var count = Math.min(90, Math.round(canvas.width * canvas.height / 16000));
            flakes = [];
            for (var i = 0; i < count; i++) flakes.push(newFlake(true));
        }

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            tick++;
            for (var i = 0; i < flakes.length; i++) {
                var f = flakes[i];
                f.y += f.speed;
                f.x += Math.sin(tick * 0.02 + f.phase) * f.sway;
                f.angle += f.spin;
                if (f.y - f.size > canvas.height) {
                    flakes[i] = newFlake(false);
                    continue;
                }
                var drawSize = f.sprite.width * (f.size / 64);
                ctx.save();
                ctx.globalAlpha = f.alpha;
                ctx.translate(f.x, f.y);
                ctx.rotate(f.angle);
                ctx.drawImage(f.sprite, -drawSize / 2, -drawSize / 2, drawSize, drawSize);
                ctx.restore();
            }
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
        // Only a real width change re-lays out -- mobile address-bar
        // show/hide fires 'resize' mid-scroll (see forge-embers-rain.js).
        var lastWidth = window.innerWidth;
        window.addEventListener('resize', function () {
            if (window.innerWidth === lastWidth) return;
            lastWidth = window.innerWidth;
            resize();
        });

        // Touch devices: pause while scrolling so canvas repaints don't
        // compete with the scroll itself.
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

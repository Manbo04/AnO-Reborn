// Deep-space starfield for Kurai's nation-page cosmetic
// (templates/country_v2.html, body.nation-nebula-theme, nation 69697637).
// No-ops everywhere else -- the #nebula-starfield-canvas element only exists
// on that one gated page. The nebula glow itself is static CSS
// (cosmetics-nebula.css); this script only draws the stars:
//
// - three parallax star layers, each pre-rendered ONCE to an offscreen tile
//   and stamped with drawImage per frame (no per-star work while running),
//   drifting at different speeds and, on desktop, shifting a little with
//   page scroll for depth;
// - a rare, faint shooting star (one every ~12-30 s, under a second long).
//
// No flashing: stars do not blink, the shooting star fades in and out.
// prefers-reduced-motion: one static frame, nothing moves.
// Same perf rules as the other theme canvases (5c3abdaa): only a real width
// change re-lays out (mobile address-bar resizes keep the canvas), drawing
// pauses while a touch device is scrolling and while the tab is hidden.
(function () {
    'use strict';

    // Tinted from Kurai's flag (an orbital photo of a coastline): deep ocean
    // blue, shallow-water cyan and sand cream, plus plain starlight white.
    var STAR_TINTS = [
        [255, 255, 255],
        [214, 232, 255],
        [140, 200, 235],
        [240, 226, 192]
    ];

    // depth 0 = far (small, slow, dim) ... 2 = near (bigger, faster, brighter)
    var LAYERS = [
        { density: 1 / 2600, rMin: 0.35, rMax: 0.8, aMin: 0.25, aMax: 0.55, drift: 0.04, parallax: 0.02 },
        { density: 1 / 7000, rMin: 0.6, rMax: 1.2, aMin: 0.4, aMax: 0.75, drift: 0.09, parallax: 0.05 },
        { density: 1 / 22000, rMin: 1.0, rMax: 1.8, aMin: 0.6, aMax: 0.95, drift: 0.18, parallax: 0.1 }
    ];
    var TILE = 512;

    function makeTile(layer) {
        var tile = document.createElement('canvas');
        tile.width = tile.height = TILE;
        var t = tile.getContext('2d');
        var count = Math.max(4, Math.round(TILE * TILE * layer.density));
        for (var i = 0; i < count; i++) {
            var x = Math.random() * TILE;
            var y = Math.random() * TILE;
            var r = layer.rMin + Math.random() * (layer.rMax - layer.rMin);
            var a = layer.aMin + Math.random() * (layer.aMax - layer.aMin);
            var c = STAR_TINTS[Math.floor(Math.random() * STAR_TINTS.length)];
            if (r > 1.1) {
                // Soft halo on the nearer, bigger stars.
                var g = t.createRadialGradient(x, y, 0, x, y, r * 3.5);
                g.addColorStop(0, 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + (a * 0.45) + ')');
                g.addColorStop(1, 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',0)');
                t.fillStyle = g;
                t.beginPath();
                t.arc(x, y, r * 3.5, 0, Math.PI * 2);
                t.fill();
            }
            t.fillStyle = 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')';
            t.beginPath();
            t.arc(x, y, r, 0, Math.PI * 2);
            t.fill();
        }
        return tile;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var canvas = document.getElementById('nebula-starfield-canvas');
        if (!canvas || !canvas.getContext) return;
        var ctx = canvas.getContext('2d');

        var reduceMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var coarse = window.matchMedia &&
            window.matchMedia('(hover: none) and (pointer: coarse)').matches;

        var tiles = LAYERS.map(makeTile);
        var offsets = LAYERS.map(function () { return Math.random() * TILE; });
        var shooting = null;
        var nextShootAt = 0;
        var frame = 0;
        var timer = null;
        var FRAME_MS = 50;

        function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }

        function scheduleShootingStar() {
            // ~12-30 s apart, counted in frames.
            nextShootAt = frame + Math.round((12000 + Math.random() * 18000) / FRAME_MS);
        }

        function spawnShootingStar() {
            var w = canvas.width;
            var h = canvas.height;
            var angle = (Math.PI / 7) + Math.random() * (Math.PI / 9); // shallow, falling right
            if (Math.random() < 0.5) angle = Math.PI - angle; // or falling left
            shooting = {
                x: w * (0.15 + Math.random() * 0.7),
                y: h * (0.05 + Math.random() * 0.35),
                dx: Math.cos(angle) * 11,
                dy: Math.sin(angle) * 11,
                len: 90 + Math.random() * 70,
                life: 0,
                maxLife: 16 // frames (~0.8 s)
            };
        }

        function drawLayers() {
            var scrollY = coarse ? 0 : (window.scrollY || 0);
            for (var l = 0; l < LAYERS.length; l++) {
                var layer = LAYERS[l];
                // Slow diagonal drift + (desktop) a little scroll parallax.
                var ox = (offsets[l] + frame * layer.drift) % TILE;
                var oy = (offsets[l] * 0.7 + frame * layer.drift * 0.35 + scrollY * layer.parallax) % TILE;
                for (var x = -ox; x < canvas.width; x += TILE) {
                    for (var y = -oy; y < canvas.height; y += TILE) {
                        ctx.drawImage(tiles[l], x, y);
                    }
                }
            }
        }

        function drawShootingStar() {
            if (!shooting) {
                if (frame >= nextShootAt) {
                    spawnShootingStar();
                    scheduleShootingStar();
                }
                return;
            }
            var s = shooting;
            s.life++;
            s.x += s.dx;
            s.y += s.dy;
            // Fade in over the first third, out over the rest -- never a flash.
            var p = s.life / s.maxLife;
            var alpha = (p < 0.33 ? p / 0.33 : (1 - p) / 0.67) * 0.7;
            var n = Math.sqrt(s.dx * s.dx + s.dy * s.dy);
            var tx = s.x - (s.dx / n) * s.len;
            var ty = s.y - (s.dy / n) * s.len;
            var g = ctx.createLinearGradient(tx, ty, s.x, s.y);
            g.addColorStop(0, 'rgba(140, 200, 235, 0)');
            g.addColorStop(1, 'rgba(240, 246, 255, ' + alpha.toFixed(3) + ')');
            ctx.strokeStyle = g;
            ctx.lineWidth = 1.6;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(tx, ty);
            ctx.lineTo(s.x, s.y);
            ctx.stroke();
            if (s.life >= s.maxLife) shooting = null;
        }

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            drawLayers();
            if (!reduceMotion) drawShootingStar();
            frame++;
        }

        function start() {
            if (timer || reduceMotion) return;
            timer = window.setInterval(draw, FRAME_MS);
        }

        function stop() {
            if (!timer) return;
            window.clearInterval(timer);
            timer = null;
        }

        resize();
        scheduleShootingStar();
        draw(); // static first frame (and the only one under reduced motion)

        var lastWidth = window.innerWidth;
        window.addEventListener('resize', function () {
            if (window.innerWidth === lastWidth) return;
            lastWidth = window.innerWidth;
            resize();
            draw();
        });

        if (coarse) {
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

        if (!document.hidden) start();
    });
})();

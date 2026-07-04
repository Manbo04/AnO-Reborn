/**
 * Province zone map — organic district zones that grow with population.
 *
 * Renders a council-district style map: each district owns an organic blob of
 * grid cells around a seed point. Zone area scales with building counts and
 * population; growth is animated cell-by-cell so the player can watch their
 * city expand in real time. Growth order is deterministic per province
 * (seeded PRNG), so the map is stable across reloads and only ever extends.
 */
(function () {
    'use strict';

    var dataEl = document.getElementById('province-base-data');
    var metaEl = document.getElementById('province-base-meta');
    var canvas = document.querySelector('[data-zone-canvas]');
    var stage = document.querySelector('.province-map-stage');
    if (!dataEl || !metaEl || !canvas || !stage || !canvas.getContext) return;

    var layout, meta;
    try {
        layout = JSON.parse(dataEl.textContent);
        meta = JSON.parse(metaEl.textContent);
    } catch (e) {
        return;
    }
    var slots = (layout && layout.slots) || [];
    if (!slots.length) return;

    var reducedMotion =
        window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
        document.body.classList.contains('game-reduced-motion');

    /* ------------------------------------------------------------------ */
    /* Deterministic PRNG (mulberry32), seeded by province id              */
    function mulberry32(a) {
        return function () {
            a |= 0; a = (a + 0x6D2B79F5) | 0;
            var t = Math.imul(a ^ (a >>> 15), 1 | a);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }
    var rand = mulberry32((meta.provinceId || 1) * 2654435761);

    /* ------------------------------------------------------------------ */
    /* Grid setup                                                          */
    var GRID = 46;                       // cells per side
    var CX = (GRID - 1) / 2, CY = (GRID - 1) / 2;
    var HUB_RADIUS = 5;                  // cells kept clear around the hub
    var EDGE = 1;                        // outer margin kept clear

    // Seed angle per district mirrors the old pin layout so identities keep
    // their compass positions (power N, food NW, retail NE, ...).
    var SEED_ANGLES = {
        power: -90, food: -142, retail: -38,
        mines: 178, industry: 2, civic: 118, military: 62
    };
    var SEED_R = 14;                     // seed distance from center, in cells

    function cellId(c, r) { return r * GRID + c; }
    function inBounds(c, r) {
        if (c < EDGE || r < EDGE || c >= GRID - EDGE || r >= GRID - EDGE) return false;
        var dx = c - CX, dy = r - CY;
        return Math.sqrt(dx * dx + dy * dy) > HUB_RADIUS;
    }

    // Precompute the full deterministic claim order for every district by
    // running a weighted multi-source region growth over the whole grid.
    var owner = new Array(GRID * GRID).fill(-1);
    var orders = slots.map(function () { return []; });
    var frontiers = slots.map(function () { return []; });

    slots.forEach(function (slot, i) {
        var ang = (SEED_ANGLES[slot.id] !== undefined ? SEED_ANGLES[slot.id] : rand() * 360);
        ang = (ang + (rand() - 0.5) * 14) * Math.PI / 180;
        var sc = Math.round(CX + Math.cos(ang) * SEED_R);
        var sr = Math.round(CY + Math.sin(ang) * SEED_R);
        sc = Math.max(EDGE, Math.min(GRID - 1 - EDGE, sc));
        sr = Math.max(EDGE, Math.min(GRID - 1 - EDGE, sr));
        frontiers[i].push([sc, sr]);
    });

    var weights = slots.map(function (s) { return 1 + Math.sqrt(s.quantity || 0); });
    var totalW = weights.reduce(function (a, b) { return a + b; }, 0);
    var active = slots.map(function (_, i) { return i; });

    while (active.length) {
        // Weighted pick of which district grows next → bigger districts get
        // earlier (= always visible) cells in the canonical order.
        var roll = rand() * active.reduce(function (a, i) { return a + weights[i]; }, 0);
        var di = active[0];
        for (var k = 0; k < active.length; k++) {
            roll -= weights[active[k]];
            if (roll <= 0) { di = active[k]; break; }
        }
        var frontier = frontiers[di];
        var claimed = false;
        while (frontier.length && !claimed) {
            var idx = Math.floor(rand() * frontier.length);
            var cell = frontier.splice(idx, 1)[0];
            var c = cell[0], r = cell[1];
            if (!inBounds(c, r) || owner[cellId(c, r)] !== -1) continue;
            owner[cellId(c, r)] = di;
            orders[di].push(cellId(c, r));
            frontier.push([c + 1, r], [c - 1, r], [c, r + 1], [c, r - 1]);
            claimed = true;
        }
        if (!claimed) {
            active = active.filter(function (i) { return i !== di; });
        }
    }

    /* ------------------------------------------------------------------ */
    /* Growth targets: area follows buildings, scaled by population        */
    var POP_FULL = 25000000;             // population at which zones max out
    var usable = orders.reduce(function (a, o) { return a + o.length; }, 0);

    function computeTargets(slotData, population) {
        var budget = Math.floor(usable * 0.85 *
            Math.max(0.06, Math.min(1, population / POP_FULL)));
        var w = slotData.map(function (s) { return 1 + (s.quantity || 0); });
        var wSum = w.reduce(function (a, b) { return a + b; }, 0);
        return slotData.map(function (s, i) {
            var share = Math.round(budget * w[i] / wSum);
            var floor = (s.quantity || 0) > 0 ? 10 : 5;
            return Math.min(orders[i].length, Math.max(floor, share));
        });
    }

    var population = layout.population || 0;
    var popRate = 0;                     // people per ms, from consecutive polls
    var lastPoll = Date.now();
    var targets = computeTargets(slots, population);
    var shown = slots.map(function () { return 0; });
    var claimTimes = {};                 // cellId -> timestamp, for pop-in anim

    /* ------------------------------------------------------------------ */
    /* Canvas rendering                                                    */
    var ctx = canvas.getContext('2d');
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var cssSize = 0, cellPx = 0;

    function resize() {
        var rect = stage.getBoundingClientRect();
        if (!rect.width) return;
        cssSize = rect.width;
        canvas.width = Math.round(cssSize * dpr);
        canvas.height = Math.round(cssSize * dpr);
        cellPx = canvas.width / GRID;
        dirty = true;
    }

    function neighborsDiffer(c, r, di) {
        return (
            (owner[cellId(c + 1, r)] !== di) || (owner[cellId(c - 1, r)] !== di) ||
            (owner[cellId(c, r + 1)] !== di) || (owner[cellId(c, r - 1)] !== di)
        );
    }

    var visible = new Array(GRID * GRID).fill(-1);

    function draw(now) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        var animating = false;
        for (var di = 0; di < slots.length; di++) {
            var accent = (slots[di].theme && slots[di].theme.accent) || '#7f8fa6';
            for (var n = 0; n < shown[di]; n++) {
                var id = orders[di][n];
                var c = id % GRID, r = (id - c) / GRID;
                var scale = 1;
                var t0 = claimTimes[id];
                if (t0 && !reducedMotion) {
                    var p = (now - t0) / 260;
                    if (p < 1) { scale = 0.25 + 0.75 * p; animating = true; }
                    else delete claimTimes[id];
                }
                var pad = cellPx * (1 - scale) / 2 + cellPx * 0.06;
                ctx.globalAlpha = 0.42;
                ctx.fillStyle = accent;
                ctx.fillRect(c * cellPx + pad, r * cellPx + pad,
                    cellPx - pad * 2, cellPx - pad * 2);
                // Crisp boundary on region edges — the council-map look.
                if (visible[id] === di && neighborsDiffer(c, r, di)) {
                    ctx.globalAlpha = 0.85;
                    ctx.strokeStyle = accent;
                    ctx.lineWidth = Math.max(1, cellPx * 0.10);
                    ctx.strokeRect(c * cellPx + pad, r * cellPx + pad,
                        cellPx - pad * 2, cellPx - pad * 2);
                }
            }
        }
        ctx.globalAlpha = 1;
        return animating;
    }

    /* ------------------------------------------------------------------ */
    /* Node pins follow their zone's centroid                              */
    function repositionNodes() {
        slots.forEach(function (slot, di) {
            if (!shown[di]) return;
            var sx = 0, sy = 0;
            for (var n = 0; n < shown[di]; n++) {
                var id = orders[di][n];
                sx += id % GRID; sy += Math.floor(id / GRID);
            }
            var node = document.querySelector('.province-map-node--' + slot.id);
            if (!node) return;
            node.style.left = ((sx / shown[di] + 0.5) / GRID * 100) + '%';
            node.style.top = ((sy / shown[di] + 0.5) / GRID * 100) + '%';
        });
    }

    /* ------------------------------------------------------------------ */
    /* Growth loop                                                         */
    var dirty = true;
    var sinceReposition = 0;

    function claimNext() {
        // Claim one pending cell for the district furthest behind its target.
        var best = -1, bestGap = 0;
        for (var i = 0; i < slots.length; i++) {
            var gap = targets[i] - shown[i];
            if (gap > bestGap) { bestGap = gap; best = i; }
        }
        if (best === -1) return false;
        var id = orders[best][shown[best]];
        shown[best]++;
        visible[id] = best;
        claimTimes[id] = performance.now();
        dirty = true;
        if (++sinceReposition >= 6) { sinceReposition = 0; repositionNodes(); }
        return true;
    }

    var buildPhase = true;               // fast initial build-out
    var lastClaim = 0;

    function tick(now) {
        var interval = buildPhase ? 14 : 900;
        if (now - lastClaim >= interval) {
            lastClaim = now;
            if (!claimNext() && buildPhase) {
                buildPhase = false;
                repositionNodes();
            }
        }
        // Real-time growth at the speed of the population: extrapolate the
        // population between polls and let the budget follow it.
        if (!buildPhase && popRate > 0) {
            var estPop = population + popRate * (Date.now() - lastPoll);
            var t2 = computeTargets(slots, estPop);
            for (var i = 0; i < slots.length; i++) {
                if (t2[i] > targets[i]) targets[i] = t2[i];
            }
        }
        if (dirty) {
            dirty = draw(now) || false;
        }
        window.requestAnimationFrame(tick);
    }

    if (reducedMotion) {
        // No animation: show final state immediately.
        for (var i = 0; i < slots.length; i++) {
            shown[i] = targets[i];
            for (var n = 0; n < shown[i]; n++) visible[orders[i][n]] = i;
        }
        buildPhase = false;
        resize();
        draw(performance.now());
        repositionNodes();
        window.requestAnimationFrame(tick);
    } else {
        resize();
        repositionNodes();
        window.requestAnimationFrame(tick);
    }

    if (window.ResizeObserver) {
        new ResizeObserver(function () { resize(); }).observe(stage);
    } else {
        window.addEventListener('resize', resize);
    }

    /* ------------------------------------------------------------------ */
    /* Poll for fresh population/buildings (own province only)             */
    if (meta.own) {
        setInterval(function () {
            fetch('/api/province/' + meta.provinceId + '/layout', {
                credentials: 'same-origin'
            })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    if (!d || !d.slots) return;
                    var now = Date.now();
                    if (d.population > population && now > lastPoll) {
                        popRate = (d.population - population) / (now - lastPoll);
                    }
                    population = d.population || population;
                    lastPoll = now;
                    // Keep slot quantities fresh so new buildings widen zones.
                    d.slots.forEach(function (s) {
                        var mine = slots.filter(function (x) { return x.id === s.id; })[0];
                        if (mine) mine.quantity = s.quantity;
                    });
                    var t2 = computeTargets(slots, population);
                    for (var i = 0; i < slots.length; i++) {
                        if (t2[i] > targets[i]) targets[i] = t2[i];
                    }
                })
                .catch(function () { /* transient network errors are fine */ });
        }, 60000);
    }
})();

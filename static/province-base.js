/**
 * Interactive province command center — tap districts, quick-build, live updates.
 */
(function () {
    'use strict';

    var layoutData = null;
    var meta = null;
    var activeSlotId = null;

    function parseJson(id) {
        var el = document.getElementById(id);
        if (!el || !el.textContent) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    }

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function qsa(sel, root) {
        return Array.from((root || document).querySelectorAll(sel));
    }

    function showToast(msg, isError) {
        var t = document.getElementById('province-base-toast');
        if (!t) return;
        t.textContent = msg;
        t.style.background = isError ? 'var(--danger, #d35649)' : 'var(--success, #2d9f6f)';
        t.classList.add('is-visible');
        clearTimeout(showToast._tm);
        showToast._tm = setTimeout(function () {
            t.classList.remove('is-visible');
        }, 2200);
    }

    function playClick() {
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var o = ctx.createOscillator();
            var g = ctx.createGain();
            o.connect(g);
            g.connect(ctx.destination);
            o.frequency.value = 520;
            g.gain.setValueAtTime(0.08, ctx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
            o.start(ctx.currentTime);
            o.stop(ctx.currentTime + 0.08);
        } catch (e) { /* optional */ }
    }

    function playSuccess() {
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            [660, 880].forEach(function (freq, i) {
                var o = ctx.createOscillator();
                var g = ctx.createGain();
                o.connect(g);
                g.connect(ctx.destination);
                o.frequency.value = freq;
                var t0 = ctx.currentTime + i * 0.06;
                g.gain.setValueAtTime(0.06, t0);
                g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.12);
                o.start(t0);
                o.stop(t0 + 0.12);
            });
        } catch (e) { /* optional */ }
    }

    function closeSheet() {
        var sheet = document.getElementById('province-base-slot-sheet');
        if (sheet) {
            sheet.classList.remove('is-open');
            sheet.setAttribute('aria-hidden', 'true');
        }
        activeSlotId = null;
    }

    function renderBuildingList(buildings, costResource) {
        var list = qs('[data-building-list]');
        if (!list) return;
        list.innerHTML = '';
        if (!buildings.length) {
            list.innerHTML = '<p class="province-base-sheet-sub">No structures in this district yet. Tap + to build.</p>';
            return;
        }
        var own = meta && meta.own;
        buildings.forEach(function (b) {
            var row = document.createElement('div');
            row.className = 'province-base-building-row';
            row.setAttribute('role', 'listitem');
            row.innerHTML =
                '<div><div class="province-base-building-name">' +
                escapeHtml(b.display_name) +
                '</div><div class="province-base-building-meta">' +
                formatCost(b.base_cost, costResource) +
                '</div></div>' +
                '<span class="province-base-building-qty" data-qty>' +
                b.quantity +
                '</span>' +
                (own
                    ? '<button type="button" class="province-base-build-btn" data-build-id="' +
                      b.building_id +
                      '" aria-label="Build one">+</button>'
                    : '');

            list.appendChild(row);
        });

        if (own) {
            list.querySelectorAll('[data-build-id]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    quickBuild(parseInt(btn.getAttribute('data-build-id'), 10), btn);
                });
            });
        }
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function formatCost(n, res) {
        return '$' + Number(n).toLocaleString() + ' · ' + (res || 'gold');
    }

    function openSheet(slotId) {
        if (!meta || !meta.provinceId) return;
        activeSlotId = slotId;
        var sheet = document.getElementById('province-base-slot-sheet');
        if (!sheet) return;

        playClick();
        sheet.classList.add('is-open');
        sheet.setAttribute('aria-hidden', 'false');

        var list = qs('[data-building-list]');
        if (list) list.innerHTML = '<p class="province-base-sheet-sub">Loading…</p>';

        fetch('/api/province/' + meta.provinceId + '/slot/' + slotId, {
            credentials: 'same-origin',
        })
            .then(function (r) {
                return r.json().then(function (data) {
                    if (!r.ok) throw new Error(data.error || 'Failed to load');
                    return data;
                });
            })
            .then(function (data) {
                var iconEl = qs('[data-sheet-icon]');
                var iconWrap = qs('[data-sheet-icon-wrap]');
                var title = qs('[data-slot-title]');
                var sub = qs('[data-slot-sub]');
                if (iconEl) iconEl.textContent = data.icon || 'category';
                if (iconWrap && data.theme) {
                    iconWrap.style.background = data.theme.gradient || '';
                    iconWrap.style.boxShadow = '0 4px 16px ' + (data.theme.glow || 'rgba(0,167,225,0.3)');
                }
                if (title) title.textContent = data.label;
                if (sub) {
                    var total = (data.buildings || []).reduce(function (s, b) {
                        return s + (b.quantity || 0);
                    }, 0);
                    sub.textContent = total + ' structure' + (total === 1 ? '' : 's') + ' · tap + to expand';
                }
                renderBuildingList(data.buildings || [], data.build_cost_resource);
            })
            .catch(function (err) {
                if (list) list.innerHTML = '<p class="province-base-sheet-sub">' + escapeHtml(err.message) + '</p>';
            });
    }

    function quickBuild(buildingId, btn) {
        if (!meta || !meta.provinceId) return;
        var row = btn.closest('.province-base-building-row');
        if (row) row.classList.add('is-busy');
        btn.disabled = true;

        fetch('/api/province/' + meta.provinceId + '/quick_build', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify({ building_id: buildingId, quantity: 1 }),
        })
            .then(function (r) {
                return r.json().then(function (data) {
                    if (!r.ok || !data.ok) throw new Error(data.error || 'Build failed');
                    return data;
                });
            })
            .then(function (data) {
                playSuccess();
                showToast(data.message || 'Built!');
                if (data.layout) {
                    layoutData = data.layout;
                    refreshSlotGrid();
                    if (activeSlotId) {
                        openSheet(activeSlotId);
                    }
                }
                if (row) {
                    row.classList.remove('is-busy');
                    row.classList.add('is-success');
                    setTimeout(function () {
                        row.classList.remove('is-success');
                    }, 500);
                }
            })
            .catch(function (err) {
                showToast(err.message, true);
                if (row) row.classList.remove('is-busy');
            })
            .finally(function () {
                btn.disabled = false;
            });
    }

    function refreshSlotGrid() {
        if (!layoutData || !layoutData.slots) return;
        layoutData.slots.forEach(function (slot) {
            var card = document.querySelector('[data-slot-id="' + slot.id + '"]');
            if (!card) return;
            var qty = slot.quantity || 0;
            card.classList.toggle('has-buildings', qty > 0);
            var qtyEl = card.querySelector('.province-base-slot-qty');
            if (qtyEl) qtyEl.textContent = String(qty);
        });
        updateVitals();
    }

    function updateVitals() {
        if (!layoutData) return;
        var happy = qs('.province-vital-fill--happy');
        var poll = qs('.province-vital-fill--pollution');
        var pow = qs('.province-vital-fill--power');
        if (happy) happy.style.width = Math.min(100, layoutData.happiness || 0) + '%';
        if (poll) poll.style.width = Math.min(100, layoutData.pollution || 0) + '%';
        if (pow) pow.style.width = Math.min(100, layoutData.electricity || 0) + '%';
    }

    function initSlotGrid() {
        qsa('.province-base-slot-card').forEach(function (card) {
            card.addEventListener('click', function () {
                openSheet(card.getAttribute('data-slot-id'));
            });
        });
    }

    function initSheetControls() {
        qsa('[data-slot-sheet-close]').forEach(function (el) {
            el.addEventListener('click', closeSheet);
        });
        var classic = qs('[data-slot-classic]');
        if (classic) {
            classic.addEventListener('click', function () {
                closeSheet();
                var toggle = qs('[data-province-view-toggle]');
                if (toggle) toggle.click();
                setTimeout(function () {
                    var el = document.getElementById('province-classic-view');
                    if (el) el.scrollIntoView({ behavior: 'smooth' });
                }, 120);
            });
        }
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeSheet();
        });
    }

    function initViewToggle() {
        var toggle = qs('[data-province-view-toggle]');
        var classic = document.getElementById('province-classic-view');
        var base = document.getElementById('province-base-view');
        if (!toggle || !classic || !base) return;

        var key = 'ano_province_view';
        var mode = localStorage.getItem(key) || 'base';

        function apply(m) {
            var isBase = m === 'base';
            base.hidden = !isBase;
            classic.hidden = isBase;
            toggle.setAttribute('aria-pressed', isBase ? 'true' : 'false');
            toggle.textContent = isBase ? 'Classic view' : 'Base view';
        }

        apply(mode);
        toggle.addEventListener('click', function () {
            mode = mode === 'base' ? 'classic' : 'base';
            localStorage.setItem(key, mode);
            apply(mode);
            playClick();
        });
    }

    function init() {
        var baseView = document.getElementById('province-base-view');
        if (!baseView || baseView.hidden) return;

        layoutData = parseJson('province-base-data');
        meta = parseJson('province-base-meta');

        initSlotGrid();
        initSheetControls();
        initViewToggle();
    }

    document.addEventListener('DOMContentLoaded', init);
})();

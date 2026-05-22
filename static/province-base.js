/**
 * Province map command center — districts on a biome map, dock + sheet build UI.
 */
(function () {
    'use strict';

    var layoutData = null;
    var meta = null;
    var activeSlotId = null;
    var slotCache = {};

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

    function isMobileLayout() {
        return window.matchMedia('(max-width: 720px)').matches;
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

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function formatCost(n, res) {
        return '$' + Number(n).toLocaleString() + ' · ' + (res || 'gold');
    }

    function closeSheet() {
        var sheet = document.getElementById('province-base-slot-sheet');
        if (sheet) {
            sheet.classList.remove('is-open');
            sheet.setAttribute('aria-hidden', 'true');
        }
    }

    function setSelectedSlot(slotId) {
        qsa('.province-map-node').forEach(function (n) {
            n.classList.toggle('is-selected', n.getAttribute('data-slot-id') === slotId);
        });
    }

    function renderHubSkyline() {
        var hub = qs('[data-hub-skyline]');
        if (!hub || !layoutData) return;
        var total = Math.min(12, layoutData.total_structures || 0);
        hub.innerHTML = '';
        for (var i = 0; i < total; i++) {
            var b = document.createElement('span');
            b.className = 'province-hub-block';
            b.style.setProperty('--hub-i', String(i));
            hub.appendChild(b);
        }
        var emptyHint = qs('.province-map-hub-empty');
        if (emptyHint) emptyHint.hidden = total > 0;
        var statChip = qs('.province-stat-chip .material-icons-outlined + span');
        qsa('.province-stat-chip').forEach(function (chip) {
            if (chip.textContent.indexOf('buildings') !== -1) {
                chip.innerHTML =
                    '<span class="material-icons-outlined">domain</span> ' +
                    (layoutData.total_structures || 0) +
                    ' buildings';
            }
        });
    }

    function renderNodeFromSlot(slot) {
        var node = document.querySelector('[data-slot-id="' + slot.id + '"]');
        if (!node) return;
        var qty = slot.quantity || 0;
        node.classList.toggle('has-buildings', qty > 0);
        node.classList.toggle('is-empty', qty === 0);
        var qtyEl = node.querySelector('[data-slot-qty]');
        if (qtyEl) qtyEl.textContent = String(qty);

        var skyline = node.querySelector('.province-map-node-skyline');
        if (skyline && !isMobileLayout()) {
            skyline.innerHTML = '';
            (slot.breakdown || []).slice(0, 3).forEach(function (b) {
                var block = document.createElement('span');
                block.className = 'province-node-block';
                block.style.setProperty('--block-h', Math.min(b.quantity * 4, 28) + 'px');
                block.title = (b.display_name || b.name) + ' ×' + b.quantity;
                block.innerHTML =
                    '<span class="material-icons-outlined">' +
                    escapeHtml(b.icon || 'domain') +
                    '</span>';
                skyline.appendChild(block);
            });
            if (qty === 0) {
                var empty = document.createElement('span');
                empty.className = 'province-node-block province-node-block--empty';
                skyline.appendChild(empty);
            }
        }

        var chipsWrap = node.querySelector('.province-map-node-chips');
        var cta = node.querySelector('.province-map-node-cta');
        if (slot.breakdown && slot.breakdown.length) {
            if (!chipsWrap) {
                chipsWrap = document.createElement('div');
                chipsWrap.className = 'province-map-node-chips';
                node.appendChild(chipsWrap);
            }
            chipsWrap.hidden = false;
            chipsWrap.innerHTML = '';
            slot.breakdown.slice(0, 2).forEach(function (b) {
                var chip = document.createElement('span');
                chip.className = 'province-chip';
                chip.innerHTML =
                    '<span class="material-icons-outlined">' +
                    escapeHtml(b.icon || 'domain') +
                    '</span>' +
                    b.quantity;
                chipsWrap.appendChild(chip);
            });
            if (cta) cta.remove();
        } else {
            if (chipsWrap) chipsWrap.hidden = true;
            if (qty === 0 && !cta) {
                cta = document.createElement('span');
                cta.className = 'province-map-node-cta';
                cta.textContent = 'Build';
                node.appendChild(cta);
            }
        }
    }

    function refreshSlotGrid() {
        if (!layoutData || !layoutData.slots) return;
        layoutData.slots.forEach(renderNodeFromSlot);
        renderHubSkyline();
        updateVitals();
        if (activeSlotId) {
            var slot = layoutData.slots.find(function (s) {
                return s.id === activeSlotId;
            });
            if (slot && slotCache[activeSlotId]) {
                renderDock(slotCache[activeSlotId]);
            }
        }
    }

    function updateVitals() {
        if (!layoutData) return;
        var happy = qs('.province-vital-fill--happy');
        var poll = qs('.province-vital-fill--pollution');
        var pow = qs('.province-vital-fill--power');
        if (happy) happy.style.width = Math.min(100, layoutData.happiness || 0) + '%';
        if (poll) poll.style.width = Math.min(100, layoutData.pollution || 0) + '%';
        if (pow) pow.style.width = Math.min(100, layoutData.electricity || 0) + '%';
        qsa('.province-vital-label').forEach(function (label) {
            var icon = label.querySelector('.material-icons-outlined');
            if (!icon) return;
            var text = label.textContent.trim();
            if (text.indexOf('sentiment') !== -1 || label.innerHTML.indexOf('sentiment') !== -1) {
                label.innerHTML =
                    icon.outerHTML + ' ' + (layoutData.happiness || 0) + '%';
            } else if (label.innerHTML.indexOf('cloud') !== -1) {
                label.innerHTML = icon.outerHTML + ' ' + (layoutData.pollution || 0) + '%';
            } else if (label.innerHTML.indexOf('bolt') !== -1) {
                label.innerHTML =
                    icon.outerHTML + ' ' + (layoutData.electricity || 0) + '%';
            }
        });
    }

    function renderBuildingList(buildings, costResource, container) {
        var list = container || qs('[data-building-list]');
        if (!list) return;
        list.innerHTML = '';
        if (!buildings.length) {
            list.innerHTML =
                '<p class="province-base-sheet-sub">No structures yet — tap + to build your first.</p>';
            return;
        }
        var own = meta && meta.own;
        buildings.forEach(function (b) {
            var row = document.createElement('div');
            row.className = 'province-base-building-row';
            row.setAttribute('role', 'listitem');
            row.innerHTML =
                '<div><div class="province-base-building-name">' +
                '<span class="material-icons-outlined" style="font-size:1rem;vertical-align:middle;margin-right:4px;">' +
                escapeHtml(b.icon || 'domain') +
                '</span>' +
                escapeHtml(b.display_name || b.name) +
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
        bindBuildButtons(list);
    }

    function renderDockCards(buildings, costResource) {
        var dockList = qs('[data-dock-buildings]');
        if (!dockList) return;
        dockList.innerHTML = '';
        var own = meta && meta.own;
        var items = buildings.filter(function (b) {
            return b.quantity > 0 || own;
        });
        if (!items.length) {
            dockList.innerHTML =
                '<p class="province-base-sheet-sub">Empty district — build below.</p>';
        }
        items.slice(0, 8).forEach(function (b) {
            var card = document.createElement('div');
            card.className = 'province-dock-card';
            card.innerHTML =
                '<div class="province-dock-card-top">' +
                '<span class="province-dock-card-icon"><span class="material-icons-outlined">' +
                escapeHtml(b.icon || 'domain') +
                '</span></span>' +
                '<span class="province-dock-card-name">' +
                escapeHtml(b.display_name || b.name) +
                '</span>' +
                '<span class="province-dock-card-qty">' +
                b.quantity +
                '</span></div>' +
                '<span class="province-base-building-meta">' +
                formatCost(b.base_cost, costResource) +
                '</span>' +
                (own
                    ? '<button type="button" class="province-base-build-btn" data-build-id="' +
                      b.building_id +
                      '">+ Build</button>'
                    : '');
            dockList.appendChild(card);
        });
        bindBuildButtons(dockList);
    }

    function bindBuildButtons(root) {
        if (!meta || !meta.own) return;
        (root || document).querySelectorAll('[data-build-id]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                quickBuild(parseInt(btn.getAttribute('data-build-id'), 10), btn);
            });
        });
    }

    function renderDock(data) {
        var dock = document.getElementById('province-dock');
        if (!dock || isMobileLayout()) return;
        dock.hidden = false;
        var iconEl = qs('[data-dock-icon]');
        var iconWrap = qs('[data-dock-icon-wrap]');
        var title = qs('[data-dock-title]');
        var sub = qs('[data-dock-sub]');
        if (iconEl) iconEl.textContent = data.icon || 'category';
        if (iconWrap && data.theme) {
            iconWrap.style.background = data.theme.gradient || '';
        }
        if (title) title.textContent = data.label;
        if (sub) {
            var total = (data.buildings || []).reduce(function (s, b) {
                return s + (b.quantity || 0);
            }, 0);
            sub.textContent =
                total + ' structure' + (total === 1 ? '' : 's') + ' in this district';
        }
        renderDockCards(data.buildings || [], data.build_cost_resource);
    }

    function fetchSlotData(slotId) {
        return fetch('/api/province/' + meta.provinceId + '/slot/' + slotId, {
            credentials: 'same-origin',
        }).then(function (r) {
            return r.json().then(function (data) {
                if (!r.ok) throw new Error(data.error || 'Failed to load');
                slotCache[slotId] = data;
                return data;
            });
        });
    }

    function openSheet(slotId) {
        if (!meta || !meta.provinceId) return;
        var sheet = document.getElementById('province-base-slot-sheet');
        if (!sheet) return;
        playClick();
        sheet.classList.add('is-open');
        sheet.setAttribute('aria-hidden', 'false');
        var list = qs('[data-building-list]');
        if (list) list.innerHTML = '<p class="province-base-sheet-sub">Loading…</p>';
        fetchSlotData(slotId)
            .then(function (data) {
                var iconEl = qs('[data-sheet-icon]');
                var iconWrap = qs('[data-sheet-icon-wrap]');
                var title = qs('[data-slot-title]');
                var sub = qs('[data-slot-sub]');
                if (iconEl) iconEl.textContent = data.icon || 'category';
                if (iconWrap && data.theme) {
                    iconWrap.style.background = data.theme.gradient || '';
                    iconWrap.style.boxShadow =
                        '0 4px 16px ' + (data.theme.glow || 'rgba(0,167,225,0.3)');
                }
                if (title) title.textContent = data.label;
                if (sub) {
                    var total = (data.buildings || []).reduce(function (s, b) {
                        return s + (b.quantity || 0);
                    }, 0);
                    sub.textContent = total + ' structures · tap + to build';
                }
                renderBuildingList(data.buildings || [], data.build_cost_resource);
            })
            .catch(function (err) {
                if (list) {
                    list.innerHTML =
                        '<p class="province-base-sheet-sub">' + escapeHtml(err.message) + '</p>';
                }
            });
    }

    function selectSlot(slotId) {
        activeSlotId = slotId;
        setSelectedSlot(slotId);
        playClick();
        if (isMobileLayout()) {
            openSheet(slotId);
            return;
        }
        var dock = document.getElementById('province-dock');
        if (dock) {
            dock.hidden = false;
            qs('[data-dock-buildings]').innerHTML =
                '<p class="province-base-sheet-sub">Loading…</p>';
        }
        fetchSlotData(slotId)
            .then(renderDock)
            .catch(function (err) {
                showToast(err.message, true);
            });
    }

    function quickBuild(buildingId, btn) {
        if (!meta || !meta.provinceId) return;
        var row = btn.closest('.province-base-building-row, .province-dock-card');
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
                    delete slotCache[activeSlotId];
                    if (activeSlotId) {
                        if (isMobileLayout()) openSheet(activeSlotId);
                        else selectSlot(activeSlotId);
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

    function initSlotGrid() {
        qsa('.province-map-node').forEach(function (node) {
            node.addEventListener('click', function () {
                selectSlot(node.getAttribute('data-slot-id'));
            });
        });
        var expand = qs('[data-dock-open-sheet]');
        if (expand) {
            expand.addEventListener('click', function () {
                if (activeSlotId) openSheet(activeSlotId);
            });
        }
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
            var nudge = document.getElementById('province-view-nudge');
            if (nudge) nudge.hidden = isBase;
        }

        apply(mode);
        qsa('[data-province-view-toggle]').forEach(function (btn) {
            if (btn === toggle) return;
            btn.addEventListener('click', function () {
                mode = mode === 'base' ? 'classic' : 'base';
                localStorage.setItem(key, mode);
                apply(mode);
                playClick();
            });
        });
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

        if (layoutData && layoutData.slots && layoutData.slots.length) {
            var first = layoutData.slots.find(function (s) {
                return s.quantity > 0;
            }) || layoutData.slots[0];
            if (!isMobileLayout()) {
                setTimeout(function () {
                    selectSlot(first.id);
                }, 400);
            }
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();

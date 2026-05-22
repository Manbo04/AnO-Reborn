/**
 * Province home base view (Phaser 3) — category slots, tap for detail sheet.
 */
(function () {
    'use strict';

    var gameInstance = null;
    var layoutData = null;

    function getLayout() {
        var el = document.getElementById('province-base-data');
        if (!el || !el.textContent) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    }

    function openSlotSheet(slot) {
        var sheet = document.getElementById('province-base-slot-sheet');
        if (!sheet) return;
        var title = sheet.querySelector('[data-slot-title]');
        var body = sheet.querySelector('[data-slot-body]');
        var anchor = sheet.querySelector('[data-slot-anchor]');
        if (title) title.textContent = slot.label + ' (' + slot.quantity + ')';
        if (body) {
            body.textContent =
                slot.quantity > 0
                    ? 'Tap Classic view below to manage individual buildings in this category.'
                    : 'No structures built in this category yet. Switch to Classic view to build.';
        }
        if (anchor) {
            anchor.href = '#province-classic-view';
            anchor.onclick = function () {
                var toggle = document.querySelector('[data-province-view-toggle]');
                if (toggle) toggle.click();
                sheet.classList.remove('is-open');
                setTimeout(function () {
                    var classic = document.getElementById('province-classic-view');
                    if (classic) classic.scrollIntoView({ behavior: 'smooth' });
                }, 100);
            };
        }
        sheet.classList.add('is-open');
    }

    function closeSlotSheet() {
        var sheet = document.getElementById('province-base-slot-sheet');
        if (sheet) sheet.classList.remove('is-open');
    }

    function bootPhaser() {
        if (typeof Phaser === 'undefined') {
            console.warn('Phaser not loaded');
            return;
        }
        layoutData = getLayout();
        if (!layoutData || !layoutData.slots) return;

        var parent = 'province-base-canvas';
        var container = document.getElementById(parent);
        if (!container) return;

        if (gameInstance) {
            gameInstance.destroy(true);
            gameInstance = null;
        }

        var w = container.clientWidth || 360;
        var h = Math.round(w * 0.75);

        var BootScene = new Phaser.Class({
            Extends: Phaser.Scene,
            initialize: function BootScene() {
                Phaser.Scene.call(this, { key: 'Boot' });
            },
            preload: function () {
                var bg = layoutData.biome_background || 'images/grassland.jpg';
                this.load.image('biome_bg', '/static/' + bg.replace(/^\//, ''));
                layoutData.slots.forEach(function (slot, i) {
                    var img = slot.image || 'images/province.jpg';
                    this.load.image('slot_' + i, '/static/' + img.replace(/^\//, ''));
                }, this);
            },
            create: function () {
                var scene = this;
                var cx = w / 2;
                var cy = h / 2;

                if (scene.textures.exists('biome_bg')) {
                    var bg = scene.add.image(cx, cy, 'biome_bg');
                    var scale = Math.max(w / bg.width, h / bg.height);
                    bg.setScale(scale).setAlpha(0.35);
                }

                scene.add.rectangle(cx, cy, w - 16, h - 16, 0x1c2029, 0.55)
                    .setStrokeStyle(2, 0x00a7e1, 0.5);

                var slots = layoutData.slots;
                var radius = Math.min(w, h) * 0.32;
                var n = slots.length;

                slots.forEach(function (slot, i) {
                    var angle = (i / n) * Math.PI * 2 - Math.PI / 2;
                    var x = cx + Math.cos(angle) * radius;
                    var y = cy + Math.sin(angle) * radius;
                    var key = 'slot_' + i;
                    var size = 56;

                    var pad = scene.add.rectangle(x, y, size + 8, size + 8, 0x212630, 0.9)
                        .setStrokeStyle(2, slot.quantity > 0 ? 0x2d9f6f : 0x5c6b7f, 1)
                        .setInteractive({ useHandCursor: true });

                    if (scene.textures.exists(key)) {
                        var icon = scene.add.image(x, y, key);
                        icon.setDisplaySize(size, size);
                    } else {
                        scene.add.text(x, y, slot.label.charAt(0), {
                            fontSize: '20px',
                            color: '#ffffff',
                        }).setOrigin(0.5);
                    }

                    var qty = slot.quantity || 0;
                    if (qty > 0) {
                        scene.add.text(x + size / 2 - 4, y - size / 2 + 4, String(qty), {
                            fontSize: '12px',
                            color: '#ffffff',
                            backgroundColor: '#00a7e1',
                            padding: { x: 4, y: 2 },
                        }).setOrigin(1, 0);
                    }

                    scene.add.text(x, y + size / 2 + 10, slot.label, {
                        fontSize: '11px',
                        color: '#e6f6fc',
                    }).setOrigin(0.5, 0);

                    pad.on('pointerup', function () {
                        openSlotSheet(slot);
                    });
                });

                scene.add.text(cx, 24, layoutData.name || 'Province', {
                    fontSize: '16px',
                    color: '#ffffff',
                    fontStyle: 'bold',
                }).setOrigin(0.5);
            },
        });

        gameInstance = new Phaser.Game({
            type: Phaser.AUTO,
            parent: parent,
            width: w,
            height: h,
            backgroundColor: '#13171e',
            scene: BootScene,
            scale: {
                mode: Phaser.Scale.NONE,
            },
        });
    }

    function init() {
        var baseView = document.getElementById('province-base-view');
        if (!baseView || baseView.hidden) return;

        var closeBtn = document.querySelector('[data-slot-sheet-close]');
        if (closeBtn) closeBtn.addEventListener('click', closeSlotSheet);

        if (document.readyState === 'complete') {
            bootPhaser();
        } else {
            window.addEventListener('load', bootPhaser);
        }
    }

    window.AnoProvinceBase = {
        resize: function () {
            if (!gameInstance) {
                bootPhaser();
                return;
            }
            var container = document.getElementById('province-base-canvas');
            if (container && gameInstance.scale) {
                var w = container.clientWidth || 360;
                gameInstance.scale.resize(w, Math.round(w * 0.75));
            }
        },
        destroy: function () {
            if (gameInstance) {
                gameInstance.destroy(true);
                gameInstance = null;
            }
        },
    };

    document.addEventListener('DOMContentLoaded', init);
})();

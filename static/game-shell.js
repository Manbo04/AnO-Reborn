/**
 * Game shell: reduced-motion preference (resource HUD strip removed).
 */
(function () {
    'use strict';

    function initReducedMotion() {
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        document.body.classList.add('game-reduced-motion');
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.body.classList.contains('game-shell-active')) return;
        initReducedMotion();
    });
})();

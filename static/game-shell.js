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

/**
 * Toggle the mobile resource drawer.
 */
function toggleResourceDrawer() {
    var drawer = document.getElementById('game-resource-drawer');
    if (!drawer) return;
    drawer.classList.toggle('is-open');
    
    // Prevent body scroll when drawer is open
    if (drawer.classList.contains('is-open')) {
        document.body.style.overflow = 'hidden';
    } else {
        document.body.style.overflow = '';
    }
}

/**
 * Toggle the mobile resource drawer.
 */
function toggleResourceDrawer() {
    var drawer = document.getElementById('game-resource-drawer');
    if (!drawer) return;
    drawer.classList.toggle('is-open');
    
    // Prevent body scroll when drawer is open
    if (drawer.classList.contains('is-open')) {
        document.body.style.overflow = 'hidden';
    } else {
        document.body.style.overflow = '';
    }
}

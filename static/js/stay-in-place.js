/* Keep the player where they were after a form action.
 * Server routes redirect back to the page the form came from (helpers.redirect_back);
 * this restores the scroll position on that page so a Buy halfway down the
 * market doesn't throw you back to the top. */
(function () {
    var KEY = 'ano:stay-in-place';
    var MAX_AGE_MS = 60000;

    function here() {
        return location.pathname + location.search;
    }

    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (e.defaultPrevented || !form || (form.method || '').toLowerCase() !== 'post') return;
        try {
            sessionStorage.setItem(KEY, JSON.stringify({ p: here(), y: window.scrollY, t: Date.now() }));
        } catch (_) {}
    });

    var saved = null;
    try {
        saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
        sessionStorage.removeItem(KEY);
    } catch (_) {}
    if (!saved || saved.p !== here() || Date.now() - saved.t > MAX_AGE_MS || !saved.y) return;

    function restore() {
        // 'instant': the site sets scroll-behavior: smooth, which would
        // visibly animate down from the top on every return.
        window.scrollTo({ top: saved.y, behavior: 'instant' });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', restore);
    } else {
        restore();
    }
    // Images and lazy sections can shift the page after DOMContentLoaded.
    window.addEventListener('load', restore);
})();

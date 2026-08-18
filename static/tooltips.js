document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize generic tooltips
    if (typeof tippy !== 'undefined') {
        // Popper (bundled inside tippy) throws "Cannot read properties of
        // undefined (reading 'applyStyles')" if asked to position a tooltip
        // against a reference element that's still 0x0 at init time (e.g.
        // the resource HUD chip strip mid-layout on page load). tippy()
        // doesn't guard against this itself, so skip those and wrap each
        // call — one bad reference shouldn't kill tooltips for the rest of
        // the page.
        const isRenderable = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        };
        const safeTippy = (target, opts) => {
            try {
                tippy(target, opts);
            } catch (e) {
                console.warn('[tooltips] skipped tippy init:', e);
            }
        };

        document.querySelectorAll('[data-tippy-content]').forEach(el => {
            if (isRenderable(el)) {
                safeTippy(el, {
                    allowHTML: true,
                    interactive: true,
                    theme: 'light-border',
                    placement: 'bottom',
                    arrow: true,
                    animation: 'scale',
                    delay: [100, 50]
                });
            }
        });

        const mechanicsLink = `<br><br><a href='/mechanics' style='color: #4da8da; text-decoration: underline; font-size: 0.9em; font-weight: 500;'>📖 View Mechanics</a>`;
        const resourceDict = {};

        // 2. Build resource dictionary from HUD and convert old CSS tooltips
        document.querySelectorAll('.resourcetagparent').forEach(el => {
            const info = el.querySelector('.resourceinfo');
            const img = el.querySelector('.resourcetag');
            if (info && img) {
                const rawName = img.title || img.alt || 'Resource';
                const name = rawName.toLowerCase().trim();
                resourceDict[name] = info.innerHTML;

                if (isRenderable(el)) {
                    safeTippy(el, {
                        content: `<strong>${rawName}</strong><br>${info.innerHTML}${mechanicsLink}`,
                        allowHTML: true,
                        interactive: true,
                        theme: 'light-border',
                        placement: 'bottom',
                        arrow: true,
                        animation: 'scale',
                        appendTo: document.body,
                        delay: [100, 50]
                    });
                }
                // Disable the old CSS-based hover
                info.style.setProperty('display', 'none', 'important');
            }
        });

        // 3. Apply to all resource images across the game (e.g. in tables, military, economy pages)
        document.querySelectorAll('img.resource, img.resourcesmall').forEach(img => {
            // Skip if inside resourcetagparent (already handled)
            if (img.closest('.resourcetagparent')) return;
            if (!isRenderable(img)) return;

            let name = (img.alt || img.title || '').toLowerCase().trim();
            // Handle some mismatches (e.g. "money" vs "gold")
            if (name === 'gold') name = 'money';

            if (name && resourceDict[name]) {
                const displayName = name.charAt(0).toUpperCase() + name.slice(1);
                safeTippy(img, {
                    content: `<strong>${displayName}</strong><br>${resourceDict[name]}${mechanicsLink}`,
                    allowHTML: true,
                    interactive: true,
                    theme: 'light-border',
                    placement: 'top',
                    arrow: true,
                    animation: 'scale',
                    appendTo: document.body,
                    delay: [100, 50]
                });
                img.style.cursor = 'help';
            }
        });
    }
});

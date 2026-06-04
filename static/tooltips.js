document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize generic tooltips
    if (typeof tippy !== 'undefined') {
        tippy('[data-tippy-content]', {
            allowHTML: true,
            interactive: true,
            theme: 'light-border',
            placement: 'bottom',
            arrow: true,
            animation: 'scale',
            delay: [100, 50]
        });

        // 2. Convert old resourceinfo CSS tooltips to interactive Tippy tooltips
        document.querySelectorAll('.resourcetagparent').forEach(el => {
            const info = el.querySelector('.resourceinfo');
            if (info) {
                const resourceName = el.querySelector('.resourcetag').title || 'Resource';
                const mechanicsLink = `<br><br><a href='/mechanics' style='color: #4da8da; text-decoration: underline; font-size: 0.9em; font-weight: 500;'>📖 View Mechanics</a>`;
                
                tippy(el, {
                    content: `<strong>${info.innerHTML}</strong>${mechanicsLink}`,
                    allowHTML: true,
                    interactive: true,
                    theme: 'light-border',
                    placement: 'left',
                    arrow: true,
                    animation: 'scale',
                    appendTo: document.body,
                    delay: [100, 50]
                });
                // Disable the old CSS-based hover
                info.style.setProperty('display', 'none', 'important');
            }
        });
    }
});

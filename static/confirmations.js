/**
 * Confirmation dialogs and performance optimizations
 */

// Confirmation dialog for market transactions
function confirmMarketTransaction(event, action, resource, amount, price) {
    const totalCost = parseInt(amount.replace(/,/g, '')) * parseInt(price.replace(/,/g, ''));
    const message = `Confirm ${action}:\n\n${amount} ${resource}\nPrice: $${price} each\nTotal: $${totalCost.toLocaleString()}\n\nProceed?`;

    if (!confirm(message)) {
        event.preventDefault();
        return false;
    }
    return true;
}

// Confirmation for destructive actions
function confirmDelete(event, itemName) {
    const message = `⚠️ WARNING: This action cannot be undone!\n\nAre you sure you want to delete ${itemName}?`;

    if (!confirm(message)) {
        event.preventDefault();
        return false;
    }
    return true;
}

// Confirmation for selling buildings/units
function confirmSell(event, itemName, amount) {
    const message = `Confirm sale:\n\nSell ${amount} ${itemName}?\n\nYou will receive money for this.`;

    if (!confirm(message)) {
        event.preventDefault();
        return false;
    }
    return true;
}

// Confirmation for buying buildings/units
function confirmBuy(event, itemName, amount, cost) {
    const message = `Confirm purchase:\n\nBuy ${amount} ${itemName}?\nCost: $${cost.toLocaleString()}\n\nProceed?`;

    if (!confirm(message)) {
        event.preventDefault();
        return false;
    }
    return true;
}

// Confirmation for nation deletion
function confirmNationDelete(event) {
    const message = `⚠️⚠️⚠️ FINAL WARNING ⚠️⚠️⚠️\n\nYou are about to PERMANENTLY DELETE your nation!\n\nThis will:\n- Delete all your provinces\n- Delete all your military units\n- Delete all your resources\n- Remove you from all coalitions and wars\n- This CANNOT be undone!\n\nType "DELETE" in the next prompt to confirm.`;

    if (!confirm(message)) {
        event.preventDefault();
        return false;
    }

    const confirmation = prompt('Type "DELETE" to confirm nation deletion:');
    if (confirmation !== 'DELETE') {
        alert('Deletion cancelled. You must type DELETE exactly.');
        event.preventDefault();
        return false;
    }

    return true;
}

// Confirmation for war declaration
function confirmWarDeclaration(event, targetNation) {
    const message = `⚠️ Declare War\n\nYou are about to declare war on ${targetNation}!\n\nThis will:\n- Begin military conflict\n- Allow attacks on their nation\n- They can attack you back\n- May affect diplomatic relations\n\nAre you sure?`;

    if (!confirm(message)) {
        event.preventDefault();
        return false;
    }
    return true;
}

// Debounce function for performance
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle function for performance
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Lazy load images for better performance
document.addEventListener('DOMContentLoaded', function() {
    const images = document.querySelectorAll('img[data-src]');

    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                observer.unobserve(img);
            }
        });
    });

    images.forEach(img => imageObserver.observe(img));
});

// Optimize form submissions
document.addEventListener('DOMContentLoaded', function() {
    // Prevent double-submission of forms
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton && !submitButton.disabled) {
                submitButton.disabled = true;
                submitButton.style.opacity = '0.6';
                setTimeout(() => {
                    submitButton.disabled = false;
                    submitButton.style.opacity = '1';
                }, 2000);
            }
        });
    });
});

// Format numbers with commas in inputs
function formatNumberInput(input) {
    let value = input.value.replace(/,/g, '');
    if (!isNaN(value) && value !== '') {
        input.value = parseInt(value).toLocaleString();
    }
}

// Cache frequently used data
const dataCache = new Map();
const CACHE_DURATION = 30000; // 30 seconds

function getCachedData(key, fetchFunction) {
    const cached = dataCache.get(key);
    if (cached && (Date.now() - cached.timestamp < CACHE_DURATION)) {
        return Promise.resolve(cached.data);
    }

    return fetchFunction().then(data => {
        dataCache.set(key, { data, timestamp: Date.now() });
        return data;
    });
}

// Reduce repaints and reflows
function batchDOMUpdates(updates) {
    requestAnimationFrame(() => {
        updates.forEach(update => update());
    });
}

(function () {
    'use strict';

    // Default transport fee; each input carries its own data-fee-percent
    // (lower between members of the same currency union).
    var DEFAULT_FEE_PERCENT = 5;

    function parseAmount(value) {
        if (!value && value !== 0) return 0;
        var n = parseInt(String(value).replace(/,/g, ''), 10);
        return isNaN(n) ? 0 : Math.max(0, n);
    }

    function formatMoney(n) {
        return '$' + n.toLocaleString();
    }

    function isPurchaseForm(form) {
        return !!form.querySelector('button[formaction*="buy_offer"]');
    }

    function buildTooltipContent(subtotal, fee, feePercent, isPurchase, hasAmount) {
        if (!hasAmount) {
            return 'Enter an amount (or tap Max) to see what this trade will cost.';
        }
        if (isPurchase) {
            return (
                '<strong>Transport fee</strong><br>' +
                'Buying adds a ' + feePercent + '% transport fee on top of the listed price.<br><br>' +
                'Subtotal: ' +
                formatMoney(subtotal) +
                '<br>Fee (' + feePercent + '%): ' +
                formatMoney(fee) +
                '<br><strong>Total you pay: ' +
                formatMoney(subtotal + fee) +
                '</strong>'
            );
        }
        return (
            '<strong>Sale proceeds</strong><br>' +
            'Selling takes a ' + feePercent + '% transport fee out of the proceeds.<br><br>' +
            'Price: ' +
            formatMoney(subtotal) +
            '<br>Fee (' + feePercent + '%): ' +
            formatMoney(fee) +
            '<br><strong>You receive: ' +
            formatMoney(subtotal - fee) +
            '</strong>'
        );
    }

    function bindTooltip(trigger, content) {
        if (!trigger) return;
        if (trigger._marketTippy) {
            trigger._marketTippy.setContent(content);
            return;
        }
        if (typeof tippy !== 'undefined') {
            trigger._marketTippy = tippy(trigger, {
                content: content,
                allowHTML: true,
                interactive: true,
                theme: 'light-border',
                placement: 'top',
                arrow: true,
                animation: 'scale',
                appendTo: document.body,
                delay: [100, 50],
            });
            return;
        }
        trigger.setAttribute(
            'title',
            content.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
        );
    }

    function updateOfferTotal(input) {
        var form = input.closest('.market-purchase-form');
        if (!form) return;

        var unitPrice = parseFloat(input.getAttribute('data-unit-price') || '0');
        var maxAmount = parseAmount(input.getAttribute('data-max-amount'));
        var amount = parseAmount(input.value);
        if (maxAmount > 0 && amount > maxAmount) {
            amount = maxAmount;
            input.value = String(maxAmount);
        }
        var feeAttr = parseInt(input.getAttribute('data-fee-percent'), 10);
        var feePercent = isNaN(feeAttr) ? DEFAULT_FEE_PERCENT : feeAttr;
        var subtotal = Math.round(amount * unitPrice);
        // Server rounds the fee down (app_core/market/fees.py trade_fee).
        var fee = Math.floor((subtotal * feePercent) / 100);
        var isPurchase = isPurchaseForm(form);
        var hasAmount = amount >= 1 && unitPrice > 0;
        var hint = form.querySelector('.market-offer-hint');
        if (!hint) return;

        bindTooltip(
            hint,
            buildTooltipContent(subtotal, fee, feePercent, isPurchase, hasAmount)
        );
    }

    function bindForm(form) {
        var input = form.querySelector('input[name^="amount_"]');
        if (!input || input.getAttribute('data-market-calc-bound')) return;
        input.setAttribute('data-market-calc-bound', '1');
        input.addEventListener('input', function () {
            updateOfferTotal(input);
        });
        input.addEventListener('change', function () {
            updateOfferTotal(input);
        });
        // "Max" button (ieb, 2026-09-27): data-max is computed server-side
        // (offer amount capped by the player's gold incl. fee, or by their
        // stock when selling). Dispatch input so the cost tooltip refreshes.
        var maxBtn = form.querySelector('.market-max-btn');
        if (maxBtn) {
            maxBtn.addEventListener('click', function () {
                var max = parseAmount(maxBtn.getAttribute('data-max'));
                if (max < 1) return;
                input.value = String(max);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
            });
        }
        updateOfferTotal(input);
    }

    function init() {
        document.querySelectorAll('.market-purchase-form').forEach(bindForm);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

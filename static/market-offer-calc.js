(function () {
    'use strict';

    var FEE_RATE = 0.05;

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

    function buildTooltipContent(subtotal, fee, total, isPurchase, hasAmount) {
        if (!hasAmount) {
            return 'Enter an amount to see what this trade will cost.';
        }
        if (isPurchase) {
            return (
                '<strong>Market transaction fee</strong><br>' +
                'Buying adds a 5% fee on top of the listed price (paid to the national bank).<br><br>' +
                'Subtotal: ' +
                formatMoney(subtotal) +
                '<br>Fee (5%): ' +
                formatMoney(fee) +
                '<br><strong>Total you pay: ' +
                formatMoney(total) +
                '</strong>'
            );
        }
        return (
            '<strong>Sale proceeds</strong><br>' +
            'Selling to a buy offer has no market fee.<br><br>' +
            '<strong>You receive: ' +
            formatMoney(subtotal) +
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
        var subtotal = Math.round(amount * unitPrice);
        var fee = Math.round(subtotal * FEE_RATE);
        var total = subtotal + fee;
        var isPurchase = isPurchaseForm(form);
        var hasAmount = amount >= 1 && unitPrice > 0;
        var hint = form.querySelector('.market-offer-hint');
        if (!hint) return;

        bindTooltip(
            hint,
            buildTooltipContent(subtotal, fee, total, isPurchase, hasAmount)
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

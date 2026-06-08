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
                delay: [120, 50],
            });
            return;
        }
        trigger.setAttribute('title', content.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim());
    }

    function ensureHintBtn(input) {
        var form = input.closest('form');
        if (!form) return null;
        var id = input.getAttribute('name') || input.id || 'market';
        var el = form.querySelector('[data-market-hint-for="' + id + '"]');
        if (el) return el;

        el = document.createElement('button');
        el.type = 'button';
        el.className = 'market-offer-hint';
        el.setAttribute('data-market-hint-for', id);
        el.setAttribute('aria-label', 'Transaction cost info');
        el.innerHTML =
            '<span class="material-icons-outlined" aria-hidden="true">info</span>';
        input.parentNode.insertBefore(el, input.nextSibling);
        return el;
    }

    function updateOfferTotal(input) {
        var form = input.closest('form');
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
        var isPurchase = form ? isPurchaseForm(form) : true;
        var hasAmount = amount >= 1 && unitPrice > 0;
        var hint = ensureHintBtn(input);
        if (!hint) return;

        bindTooltip(
            hint,
            buildTooltipContent(subtotal, fee, total, isPurchase, hasAmount)
        );
    }

    function bindInput(input) {
        if (!input || input.getAttribute('data-market-calc-bound')) return;
        input.setAttribute('data-market-calc-bound', '1');
        ensureHintBtn(input);
        input.addEventListener('input', function () {
            updateOfferTotal(input);
        });
        input.addEventListener('change', function () {
            updateOfferTotal(input);
        });
        updateOfferTotal(input);
    }

    document.querySelectorAll('input[name^="amount_"]').forEach(bindInput);
})();

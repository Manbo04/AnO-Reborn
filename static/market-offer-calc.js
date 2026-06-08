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

    function buildTooltipContent(subtotal, fee, total, isPurchase) {
        if (isPurchase) {
            return (
                '<strong>Market transaction fee</strong><br>' +
                'When you buy resources, the market adds a 5% fee on top of the listed price. ' +
                'This fee is paid to the national bank.<br><br>' +
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
            'When you sell to a buy offer, there is no market fee. ' +
            'The buyer pays the listed price and you receive the full amount.<br><br>' +
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
                delay: [80, 50],
            });
            return;
        }
        trigger.setAttribute('title', content.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim());
    }

    function ensureTotalEl(input) {
        var form = input.closest('form');
        if (!form) return null;
        var id = input.getAttribute('name') || input.id || 'market';
        var el = form.querySelector('[data-market-total-for="' + id + '"]');
        if (el) return el;

        el = document.createElement('span');
        el.className = 'market-offer-total';
        el.setAttribute('data-market-total-for', id);

        var flexRow = input.closest('.templatedivflex2');
        if (flexRow) {
            flexRow.parentNode.insertBefore(el, flexRow.nextSibling);
            return el;
        }

        form.appendChild(el);
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
        var el = ensureTotalEl(input);
        if (!el) return;

        if (amount < 1 || unitPrice <= 0) {
            el.innerHTML = '';
            el.classList.remove('is-visible');
            return;
        }

        var label = isPurchase
            ? 'Total: ' + formatMoney(total)
            : 'You receive: ' + formatMoney(subtotal);
        var tooltip = buildTooltipContent(subtotal, fee, total, isPurchase);

        el.innerHTML =
            '<span class="market-offer-total-label">' +
            label +
            '</span>' +
            '<button type="button" class="market-offer-total-info" aria-label="Explain this total">' +
            '<span class="material-icons-outlined" aria-hidden="true">info</span>' +
            '</button>';
        el.classList.add('is-visible');

        bindTooltip(el.querySelector('.market-offer-total-info'), tooltip);
    }

    function bindInput(input) {
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

    document.querySelectorAll('input[name^="amount_"]').forEach(bindInput);
})();

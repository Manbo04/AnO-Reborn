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
        var el = ensureTotalEl(input);
        if (!el) return;
        if (amount < 1 || unitPrice <= 0) {
            el.textContent = '';
            el.classList.remove('is-visible');
            return;
        }
        el.textContent =
            'Total: ' +
            formatMoney(total) +
            ' (incl. 5% fee: ' +
            formatMoney(fee) +
            ')';
        el.classList.add('is-visible');
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

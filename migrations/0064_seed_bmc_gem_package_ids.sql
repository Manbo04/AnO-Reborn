-- Wires up the 4 existing gem_packages rows (seeded in 0049) to the BMC
-- Extras created for them in the creator dashboard. bmc_price_cents is
-- BMC's actual whole-dollar price (its Extras price field doesn't accept
-- cents), separate from the Stripe price_cents these rows already carry.
BEGIN;

UPDATE gem_packages SET bmc_extra_id = 572730, bmc_price_cents = 300  WHERE id = 1 AND name = 'Starter Pack';
UPDATE gem_packages SET bmc_extra_id = 572731, bmc_price_cents = 500  WHERE id = 2 AND name = 'Popular Pack';
UPDATE gem_packages SET bmc_extra_id = 572732, bmc_price_cents = 1000 WHERE id = 3 AND name = 'Value Pack';
UPDATE gem_packages SET bmc_extra_id = 572733, bmc_price_cents = 2000 WHERE id = 4 AND name = 'Mega Pack';

COMMIT;

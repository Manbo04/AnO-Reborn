-- Master switch for the 11 Ledger goods and their producer buildings.
-- OFF: the goods stay invisible, unbuildable and untradable until ledger_goods is on.
INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('ledger_goods', FALSE, 100,
        'Shows the 11 Ledger goods (machinery, cement, textiles, clothing, chemicals, medicine, fertilizer, plastics, electronics, vehicles, luxury goods) and their producer buildings: build cards, market, country page. ledger_cement, ledger_wearout and ledger_goods_use only work while this is on.',
        'Turn off if a build or market page errors on one of the new goods. Buildings already built keep producing.')
ON CONFLICT (key) DO NOTHING;
UPDATE feature_flags SET description = 'Industrial buildings (not farms or fisheries) wear out and need Machinery to run at full output; without it they run at 50%. Needs ledger_goods on.', rollback_trigger = 'Turn off if production drops for nations that hold Machinery' WHERE key = 'ledger_wearout' AND description = '';
UPDATE feature_flags SET description = 'Buildings cost 1 Cement per 100k gold of price, not refunded on sell. Needs ledger_goods on.', rollback_trigger = 'Turn off if players cannot build because no Cement is on the market' WHERE key = 'ledger_cement' AND description = '';
UPDATE feature_flags SET description = 'Population uses clothing, hospitals use medicine, farms use fertilizer (+20% output), electronics/vehicles/luxury goods give up to +5 happiness. Ramps in over 14 days. Needs ledger_goods on.', rollback_trigger = 'Turn off if happiness drops sharply after enabling' WHERE key = 'ledger_goods_use' AND description = '';

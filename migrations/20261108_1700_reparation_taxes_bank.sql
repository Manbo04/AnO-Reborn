INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('reparation_taxes_bank', FALSE, 100,
        'War reparations also tax the loser''s personal coalition-bank balance of the 15 stockpile resources at the same rate (20%, Raze 5%).',
        'Turn off if a coalition bank balance goes negative, or reparation_taxes in col_bank_transactions look wrong')
ON CONFLICT (key) DO NOTHING;

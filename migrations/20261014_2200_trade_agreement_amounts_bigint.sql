-- Agreement amounts must support the same range as the bigint resource balances.
ALTER TABLE trade_agreements
    ALTER COLUMN proposer_amount TYPE bigint USING proposer_amount::bigint,
    ALTER COLUMN receiver_amount TYPE bigint USING receiver_amount::bigint;

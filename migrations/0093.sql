-- 0093.sql

CREATE TABLE IF NOT EXISTS assembly_proposals (
    id SERIAL PRIMARY KEY,
    proposer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(32) NOT NULL, -- 'sanction', 'condemn', 'lift_sanction', 'currency_cap', 'free_text'
    target_nation_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    target_currency_id INTEGER,
    currency_cap_amount BIGINT,
    text TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'open', -- 'open', 'passed', 'failed'
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    closes_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS assembly_votes (
    id SERIAL PRIMARY KEY,
    proposal_id INTEGER NOT NULL REFERENCES assembly_proposals(id) ON DELETE CASCADE,
    voter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vote VARCHAR(16) NOT NULL, -- 'for', 'against', 'abstain'
    weight FLOAT NOT NULL,
    UNIQUE (proposal_id, voter_id)
);

CREATE TABLE IF NOT EXISTS assembly_effects (
    id SERIAL PRIMARY KEY,
    proposal_id INTEGER NOT NULL REFERENCES assembly_proposals(id) ON DELETE CASCADE,
    target_nation_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    target_currency_id INTEGER,
    effect_type VARCHAR(32) NOT NULL, -- 'sanction', 'currency_cap'
    active BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMP WITHOUT TIME ZONE
);

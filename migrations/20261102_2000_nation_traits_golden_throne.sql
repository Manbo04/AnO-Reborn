-- Unique nation traits + "The Golden Throne". Additive only, safe to re-run; no backfill.
-- Config (which nation holds which trait) lives in app_core/traits/config.py and is synced
-- into nation_traits at runtime, so this file contains no player data.

CREATE TABLE IF NOT EXISTS nation_traits (
    user_id    INTEGER NOT NULL,
    trait_key  TEXT NOT NULL,
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    state      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, trait_key)
);

CREATE TABLE IF NOT EXISTS throne_state (
    user_id        INTEGER PRIMARY KEY,
    vitality       NUMERIC(5,2) NOT NULL DEFAULT 60,
    vigil_start    DATE NOT NULL,
    last_dawn      DATE,
    souls_total    BIGINT NOT NULL DEFAULT 0,
    crisis         BOOLEAN NOT NULL DEFAULT FALSE,
    active_event   TEXT,
    event_ends_at  TIMESTAMPTZ,
    last_event_day DATE,
    surge_dawn     DATE
);

-- One row per dawn (the sacrifice). `day` is the Europe/Vilnius calendar date of that dawn.
CREATE TABLE IF NOT EXISTS throne_days (
    day            DATE PRIMARY KEY,
    souls_own      INTEGER NOT NULL DEFAULT 0,
    souls_pilgrim  INTEGER NOT NULL DEFAULT 0,
    pilgrims       INTEGER NOT NULL DEFAULT 0,
    vitality_after NUMERIC(5,2) NOT NULL,
    event          TEXT,
    skipped        BOOLEAN NOT NULL DEFAULT FALSE
);

-- `for_dawn` = the dawn this pilgrimage is offered at. UNIQUE (for_dawn, pilgrim_user_id) is the
-- once-per-window limit AND the double-spend guard (taken in the same transaction as the cost).
CREATE TABLE IF NOT EXISTS throne_pilgrimages (
    id              BIGSERIAL PRIMARY KEY,
    for_dawn        DATE NOT NULL,
    pilgrim_user_id INTEGER NOT NULL,
    weight          INTEGER NOT NULL DEFAULT 1,
    cost_kind       TEXT NOT NULL,
    people          INTEGER NOT NULL DEFAULT 0,  -- population actually given by the pilgrim nation
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (for_dawn, pilgrim_user_id)
);
CREATE INDEX IF NOT EXISTS idx_throne_pilgrimages_dawn ON throne_pilgrimages (for_dawn);

-- One row per blessed nation: refreshed on every pilgrimage, never stacked.
CREATE TABLE IF NOT EXISTS throne_blessings (
    user_id    INTEGER PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    pct        NUMERIC(5,2) NOT NULL
);

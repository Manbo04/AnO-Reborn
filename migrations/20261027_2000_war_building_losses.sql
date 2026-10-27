-- Log of buildings destroyed in wars, shown on the public war history page.
CREATE TABLE IF NOT EXISTS war_building_losses (
    id          BIGSERIAL PRIMARY KEY,
    war_id      INTEGER NOT NULL,
    victim_id   INTEGER NOT NULL,
    building    TEXT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    source      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_war_building_losses_war ON war_building_losses (war_id, created_at DESC);

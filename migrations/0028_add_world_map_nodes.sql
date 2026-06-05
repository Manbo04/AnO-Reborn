-- Migration: Add World Map Node System

-- 1. Represents the control points on the world map
CREATE TABLE IF NOT EXISTS nodes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'resource', 'strategic', 'fortress'
    coordinate_x INTEGER NOT NULL,
    coordinate_y INTEGER NOT NULL,
    controlling_coalition_id INTEGER REFERENCES colNames(id) ON DELETE SET NULL,
    health INTEGER DEFAULT 1000, -- Used for tracking damage during sieges
    shield_expires_at TIMESTAMP WITH TIME ZONE, -- When the protection shield ends
    last_resupplied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- For Garrison Decay
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tracks the resources or benefits produced by nodes
CREATE TABLE IF NOT EXISTS node_yields (
    id SERIAL PRIMARY KEY,
    node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    resource_type VARCHAR(50) NOT NULL, -- 'gold', 'iron', 'mana', etc.
    amount_per_hour INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tracks ongoing and historical skirmishes over a node
CREATE TABLE IF NOT EXISTS node_battles (
    id SERIAL PRIMARY KEY,
    node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    attacking_coalition_id INTEGER REFERENCES colNames(id) ON DELETE CASCADE,
    defending_coalition_id INTEGER REFERENCES colNames(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'ongoing', -- 'ongoing', 'resolved_attacker_won', 'resolved_defender_won'
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolves_at TIMESTAMP WITH TIME ZONE NOT NULL, -- The time when the battle automatically resolves (Siege Timer)
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Add some indexes for performance on hot queries
CREATE INDEX IF NOT EXISTS idx_nodes_controlling_coalition ON nodes(controlling_coalition_id);
CREATE INDEX IF NOT EXISTS idx_node_battles_status ON node_battles(status, resolves_at);
CREATE INDEX IF NOT EXISTS idx_node_battles_node_id ON node_battles(node_id);

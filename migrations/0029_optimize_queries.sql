-- Optimize hotpath queries with indexes

-- Index for statistics.py offers query
CREATE INDEX IF NOT EXISTS idx_offers_type_resource ON offers(type, resource);

-- Index for stats.gold which is heavily queried in market transactions
CREATE INDEX IF NOT EXISTS idx_stats_gold ON stats(gold);

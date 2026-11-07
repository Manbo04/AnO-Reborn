-- stats.manpower was a 32-bit integer (gold and unit quantities are bigint). Nations near
-- 2.147B manpower overflowed it on big unit sells ("integer out of range" -> 500).
-- The LEAST(2147483647, ...) clamps from #284 stay as a safety net; this removes the ceiling.
ALTER TABLE stats ALTER COLUMN manpower TYPE bigint;

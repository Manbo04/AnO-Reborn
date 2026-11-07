-- Aggregated daily activity counters (flag: activity_counters). No user ids are stored.
-- activity_daily: how many successful actions of each type happened per UTC day and cohort.
-- activity_daily_users: a 1024-byte HyperLogLog sketch per (day, cohort) estimating distinct active users.
CREATE TABLE IF NOT EXISTS activity_daily (
    day DATE NOT NULL,
    action TEXT NOT NULL,
    cohort TEXT NOT NULL,
    count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (day, action, cohort)
);
CREATE TABLE IF NOT EXISTS activity_daily_users (
    day DATE NOT NULL,
    cohort TEXT NOT NULL,
    hll BYTEA NOT NULL,
    PRIMARY KEY (day, cohort)
);

INSERT INTO feature_flags (key, enabled, rollout_percent, description, rollback_trigger)
VALUES ('activity_counters', FALSE, 100,
        'Counts successful player actions per day (no user ids) so retention and late-game activity can be measured.',
        'Turn off if request latency rises or activity_daily shows lock waits')
ON CONFLICT (key) DO NOTHING;

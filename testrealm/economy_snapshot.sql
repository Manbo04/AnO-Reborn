-- Ledger Lite Phase 0: read-only economy snapshot. Run hourly on the realm DB.
CREATE TABLE IF NOT EXISTS ledger_snapshots (
  ts timestamptz PRIMARY KEY DEFAULT now(), humans int, gold_total numeric, gold_median numeric,
  gold_p90 numeric, gold_p99 numeric, top10pct_share numeric, resources jsonb);
INSERT INTO ledger_snapshots(humans,gold_total,gold_median,gold_p90,gold_p99,top10pct_share,resources)
SELECT count(*), sum(s.gold), percentile_cont(0.5) WITHIN GROUP (ORDER BY s.gold),
  percentile_cont(0.9) WITHIN GROUP (ORDER BY s.gold), percentile_cont(0.99) WITHIN GROUP (ORDER BY s.gold),
  (SELECT sum(g) FROM (SELECT s2.gold g, ntile(10) OVER (ORDER BY s2.gold DESC) t FROM stats s2 JOIN users u2 ON u2.id=s2.id WHERE u2.auth_type<>'bot') x WHERE t=1) / NULLIF(sum(s.gold),0),
  (SELECT jsonb_object_agg(rd.name, q) FROM (SELECT resource_id, sum(quantity) q FROM user_economy WHERE user_id IN (SELECT id FROM users WHERE auth_type<>'bot') GROUP BY 1) e JOIN resource_dictionary rd USING (resource_id))
FROM stats s JOIN users u ON u.id=s.id WHERE u.auth_type<>'bot';

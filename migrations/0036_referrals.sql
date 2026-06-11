-- Referral system: invite codes, active-day tracking, milestone payouts

ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(12) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_user_id INTEGER REFERENCES users(id);

CREATE TABLE IF NOT EXISTS referral_active_days (
  referred_user_id INTEGER NOT NULL REFERENCES users(id),
  activity_date DATE NOT NULL,
  PRIMARY KEY (referred_user_id, activity_date)
);

CREATE TABLE IF NOT EXISTS referral_milestone_payouts (
  id SERIAL PRIMARY KEY,
  referrer_user_id INTEGER NOT NULL REFERENCES users(id),
  referred_user_id INTEGER NOT NULL REFERENCES users(id),
  milestone_days INTEGER NOT NULL,
  paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (referrer_user_id, referred_user_id, milestone_days)
);

CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users (referred_by_user_id);
CREATE INDEX IF NOT EXISTS idx_referral_payouts_referrer ON referral_milestone_payouts (referrer_user_id);

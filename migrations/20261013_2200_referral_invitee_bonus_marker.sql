-- Invitee referral bonus is now deferred (verified + active days) and tracked
-- with a milestone_days=0 marker row. Everyone already referred was paid at
-- signup under the old rule: mark them paid so they are never paid twice.
INSERT INTO referral_milestone_payouts (referrer_user_id, referred_user_id, milestone_days)
SELECT referred_by_user_id, id, 0
FROM users
WHERE referred_by_user_id IS NOT NULL
ON CONFLICT DO NOTHING;

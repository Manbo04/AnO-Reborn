-- Synthetic accounts for the CI test database ONLY (never loaded in production).
-- Many tests assume production's fixed accounts exist:
--   id 1  = the owner's nation (admin)
--   id 16 = "Tester of the Game", the designated test account
-- Without them, whichever test creates a user first silently becomes id 1
-- and results depend on test order.
INSERT INTO users (id, username, email, date, hash, auth_type, is_verified)
VALUES
  (1,  'Seed Owner',         'seed-owner@example.invalid',  '2020-01-01', 'x', 'normal', true),
  (16, 'Tester of the Game', 'seed-tester@example.invalid', '2020-01-01', 'x', 'normal', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO stats (id, location) VALUES (1, 'Grassland'), (16, 'Grassland')
ON CONFLICT (id) DO NOTHING;
INSERT INTO military (id) VALUES (1), (16) ON CONFLICT (id) DO NOTHING;

-- Test-created users/provinces start well clear of the fixed ids.
SELECT setval('public.users_id_seq', 1000, false);
SELECT setval('public.provinces_id_seq', 1000, false);

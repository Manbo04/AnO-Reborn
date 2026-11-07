-- Test realm scrub (docs/TEST_REALM.md). Run ONLY against the test copy, never production.
-- Columns come from a scan of db/schema.sql for emails, secrets, tokens, IPs and free-text
-- messages. tests/test_testrealm_scrub.py fails if a new sensitive-looking column appears in the
-- schema without being handled here or listed as public game content.
BEGIN;

-- Accounts: no real email, no login, no 2FA, no Discord link, no recovery key.
UPDATE users SET
    email = 'user' || id || '@test.invalid',
    hash = '!scrubbed',
    verification_token = NULL,
    token_created_at = NULL,
    verification_email_failed_at = NULL,
    discord_id = NULL,
    recovery_key = NULL,
    totp_secret_encrypted = NULL,
    totp_enabled = FALSE,
    totp_enrolled_at = NULL,
    session_epoch = COALESCE(session_epoch, 0) + 1000;

-- Private and free-text content: delete.
TRUNCATE direct_messages, coalition_messages, forum_replies, forum_threads, global_chat_messages,
         login_events, login_verifications, signup_attempts, identity_diagnostic_log,
         site_visits, totp_backup_codes, gem_purchases, bmc_gem_purchases, patreon_gem_grants;
UPDATE requests SET message = '';
UPDATE col_applications SET message = '';
UPDATE trade_agreements SET message = '';
UPDATE wars SET agressor_message = '', aggressor_message = '';
UPDATE wars_normalized SET aggressor_message = '';

-- Discord integration data (guild settings, tickets, suggestions): none of it belongs in a test copy.
DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'discord\_%' LOOP
        EXECUTE format('TRUNCATE %I', t);
    END LOOP;
END $$;

-- Free text players typed (profile descriptions, coalition text, news): strip anything shaped like
-- an email address, in every text column. Only the matching substring changes.
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN pg_tables t ON t.schemaname = 'public' AND t.tablename = c.table_name
        WHERE c.table_schema = 'public' AND c.data_type IN ('text', 'character varying')
    LOOP
        EXECUTE format(
            'UPDATE %I SET %I = regexp_replace(%I, %L, %L, %L) WHERE %I ~ %L AND %I NOT LIKE %L',
            r.table_name, r.column_name, r.column_name,
            '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[email removed]', 'g',
            r.column_name, '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
            r.column_name, '%@test.invalid'
        );
    END LOOP;
END $$;

COMMIT;

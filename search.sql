DO $$
DECLARE
    tname text;
    rec record;
BEGIN
    FOR tname IN SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' LOOP
        BEGIN
            EXECUTE 'SELECT * FROM ' || quote_ident(tname) || ' WHERE CAST(' || quote_ident(tname) || ' AS text) ILIKE ''%moham%'' OR CAST(' || quote_ident(tname) || ' AS text) ILIKE ''%20891%'' LIMIT 1' INTO rec;
            IF rec IS NOT NULL THEN
                RAISE NOTICE 'Found in %: %', tname, rec;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- ignore
        END;
    END LOOP;
END $$;

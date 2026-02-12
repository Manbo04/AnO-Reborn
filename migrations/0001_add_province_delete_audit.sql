-- Add admin_actions table (if not present) and trigger to audit deletes from provinces

CREATE TABLE IF NOT EXISTS admin_actions (
    id SERIAL PRIMARY KEY,
    actor TEXT,
    action TEXT,
    user_id INTEGER,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Trigger function to log province deletions
CREATE OR REPLACE FUNCTION audit_province_delete()
RETURNS trigger AS $$
BEGIN
  INSERT INTO admin_actions (actor, action, user_id, details)
  VALUES (
    current_setting('app.current_actor', true),
    'province_deleted',
    OLD.userId,
    jsonb_build_object('province', to_json(OLD))
  );
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Create the trigger
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_province_delete'
  ) THEN
    CREATE TRIGGER trg_audit_province_delete
      AFTER DELETE ON provinces
      FOR EACH ROW
      EXECUTE FUNCTION audit_province_delete();
  END IF;
END$$;

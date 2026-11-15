-- Nuke rework phase 2 (flag nuke_rework, OFF): auto-retaliation opt-in.
ALTER TABLE user_nuke_settings ADD COLUMN IF NOT EXISTS auto_retaliate BOOLEAN NOT NULL DEFAULT FALSE;

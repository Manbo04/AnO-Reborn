-- Tutorial per-chapter and graduation reward tracking
ALTER TABLE stats ADD COLUMN IF NOT EXISTS tutorial_chapters_claimed INTEGER[] DEFAULT '{}';
ALTER TABLE stats ADD COLUMN IF NOT EXISTS tutorial_graduated_at TIMESTAMPTZ;

-- Migration: 0077 - Add advertisements.image_data (base64 TEXT), the same
-- DB-storage fix already applied to flags (see FLAG_STORAGE_FIX.md /
-- migration adding users.flag_data, colNames.flag_data, provinces.flag_data).
-- Ad images were saved to static/uploads/ads/ on the web service's local
-- disk, which is ephemeral on Railway -- any ad approved/pending across a
-- redeploy loses its image (404), as found 2026-09-15 investigating a
-- pending ad's broken preview in /admin/ads.
ALTER TABLE advertisements ADD COLUMN IF NOT EXISTS image_data TEXT;

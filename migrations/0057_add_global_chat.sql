-- Real sitewide "Global Chat" for the homepage hub -- previously a fully
-- scripted/fake mockup section (no backend); this makes it real, reusing
-- the same message-table shape as coalition_messages/direct_messages
-- (migration 0047).

CREATE TABLE IF NOT EXISTS global_chat_messages (
    id BIGSERIAL PRIMARY KEY,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content VARCHAR(1000) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_global_chat_messages_created
    ON global_chat_messages(created_at);

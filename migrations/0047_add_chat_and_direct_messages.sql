-- In-game messaging: coalition group chat + 1:1 nation direct messages.
-- Requested in Discord #suggestions "Coalition chat": "no way to message
-- nations in game or chat with coalition members."

CREATE TABLE IF NOT EXISTS coalition_messages (
    id BIGSERIAL PRIMARY KEY,
    coalition_id INTEGER NOT NULL REFERENCES coalitions_normalized(coalition_id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content VARCHAR(1000) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_coalition_messages_coalition_created
    ON coalition_messages(coalition_id, created_at);

CREATE TABLE IF NOT EXISTS direct_messages (
    id BIGSERIAL PRIMARY KEY,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content VARCHAR(1000) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    read_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT direct_messages_no_self_message CHECK (sender_id <> recipient_id)
);

CREATE INDEX IF NOT EXISTS idx_direct_messages_sender_recipient_created
    ON direct_messages(sender_id, recipient_id, created_at);
CREATE INDEX IF NOT EXISTS idx_direct_messages_recipient_sender_created
    ON direct_messages(recipient_id, sender_id, created_at);
-- Powers "list my conversations" (most recent message per other-party).
CREATE INDEX IF NOT EXISTS idx_direct_messages_recipient_unread
    ON direct_messages(recipient_id) WHERE read_at IS NULL;

CREATE TABLE IF NOT EXISTS poll_votes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    poll_name TEXT NOT NULL,
    vote_option TEXT NOT NULL,
    PRIMARY KEY (user_id, poll_name)
);

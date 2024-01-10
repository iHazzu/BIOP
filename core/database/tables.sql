CREATE TABLE messages (
    event_slug	TEXT NOT NULL,
    channel_id	BIGINT NOT NULL,
    message_id	BIGINT NOT NULL
);

CREATE TABLE users (
    user_id	BIGINT NOT NULL PRIMARY KEY,
    username	TEXT NOT NULL,
    active	BOOLEAN DEFAULT True,
    bookies	TEXT,
    channel_id BIGINT NOT NULL,
    stake_amount JSON NOT NULL DEFAULT JSON_OBJECT()
);

CREATE TABLE orders (
    user_id	BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    bet_id TEXT NOT NULL,
    bookmaker_id SMALLINT NOT NULL,
    match_time TIMESTAMP NOT NULL,
    created TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE history(
    event_name TEXT NOT NULL,
    sport TEXT NOT NULL,
    bookmaker_id SMALLINT NOT NULL,
    found TIMESTAMP DEFAULT current_timestamp
)
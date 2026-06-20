-- SQLite schema for the data-layer cache.
-- Applied by app.data.cache.Cache on initialization.

CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value BLOB NOT NULL,            -- pickled payload
    expires_at INTEGER NOT NULL,   -- unix timestamp ms
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at);

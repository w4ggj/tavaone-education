-- TavaOne Education — class registration schema
-- Run: npx wrangler d1 execute tavaone-education --remote --file=schema.sql

CREATE TABLE IF NOT EXISTS classes (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  starts_at   TEXT NOT NULL,  -- ISO 8601
  price_cents INTEGER NOT NULL DEFAULT 0,
  capacity    INTEGER,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS registrations (
  id               TEXT PRIMARY KEY,
  class_id         TEXT NOT NULL REFERENCES classes(id),
  name             TEXT NOT NULL,
  email            TEXT NOT NULL,
  guardian_name    TEXT,
  consent          INTEGER NOT NULL DEFAULT 0,  -- 1 = consented
  paid             INTEGER NOT NULL DEFAULT 0,  -- 1 = paid or free class
  stripe_session_id TEXT,
  notes            TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reg_class ON registrations(class_id);
CREATE INDEX IF NOT EXISTS idx_reg_email ON registrations(email);

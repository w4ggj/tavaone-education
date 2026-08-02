CREATE TABLE IF NOT EXISTS rsvps (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  email      TEXT    NOT NULL,
  phone      TEXT    NOT NULL DEFAULT '',
  party      TEXT    NOT NULL DEFAULT 'Just me',
  minors     TEXT    NOT NULL DEFAULT 'No',
  created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS course_signups (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  email      TEXT    NOT NULL,
  phone      TEXT    NOT NULL DEFAULT '',
  schedule   TEXT    NOT NULL DEFAULT '',
  group_type TEXT    NOT NULL DEFAULT 'Individual',
  notes      TEXT    NOT NULL DEFAULT '',
  created_at TEXT    NOT NULL
);

-- Query all RSVPs (run via: npx wrangler d1 execute tavaone-rsvp --command "SELECT * FROM rsvps ORDER BY created_at")
-- No public read endpoint is exposed by the Worker.

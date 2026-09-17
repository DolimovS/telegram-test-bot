CREATE TABLE tests (
 code TEXT PRIMARY KEY, key TEXT NOT NULL, delayed INTEGER NOT NULL,
 deadline REAL, closed INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0, source_update TEXT UNIQUE
);
CREATE INDEX tests_deadline ON tests(closed, deadline);
CREATE TABLE attempts (
 code TEXT NOT NULL REFERENCES tests(code), uid INTEGER NOT NULL,
 answers TEXT NOT NULL, submitted REAL NOT NULL, score INTEGER NOT NULL,
 wrong TEXT NOT NULL, notified INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(code,uid)
);
CREATE INDEX attempts_user ON attempts(uid,submitted DESC);
CREATE INDEX attempts_notifications ON attempts(notified,submitted);
CREATE TABLE pending (
 token TEXT PRIMARY KEY, uid INTEGER NOT NULL, code TEXT NOT NULL,
 answers TEXT NOT NULL, created REAL NOT NULL, source_update TEXT UNIQUE
);
CREATE INDEX pending_created ON pending(created);
CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE available_codes(code TEXT PRIMARY KEY);
CREATE TABLE retired_codes(code TEXT PRIMARY KEY);
INSERT INTO available_codes(code)
 WITH RECURSIVE numbers(n) AS (SELECT 1000 UNION ALL SELECT n+1 FROM numbers WHERE n<9999)
 SELECT CAST(n AS TEXT) FROM numbers;
CREATE TABLE updates(id INTEGER PRIMARY KEY, lease REAL NOT NULL, owner TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE INDEX updates_cleanup ON updates(done,created);
CREATE TABLE outbox (
 id TEXT PRIMARY KEY, uid INTEGER NOT NULL, payload TEXT NOT NULL,
 created REAL NOT NULL, sent INTEGER NOT NULL DEFAULT 0,
 lease REAL NOT NULL DEFAULT 0, owner TEXT, retry_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX outbox_pending ON outbox(sent,retry_at,created,id);

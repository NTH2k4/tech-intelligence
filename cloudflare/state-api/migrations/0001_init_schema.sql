-- Migration number: 0001 	 2026-11-03T07:24:47.675Z

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,

    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,

    category TEXT,
    published_at TEXT,

    score REAL NOT NULL DEFAULT 0
        CHECK (score >= 0 AND score <= 100),

    status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (
            status IN (
                'discovered',
                'selected',
                'delivered',
                'failed'
            )
        ),

    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_articles_published
ON articles(published_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_status
ON articles(status);

CREATE INDEX IF NOT EXISTS idx_articles_first_seen
ON articles(first_seen_at DESC);


CREATE TABLE IF NOT EXISTS daily_runs (
    id TEXT PRIMARY KEY,

    started_at TEXT NOT NULL,
    completed_at TEXT,

    status TEXT NOT NULL
        CHECK (
            status IN (
                'running',
                'success',
                'partial',
                'failed',
                'no_news'
            )
        ),

    article_count INTEGER NOT NULL DEFAULT 0
        CHECK (article_count >= 0),

    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_runs_started
ON daily_runs(started_at DESC);

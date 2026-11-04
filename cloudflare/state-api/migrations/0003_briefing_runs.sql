-- Track daily Telegram briefing deliveries independently
-- from news collection and scoring runs.

CREATE TABLE IF NOT EXISTS briefing_runs (
    id TEXT PRIMARY KEY,

    briefing_date TEXT NOT NULL UNIQUE,

    status TEXT NOT NULL
        CHECK (
            status IN (
                'sending',
                'sent',
                'failed'
            )
        ),

    started_at TEXT NOT NULL,
    sent_at TEXT,

    article_count INTEGER NOT NULL
        CHECK (
            article_count >= 1
            AND article_count <= 30
        ),

    article_ids TEXT NOT NULL,

    content_hash TEXT,
    telegram_message_ids TEXT,

    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_briefing_runs_status
ON briefing_runs(status);

CREATE INDEX IF NOT EXISTS idx_briefing_runs_started
ON briefing_runs(started_at DESC);

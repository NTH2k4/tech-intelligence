-- Preserve original RSS summary
ALTER TABLE articles ADD COLUMN summary TEXT;

-- AI classification
ALTER TABLE articles ADD COLUMN ai_category TEXT;

-- AI scoring dimensions (0-100)
ALTER TABLE articles ADD COLUMN relevance_score INTEGER
    CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 100);

ALTER TABLE articles ADD COLUMN impact_score INTEGER
    CHECK (impact_score IS NULL OR impact_score BETWEEN 0 AND 100);

ALTER TABLE articles ADD COLUMN novelty_score INTEGER
    CHECK (novelty_score IS NULL OR novelty_score BETWEEN 0 AND 100);

ALTER TABLE articles ADD COLUMN source_authority_score INTEGER
    CHECK (
        source_authority_score IS NULL
        OR source_authority_score BETWEEN 0 AND 100
    );

-- AI-generated Vietnamese content
ALTER TABLE articles ADD COLUMN summary_vi TEXT;
ALTER TABLE articles ADD COLUMN why_it_matters TEXT;

-- AI confidence and recommendation
ALTER TABLE articles ADD COLUMN confidence TEXT
    CHECK (
        confidence IS NULL
        OR confidence IN ('low', 'medium', 'high')
    );

ALTER TABLE articles ADD COLUMN recommendation TEXT
    CHECK (
        recommendation IS NULL
        OR recommendation IN ('read', 'monitor', 'skip')
    );

-- Model traceability
ALTER TABLE articles ADD COLUMN scoring_model TEXT;
ALTER TABLE articles ADD COLUMN scored_at TEXT;

-- Indexes for future queries and reporting
CREATE INDEX IF NOT EXISTS idx_articles_recommendation_score
    ON articles(recommendation, score DESC);

CREATE INDEX IF NOT EXISTS idx_articles_scored_at
    ON articles(scored_at DESC);

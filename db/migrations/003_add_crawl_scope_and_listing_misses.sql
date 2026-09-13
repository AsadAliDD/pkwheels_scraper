BEGIN;

ALTER TABLE scrape_runs
    ADD COLUMN is_full_crawl BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN requested_pages INTEGER,
    ADD COLUMN pages_scraped INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN requests_failed INTEGER NOT NULL DEFAULT 0,
    ADD CONSTRAINT scrape_runs_requested_pages_positive
        CHECK (requested_pages IS NULL OR requested_pages > 0);

ALTER TABLE listings
    ADD COLUMN consecutive_misses INTEGER NOT NULL DEFAULT 0,
    ADD CONSTRAINT listings_consecutive_misses_nonnegative
        CHECK (consecutive_misses >= 0);

COMMENT ON COLUMN listings.consecutive_misses IS
    'Consecutive successful full crawls in which this listing was not observed.';

COMMIT;

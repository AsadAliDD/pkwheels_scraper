ALTER TABLE scrape_runs
    ADD COLUMN is_full_crawl BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN requested_pages INT,
    ADD COLUMN pages_scraped INT NOT NULL DEFAULT 0,
    ADD COLUMN requests_failed INT NOT NULL DEFAULT 0,
    ADD CONSTRAINT scrape_runs_requested_pages_positive
        CHECK (requested_pages IS NULL OR requested_pages > 0);

ALTER TABLE listings
    ADD COLUMN consecutive_misses INT NOT NULL DEFAULT 0 COMMENT
        'Consecutive successful full crawls in which this listing was not observed.',
    ADD CONSTRAINT listings_consecutive_misses_nonnegative
        CHECK (consecutive_misses >= 0);

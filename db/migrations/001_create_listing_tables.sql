PRAGMA foreign_keys = ON;

CREATE TABLE scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spider_name TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    items_seen INTEGER NOT NULL DEFAULT 0,
    items_inserted INTEGER NOT NULL DEFAULT 0,
    items_changed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    is_full_crawl INTEGER NOT NULL DEFAULT 0 CHECK (is_full_crawl IN (0, 1)),
    requested_pages INTEGER CHECK (requested_pages IS NULL OR requested_pages > 0),
    pages_scraped INTEGER NOT NULL DEFAULT 0,
    requests_failed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT 'pakwheels',
    source_listing_id TEXT NOT NULL CHECK (trim(source_listing_id) <> ''),
    url TEXT NOT NULL CHECK (trim(url) <> ''),
    name TEXT, price_pkr INTEGER, make TEXT, model TEXT, model_year INTEGER,
    location TEXT, mileage_km INTEGER, registered_city TEXT, engine_type TEXT,
    engine_capacity_cc INTEGER, transmission TEXT, color TEXT, assembly TEXT,
    body_type TEXT, features TEXT NOT NULL, source_updated_at TEXT,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
    last_seen_run_id INTEGER REFERENCES scrape_runs(id),
    content_hash TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
    inactive_at TEXT, consecutive_misses INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_misses >= 0),
    UNIQUE (source, source_listing_id)
);

CREATE INDEX listings_price_pkr_idx ON listings(price_pkr);
CREATE INDEX listings_make_model_model_year_idx ON listings(make, model, model_year);
CREATE INDEX listings_last_seen_at_idx ON listings(last_seen_at);
CREATE INDEX listings_active_idx ON listings(source, is_active, last_seen_at DESC);

CREATE TABLE listing_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    scrape_run_id INTEGER NOT NULL REFERENCES scrape_runs(id),
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    url TEXT NOT NULL, name TEXT, price_pkr INTEGER, make TEXT, model TEXT,
    model_year INTEGER, location TEXT, mileage_km INTEGER, registered_city TEXT,
    engine_type TEXT, engine_capacity_cc INTEGER, transmission TEXT, color TEXT,
    assembly TEXT, body_type TEXT, features TEXT NOT NULL, source_updated_at TEXT,
    content_hash TEXT NOT NULL, changed_fields TEXT NOT NULL,
    UNIQUE (listing_id, content_hash)
);

CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    scrape_run_id INTEGER NOT NULL REFERENCES scrape_runs(id),
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    old_price_pkr INTEGER, new_price_pkr INTEGER,
    CHECK (old_price_pkr IS NULL OR old_price_pkr IS NOT new_price_pkr)
);

CREATE INDEX price_history_listing_id_observed_at_idx
    ON price_history(listing_id, observed_at DESC);

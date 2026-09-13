BEGIN;

CREATE TABLE scrape_runs (
    id BIGSERIAL PRIMARY KEY,
    spider_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    items_seen INTEGER NOT NULL DEFAULT 0,
    items_inserted INTEGER NOT NULL DEFAULT 0,
    items_changed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE listings (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'pakwheels',
    source_listing_id TEXT NOT NULL,
    url TEXT NOT NULL,
    name TEXT,
    price_pkr BIGINT,
    make TEXT,
    model TEXT,
    model_year SMALLINT,
    location TEXT,
    mileage_km INTEGER,
    registered_city TEXT,
    engine_type TEXT,
    engine_capacity_cc INTEGER,
    transmission TEXT,
    color TEXT,
    assembly TEXT,
    body_type TEXT,
    features JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_updated_at DATE,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_run_id BIGINT REFERENCES scrape_runs(id),
    content_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    inactive_at TIMESTAMPTZ,
    CONSTRAINT listings_source_listing_id_not_blank
        CHECK (btrim(source_listing_id) <> ''),
    CONSTRAINT listings_url_not_blank CHECK (btrim(url) <> ''),
    CONSTRAINT listings_source_source_listing_id_key
        UNIQUE (source, source_listing_id)
);

CREATE INDEX listings_price_pkr_idx ON listings (price_pkr);
CREATE INDEX listings_make_model_model_year_idx
    ON listings (make, model, model_year);
CREATE INDEX listings_last_seen_at_idx ON listings (last_seen_at);
CREATE INDEX listings_active_idx
    ON listings (source, last_seen_at DESC)
    WHERE is_active = true;

CREATE TABLE listing_versions (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    scrape_run_id BIGINT NOT NULL REFERENCES scrape_runs(id),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    url TEXT NOT NULL,
    name TEXT,
    price_pkr BIGINT,
    make TEXT,
    model TEXT,
    model_year SMALLINT,
    location TEXT,
    mileage_km INTEGER,
    registered_city TEXT,
    engine_type TEXT,
    engine_capacity_cc INTEGER,
    transmission TEXT,
    color TEXT,
    assembly TEXT,
    body_type TEXT,
    features JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_updated_at DATE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    inactive_at TIMESTAMPTZ,
    content_hash TEXT NOT NULL,
    changed_fields JSONB NOT NULL,
    CONSTRAINT listing_versions_listing_id_content_hash_key
        UNIQUE (listing_id, content_hash)
);

CREATE TABLE price_history (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    scrape_run_id BIGINT NOT NULL REFERENCES scrape_runs(id),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    old_price_pkr BIGINT,
    new_price_pkr BIGINT,
    CONSTRAINT price_history_price_changed
        CHECK (old_price_pkr IS DISTINCT FROM new_price_pkr)
);

CREATE INDEX price_history_listing_id_observed_at_idx
    ON price_history (listing_id, observed_at DESC);

COMMENT ON COLUMN listings.source_listing_id IS
    'Authoritative per-source duplicate key. Ingestion must use the Ad Ref number, or a canonicalized URL-derived identifier only when the Ad Ref is absent; items with neither must be rejected.';

COMMENT ON TABLE listing_versions IS
    'Content snapshots for meaningful field changes. Do not insert a snapshot when only listings.last_seen_at or last_seen_run_id changes.';

COMMENT ON TABLE price_history IS
    'Compact history of price changes; listing_versions remains the general field history.';

COMMIT;

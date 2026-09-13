BEGIN;

-- A first observation can legitimately report an unavailable price.  Later
-- identical observations do not create history rows, so this exception does
-- not weaken change detection.
ALTER TABLE price_history DROP CONSTRAINT price_history_price_changed;
ALTER TABLE price_history ADD CONSTRAINT price_history_price_changed
    CHECK (old_price_pkr IS NULL OR old_price_pkr IS DISTINCT FROM new_price_pkr);

COMMIT;

-- A first observation can legitimately report an unavailable price.
ALTER TABLE price_history DROP CHECK price_history_price_changed;
ALTER TABLE price_history ADD CONSTRAINT price_history_price_changed
    CHECK (old_price_pkr IS NULL OR NOT (old_price_pkr <=> new_price_pkr));

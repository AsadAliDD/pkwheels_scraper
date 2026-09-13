"""Transactional MySQL persistence for PakWheels listings."""

import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import parse_qsl, unquote, urlparse

import mysql.connector
from itemadapter import ItemAdapter
from mysql.connector import errors as mysql_errors
from scrapy.exceptions import NotConfigured


FIELDS = (
    'name', 'price_pkr', 'make', 'model', 'model_year', 'location',
    'mileage_km', 'registered_city', 'engine_type', 'engine_capacity_cc',
    'transmission', 'color', 'assembly', 'body_type', 'features',
    'source_updated_at',
)
INTEGER_FIELDS = {'price_pkr', 'model_year', 'mileage_km', 'engine_capacity_cc'}


class PakwheelsPipeline:
    """Maintain current listings and append-only versions and price history."""

    def __init__(self, database_url, connect_timeout=10, max_retries=3,
                 retry_delay=0.25, connect=mysql.connector.connect, miss_threshold=3):
        self.database_url = database_url
        self.connect_timeout = connect_timeout
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0, retry_delay)
        self.miss_threshold = max(2, miss_threshold)
        self.connect = connect
        self.connection = None
        self.run_id = None
        self.items_seen = self.items_inserted = self.items_changed = 0
        self.terminal_error = None

    @classmethod
    def from_crawler(cls, crawler):
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise NotConfigured('DATABASE_URL is required for PakwheelsPipeline')
        settings = crawler.settings
        return cls(
            database_url,
            settings.getint('DATABASE_CONNECT_TIMEOUT', 10),
            settings.getint('DATABASE_MAX_RETRIES', 3),
            settings.getfloat('DATABASE_RETRY_DELAY', 0.25),
            miss_threshold=settings.getint('LISTING_INACTIVE_MISS_THRESHOLD', 3),
        )

    def open_spider(self, spider):
        config = self._connection_config(self.database_url)
        config['connection_timeout'] = self.connect_timeout
        self.connection = self.connect(**config)
        with self.connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")
            cursor.execute(
                """INSERT INTO scrape_runs
                   (spider_name, status, is_full_crawl, requested_pages)
                   VALUES (%s, 'running', %s, %s)""",
                (spider.name, spider.is_full_crawl, spider.requested_pages),
            )
            self.run_id = cursor.lastrowid
        self.connection.commit()

    def process_item(self, item, spider):
        values = self._normalize(ItemAdapter(item).asdict())
        if not values['source_listing_id'] or not values['url']:
            raise ValueError('source_listing_id and url are required')
        self.items_seen += 1

        for attempt in range(self.max_retries):
            try:
                outcome = self._store(values)
                self.connection.commit()
                if outcome == 'inserted':
                    self.items_inserted += 1
                elif outcome == 'changed':
                    self.items_changed += 1
                return item
            except (mysql_errors.OperationalError, mysql_errors.InternalError) as error:
                self.connection.rollback()
                if not self._is_retryable(error):
                    self.terminal_error = str(error)
                    raise
                if attempt + 1 == self.max_retries:
                    self.terminal_error = str(error)
                    raise
                time.sleep(self.retry_delay * (2 ** attempt))
            except Exception as error:
                self.connection.rollback()
                self.terminal_error = str(error)
                raise

    def _store(self, values):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        content_hash = self.content_hash(values)
        columns = ', '.join(FIELDS)
        placeholders = ', '.join(['%s'] * len(FIELDS))
        field_values = self._db_field_values(values)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO listings
                    (source, source_listing_id, url, {columns}, first_seen_at,
                     last_seen_at, last_seen_run_id, content_hash, is_active)
                    VALUES ('pakwheels', %s, %s, {placeholders}, %s, %s, %s, %s, true)
                    ON DUPLICATE KEY UPDATE id=id""",
                (values['source_listing_id'], values['url'], *field_values,
                 now, now, self.run_id, content_hash),
            )
            if cursor.rowcount == 1:
                listing_id = cursor.lastrowid
                self._insert_version(cursor, listing_id, values, content_hash,
                                     ['url', *FIELDS], now)
                cursor.execute(
                    """INSERT INTO price_history
                       (listing_id, scrape_run_id, observed_at, old_price_pkr, new_price_pkr)
                       VALUES (%s, %s, %s, NULL, %s)""",
                    (listing_id, self.run_id, now, values['price_pkr']),
                )
                return 'inserted'

            cursor.execute(
                f"""SELECT id, content_hash, {columns}
                    FROM listings WHERE source = 'pakwheels'
                    AND source_listing_id = %s FOR UPDATE""",
                (values['source_listing_id'],),
            )
            row = cursor.fetchone()
            listing_id, old_hash = row[0], row[1]
            if old_hash == content_hash:
                cursor.execute(
                    """UPDATE listings SET last_seen_at=%s, last_seen_run_id=%s,
                       url=%s, is_active=true, inactive_at=NULL,
                       consecutive_misses=0 WHERE id=%s""",
                    (now, self.run_id, values['url'], listing_id),
                )
                return 'unchanged'

            old = dict(zip(FIELDS, row[2:]))
            old = self._normalize({'source_listing_id': values['source_listing_id'],
                                   'url': values['url'], **old})
            changed = [field for field in FIELDS if old[field] != values[field]]
            self._insert_version(cursor, listing_id, values, content_hash, changed, now)
            if 'price_pkr' in changed:
                cursor.execute(
                    """INSERT INTO price_history
                       (listing_id, scrape_run_id, observed_at, old_price_pkr, new_price_pkr)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (listing_id, self.run_id, now, old['price_pkr'], values['price_pkr']),
                )
            assignments = ', '.join(f'{field}=%s' for field in FIELDS)
            cursor.execute(
                f"""UPDATE listings SET url=%s, {assignments}, last_seen_at=%s,
                    last_seen_run_id=%s, content_hash=%s, is_active=true,
                    inactive_at=NULL, consecutive_misses=0 WHERE id=%s""",
                (values['url'], *field_values, now, self.run_id, content_hash,
                 listing_id),
            )
            return 'changed'

    def _insert_version(self, cursor, listing_id, values, content_hash,
                        changed_fields, observed_at):
        columns = ', '.join(FIELDS)
        placeholders = ', '.join(['%s'] * len(FIELDS))
        cursor.execute(
            f"""INSERT INTO listing_versions
                (listing_id, scrape_run_id, observed_at, url, {columns},
                 content_hash, changed_fields)
                VALUES (%s, %s, %s, %s, {placeholders}, %s, %s)
                ON DUPLICATE KEY UPDATE id=id""",
            (listing_id, self.run_id, observed_at, values['url'],
             *self._db_field_values(values), content_hash,
             json.dumps(changed_fields, ensure_ascii=False)),
        )

    @staticmethod
    def _normalize(raw):
        result = {}
        for key in ('source_listing_id', 'url', *FIELDS):
            value = raw.get(key)
            if key == 'features':
                if isinstance(value, str):
                    try:
                        decoded = json.loads(value)
                        value = decoded if isinstance(decoded, list) else value.split(',')
                    except json.JSONDecodeError:
                        value = value.split(',')
                result[key] = sorted({str(v).strip() for v in (value or [])
                                      if v is not None and str(v).strip()}, key=str.casefold)
            elif key in INTEGER_FIELDS:
                if value in (None, ''):
                    result[key] = None
                else:
                    try:
                        result[key] = int(Decimal(str(value).strip()).quantize(
                            Decimal('1'), rounding=ROUND_HALF_UP))
                    except (InvalidOperation, ValueError):
                        result[key] = None
            elif key == 'source_updated_at':
                result[key] = value.date() if isinstance(value, datetime) else value
                if result[key] and not isinstance(result[key], date):
                    try:
                        result[key] = date.fromisoformat(str(result[key]).strip())
                    except ValueError:
                        result[key] = None
            else:
                result[key] = str(value).strip() or None if value is not None else None
        return result

    @staticmethod
    def content_hash(values):
        payload = {field: (values[field].isoformat()
                           if isinstance(values[field], date) else values[field])
                   for field in FIELDS}
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _db_field_values(values):
        return tuple(json.dumps(values[field], ensure_ascii=False)
                     if field == 'features' else values[field]
                     for field in FIELDS)

    @staticmethod
    def _connection_config(database_url):
        parsed = urlparse(database_url)
        if parsed.scheme not in ('mysql', 'mysql+mysqlconnector'):
            raise ValueError('DATABASE_URL must use the mysql:// scheme')
        if not parsed.hostname or not parsed.path.strip('/'):
            raise ValueError('DATABASE_URL must include a host and database name')
        config = {
            'host': parsed.hostname,
            'port': parsed.port or 3306,
            'database': unquote(parsed.path.lstrip('/')),
            'charset': 'utf8mb4',
        }
        if parsed.username is not None:
            config['user'] = unquote(parsed.username)
        if parsed.password is not None:
            config['password'] = unquote(parsed.password)
        config.update(dict(parse_qsl(parsed.query)))
        return config

    @staticmethod
    def _is_retryable(error):
        return getattr(error, 'errno', None) in (None, 1205, 1213)

    def close_spider(self, spider):
        if self.connection is None:
            return
        reason = getattr(spider, 'crawler', None)
        reason = getattr(getattr(reason, 'stats', None), 'get_value', lambda *a: None)(
            'finish_reason')
        stats = getattr(getattr(spider, 'crawler', None), 'stats', None)
        get_stat = getattr(stats, 'get_value', lambda key, default=0: default)
        pages_scraped = get_stat('pages_scraped', 0) or 0
        requests_failed = get_stat('requests_failed', 0) or 0
        spider_exceptions = get_stat('spider_exceptions/count', 0) or 0
        failed = (bool(self.terminal_error) or reason not in (None, 'finished')
                  or bool(spider_exceptions) or requests_failed > 0)
        complete = (not failed and spider.is_full_crawl and spider.crawl_complete
                    and requests_failed == 0)
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE scrape_runs SET finished_at=now(), status=%s,
                       items_seen=%s, items_inserted=%s, items_changed=%s,
                       pages_scraped=%s, requests_failed=%s,
                       error_message=%s WHERE id=%s""",
                    ('failed' if failed else 'succeeded', self.items_seen,
                     self.items_inserted, self.items_changed, pages_scraped,
                     requests_failed,
                     self.terminal_error or (reason if reason != 'finished' else None)
                     or (f'{requests_failed} request(s) failed'
                         if requests_failed else None)
                     or (f'{spider_exceptions} spider exception(s)'
                         if spider_exceptions else None),
                     self.run_id),
                )
                if complete:
                    self._reconcile_disappearances(cursor)
            self.connection.commit()
        finally:
            self.connection.close()

    def _reconcile_disappearances(self, cursor):
        """Advance misses only after a fully successful, unbounded crawl."""
        cursor.execute(
            """UPDATE listings
               SET consecutive_misses = consecutive_misses + 1,
                   is_active = CASE
                       WHEN consecutive_misses + 1 >= %s THEN false
                       ELSE is_active END,
                   inactive_at = CASE
                       WHEN consecutive_misses + 1 >= %s
                           THEN COALESCE(inactive_at, now())
                       ELSE inactive_at END
               WHERE source = 'pakwheels'
                 AND NOT (last_seen_run_id <=> %s)""",
            (self.miss_threshold, self.miss_threshold, self.run_id),
        )

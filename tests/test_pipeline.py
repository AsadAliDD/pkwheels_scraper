from copy import deepcopy

import psycopg
import pytest

from pakwheels.pipelines import FIELDS, PakwheelsPipeline


BASE_ITEM = {
    'source_listing_id': ' 42 ', 'url': ' https://example.test/42 ',
    'name': ' Corolla ', 'price_pkr': 2_500_000, 'make': 'Toyota',
    'model': 'Corolla', 'model_year': 2020, 'location': 'Lahore',
    'mileage_km': 50_000, 'registered_city': 'Lahore',
    'engine_type': 'Petrol', 'engine_capacity_cc': 1300,
    'transmission': 'Automatic', 'color': 'White', 'assembly': 'Local',
    'body_type': 'Sedan', 'features': [' ABS ', 'Air Bags', 'ABS'],
    'source_updated_at': '2026-09-13',
}


class Connection:
    def __init__(self):
        self.commits = self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params):
        self.connection.queries.append((query, params))


class ClosingConnection(Connection):
    def __init__(self):
        super().__init__()
        self.queries = []
        self.closed = False

    def cursor(self):
        return Cursor(self)

    def close(self):
        self.closed = True


class Stats:
    def __init__(self, **values):
        self.values = values

    def get_value(self, key, default=None):
        return self.values.get(key, default)


class Spider:
    name = 'pak1'

    def __init__(self, *, full=True, complete=True, finish_reason='finished',
                 pages_scraped=4, requests_failed=0):
        self.is_full_crawl = full
        self.requested_pages = None if full else pages_scraped
        self.crawl_complete = complete
        self.crawler = type('Crawler', (), {
            'stats': Stats(finish_reason=finish_reason,
                           pages_scraped=pages_scraped,
                           requests_failed=requests_failed),
        })()


class ReconciliationPipeline(PakwheelsPipeline):
    def __init__(self, listings, threshold=3):
        super().__init__('unused', miss_threshold=threshold)
        self.connection = ClosingConnection()
        self.run_id = 10
        self.listings = listings

    def _reconcile_disappearances(self, cursor):
        for listing in self.listings:
            if listing['seen']:
                listing['misses'] = 0
                listing['active'] = True
            else:
                listing['misses'] += 1
                if listing['misses'] >= self.miss_threshold:
                    listing['active'] = False


class MemoryPipeline(PakwheelsPipeline):
    """Exercise ingestion decisions without requiring a PostgreSQL server."""

    def __init__(self):
        super().__init__('unused', max_retries=2, retry_delay=0)
        self.connection = Connection()
        self.rows = {}
        self.versions = []
        self.prices = []
        self.fail_once = False

    def _store(self, values):
        if self.fail_once:
            self.fail_once = False
            raise psycopg.OperationalError('temporary failure')
        key = values['source_listing_id']
        digest = self.content_hash(values)
        old = self.rows.get(key)
        if old is None:
            self.rows[key] = deepcopy(values)
            self.rows[key]['hash'] = digest
            self.versions.append(['url', *FIELDS])
            self.prices.append((None, values['price_pkr']))
            return 'inserted'
        if old['hash'] == digest:
            old['url'] = values['url']
            return 'unchanged'
        changed = [field for field in FIELDS if old[field] != values[field]]
        if 'price_pkr' in changed:
            self.prices.append((old['price_pkr'], values['price_pkr']))
        self.versions.append(changed)
        self.rows[key] = deepcopy(values)
        self.rows[key]['hash'] = digest
        return 'changed'


@pytest.fixture
def pipeline():
    return MemoryPipeline()


def test_duplicate_items_within_one_run(pipeline):
    pipeline.process_item(BASE_ITEM, None)
    pipeline.process_item(deepcopy(BASE_ITEM), None)
    assert (pipeline.items_inserted, pipeline.items_changed) == (1, 0)
    assert len(pipeline.versions) == len(pipeline.prices) == 1


def test_same_unchanged_item_in_successive_runs(pipeline):
    pipeline.process_item(BASE_ITEM, None)
    pipeline.run_id = 2
    pipeline.process_item(deepcopy(BASE_ITEM), None)
    assert len(pipeline.versions) == 1


def test_price_only_change(pipeline):
    pipeline.process_item(BASE_ITEM, None)
    changed = {**BASE_ITEM, 'price_pkr': 2_400_000}
    pipeline.process_item(changed, None)
    assert pipeline.versions[-1] == ['price_pkr']
    assert pipeline.prices[-1] == (2_500_000, 2_400_000)


def test_multiple_fields_change_together(pipeline):
    pipeline.process_item(BASE_ITEM, None)
    changed = {**BASE_ITEM, 'price_pkr': 2_400_000, 'color': 'Black'}
    pipeline.process_item(changed, None)
    assert pipeline.versions[-1] == ['price_pkr', 'color']


def test_missing_price_is_preserved_and_versioned(pipeline):
    item = {**BASE_ITEM, 'price_pkr': None}
    pipeline.process_item(item, None)
    assert pipeline.rows['42']['price_pkr'] is None
    assert pipeline.prices == [(None, None)]


def test_float_like_prices_have_the_same_hash():
    integer = PakwheelsPipeline._normalize(BASE_ITEM)
    float_like = PakwheelsPipeline._normalize({**BASE_ITEM, 'price_pkr': '2500000.0'})
    assert integer['price_pkr'] == float_like['price_pkr'] == 2_500_000
    assert PakwheelsPipeline.content_hash(integer) == PakwheelsPipeline.content_hash(float_like)


def test_transaction_rolls_back_then_retries_transient_error(pipeline):
    pipeline.fail_once = True
    assert pipeline.process_item(BASE_ITEM, None) is BASE_ITEM
    assert pipeline.connection.rollbacks == 1
    assert pipeline.connection.commits == 1
    assert pipeline.items_inserted == 1


@pytest.mark.parametrize('spider', [
    Spider(full=False),
    Spider(requests_failed=1),
    Spider(finish_reason='shutdown'),
])
def test_incomplete_runs_never_advance_listing_misses(spider):
    listing = {'seen': False, 'misses': 1, 'active': True}
    pipeline = ReconciliationPipeline([listing], threshold=2)
    pipeline.close_spider(spider)
    assert listing == {'seen': False, 'misses': 1, 'active': True}


def test_repeated_successful_full_crawls_deactivate_at_threshold():
    listing = {'seen': False, 'misses': 0, 'active': True}
    for run_id in (10, 11, 12):
        pipeline = ReconciliationPipeline([listing], threshold=3)
        pipeline.run_id = run_id
        pipeline.close_spider(Spider())
    assert listing == {'seen': False, 'misses': 3, 'active': False}


def test_seen_listing_resets_misses_and_reactivates():
    listing = {'seen': True, 'misses': 3, 'active': False}
    pipeline = ReconciliationPipeline([listing])
    pipeline.close_spider(Spider())
    assert listing == {'seen': True, 'misses': 0, 'active': True}

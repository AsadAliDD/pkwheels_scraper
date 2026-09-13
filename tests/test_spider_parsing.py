import pytest
from scrapy.http import HtmlResponse, Request

from pakwheels.spiders.pak1 import Pak1Spider


def test_pages_argument_defines_crawl_scope():
    full = Pak1Spider()
    limited = Pak1Spider(pages='2')
    assert (full.is_full_crawl, full.requested_pages) == (True, None)
    assert (limited.is_full_crawl, limited.requested_pages) == (False, 2)


@pytest.mark.parametrize('pages', ['0', '-1', '1.5', 'two', '', True])
def test_pages_argument_requires_a_positive_integer(pages):
    with pytest.raises(ValueError, match='pages must be a positive integer'):
        Pak1Spider(pages=pages)


def test_pages_argument_stops_result_pagination_at_requested_page():
    spider = Pak1Spider(pages='2')
    crawler = type('Crawler', (), {
        'stats': type('Stats', (), {'inc_value': lambda self, key: None})(),
    })()
    spider.crawler = crawler

    def response(page_number):
        request = Request(
            f'https://www.pakwheels.com/used-cars/search/-/?page={page_number}',
            meta={'page_number': page_number},
        )
        return HtmlResponse(
            request.url,
            request=request,
            encoding='utf-8',
            body=b'<li class="next_page"><a href="/used-cars/search/-/?page=next">Next</a></li>',
        )

    first_page_requests = list(spider.parse(response(1)))
    second_page_requests = list(spider.parse(response(2)))

    assert len(first_page_requests) == 1
    assert first_page_requests[0].meta['page_number'] == 2
    assert second_page_requests == []


def test_price_units_and_plain_pkr():
    assert Pak1Spider.parse_price('PKR 25.5', 'lacs') == 2_550_000
    assert Pak1Spider.parse_price('PKR 1.25 crore') == 12_500_000
    assert Pak1Spider.parse_price('PKR 2,550,000') == 2_550_000
    assert Pak1Spider.parse_price(None) is None


def test_last_updated_is_a_date():
    assert Pak1Spider.parse_updated_date(' Sep 13, 2026 ').isoformat() == '2026-09-13'

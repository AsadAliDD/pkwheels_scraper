from pakwheels.spiders.pak1 import Pak1Spider


def test_price_units_and_plain_pkr():
    assert Pak1Spider.parse_price('PKR 25.5', 'lacs') == 2_550_000
    assert Pak1Spider.parse_price('PKR 1.25 crore') == 12_500_000
    assert Pak1Spider.parse_price('PKR 2,550,000') == 2_550_000
    assert Pak1Spider.parse_price(None) is None


def test_last_updated_is_a_date():
    assert Pak1Spider.parse_updated_date(' Sep 13, 2026 ').isoformat() == '2026-09-13'

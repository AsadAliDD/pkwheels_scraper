# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class PakwheelsItem(scrapy.Item):
    source_listing_id = scrapy.Field()
    name = scrapy.Field()
    price_pkr = scrapy.Field()
    make = scrapy.Field()
    model = scrapy.Field()
    model_year = scrapy.Field()
    location = scrapy.Field()
    mileage_km = scrapy.Field()
    registered_city = scrapy.Field()
    engine_type = scrapy.Field()
    engine_capacity_cc = scrapy.Field()
    transmission = scrapy.Field()
    color = scrapy.Field()
    assembly = scrapy.Field()
    body_type = scrapy.Field()
    features = scrapy.Field()
    source_updated_at = scrapy.Field()
    url = scrapy.Field()

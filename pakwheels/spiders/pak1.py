import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit

import scrapy
from scrapy.exceptions import DropItem

from pakwheels.items import PakwheelsItem


class Pak1Spider(scrapy.Spider):
    name = 'pak1'
    allowed_domains = ['pakwheels.com']
    start_urls = ['https://www.pakwheels.com/used-cars/search/-/']

    def __init__(self, pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_full_crawl = pages is None
        self.requested_pages = None
        self.crawl_complete = False

        if pages is None:
            self.max_pages = None
            return

        try:
            self.max_pages = int(pages)
        except (TypeError, ValueError):
            raise ValueError('pages must be a positive integer') from None

        if self.max_pages < 1:
            raise ValueError('pages must be a positive integer')
        self.requested_pages = self.max_pages

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, errback=self.request_failed,
                                 meta={'page_number': 1})

    def request_failed(self, failure):
        """Record any failed result or detail request for run reconciliation."""
        self.crawler.stats.inc_value('requests_failed')
        self.logger.warning('Request failed: %s', failure)

    @staticmethod
    def variant_from_name(name, make, model, year):
        """Return the trim/variant portion of a listing name."""
        if not all((name, make, model, year)):
            return None

        prefix = '{} {} '.format(make.strip(), model.strip())
        year_suffix = ' {}'.format(year)
        if name.startswith(prefix) and name.endswith(year_suffix):
            return name[len(prefix):-len(year_suffix)].strip() or None

        return None

    def parse(self, response):
        self.crawler.stats.inc_value('pages_scraped')
        urls=response.xpath('//div[@class="search-title"]/a/@href').extract()
        for url in urls:
            comp_url='https://www.pakwheels.com'+url
            yield scrapy.Request(comp_url, callback=self.parse_car,
                                 errback=self.request_failed)

        # Next Page
        next_page=response.xpath('//li[@class="next_page"]/a/@href').extract_first()
        page_number = response.meta.get('page_number', 1)
        if next_page and (self.max_pages is None or page_number < self.max_pages):
            comp_url='https://www.pakwheels.com'+next_page
            yield scrapy.Request(
                comp_url,
                callback=self.parse,
                errback=self.request_failed,
                meta={'page_number': page_number + 1},
            )
        elif self.is_full_crawl and not next_page:
            # Reaching the natural end, rather than an operator-supplied page
            # limit, is required before missing listings can be reconciled.
            self.crawl_complete = True



    def parse_car(self,response):
        def text(xpath):
            value = response.xpath(xpath).extract_first()
            if value is None:
                return None
            value = value.strip()
            return value or None

        def integer(value):
            if not value:
                return None
            match = re.search(r"[\d,]+", value)
            return int(match.group().replace(',', '')) if match else None

        # Name tag of AD
        name=text('//h1/text()')
        
        url=response.request.url
        # Price
        price = self.parse_price(
            text('//div[@class="price-box"]/strong/text()'),
            text('//div[@class="price-box"]/strong/span/text()'),
        )
        
        # Model Year
        year=integer(text('//span[@class="engine-icon year"]/../p/a/text()'))

        # Make and Model
        make=text("//*[normalize-space(text())='Make']/following-sibling::li/a/text()")
        if (make is None):
            make=text("//*[normalize-space(text())='Make']/following-sibling::li/text()")

        model=text("//*[normalize-space(text())='Model']/following-sibling::li/a/text()")
        if (model is None):
            model=text("//*[normalize-space(text())='Model']/following-sibling::li/text()")

        # Ad Location
        location=text('//*[@id="scroll_car_info"]/p/a/text()')

        # mileage
        mileage=integer(text('//span[@class="engine-icon millage"]/../p/text()'))

        # Engine Type
        engine_type=text('//span[@class="engine-icon type"]/../p/a/text()')


        # Transmission
        transmission=text('//span[@class="engine-icon transmission"]/../p/a/text()')
        if (transmission is None):
            transmission=text('//span[@class="engine-icon transmission"]/../p/text()')

        # Registered City
        register_city=text('//*[@id="scroll_car_detail"]/li[2]/text()')

        # Color
        color=text("//*[contains(text(),'Color')]/following-sibling::li/text()")


        # Assembly
        assembly=text("//*[contains(text(),'Assembly')]/following-sibling::li/a/text()")
        if (assembly!='Local') and (assembly!='Imported'):
            assembly=text("//*[contains(text(),'Assembly')]/following-sibling::li/text()")


        # Body Type
        body_type=text("//*[contains(text(),'Body Type')]/following-sibling::li/a/text()")

        # Engine Capacity 
        capacity=integer(text("//*[contains(text(),'Engine Capacity')]/following-sibling::li/text()"))

        # last updated
        updated=self.parse_updated_date(text("//*[contains(text(),'Last Updated')]/following-sibling::li/text()"))

        # Refrence Number
        ref_no=text("//*[contains(text(),'Ad Ref #')]/following-sibling::li/text()")
        if ref_no:
            ref_no = re.sub(r'^\s*Ad\s*Ref\s*#?\s*', '', ref_no, flags=re.I).strip()
        if not ref_no:
            path = urlsplit(url).path.rstrip('/')
            match = re.search(r'/(\d+)$', path)
            ref_no = match.group(1) if match else None
        if not ref_no or not url.strip():
            raise DropItem('listing has neither a usable Ad Ref nor URL identifier')


        # Feature List
        raw_features=response.xpath('//ul[@class="list-unstyled car-feature-list nomargin"]/li/text()').extract()
        features=sorted({value.strip() for value in raw_features if value and value.strip()}, key=str.casefold)


        yield PakwheelsItem(source_listing_id=ref_no, name=name, price_pkr=price,
                make=make, model=model, model_year=year, location=location,
                mileage_km=mileage, registered_city=register_city,
                engine_type=engine_type, engine_capacity_cc=capacity,
                transmission=transmission, color=color, assembly=assembly,
                body_type=body_type, features=features,
                source_updated_at=updated, url=url.strip())

    @staticmethod
    def parse_price(value, unit=None):
        """Return a rounded integer PKR value without binary floating point."""
        if value is None:
            return None
        combined = ' '.join(filter(None, (value, unit))).strip().lower()
        match = re.search(r'(\d[\d,]*(?:\.\d+)?)', combined)
        if not match:
            return None
        multiplier = Decimal(1)
        if re.search(r'\b(?:lac|lacs|lakh|lakhs)\b', combined):
            multiplier = Decimal(100000)
        elif re.search(r'\bcrores?\b', combined):
            multiplier = Decimal(10000000)
        try:
            amount = Decimal(match.group(1).replace(',', '')) * multiplier
        except InvalidOperation:
            return None
        return int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @staticmethod
    def parse_updated_date(value):
        if not value:
            return None
        cleaned = re.sub(r'^\s*Last Updated\s*:?', '', value, flags=re.I).strip()
        for pattern in ('%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%d %B %Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(cleaned, pattern).date()
            except ValueError:
                continue
        return None

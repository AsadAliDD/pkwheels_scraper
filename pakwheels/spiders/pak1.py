import scrapy


class Pak1Spider(scrapy.Spider):
    name = 'pak1'
    allowed_domains = ['pakwheels.com']
    start_urls = ['https://www.pakwheels.com/used-cars/search/-/']

    def __init__(self, pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if pages is None:
            self.max_pages = None
            return

        try:
            self.max_pages = int(pages)
        except (TypeError, ValueError):
            raise ValueError('pages must be a positive integer') from None

        if self.max_pages < 1:
            raise ValueError('pages must be a positive integer')

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, meta={'page_number': 1})

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
        urls=response.xpath('//div[@class="search-title"]/a/@href').extract()
        for url in urls:
            comp_url='https://www.pakwheels.com'+url
            yield scrapy.Request(comp_url, callback=self.parse_car)

        # Next Page
        next_page=response.xpath('//li[@class="next_page"]/a/@href').extract_first()
        page_number = response.meta.get('page_number', 1)
        if next_page and (self.max_pages is None or page_number < self.max_pages):
            comp_url='https://www.pakwheels.com'+next_page
            yield scrapy.Request(
                comp_url,
                callback=self.parse,
                meta={'page_number': page_number + 1},
            )



    def parse_car(self,response):
        
        # Name tag of AD
        name=response.xpath('//h1/text()').extract_first()  
        
        url=response.request.url
        # Price
        price=response.xpath('//div[@class="price-box"]/strong/text()').extract_first()
        unit=response.xpath('//div[@class="price-box"]/strong/span/text()').extract_first()
        
        if (unit=='lacs'):
            price=float(price.strip().split('PKR')[1])*100000 
        elif (unit=='crore'):
            price=float(price.strip().split('PKR')[1])*10000000
        
        # Model Year
        year=int(response.xpath('//span[@class="engine-icon year"]/../p/a/text()').extract_first())

        # Make and Model
        make=response.xpath("//*[normalize-space(text())='Make']/following-sibling::li/a/text()").extract_first()
        if (make is None):
            make=response.xpath("//*[normalize-space(text())='Make']/following-sibling::li/text()").extract_first()

        model=response.xpath("//*[normalize-space(text())='Model']/following-sibling::li/a/text()").extract_first()
        if (model is None):
            model=response.xpath("//*[normalize-space(text())='Model']/following-sibling::li/text()").extract_first()

        # Ad Location
        location=response.xpath('//*[@id="scroll_car_info"]/p/a/text()').extract_first() 

        # mileage
        mileage=response.xpath('//span[@class="engine-icon millage"]/../p/text()').extract_first()   
        mileage=int(mileage.replace('km','').replace(',',''))

        # Engine Type
        engine_type=response.xpath('//span[@class="engine-icon type"]/../p/a/text()').extract_first()  


        # Transmission
        transmission=response.xpath('//span[@class="engine-icon transmission"]/../p/a/text()').extract_first() 
        if (transmission is None):
            transmission=response.xpath('//span[@class="engine-icon transmission"]/../p/text()').extract_first() 

        # Registered City
        register_city=response.xpath('//*[@id="scroll_car_detail"]/li[2]/text()').extract_first() 

        # Color
        color=response.xpath("//*[contains(text(),'Color')]/following-sibling::li/text()").extract_first() 


        # Assembly
        assembly=response.xpath("//*[contains(text(),'Assembly')]/following-sibling::li/a/text()").extract_first() 
        if (assembly!='Local') and (assembly!='Imported'):
            assembly=response.xpath("//*[contains(text(),'Assembly')]/following-sibling::li/text()").extract_first() 


        # Body Type
        body_type=response.xpath("//*[contains(text(),'Body Type')]/following-sibling::li/a/text()").extract_first()          

        # Engine Capacity 
        capacity=response.xpath("//*[contains(text(),'Engine Capacity')]/following-sibling::li/text()").extract_first() 

        # last updated
        updated=response.xpath("//*[contains(text(),'Last Updated')]/following-sibling::li/text()").extract_first()

        # Refrence Number
        ref_no=response.xpath("//*[contains(text(),'Ad Ref #')]/following-sibling::li/text()").extract_first()


        # Feature List
        features=response.xpath('//ul[@class="list-unstyled car-feature-list nomargin"]/li/text()').extract()
        features=','.join(features)


        yield {
                "Ad No":    ref_no,
                "Name":     name,
                "Price":    price,
                "Make":     make,
                "Model":    model,
                "Model Year": year,
                "Location": location,
                "Mileage": mileage,
                "Registered City": register_city,
                "Engine Type": engine_type,
                "Engine Capacity": capacity,
                "Transmission": transmission,
                "Color": color,
                "Assembly": assembly,
                "Body Type": body_type,
                "Features": features,
                "Last Updated": updated,
                "URL": url
        }

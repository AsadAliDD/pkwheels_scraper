# pkwheels_scraper
Scrapy based Ad scraper from https://www.pakwheels.com/


## Scraped Fields

- Ad Ref No.
- Name
- Price
- Model Year
- Location
- Mileage
- Registered City
- Engine Type
- Engine Capacity
- Transmission
- Color
- Assembly
- Body Type
- Features
- Last Updated
- URL


## Usage 
### To export in JSON run the command
- scrapy crawl pak1 -O sracppedData.json

### To export in .csv run the command
- scrapy crawl pak1 -O scrappedData.csv

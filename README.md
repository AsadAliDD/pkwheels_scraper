# pkwheels_scraper
Scrapy based Ad scraper from https://www.pakwheels.com/


## Scraped Fields

- Ad Ref No.
- Name
- Price
- Make
- Model
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
Use the `pages` spider argument to limit how many search-result pages are
scraped. If it is omitted, the spider continues through all available pages.
Only an unbounded crawl that reaches the final results page without request or
spider failures contributes to disappearance detection. A listing is marked
inactive after three such crawls omit it (configurable with
`LISTING_INACTIVE_MISS_THRESHOLD`); seeing it again resets the count and
reactivates it. Page-limited development crawls never infer removals.

Requests are sent one at a time with a randomized delay around two seconds and
a randomly selected browser user agent.

### To export five pages in JSON run the command
- `scrapy crawl pak1 -a pages=5 -O scrappedData.json`

### To export five pages in .csv run the command
- `scrapy crawl pak1 -a pages=5 -O scrappedData.csv`

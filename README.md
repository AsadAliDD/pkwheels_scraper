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
scraped. It must be a positive integer and includes the initial results page.
If it is omitted, the spider continues through all available pages.
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

## Scheduled database scrape

The production wrapper performs an unbounded database crawl (it deliberately
does not pass Scrapy feed-export options), prevents overlapping runs, and
returns Scrapy's exit status to cron. The examples below assume the repository
is installed at `/opt/pkwheels_scraper`; replace that path with the real,
absolute checkout path.

### Installation and database migration

Install MySQL 8 locally, create a database and a least-privilege application
user, then create the project-local virtual environment expected by the
wrapper and apply the migrations in filename order:

```sh
sudo mysql <<'SQL'
CREATE DATABASE pakwheels CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'scraper'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT SELECT, INSERT, UPDATE, DELETE ON pakwheels.* TO 'scraper'@'localhost';
SQL

cd /opt/pkwheels_scraper
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
for migration in db/migrations/*.sql; do
    mysql --user=root --password pakwheels < "$migration" || exit 1
done
```

Migrations create the `scrape_runs`, `listings`, `listing_versions`, and
`price_history` tables. Record applied migrations in your deployment tooling;
each migration should be applied exactly once.

### Environment and credentials

`DATABASE_URL` is required. For a local server it has the form
`mysql://scraper:password@localhost/pakwheels`. Percent-encode reserved URL
characters in the username or password. Supply the URL through the service
environment, or put it in `/etc/pakwheels-scraper.env`:

```sh
sudo install -o root -g root -m 0600 /dev/null /etc/pakwheels-scraper.env
sudoedit /etc/pakwheels-scraper.env
# Add one shell assignment; quote the value if it contains shell metacharacters:
# DATABASE_URL='mysql://scraper:REDACTED@localhost/pakwheels'
```

The wrapper refuses a credentials file that is not root-owned or has any group
or other permissions. It does not enable shell tracing or print the connection
string, and creates logs with mode `0600`. Optional deployment overrides are
`PAKWHEELS_ENV_FILE`, `PAKWHEELS_LOCK_FILE`, and `PAKWHEELS_LOG_DIR`.

Run it manually as the same account used by cron (normally root):

```sh
sudo /opt/pakwheels_scraper/scripts/run_scrape.sh
echo "$?"
```

### Cron schedule and logs

Add this to root's crontab to start a scrape at 00:00 and 12:00 UTC:

```cron
CRON_TZ=UTC
0 0,12 * * * /opt/pakwheels_scraper/scripts/run_scrape.sh
```

The wrapper itself uses a non-blocking lock at
`/var/lock/pakwheels-scraper.lock`, so the cron entry must not add a second
`flock`. An invocation exits successfully without starting Scrapy when the
previous crawl still owns that lock. Scrape output is stored in timestamped UTC
files under `/var/log/pakwheels-scraper/`; files older than 14 days are removed
at the beginning of each invocation. Cron can therefore alert on any non-zero
wrapper exit (including Scrapy failures), while an overlap is handled as an
intentional no-op.

### Health check

Because the job runs every 12 hours, alert if there has been no successful,
finished run in the last 14 hours (13 hours is a stricter alternative). For
example, a monitoring check can run:

```sh
mysql --batch --skip-column-names --user=scraper --password \
  --host=localhost pakwheels --execute="SELECT CASE WHEN EXISTS (
       SELECT 1 FROM scrape_runs
       WHERE status = 'succeeded'
         AND finished_at >= UTC_TIMESTAMP() - INTERVAL 14 HOUR
   ) THEN 'OK' ELSE 'CRITICAL: no successful scrape in 14 hours' END"
```

Configure the monitor to alert unless the single output line is `OK` (and also
on a non-zero `mysql` exit), so database outages and stale scrape schedules are
both visible.

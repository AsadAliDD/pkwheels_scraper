#!/usr/bin/env bash

set -Eeuo pipefail

# Resolve this file rather than relying on cron's working directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd -- "${REPO_DIR}"

LOCK_FILE="${PAKWHEELS_LOCK_FILE:-/var/lock/pakwheels-scraper.lock}"
exec 9>"${LOCK_FILE}"
if ! /usr/bin/flock -n 9; then
    # A concurrent run is expected occasionally and is not a scrape failure.
    exit 0
fi

# A service manager may provide DATABASE_URL directly. Otherwise, only trust a
# root-owned file whose group/other permission bits are clear.
ENV_FILE="${PAKWHEELS_ENV_FILE:-/etc/pakwheels-scraper.env}"
if [[ -z "${DATABASE_URL:-}" ]]; then
    [[ -f "${ENV_FILE}" ]] || {
        printf 'DATABASE_URL is unset and environment file is missing: %s\n' "${ENV_FILE}" >&2
        exit 1
    }
    read -r env_owner env_mode < <(/usr/bin/stat -c '%u %a' -- "${ENV_FILE}")
    if [[ "${env_owner}" != 0 || $((8#${env_mode} & 8#077)) -ne 0 ]]; then
        printf 'Environment file must be root-owned and mode 0600 (or stricter): %s\n' "${ENV_FILE}" >&2
        exit 1
    fi
    # shellcheck disable=SC1090 -- this path is deliberately configurable.
    source "${ENV_FILE}"
fi
: "${DATABASE_URL:?DATABASE_URL must be set in the service environment or root-owned environment file}"
export DATABASE_URL

SCRAPY="${REPO_DIR}/.venv/bin/scrapy"
[[ -x "${SCRAPY}" ]] || {
    printf 'Scrapy executable not found; create the project environment at %s/.venv\n' "${REPO_DIR}" >&2
    exit 1
}

LOG_DIR="${PAKWHEELS_LOG_DIR:-/var/log/pakwheels-scraper}"
/usr/bin/install -d -m 0750 -- "${LOG_DIR}"

# Retain two weeks of timestamped logs. Files are private to root and the
# wrapper never enables xtrace or prints the database connection string.
/usr/bin/find "${LOG_DIR}" -maxdepth 1 -type f -name 'scrape-*.log' -mtime +14 -delete
timestamp="$(/usr/bin/date -u +'%Y%m%dT%H%M%SZ')"
log_file="${LOG_DIR}/scrape-${timestamp}.log"
/usr/bin/install -m 0600 /dev/null "${log_file}"

# exec preserves Scrapy's exit status for cron while sending both streams to a
# timestamped file. No feed-export arguments are intentionally supplied.
exec "${SCRAPY}" crawl pak1 >>"${log_file}" 2>&1

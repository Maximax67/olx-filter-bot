# OLX Filter Bot

A serverless Telegram bot that watches OLX.ua search pages for you. Send it the link of an OLX.ua results page with your filters applied, and it messages you every new advert that appears.

Python 3.12 · FastAPI · aiogram 3 · SQLAlchemy 2 (async) · Alembic · PostgreSQL · httpx + selectolax

## How it works

1. **Add.** The user sends an OLX link. The bot validates it (see [URL validation](#url-validation-and-safety)), forces `search[order]=created_at:desc`, makes one live request to prove OLX returns a list of adverts for it, stores the filter, and silently records the adverts that already exist so nothing old is announced.
2. **Watch.** A scheduler calls `GET /api/cron/check-filters`. Due filters are checked within a time budget (250 s by default). Every unseen advert is sent as `Filter N:` plus its link.
3. **Manage.** `/list` shows the filters with delete buttons, `/delete N` removes one, `/add <link>` or a bare link adds one, `/help` explains. Each user has a personal limit in `bot_user.filter_limit`; new users get `FILTER_DEFAULT_LIMIT` (10).

Filter numbers belong to the user and stay stable. A number freed by a deletion is reused by the next filter, so numbers do not grow beyond the user's limit.

## Architecture

```
presentation ──► application ──► domain
FastAPI, aiogram   use cases, ports   entities, value objects, rules
      │                 ▲
      └──► infrastructure implements the ports: SQLAlchemy, httpx + selectolax, aiogram Bot, settings
src/container.py wires every layer together (composition root)
```

| Layer | Path | Responsibility |
|---|---|---|
| Domain | `src/domain` | `User`, `SearchFilter`, `Advert`; `FilterUrl` and `AdvertUrl` value objects; rules (limit, numbering, freshness). No framework imports. |
| Application | `src/application` | Use cases, ports (`AdvertSource`, `Notifier`, repositories, `UnitOfWork`, `Clock`), backoff, deadline. |
| Infrastructure | `src/infrastructure` | Settings per domain, SQLAlchemy models, repositories and unit of work, OLX client and parser, Telegram notifier, logging. |
| Presentation | `src/presentation` | FastAPI routers and security dependencies; aiogram handlers, middlewares, keyboards, texts; operator CLIs. |

Request pipelines:

- **Bot:** `LoggingMiddleware` (update level) → `ThrottlingMiddleware` → `DomainErrorMiddleware` (turns domain errors into user-facing replies) → `UserMiddleware` (upserts the user, injects `user`) → handlers. Handlers only parse input and call one use case.
- **API:** secrets are verified by FastAPI dependencies (`verify_cron_secret`, `verify_webhook_secret`) before any logic runs.
- **Persistence:** use cases open short `UnitOfWork` transactions (commit on success, rollback on error) and never hold a database connection while waiting for OLX or Telegram.

## URL validation and safety

Every link goes through `FilterUrl.parse` before anything else happens.

| Rule | Why |
|---|---|
| Scheme `http`/`https` only, stored as `https` | no `javascript:`, `ftp:`, scheme-relative URLs |
| Host must be exactly `olx.ua` or `www.olx.ua`, normalised to `www.olx.ua` | rejects `www.olx.ua.evil.com`, `olx.ua@evil.com`, IDN homographs, trailing dots, IPs, other subdomains |
| No credentials, default ports only, no backslashes, whitespace or control characters, 2048 characters max | parser-confusion and SSRF tricks |
| Path must be a category or search listing | rejects single adverts (`/d/...`, `*.html`), the home page, account and API paths; at most 8 segments; each segment must match `[\w-]+` after decoding, which rejects `..`, dots and encoded slashes |
| Only `currency` and `search[...]` parameters survive | tracking and pagination parameters are dropped; count and size are bounded |
| `search[order]=created_at:desc` is forced | the check relies on newest-first ordering |
| Parameters are sorted | equivalent URLs get the same fingerprint, so duplicates are detected |

Beyond syntax, the bot makes a **live probe** when a filter is added, so a link that looks right but is not an advert list is refused instead of failing forever in the cron. On the network side: redirects are followed manually and every hop is re-validated against the same rules, response size and total fetch time are capped, advert links found in the HTML are re-validated as olx.ua advert URLs, and everything echoed back into Telegram is HTML-escaped.

## Cron behaviour

- **Auth:** `Authorization: Bearer <CRON_SECRET>`, compared in constant time. Vercel sends this header automatically when `CRON_SECRET` is set.
- **Queue:** due filters are claimed one at a time with `FOR UPDATE SKIP LOCKED` and a lease. Overlapping invocations never process the same filter, and a crashed run releases its filters when the lease expires.
- **Time budget:** `CRON_TIME_BUDGET_SECONDS` (250). Workers stop claiming new filters when less than `CRON_TASK_GRACE_SECONDS` remains, and a hard timeout ends the run at the budget. Filters that were not reached stay due and are served first by the next run; the oldest-due filter always goes first. A filter is checked at most once per run.
- **New adverts:** each filter keeps the set of advert codes it has seen. An advert is recorded only after Telegram accepted the message, so a failed delivery is retried and nothing is skipped. Messages go oldest first. Unseen adverts older than `FILTER_MAX_ADVERT_AGE_HOURS` (promoted adverts rotating into the first page) are recorded without being announced whenever OLX provides the creation time.

How outcomes are classified:

| Outcome | Treated as | Effect |
|---|---|---|
| 200 and a recognised listing | success | send new adverts, reset failure counters |
| 404, 410, or a redirect to another host or a non-listing page | *missing* | exponential backoff; after `FILTER_PAUSE_AFTER_MISSING_CHECKS` consecutive results the filter is paused and the user is told |
| 403, 429, 5xx, timeout, network error, oversized body, or a 200 page with unrecognised markup | *transient* | exponential backoff up to `FILTER_RETRY_MAX_DELAY_SECONDS`; **never pauses** a filter |
| Telegram flood limit | deferred | stop sending, retry after Telegram's `retry_after` |
| Telegram "blocked" or chat gone | recipient gone | user deactivated and skipped; reactivated by their next message |
| Other Telegram errors | failure | backoff |

Because markup problems are transient, an OLX redesign cannot mass-pause users. It shows up as growing `failed` counts in the cron report and as errors in the logs.

The endpoint returns a JSON report: `claimed`, `checked`, `failed`, `paused`, `notified`, `purged`, `deadline_reached`, `duration_seconds`.

## Configuration

Copy `.env.example` to `.env` for local work. On a serverless platform set the same names as environment variables.

| Variable | Default | Description |
|---|---|---|
| `APP_ENVIRONMENT` | `production` | `local`, `staging` or `production`. API docs are served only in `local` and `staging` |
| `APP_PUBLIC_BASE_URL` | `-` | Public https base URL, used by the webhook CLI |
| `DATABASE_URL` | **required** | PostgreSQL URL. `postgres://`, `postgresql://`, `sslmode=` and `channel_binding=` are normalised for asyncpg |
| `DATABASE_POOL_SIZE` | `5` | Connections kept per instance |
| `DATABASE_MAX_OVERFLOW` | `5` | Extra connections allowed under load |
| `DATABASE_POOL_RECYCLE_SECONDS` | `300` | Recycle connections older than this |
| `DATABASE_PGBOUNCER_MODE` | `False` | Disable prepared statements for PgBouncer transaction pooling (Neon/Supabase poolers) |
| `DATABASE_ECHO` | `False` | Log SQL statements |
| `TELEGRAM_BOT_TOKEN` | **required** | Token from BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | **required** | Secret Telegram sends in `X-Telegram-Bot-Api-Secret-Token`. 16-256 chars of `A-Za-z0-9_-` |
| `TELEGRAM_THROTTLE_SECONDS` | `1.0` | Minimum gap between requests from one user (0 disables) |
| `TELEGRAM_REQUEST_TIMEOUT_SECONDS` | `15.0` | Timeout of every Telegram API call |
| `CRON_SECRET` | **required** | Bearer secret for the cron endpoint (min 16 chars). Vercel sends it automatically |
| `CRON_TIME_BUDGET_SECONDS` | `250` | Hard wall-clock budget of one cron run |
| `CRON_CONCURRENCY` | `5` | Parallel filter checks per run |
| `CRON_CLAIM_LEASE_SECONDS` | `600` | How long a claimed filter stays reserved if a run dies (must exceed the budget) |
| `CRON_TASK_GRACE_SECONDS` | `25` | Stop claiming new filters when less than this remains |
| `FILTER_DEFAULT_LIMIT` | `10` | Filter limit given to **new** users (stored per user in `bot_user.filter_limit`) |
| `FILTER_CHECK_INTERVAL_SECONDS` | `0` | Minimum time between checks of one filter. `0` = check on every cron run |
| `FILTER_MAX_ADVERT_AGE_HOURS` | `48` | Unseen adverts older than this are remembered but not announced |
| `FILTER_MAX_NOTIFICATIONS_PER_CHECK` | `20` | Messages per filter per run; the rest follow on later runs |
| `FILTER_PAUSE_AFTER_MISSING_CHECKS` | `5` | Consecutive 404/410/redirect-away results before a filter is paused |
| `FILTER_RETRY_BASE_DELAY_SECONDS` | `60` | First retry delay after a failure (doubles each time) |
| `FILTER_RETRY_MAX_DELAY_SECONDS` | `3600` | Upper bound of the retry delay |
| `FILTER_SEEN_RETENTION_DAYS` | `14` | Forget adverts that have not appeared in a listing for this long |
| `OLX_USER_AGENT` | `Chrome-like` | User-Agent header sent to OLX |
| `OLX_REQUEST_TIMEOUT_SECONDS` | `15.0` | Per-request read timeout |
| `OLX_CONNECT_TIMEOUT_SECONDS` | `5.0` | Connect timeout |
| `OLX_TOTAL_TIMEOUT_SECONDS` | `25.0` | Upper bound for one page fetch including redirects |
| `OLX_MAX_RESPONSE_BYTES` | `5000000` | Responses larger than this are rejected |
| `OLX_MAX_REDIRECTS` | `3` | Redirect hops followed (each hop is re-validated) |
| `OLX_MAX_CONCURRENT_REQUESTS` | `5` | Simultaneous requests to OLX per instance |
| `OLX_PROXY_URL` | `-` | Optional outbound proxy for OLX requests |
| `LOG_LEVEL` | `INFO` | `DEBUG` to `CRITICAL` |
| `LOG_FORMAT` | `json` | `json` or `text` |

## Local development

```
docker compose up -d
cp .env.example .env
pip install -e ".[dev]"
alembic upgrade head
uvicorn src.asgi:app --reload
```

Before anything else, check the scraper against the live site from your own machine. It canonicalises the link, fetches it and prints what the parser found:

```
python -m src.presentation.cli.probe "https://www.olx.ua/uk/nedvizhimost/doma/prodazha-domov/?currency=UAH"
```

To receive Telegram updates locally, expose the app through a tunnel and register it:

```
python -m src.presentation.cli.webhook set --url https://your-tunnel-host
python -m src.presentation.cli.webhook info
```

`set` also publishes the bot command menu. In `local` and `staging` the API docs are at `/api/docs`.

## Deploy to Vercel

1. Create a PostgreSQL database. For a pooled (PgBouncer transaction mode) connection string set `DATABASE_PGBOUNCER_MODE=true`.
2. Add the required variables in the project settings: `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `CRON_SECRET`, `APP_PUBLIC_BASE_URL`, plus any overrides.
3. Apply migrations from your machine or CI: `DATABASE_URL=... alembic upgrade head`.
4. Deploy. `pyproject.toml` sets the entrypoint (`src.asgi:app`); `vercel.json` sets the cron (`*/5 * * * *`) and `maxDuration` (300). Keep `maxDuration` comfortably above `CRON_TIME_BUDGET_SECONDS`, and check that your plan allows the cron frequency.
5. Register the webhook: `python -m src.presentation.cli.webhook set --url https://your-project.vercel.app`

Any ASGI host works the same way (`src.asgi:app`) together with any scheduler that sends `GET` with the Bearer header.

## Operations

Raise a user's limit (takes effect on their next request):

```sql
UPDATE bot_user SET filter_limit = 25 WHERE telegram_id = 123456789;
```

Find filters that are failing or paused:

```sql
SELECT u.telegram_id, f.number, f.is_active, f.consecutive_failures, f.consecutive_misses, f.next_check_at, f.url
FROM search_filter f JOIN bot_user u ON u.id = f.user_id
WHERE NOT f.is_active OR f.consecutive_failures > 0
ORDER BY f.consecutive_failures DESC;
```

Resume a paused filter:

```sql
UPDATE search_filter
SET is_active = true, consecutive_failures = 0, consecutive_misses = 0, next_check_at = now()
WHERE id = 42;
```

The table is called `bot_user` because `user` is a reserved word in PostgreSQL and would need quoting in every manual query. Table names are singular, as in the project guidelines.

Logs are JSON on stdout (`LOG_FORMAT=text` for development). Every processed update logs its id, type, user and duration.

## Tests and quality

```
export TEST_DATABASE_URL=postgresql://olx:olx@localhost:5432/olx_bot_test
pytest
ruff check . && ruff format --check .
mypy
```

Integration tests run against a real PostgreSQL and apply the migrations through the Alembic CLI; they are skipped when `TEST_DATABASE_URL` is not set. They cover the repositories (including concurrent claims), every use case, and complete flows: a Telegram update through the webhook into aiogram and the database, then the cron endpoint, asserting the exact `Filter N:` message. `test_code_style.py` fails the build if any Python file contains a comment or a docstring. `alembic check` runs as a test, so models and migrations cannot drift apart.

The suite passes on SQLAlchemy 2.0.35 (the minimum) and 2.1.

## Things to know before production

- **The parser was verified against fixtures, not the live site.** The build environment could not reach olx.ua. The parser reads the `__PRERENDERED_STATE__` JSON that OLX embeds in listing pages and falls back to `data-cy="l-card"` result cards; both are modelled on publicly documented structures. Run the `probe` command first. If OLX changes its markup, filters back off (see the classification table) instead of being paused.
- **OLX may block datacenter IPs or unusual TLS fingerprints**, which would show up as 403/429. `OLX_PROXY_URL` routes OLX traffic through a proxy. Set `OLX_USER_AGENT` to something that identifies your service, and keep concurrency modest.
- **Only the first results page is read.** A filter that gains more new adverts than fit on one page between two checks would miss the overflow. The `probe` command shows how many adverts a page holds.
- **Throttling is per instance** (in memory). It limits bursts from one user; a shared limiter would need Redis.
- **Messages are in English** and live in `src/presentation/bot/texts.py`, ready for localisation.

# Payment Requests Portal

A read-only web view onto the `payment_requests` table in the core banking
database (`dashmfb-cba-mcs`), with filtering and CSV/Excel download.

## Read-only, three ways over

1. **Database grant.** The `robot` account holds `GRANT SELECT ON *.*` — MySQL
   itself rejects any write.
2. **Router.** `payments/routers.py` raises `ReadOnlyDatabaseError` on any write
   routed to the `payments` app, and blocks migrations against the `cba`
   connection so Django can never create its own tables in the banking schema.
3. **Model.** `PaymentRequest` is `managed = False`. Django never creates,
   alters or drops the table.

Django's own tables (users, sessions, admin log) live in `local.sqlite3`,
entirely separate from the banking database.

Verify at any time:

    .venv/bin/python manage.py shell < scripts/verify_readonly.py

## Local development (no VPN or tunnel needed)

`USE_SAMPLE_DB=True` points the `cba` connection at `sample.sqlite3`, holding
fabricated rows in the same shape as the live table.

    USE_SAMPLE_DB=True .venv/bin/python manage.py seed_sample_db
    USE_SAMPLE_DB=True .venv/bin/python manage.py runserver

Open http://127.0.0.1:8000/ and sign in.

The seed command refuses to run when `cba` points at MySQL, so it cannot reach
the real database.

## Running against the live database

Requires a network route to `172.22.0.93` — either running on the Oracle Cloud
server, or through an SSH tunnel:

    ssh -N -L 3307:172.22.0.93:3306 Alatiseo@132.145.47.17

With a tunnel, set `CBA_DB_HOST=127.0.0.1` and `CBA_DB_PORT=3307` in `.env`.

Without a route the app shows a readable connectivity page (HTTP 503) rather
than a stack trace.

## Deploying to the Windows server (132.145.47.17)

    git clone <repo> && cd PaymentRequestApk
    py -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    copy .env.example .env      # then fill in, leave USE_SAMPLE_DB unset
    .venv\Scripts\python manage.py collectstatic --noinput
    .venv\Scripts\python manage.py migrate
    .venv\Scripts\python manage.py createsuperuser
    .venv\Scripts\python manage.py runserver 0.0.0.0:8000

Before exposing it beyond the server itself:

- Set `DJANGO_DEBUG=False` and a real `DJANGO_SECRET_KEY`. Generate one with:

      python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"

- Add the server to `DJANGO_ALLOWED_HOSTS`.
- Serve behind a real WSGI server (waitress works well on Windows) rather than
  `runserver`.
- Restrict the OCI security list rule to known source addresses.

## Search engines

The app is marked "do not index" three ways:

- `<meta name="robots">` on every HTML page
- an `X-Robots-Tag` response header on **every** response, applied in
  `payments/middleware.py` - this is what covers the CSV and Excel downloads,
  which cannot carry a meta tag
- `/robots.txt` returning `Disallow: /`

**These are requests, not access control.** They stop well-behaved crawlers
(Google, Bing) listing the site; they do not stop anyone who has the URL. Since
every page already requires a login, there is no payment data for a crawler to
reach either way - what this actually prevents is the sign-in page turning up in
search results.

If the requirement is genuinely "not reachable from the internet", that is a
network control, not a meta tag: restrict the OCI security list so the app's
port only accepts traffic from known addresses.

## Branding and static files

The logo lives at `static/img/logo.png` (cropped from the original, kept at
`static/img/DASH_LOGO-original.png`). Favicons are generated from it. Because
the mark is dark purple, it sits on a white plate in the app bar and on the
sign-in card - on the purple bar directly it would disappear.

Static files are served by WhiteNoise, so no separate web server is needed.
Run `collectstatic` after any change to `static/`.

Pillow is not a runtime dependency and is deliberately absent from
`requirements.txt`; it is only needed if you want to regenerate the favicons
from a new logo (`pip install pillow` when you do).

## Windows notes

`tzdata` is in `requirements.txt` because Windows ships no system timezone
database - without it, `TIME_ZONE = "Africa/Lagos"` raises
`ZoneInfoNotFoundError` at runtime. macOS and Linux do not need it, but it is
harmless there and keeps one requirements file for both.

Every dependency is pure Python, so there is no compiler toolchain to install.

## Schema changes

The model mirrors the live schema as of 2026-08-28 (38 columns). If a column is
added upstream:

    .venv/bin/python manage.py inspectdb payment_requests --database=cba

and update `payments/models.py`.

## Authentication

Django's own auth (PBKDF2-SHA256 password hashing, CSRF on every form, signed
session cookies), plus:

- **Lockout** — 5 failed attempts locks that username+IP pair for 30 minutes
  (`django-axes`). Pairing on username+IP rather than username alone means an
  attacker cannot lock a real user out of their own account from elsewhere.
- **Sessions** — expire after 8 hours, and on browser close. Sliding window:
  activity extends them.
- **Cookies** — HttpOnly, SameSite=Lax; `Secure` plus HSTS and an HTTPS redirect
  switch on automatically whenever `DEBUG` is off.
- **Audit log** — `logs/audit.log` records every export (who, when, filters, row
  count, whether PII was included) and every failed login. Rotates at 5MB.

Not included, and worth deciding on: **two-factor authentication**. For an
internal tool on a private network that may be acceptable; if this is ever
reachable from the internet, add `django-otp` before exposing it.

## Exports and PII

The table holds emails, phone numbers, customer IDs and account numbers for
both parties. `EXPORT_INCLUDE_PII` in `config/settings.py` is `True`; set it to
`False` to mask those six columns in CSV and Excel downloads. Exports always
cover every row matching the current filters, not just the visible page.

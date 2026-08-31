# Payment Requests Portal

A read-only web view onto the `payment_requests` table in the core banking
database (`dashmfb-cba-mcs`), with filtering and CSV/Excel download.

## Read-only, three ways over

1. **Database grant.** The `robot` account holds `GRANT SELECT ON *.*` - MySQL
   itself rejects any write.
2. **Router.** `payments/routers.py` raises `ReadOnlyDatabaseError` on any write
   routed to the `payments` app, and blocks migrations against the `cba`
   connection so Django cannot create its own tables in the banking schema.
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

Requires a network route to `172.22.0.93` - either running on the Oracle Cloud
server, or through an SSH tunnel:

    ssh -N -L 3307:172.22.0.93:3306 Alatiseo@132.145.47.17

With a tunnel, set `CBA_DB_HOST=127.0.0.1` and `CBA_DB_PORT=3307` in `.env`.

Without a route the app shows a readable connectivity page (HTTP 503) rather
than a stack trace.

## Deploying to the Windows server (132.145.47.17)

    git clone <repo> && cd PaymentRequestApk
    py -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    copy .env.example .env

Then edit `.env`:

- `CBA_DB_PASSWORD` - the real password
- `DJANGO_SECRET_KEY` - generate one, see below
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS` - the server's hostname/IP
- `DJANGO_SECURE_SSL_REDIRECT=False` until TLS is in place, otherwise plain
  HTTP requests redirect to a port nothing is listening on
- `DJANGO_PORT` - see "Choosing a port" below
- leave `USE_SAMPLE_DB` unset, or the app shows fabricated data

Then:

    .venv\Scripts\python manage.py collectstatic --noinput
    .venv\Scripts\python manage.py migrate
    .venv\Scripts\python manage.py createsuperuser
    .venv\Scripts\python serve.py

### Generating DJANGO_SECRET_KEY

    .venv\Scripts\python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

Paste the result into `.env` unquoted. The generated characters
(`!@#$%^&*(-_=+)`) survive `.env` parsing intact - verified over 300 generated
keys. Do not reuse the development key, and do not commit it.

### Choosing a port

Ports 8000-8002 are already used by other applications on this server. Check
what is listening before picking one:

    netstat -ano | findstr LISTENING

or, more readably:

    Get-NetTCPConnection -State Listen | Select-Object -ExpandProperty LocalPort | Sort-Object -Unique

Set the free port in `.env` as `DJANGO_PORT` (default 8500). Then open it in
**both** firewalls, or the app will be unreachable with no error:

    New-NetFirewallRule -DisplayName "Payment Requests portal" -Direction Inbound `
      -Protocol TCP -LocalPort 8500 -Action Allow

and add a matching ingress rule to the OCI security list for the VCN subnet -
restricted to known source addresses, not 0.0.0.0/0.

### Why serve.py rather than runserver

`runserver` is a development server: single-threaded, no request queuing, and
it stops serving static files once `DEBUG=False`. `serve.py` runs the app under
Waitress, which is pure Python and works on Windows (gunicorn does not). Static
files are handled by WhiteNoise, so no separate web server is needed.

## First deployment, in order

The order matters: Caddy cannot obtain a certificate until DNS resolves and
port 80 is reachable, so those come first.

1. **DNS.** `payments.dashmfb.com` -> A record -> the server's public IP.
   Confirm with `nslookup payments.dashmfb.com` before continuing.
2. **OCI security list.** Open TCP 80 and 443 to `0.0.0.0/0` - Let's Encrypt
   validates from addresses that cannot be predicted. Do **not** open 8500.
3. **Windows Firewall.** Allow 80 and 443. Remove any earlier 8500 rule.
4. **Code and config.** `git pull`, install requirements, write `.env`.
5. **Django setup.** `collectstatic`, `migrate`, `createsuperuser`.
6. **App service** under NSSM, bound to loopback.
7. **Caddy service**, which fetches the certificate on first start.
8. **Verify** over HTTPS.

Steps 6 and 7 are below. Once both services are running, the app is reachable
only through Caddy: Waitress listens on `127.0.0.1:8500`, which nothing outside
the machine can address.

## Running as a Windows service (NSSM)

`serve.py` in a console window dies when the session ends and does not survive a
reboot. NSSM runs it as a proper service.

    nssm install PaymentRequests "C:\sites\PaymentRequestApk\.venv\Scripts\python.exe" "C:\sites\PaymentRequestApk\serve.py"
    nssm set PaymentRequests AppDirectory   C:\sites\PaymentRequestApk
    nssm set PaymentRequests DisplayName    "DashMFB Payment Requests Portal"
    nssm set PaymentRequests Description    "Read-only reporting view onto payment_requests"
    nssm set PaymentRequests Start          SERVICE_AUTO_START

    nssm set PaymentRequests AppStdout      C:\sites\PaymentRequestApk\logs\service.log
    nssm set PaymentRequests AppStderr      C:\sites\PaymentRequestApk\logs\service.log
    nssm set PaymentRequests AppRotateFiles 1
    nssm set PaymentRequests AppRotateBytes 5242880

    nssm set PaymentRequests AppExit Default Restart
    nssm set PaymentRequests AppRestartDelay 5000

    nssm start PaymentRequests

`AppDirectory` matters: without it the service starts in `system32` and relative
paths resolve wrongly.

`serve.py` refuses to start if `.env` is missing or if `DJANGO_SECRET_KEY`,
`CBA_DB_HOST` or `CBA_DB_PASSWORD` are unset, and prints why. Under a service
there is no console to watch, so it fails loudly into the log rather than
starting up broken. Its output is unbuffered for the same reason - a buffered
banner makes a running service look like a dead one.

The first three lines of `logs\service.log` after a healthy start:

    Payment Requests portal -> http://127.0.0.1:8500  (8 threads)
    Settings: DEBUG=False  hosts=['reports.example.com']
    Database: 172.22.0.93

If it is running on sample data instead, the log says so in capitals. That line
is the quickest check that a deployment is real.

### Service account

NSSM defaults to LocalSystem, which is far more privilege than this needs. For
anything touching banking data, create a dedicated low-privilege account with
read access to the application directory and set:

    nssm set PaymentRequests ObjectName .\svc_payments "<password>"

### Health check

`GET /healthz/` needs no login and returns:

    {"app": "ok", "database": "ok"}          200
    {"app": "ok", "database": "unreachable"} 503

It reports whether the banking database answers, never what is in it and never
the connection error. Point monitoring at it, and use it to tell "the service is
down" apart from "the database is unreachable" without signing in.

## HTTPS and a domain

Until this is behind TLS, passwords cross the network in clear text. The
simplest path on Windows is Caddy in front of Waitress - it obtains and renews a
Let's Encrypt certificate with no further work.

`Caddyfile`:

    reports.example.com {
        reverse_proxy 127.0.0.1:8500
    }

Then run Caddy as a second NSSM service. Once it is in front, change `.env`:

    DJANGO_BIND_HOST=127.0.0.1
    DJANGO_ALLOWED_HOSTS=reports.example.com
    DJANGO_BEHIND_TLS_PROXY=True
    DJANGO_SECURE_SSL_REDIRECT=True
    DJANGO_CSRF_TRUSTED_ORIGINS=https://reports.example.com

**`DJANGO_BIND_HOST=127.0.0.1` is the important one.** Behind a proxy, Waitress
should answer only on loopback. Left on `0.0.0.0`, port 8500 stays reachable
directly and anyone who knows it bypasses TLS entirely.

`DJANGO_BEHIND_TLS_PROXY=True` sets `SECURE_PROXY_SSL_HEADER` so Django trusts
Caddy's `X-Forwarded-Proto` and does not redirect-loop. Verified configuration:

    SECURE_SSL_REDIRECT        True
    SECURE_PROXY_SSL_HEADER    ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS        31536000
    SESSION_COOKIE_SECURE      True
    CSRF_COOKIE_SECURE         True

Ports 80 and 443 must be open publicly for Caddy's certificate challenge; 8500
should not be. In the OCI security list, open 80 and 443 and close 8500.

## Authentication

Django's own auth (PBKDF2-SHA256 password hashing, CSRF on every form, signed
session cookies), plus:

- **Lockout** - 5 failed attempts locks that username+IP pair for 30 minutes
  (`django-axes`). Pairing on username+IP rather than username alone means an
  attacker cannot lock a real user out of their own account from elsewhere.
- **Sessions** - expire after 8 hours, and on browser close. Sliding window:
  activity extends them.
- **Cookies** - HttpOnly, SameSite=Lax; `Secure` plus HSTS and an HTTPS redirect
  switch on automatically whenever `DEBUG` is off.
- **Audit log** - `logs/audit.log` records every export (who, when, filters, row
  count, whether PII was included) and every failed login. Rotates at 5MB.

Not included, and worth deciding on: **two-factor authentication**. For an
internal tool on a private network that may be acceptable; if this is ever
reachable from the internet, add `django-otp` before exposing it.

## The download format

**Excel (.xlsx) only.** The download carries column widths,
`yyyy-mm-dd hh:mm:ss` date formats, thousands separators on amounts and a frozen
header row. Dates and amounts are written as real Excel dates and numbers, so
they sort and filter correctly rather than as text.

There was a CSV download; it was removed. A CSV is plain text and carries no
formatting, so Excel opened every column at its default width and showed
`######` wherever a date or amount did not fit - the data was fine, but it
looked broken, and people click whichever button is in front of them. Excel is
now the only option, so nobody lands on the format that looks wrong.

CSV is still produced by `manage.py export_payments`, which exists for the
verification script below rather than for people.

## Exports and PII

The table holds emails, phone numbers, customer IDs and account numbers for
both parties. `EXPORT_INCLUDE_PII` in `config/settings.py` is `True`; set it to
`False` to mask those six columns in CSV and Excel downloads. Exports always
cover every row matching the current filters, not just the visible page.

## Verifying an export against the database

`scripts/compare_reports.py` compares two files. To check the application
against the source of truth instead, use:

    .venv\Scripts\python scripts\verify_against_db.py                 # what the database says
    .venv\Scripts\python scripts\verify_against_db.py <export.csv>    # compare an export against it

This deliberately does **not** import Django. It opens its own PyMySQL
connection and issues plain SQL, so the model, the router, the filters and the
export code are all outside the path being checked - an agreement between the
two means something. Every statement is a SELECT.

With no argument it prints row count, total value, date range and the
breakdowns by status and type, to check against the dashboard tiles. With a CSV
it reports rows in the database but missing from the export, rows the export
invented, per-field mismatches on status/amount/created_at, and whether the
totals agree. Exit status is non-zero if anything differs, so it can be wired
into a scheduled check later.

Run it on the server, or through the SSH tunnel with `CBA_DB_HOST=127.0.0.1`
and `CBA_DB_PORT=3307`.

### Producing the export on the server

Downloading from the browser saves the file wherever that browser runs - if you
are viewing the app from your own machine, the CSV lands there, not on the
server. To avoid the round-trip, write the export server-side:

    .venv\Scripts\python manage.py export_payments check.csv
    .venv\Scripts\python scripts\verify_against_db.py check.csv

`export_payments` shares `EXPORT_COLUMNS` and `_cell` with the Excel export, so
verifying its output verifies the same column set and value formatting the
download uses. It exports every row by default; `--status PENDING` narrows it,
but compare unfiltered or the export will legitimately hold fewer rows than the
table.

## Comparing against an older report

To check an export against a previously produced report of the same table:

    python scripts/compare_reports.py <old-report.csv> <new-export.csv>

It matches rows on ID and normalises formats first, so `"1,000.00"` and
`1000.0000` compare equal. It reports rows present in only one file and
field-level differences for shared rows. A status that differs is not
necessarily wrong - check `updated_at`: if the row changed after the older
report was generated, the export is simply more current.

## Error pages

Custom, branded pages for `400`, `403`, `404` and `500`, plus `403_csrf.html`
for an expired CSRF token - which in practice means an expired session, so it
says that rather than "CSRF verification failed".

These only appear when `DEBUG=False`; with `DEBUG=True` Django shows its own
debug pages instead, which is what you want locally.

One constraint worth knowing if you edit them: Django renders `500.html` by
calling `template.render()` with **no request and no context**, so that page
cannot rely on `{{ user }}`, `{% csrf_token %}`, or anything a context processor
supplies. It extends `base.html` safely because the header's user block is
inside an `{% if user.is_authenticated %}` that simply evaluates false. Test any
change to it the way Django renders it:

    from django.template import loader
    loader.get_template("500.html").render()

## Search engines

The app is marked "do not index" three ways:

- `<meta name="robots">` on every HTML page
- an `X-Robots-Tag` response header on **every** response, applied in
  `payments/middleware.py` - this is what covers the CSV and Excel downloads,
  which cannot carry a meta tag, and the static files, which WhiteNoise serves
  before the rest of the middleware chain runs
- `/robots.txt` returning `Disallow: /`

**These are requests, not access control.** They stop well-behaved crawlers
listing the site; they do not stop anyone who has the URL. Since every page
already requires a login, there is no payment data for a crawler to reach
either way - what this prevents is the sign-in page turning up in search
results.

If the requirement is genuinely "not reachable from the internet", that is a
network control: restrict the OCI security list so the app's port only accepts
traffic from known addresses.

## Branding and static files

The logo lives at `static/img/logo.png` (cropped from the original, kept at
`static/img/DASH_LOGO-original.png`). Favicons are generated from it. Because
the mark is dark purple, it sits on a white plate in the app bar and on the
sign-in card - on the purple bar directly it would disappear.

Static files are served by WhiteNoise, so no separate web server is needed.
Run `collectstatic` after any change to `static/`.

Pillow is not a runtime dependency and is deliberately absent from
`requirements.txt`; it is only needed to regenerate the favicons from a new
logo (`pip install pillow` when you do).

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

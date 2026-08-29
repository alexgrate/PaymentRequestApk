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

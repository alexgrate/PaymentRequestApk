from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "insecure-dev-key")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_filters",
    "axes",
    "payments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Above WhiteNoise on purpose: responses unwind bottom-to-top, so this also
    # stamps the noindex header on static files, which WhiteNoise returns
    # without reaching the rest of the chain.
    "payments.middleware.NoIndexMiddleware",
    # Serves static files without a separate web server - needed once DEBUG is
    # off, since runserver stops serving them.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Must be last: it wraps authentication to record and block failed logins.
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Two databases, deliberately.
#
#   default -> a local SQLite file holding ONLY Django's own housekeeping
#              (users, sessions, admin log). Nothing to do with payments.
#   cba     -> the core banking MySQL. Read-only. The `robot` account holds
#              GRANT SELECT only, and CbaRouter blocks writes and migrations
#              on this side as well.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "local.sqlite3",
    },
    "cba": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("CBA_DB_NAME", "dashmfb-cba-mcs"),
        "USER": os.getenv("CBA_DB_USER", ""),
        "PASSWORD": os.getenv("CBA_DB_PASSWORD", ""),
        "HOST": os.getenv("CBA_DB_HOST", ""),
        "PORT": os.getenv("CBA_DB_PORT", "3306"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "charset": "utf8mb4",
            "connect_timeout": 10,
        },
    },
}

# Local development convenience. With USE_SAMPLE_DB=True the `cba` alias points
# at a local SQLite file holding fabricated rows in the same shape as the real
# table, so the UI can be built without a route to 172.22.0.93. Never enable
# this on the server - it would show fake data.
if os.getenv("USE_SAMPLE_DB", "False").lower() == "true":
    DATABASES["cba"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "sample.sqlite3",
        "HOST": "local sample data (USE_SAMPLE_DB=True)",
    }

DATABASE_ROUTERS = ["payments.routers.CbaRouter"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = False  # The CBA table stores naive datetimes; keep them as written.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "payment-request-list"
LOGOUT_REDIRECT_URL = "login"

# Set to False to mask emails, phone numbers and customer IDs in exports.
EXPORT_INCLUDE_PII = True

# --- Authentication hardening -------------------------------------------------

# Lock an account out after 5 failed attempts, for 30 minutes. Locking on the
# username+IP pair rather than username alone means one attacker cannot lock a
# real user out of their own account from elsewhere.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "payments/locked_out.html"
# By default axes masks the username and IP in its log lines, which defeats the
# purpose of an audit trail. Passwords are masked unconditionally by axes and
# are unaffected by this.
AXES_SENSITIVE_PARAMETERS = []

# Sessions end when the browser closes, and expire after 8 hours regardless.
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True  # sliding window: activity extends the session

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the CSRF cookie must be readable by the form
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# HTTPS-only settings. Enabled whenever DEBUG is off, so a production deploy
# cannot accidentally ship cookies over plain HTTP. If the server sits behind a
# reverse proxy terminating TLS, also set SECURE_PROXY_SSL_HEADER below.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true"
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    if os.getenv("DJANGO_BEHIND_TLS_PROXY", "False").lower() == "true":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# --- Audit logging ------------------------------------------------------------

# Every export is recorded: who, when, which filters, how many rows. The table
# holds customer PII, so downloads need to be traceable.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "audit": {"format": "%(asctime)s %(levelname)s %(message)s"},
    },
    "handlers": {
        "audit_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "audit.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 10,
            "formatter": "audit",
        },
        "console": {"class": "logging.StreamHandler", "formatter": "audit"},
    },
    "loggers": {
        "payments.audit": {
            "handlers": ["audit_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        # WARNING only: failed logins and lockouts reach the audit log, while
        # per-request housekeeping ("cleaned up 0 expired attempts") does not.
        "axes": {"handlers": ["audit_file", "console"], "level": "WARNING",
                 "propagate": False},
    },
}

(BASE_DIR / "logs").mkdir(exist_ok=True)

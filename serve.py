"""Production server.

`runserver` is a development server and should not be used to serve real
traffic. This runs the app under Waitress, which is pure Python and works well
on Windows (gunicorn does not run there).

    py serve.py

Host, port and thread count come from .env so the port can be changed without
touching code - the server already runs other applications on 8000-8002.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

env_file = BASE_DIR / ".env"
if not env_file.exists():
    sys.exit(
        f"No .env at {env_file}\n"
        "Copy .env.example to .env and fill it in before starting the server."
    )
load_dotenv(env_file)

for required in ("DJANGO_SECRET_KEY", "CBA_DB_HOST", "CBA_DB_PASSWORD"):
    if not os.getenv(required):
        sys.exit(f"{required} is not set in {env_file}. Refusing to start.")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from waitress import serve  

from config.wsgi import application  # noqa: E402

host = os.getenv("DJANGO_BIND_HOST", "0.0.0.0")
port = int(os.getenv("DJANGO_PORT", "8500"))
threads = int(os.getenv("DJANGO_THREADS", "8"))

print(f"Payment Requests portal -> http://{host}:{port}  ({threads} threads)", flush=True)
from django.conf import settings  # noqa: E402

cba = settings.DATABASES["cba"]
print(f"Settings: DEBUG={settings.DEBUG}  hosts={settings.ALLOWED_HOSTS}", flush=True)
print(f"Database: {cba.get('HOST') or cba.get('NAME')}", flush=True)
if "sqlite" in cba["ENGINE"]:
    print("WARNING: serving FABRICATED sample data (USE_SAMPLE_DB is set).", flush=True)
trusted_proxy = os.getenv("DJANGO_TRUSTED_PROXY", "127.0.0.1")

serve(
    application,
    host=host,
    port=port,
    threads=threads,
    ident="",
    trusted_proxy=trusted_proxy,
    trusted_proxy_count=1,
    trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
    clear_untrusted_proxy_headers=True,
)

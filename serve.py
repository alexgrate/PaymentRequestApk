"""Production server.

`runserver` is a development server and should not be used to serve real
traffic. This runs the app under Waitress, which is pure Python and works well
on Windows (gunicorn does not run there).

    py serve.py

Host, port and thread count come from .env so the port can be changed without
touching code - the server already runs other applications on 8000-8002.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from waitress import serve  # noqa: E402  (import after settings are configured)

from config.wsgi import application  # noqa: E402

host = os.getenv("DJANGO_BIND_HOST", "0.0.0.0")
port = int(os.getenv("DJANGO_PORT", "8500"))
threads = int(os.getenv("DJANGO_THREADS", "8"))

print(f"Payment Requests portal -> http://{host}:{port}  ({threads} threads)")
print("Ctrl+C to stop.")
serve(application, host=host, port=port, threads=threads, ident="")

import os

# Keep one worker because exporter keeps in-process state and collector thread.
workers = int(os.getenv("EXPORTER_GUNICORN_WORKERS", "1"))
threads = int(os.getenv("EXPORTER_GUNICORN_THREADS", "2"))
bind = os.getenv("EXPORTER_GUNICORN_BIND", "0.0.0.0:9100")
timeout = int(os.getenv("EXPORTER_GUNICORN_TIMEOUT", "60"))
keepalive = int(os.getenv("EXPORTER_GUNICORN_KEEPALIVE", "5"))
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("EXPORTER_GUNICORN_LOG_LEVEL", "info")

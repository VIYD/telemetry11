from pathlib import Path
import os

import yaml

# NOTE: Keep one worker because this app keeps telemetry in process memory
# and runs background scraper/federate threads in-process.
workers = int(os.getenv("GUNICORN_WORKERS", "1"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))


def _load_app_port_from_config(config_path: str | None) -> int | None:
	if not config_path:
		return None

	cfg_file = Path(config_path)
	if not cfg_file.exists():
		return None

	try:
		with cfg_file.open("r", encoding="utf-8") as handle:
			parsed = yaml.safe_load(handle) or {}
	except Exception:
		return None

	if not isinstance(parsed, dict):
		return None

	app_port = parsed.get("app-port")
	if isinstance(app_port, int) and app_port > 0:
		return app_port

	return None


def _resolve_bind() -> str:
	explicit = os.getenv("GUNICORN_BIND")
	if explicit:
		return explicit

	config_path = os.getenv("TELEMETRY_CONFIG")
	app_port = _load_app_port_from_config(config_path)
	if app_port:
		return f"0.0.0.0:{app_port}"

	return "0.0.0.0:5000"


bind = _resolve_bind()
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

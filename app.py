import logging
import os

from flask import Flask

import startup
from routes import register_routes


logger = logging.getLogger("telemetry.app")


def create_app(config_path=None):
    app = Flask(__name__)
    startup.init_app_defaults(app)
    register_routes(app, logger)

    startup.load_runtime_config(app, logger, config_path)
    startup.start_federate_refresher(app, logger)
    startup.start_scraper_if_configured(app, logger)

    return app


env_config = os.environ.get("TELEMETRY_CONFIG")
app = create_app(config_path=env_config)


if __name__ == "__main__":
    raise SystemExit(
        "Direct execution is disabled. Start with Gunicorn, e.g.: "
        "TELEMETRY_CONFIG=examples/config.example.yaml gunicorn -c gunicorn.conf.py app:app"
    )


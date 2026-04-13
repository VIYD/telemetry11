import argparse
import logging
import os

from flask import Flask

import startup
from routes import register_routes


app = Flask(__name__)
logger = logging.getLogger("telemetry.app")
startup.init_app_defaults(app)
register_routes(app, logger)


def _should_start_background_workers(debug_enabled: bool) -> bool:
    # Flask debug reloader runs this module twice:
    # - parent process (monitor)
    # - child process (actual server)
    # Start workers only in the serving process.
    if not debug_enabled:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


if __name__ == "__main__":
    debug_enabled = app.config.get("DEBUG", False)
    parser = argparse.ArgumentParser(description="Telemetry application")
    parser.add_argument(
        "--config",
        help="Path to YAML config file (supports key: push-api, metric-retention)",
    )
    args = parser.parse_args()

    startup.load_runtime_config(app, logger, args.config)
    if _should_start_background_workers(debug_enabled):
        startup.start_federate_refresher(app, logger)

    if _should_start_background_workers(debug_enabled):
        startup.start_scraper_if_configured(app, logger)
    else:
        logger.info("Skipping background workers in Flask reloader parent process")
    logger.info("Starting application host=0.0.0.0 port=%s", app.config.get("APP_PORT", 5000))
    app.run(host="0.0.0.0", port=app.config.get("APP_PORT", 5000), debug=debug_enabled)


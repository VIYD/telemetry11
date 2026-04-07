from datetime import timedelta
import argparse
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error
import json
import logging

from flask import Flask, jsonify, render_template, request
import yaml

import metrics.ingester
import metrics.query
import metrics.storage


app = Flask(__name__)

DEFAULT_RETENTION = timedelta(hours=12)

app.config["PUSH_API_ENABLED"] = True
app.config["METRIC_RETENTION"] = DEFAULT_RETENTION
app.config["RAW_CONFIG"] = {}
app.config["CONFIG_PATH"] = None
app.config["APP_PORT"] = 5000
app.config["SCRAPE_ENDPOINT"] = None
app.config["SCRAPE_INTERVAL_SECONDS"] = 15
app.config["LOG_LEVEL"] = "INFO"

_scraper_started = False
logger = logging.getLogger("telemetry.app")


def parse_metric_retention(value):
    if value is None:
        return DEFAULT_RETENTION

    if isinstance(value, int):
        if value <= 0:
            raise ValueError("Config key 'metric-retention' must be > 0")
        return timedelta(hours=value)

    if isinstance(value, str):
        raw = value.strip().lower()
        if len(raw) < 2:
            raise ValueError("Config key 'metric-retention' must be like '12h' or '30m'")

        unit = raw[-1]
        amount = raw[:-1]
        if not amount.isdigit():
            raise ValueError("Config key 'metric-retention' must be like '12h' or '30m'")

        numeric = int(amount)
        if numeric <= 0:
            raise ValueError("Config key 'metric-retention' must be > 0")

        if unit == "h":
            return timedelta(hours=numeric)
        if unit == "m":
            return timedelta(minutes=numeric)

    raise ValueError(
        "Config key 'metric-retention' must be an int (hours) or string like '12h'/'30m'"
    )


def _format_retention(retention: timedelta) -> str:
    total_minutes = int(retention.total_seconds() // 60)
    if total_minutes % 60 == 0:
        return f"{total_minutes // 60}h"
    return f"{total_minutes}m"


def _parse_positive_int(value, key_name):
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Config key '{key_name}' must be a positive integer")
    return value


def _parse_log_level(value, key_name="log-level"):
    if value is None:
        return "INFO"
    if not isinstance(value, str):
        raise ValueError(f"Config key '{key_name}' must be a string")

    normalized = value.strip().upper()
    allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
    if normalized not in allowed:
        raise ValueError(
            f"Config key '{key_name}' must be one of: {', '.join(sorted(allowed))}"
        )
    return normalized


def configure_logging(level_name: str):
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    logger.info("Logging configured at level=%s", level_name)


def _extract_pull_config(parsed: dict):
    pull_cfg = parsed.get("pull")
    if pull_cfg is None:
        return None, None
    if not isinstance(pull_cfg, dict):
        raise ValueError("Config key 'pull' must be an object")

    endpoint = pull_cfg.get("endpoint")
    if endpoint is not None and not isinstance(endpoint, str):
        raise ValueError("Config key 'pull.endpoint' must be a string")

    interval = pull_cfg.get("scrape-interval-seconds")
    interval = _parse_positive_int(interval, "pull.scrape-interval-seconds")
    return endpoint, interval


def scrape_metrics_once(endpoint: str):
    logger.debug("Scraping metrics from endpoint=%s", endpoint)
    with urllib.request.urlopen(endpoint, timeout=5) as response:
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)

    metrics_list = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(metrics_list, list):
        return 0

    added = 0
    for item in metrics_list:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}

        if not isinstance(name, str):
            continue

        merged_labels = dict(labels)
        merged_labels["method"] = "scraped"
        metrics.ingester.add_metric(name=name, value=value, labels=merged_labels)
        added += 1

    logger.info("Scrape complete endpoint=%s added_metrics=%s", endpoint, added)
    return added


def _scrape_loop(endpoint: str, interval: int):
    logger.info("Background scraper loop started endpoint=%s interval=%ss", endpoint, interval)
    while True:
        try:
            scrape_metrics_once(endpoint)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Scrape failed endpoint=%s error=%s", endpoint, exc)
        time.sleep(interval)


def start_scraper_if_configured():
    global _scraper_started
    if _scraper_started:
        return

    endpoint = app.config.get("SCRAPE_ENDPOINT")
    interval = app.config.get("SCRAPE_INTERVAL_SECONDS")
    if not endpoint or not interval:
        logger.info("Scraper disabled (missing pull.endpoint or pull.scrape-interval-seconds)")
        return

    thread = threading.Thread(target=_scrape_loop, args=(endpoint, interval), daemon=True)
    thread.start()
    _scraper_started = True
    logger.info("Scraper thread started endpoint=%s interval=%ss", endpoint, interval)


def load_runtime_config(config_path=None):
    app.config["PUSH_API_ENABLED"] = True
    app.config["METRIC_RETENTION"] = DEFAULT_RETENTION
    app.config["RAW_CONFIG"] = {}
    app.config["CONFIG_PATH"] = config_path
    app.config["APP_PORT"] = 5000
    app.config["SCRAPE_ENDPOINT"] = None
    app.config["SCRAPE_INTERVAL_SECONDS"] = 15
    app.config["LOG_LEVEL"] = "INFO"

    if not config_path:
        configure_logging(app.config["LOG_LEVEL"])
        logger.info("No config path provided, using defaults")
        return

    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    with cfg_file.open("r", encoding="utf-8") as f:
        parsed = yaml.safe_load(f) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Config file root must be a YAML object")

    app.config["RAW_CONFIG"] = parsed

    app.config["LOG_LEVEL"] = _parse_log_level(parsed.get("log-level"), "log-level")
    configure_logging(app.config["LOG_LEVEL"])
    logger.info("Loaded config file path=%s", config_path)

    push_api = parsed.get("push-api")
    if push_api is not None and not isinstance(push_api, bool):
        raise ValueError("Config key 'push-api' must be a boolean")
    if isinstance(push_api, bool):
        app.config["PUSH_API_ENABLED"] = push_api

    app.config["METRIC_RETENTION"] = parse_metric_retention(parsed.get("metric-retention"))

    app_port = parsed.get("app-port")
    if app_port is not None:
        app.config["APP_PORT"] = _parse_positive_int(app_port, "app-port")

    endpoint, interval = _extract_pull_config(parsed)
    if endpoint:
        app.config["SCRAPE_ENDPOINT"] = endpoint
    if interval:
        app.config["SCRAPE_INTERVAL_SECONDS"] = interval

    logger.info(
        "Effective config push_api=%s retention=%s app_port=%s scrape_endpoint=%s scrape_interval=%s log_level=%s",
        app.config["PUSH_API_ENABLED"],
        _format_retention(app.config["METRIC_RETENTION"]),
        app.config["APP_PORT"],
        app.config["SCRAPE_ENDPOINT"],
        app.config["SCRAPE_INTERVAL_SECONDS"],
        app.config["LOG_LEVEL"],
    )


@app.before_request
def apply_metric_retention_policy():
    retention = app.config.get("METRIC_RETENTION", DEFAULT_RETENTION)
    metrics.storage.prune_old_metrics(retention)
    logger.debug("Applied retention pruning retention=%s", retention)


@app.route("/")
def home():
    return render_template("home.html", active_page="home")


@app.route("/dashboard")
@app.route("/query")
def query_page():
    metric = request.args.get("metric")
    minutes = request.args.get("minutes", default=15, type=int)
    if minutes is None or minutes <= 0:
        minutes = 15

    data = None
    if metric:
        data = metrics.query.get_series_for_chart(metrics.storage.metrics_storage, metric, minutes)
        logger.debug("Query request metric=%s minutes=%s has_data=%s", metric, minutes, data is not None)

    return render_template(
        "query.html",
        active_page="query",
        metric=metric,
        minutes=minutes,
        data=data,
    )


@app.route("/status")
def status_page():
    raw_config = app.config.get("RAW_CONFIG", {})
    retention = app.config.get("METRIC_RETENTION", DEFAULT_RETENTION)

    effective_settings = {
        "push-api": app.config.get("PUSH_API_ENABLED", True),
        "metric-retention": _format_retention(retention),
        "app-port": app.config.get("APP_PORT", 5000),
        "pull.endpoint": app.config.get("SCRAPE_ENDPOINT") or "(disabled)",
        "pull.scrape-interval-seconds": app.config.get("SCRAPE_INTERVAL_SECONDS"),
        "log-level": app.config.get("LOG_LEVEL", "INFO"),
    }

    return render_template(
        "status.html",
        active_page="status",
        config_path=app.config.get("CONFIG_PATH") or "(no --config provided)",
        raw_config=raw_config,
        effective_settings=effective_settings,
    )


@app.route("/federate")
def federate_metrics():
    return metrics.storage.federate_metrics()


@app.route("/api/metrics")
def api_metrics():
    metric = request.args.get("metric")
    if not metric:
        return jsonify({"error": "metric query parameter is required"}), 400

    minutes = request.args.get("minutes", default=15, type=int)
    if minutes is None or minutes <= 0:
        return jsonify({"error": "minutes must be a positive integer"}), 400

    data = metrics.query.get_series_for_api(metrics.storage.metrics_storage, metric, minutes)

    if data is None:
        return jsonify(
            {
                "metric": metric,
                "series": [],
                "start": None,
                "end": None,
                "window_minutes": minutes,
            }
        )

    return jsonify(data)


@app.route("/push", methods=["POST"])
def push_metrics():
    if not app.config.get("PUSH_API_ENABLED", True):
        logger.warning("Push request rejected because push-api is disabled")
        return jsonify({"error": "push api is disabled"}), 503
    logger.debug("Push request accepted")
    return metrics.ingester.ingest_metric(request, forced_labels={"method": "push"})


@app.route("/debug/populate")
def debug_populate():
    metrics.storage.debug_populate()
    logger.info("Debug population invoked")
    return "Debug population completed."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telemetry application")
    parser.add_argument(
        "--config",
        help="Path to YAML config file (supports key: push-api, metric-retention)",
    )
    args = parser.parse_args()

    load_runtime_config(args.config)
    start_scraper_if_configured()
    logger.info("Starting application host=0.0.0.0 port=%s", app.config.get("APP_PORT", 5000))
    app.run(host="0.0.0.0", port=app.config.get("APP_PORT", 5000), debug=True)


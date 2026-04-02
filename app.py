from datetime import timedelta
import argparse
from pathlib import Path

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


def load_runtime_config(config_path=None):
    app.config["PUSH_API_ENABLED"] = True
    app.config["METRIC_RETENTION"] = DEFAULT_RETENTION
    app.config["RAW_CONFIG"] = {}
    app.config["CONFIG_PATH"] = config_path

    if not config_path:
        return

    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    with cfg_file.open("r", encoding="utf-8") as f:
        parsed = yaml.safe_load(f) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Config file root must be a YAML object")

    app.config["RAW_CONFIG"] = parsed

    push_api = parsed.get("push-api")
    if push_api is not None and not isinstance(push_api, bool):
        raise ValueError("Config key 'push-api' must be a boolean")
    if isinstance(push_api, bool):
        app.config["PUSH_API_ENABLED"] = push_api

    app.config["METRIC_RETENTION"] = parse_metric_retention(parsed.get("metric-retention"))


@app.before_request
def apply_metric_retention_policy():
    retention = app.config.get("METRIC_RETENTION", DEFAULT_RETENTION)
    metrics.storage.prune_old_metrics(retention)


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
        return jsonify({"error": "push api is disabled"}), 503
    return metrics.ingester.ingest_metric(request, forced_labels={"method": "push"})


@app.route("/debug/populate")
def debug_populate():
    metrics.storage.debug_populate()
    return "Debug population completed."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telemetry application")
    parser.add_argument(
        "--config",
        help="Path to YAML config file (supports key: push-api, metric-retention)",
    )
    args = parser.parse_args()

    load_runtime_config(args.config)
    app.run(host="0.0.0.0", port=5000, debug=True)


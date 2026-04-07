import argparse
import socket
import threading
import time
import logging

import psutil
import yaml
from flask import Flask, jsonify


app = Flask(__name__)

DEFAULT_REFRESH_SECONDS = 5
DEFAULT_PORT = 9100

state = {
    "refresh-seconds": DEFAULT_REFRESH_SECONDS,
    "port": DEFAULT_PORT,
    "log-level": "INFO",
    "metrics": [],
}

logger = logging.getLogger("telemetry.exporter")


def parse_log_level(value):
    if value is None:
        return "INFO"
    if not isinstance(value, str):
        raise ValueError("Exporter config key 'log-level' must be a string")

    normalized = value.strip().upper()
    allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
    if normalized not in allowed:
        raise ValueError(
            f"Exporter config key 'log-level' must be one of: {', '.join(sorted(allowed))}"
        )
    return normalized


def configure_logging(level_name: str):
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    logger.info("Exporter logging configured level=%s", level_name)


def load_config(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        parsed = yaml.safe_load(f) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Exporter config root must be a YAML object")

    refresh = parsed.get("refresh-seconds", DEFAULT_REFRESH_SECONDS)
    port = parsed.get("port", DEFAULT_PORT)
    log_level = parse_log_level(parsed.get("log-level"))

    if not isinstance(refresh, int) or refresh <= 0:
        raise ValueError("Exporter config key 'refresh-seconds' must be a positive integer")
    if not isinstance(port, int) or port <= 0:
        raise ValueError("Exporter config key 'port' must be a positive integer")

    state["refresh-seconds"] = refresh
    state["port"] = port
    state["log-level"] = log_level

    configure_logging(log_level)
    logger.info(
        "Loaded exporter config path=%s refresh_seconds=%s port=%s log_level=%s",
        config_path,
        refresh,
        port,
        log_level,
    )


def collect_metrics_once():
    host = socket.gethostname()
    mem = psutil.virtual_memory()

    state["metrics"] = [
        {"name": "cpu_percent", "labels": {"host": host}, "value": psutil.cpu_percent(interval=None)},
        {"name": "memory_percent", "labels": {"host": host}, "value": mem.percent},
        {"name": "memory_used_bytes", "labels": {"host": host}, "value": mem.used},
        {"name": "memory_available_bytes", "labels": {"host": host}, "value": mem.available},
    ]
    logger.debug("Collected metrics count=%s host=%s", len(state["metrics"]), host)


def collector_loop():
    logger.info("Exporter collector loop started refresh_seconds=%s", state["refresh-seconds"])
    while True:
        collect_metrics_once()
        time.sleep(state["refresh-seconds"])


@app.route("/metrics")
def metrics():
    logger.debug("Serving /metrics count=%s", len(state["metrics"]))
    return jsonify({"metrics": state["metrics"]})


@app.route("/health")
def health():
    logger.debug("Serving /health")
    return jsonify({"status": "ok", "metrics_count": len(state["metrics"])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="System metrics exporter")
    parser.add_argument(
        "--config",
        default="exporter/config.yaml",
        help="Path to exporter config yaml",
    )
    args = parser.parse_args()

    load_config(args.config)
    collect_metrics_once()

    thread = threading.Thread(target=collector_loop, daemon=True)
    thread.start()

    logger.info("Starting exporter host=0.0.0.0 port=%s", state["port"])
    app.run(host="0.0.0.0", port=state["port"], debug=False)

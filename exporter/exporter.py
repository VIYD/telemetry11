import argparse
import socket
import threading
import time

import psutil
import yaml
from flask import Flask, jsonify


app = Flask(__name__)

DEFAULT_REFRESH_SECONDS = 5
DEFAULT_PORT = 9100

state = {
    "refresh-seconds": DEFAULT_REFRESH_SECONDS,
    "port": DEFAULT_PORT,
    "metrics": [],
}


def load_config(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        parsed = yaml.safe_load(f) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Exporter config root must be a YAML object")

    refresh = parsed.get("refresh-seconds", DEFAULT_REFRESH_SECONDS)
    port = parsed.get("port", DEFAULT_PORT)

    if not isinstance(refresh, int) or refresh <= 0:
        raise ValueError("Exporter config key 'refresh-seconds' must be a positive integer")
    if not isinstance(port, int) or port <= 0:
        raise ValueError("Exporter config key 'port' must be a positive integer")

    state["refresh-seconds"] = refresh
    state["port"] = port


def collect_metrics_once():
    host = socket.gethostname()
    mem = psutil.virtual_memory()

    state["metrics"] = [
        {"name": "cpu_percent", "labels": {"host": host}, "value": psutil.cpu_percent(interval=None)},
        {"name": "memory_percent", "labels": {"host": host}, "value": mem.percent},
        {"name": "memory_used_bytes", "labels": {"host": host}, "value": mem.used},
        {"name": "memory_available_bytes", "labels": {"host": host}, "value": mem.available},
    ]


def collector_loop():
    while True:
        collect_metrics_once()
        time.sleep(state["refresh-seconds"])


@app.route("/metrics")
def metrics():
    return jsonify({"metrics": state["metrics"]})


@app.route("/health")
def health():
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

    app.run(host="0.0.0.0", port=state["port"], debug=False)

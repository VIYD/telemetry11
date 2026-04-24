import os
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
_collector_started = False
_collector_lock = threading.Lock()


def _add_metric(metrics_list, name, value, labels=None):
    if value is None:
        return
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)):
        metrics_list.append(
            {
                "name": name,
                "labels": labels or {},
                "value": value,
            }
        )


def _safe_call(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


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
    host_labels = {"host": host}
    metrics = []

    mem = _safe_call(psutil.virtual_memory)
    swap = _safe_call(psutil.swap_memory)
    cpu_times = _safe_call(psutil.cpu_times)
    disk_io = _safe_call(psutil.disk_io_counters)
    net_io = _safe_call(psutil.net_io_counters)

    # CPU metrics
    _add_metric(metrics, "cpu_percent", _safe_call(lambda: psutil.cpu_percent(interval=None)), host_labels)
    _add_metric(metrics, "cpu_count_logical", _safe_call(psutil.cpu_count), host_labels)
    _add_metric(metrics, "cpu_count_physical", _safe_call(lambda: psutil.cpu_count(logical=False)), host_labels)
    load_avg = _safe_call(psutil.getloadavg)
    if load_avg:
        _add_metric(metrics, "loadavg_1m", load_avg[0], host_labels)
        _add_metric(metrics, "loadavg_5m", load_avg[1], host_labels)
        _add_metric(metrics, "loadavg_15m", load_avg[2], host_labels)
    cpu_freq = _safe_call(psutil.cpu_freq)
    if cpu_freq:
        _add_metric(metrics, "cpu_freq_current_mhz", cpu_freq.current, host_labels)
        _add_metric(metrics, "cpu_freq_min_mhz", cpu_freq.min, host_labels)
        _add_metric(metrics, "cpu_freq_max_mhz", cpu_freq.max, host_labels)
    if cpu_times:
        _add_metric(metrics, "cpu_time_user_seconds", cpu_times.user, host_labels)
        _add_metric(metrics, "cpu_time_system_seconds", cpu_times.system, host_labels)
        _add_metric(metrics, "cpu_time_idle_seconds", cpu_times.idle, host_labels)

    # Memory metrics
    if mem:
        _add_metric(metrics, "memory_percent", mem.percent, host_labels)
        _add_metric(metrics, "memory_total_bytes", mem.total, host_labels)
        _add_metric(metrics, "memory_used_bytes", mem.used, host_labels)
        _add_metric(metrics, "memory_available_bytes", mem.available, host_labels)
        _add_metric(metrics, "memory_free_bytes", getattr(mem, "free", None), host_labels)
        _add_metric(metrics, "memory_cached_bytes", getattr(mem, "cached", None), host_labels)
        _add_metric(metrics, "memory_buffers_bytes", getattr(mem, "buffers", None), host_labels)
    if swap:
        _add_metric(metrics, "swap_total_bytes", swap.total, host_labels)
        _add_metric(metrics, "swap_used_bytes", swap.used, host_labels)
        _add_metric(metrics, "swap_free_bytes", swap.free, host_labels)
        _add_metric(metrics, "swap_percent", swap.percent, host_labels)

    # Disk metrics
    root_disk = _safe_call(lambda: psutil.disk_usage("/"))
    if root_disk:
        _add_metric(metrics, "disk_root_total_bytes", root_disk.total, host_labels)
        _add_metric(metrics, "disk_root_used_bytes", root_disk.used, host_labels)
        _add_metric(metrics, "disk_root_free_bytes", root_disk.free, host_labels)
        _add_metric(metrics, "disk_root_percent", root_disk.percent, host_labels)
    if disk_io:
        _add_metric(metrics, "disk_read_bytes_total", disk_io.read_bytes, host_labels)
        _add_metric(metrics, "disk_write_bytes_total", disk_io.write_bytes, host_labels)
        _add_metric(metrics, "disk_read_count_total", disk_io.read_count, host_labels)
        _add_metric(metrics, "disk_write_count_total", disk_io.write_count, host_labels)

    # Network metrics
    if net_io:
        _add_metric(metrics, "network_bytes_sent_total", net_io.bytes_sent, host_labels)
        _add_metric(metrics, "network_bytes_recv_total", net_io.bytes_recv, host_labels)
        _add_metric(metrics, "network_packets_sent_total", net_io.packets_sent, host_labels)
        _add_metric(metrics, "network_packets_recv_total", net_io.packets_recv, host_labels)
        _add_metric(metrics, "network_errin_total", net_io.errin, host_labels)
        _add_metric(metrics, "network_errout_total", net_io.errout, host_labels)
        _add_metric(metrics, "network_dropin_total", net_io.dropin, host_labels)
        _add_metric(metrics, "network_dropout_total", net_io.dropout, host_labels)

    # System/runtime metrics
    _add_metric(metrics, "process_count", _safe_call(lambda: len(psutil.pids())), host_labels)
    _add_metric(metrics, "boot_time_unix", _safe_call(psutil.boot_time), host_labels)
    now_unix = time.time()
    boot_time = _safe_call(psutil.boot_time)
    if boot_time:
        _add_metric(metrics, "uptime_seconds", max(0, now_unix - boot_time), host_labels)

    state["metrics"] = metrics
    logger.debug("Collected metrics count=%s host=%s", len(state["metrics"]), host)


def collector_loop():
    logger.info("Exporter collector loop started refresh_seconds=%s", state["refresh-seconds"])
    while True:
        collect_metrics_once()
        time.sleep(state["refresh-seconds"])


def _start_collector_if_needed():
    global _collector_started
    with _collector_lock:
        if _collector_started:
            return
        thread = threading.Thread(target=collector_loop, daemon=True)
        thread.start()
        _collector_started = True


def create_app(config_path=None):
    resolved = config_path or os.environ.get("EXPORTER_CONFIG") or "examples/exporter-config.example.yaml"
    load_config(resolved)
    collect_metrics_once()
    _start_collector_if_needed()
    return app


@app.route("/metrics")
def metrics():
    logger.debug("Serving /metrics count=%s", len(state["metrics"]))
    return jsonify({"metrics": state["metrics"]})


@app.route("/health")
def health():
    logger.debug("Serving /health")
    return jsonify({"status": "ok", "metrics_count": len(state["metrics"])})


app = create_app()


if __name__ == "__main__":
    raise SystemExit(
        "Direct execution is disabled. Start with Gunicorn, e.g.: "
        "EXPORTER_CONFIG=examples/exporter-config.example.yaml "
        "gunicorn -c exporter/gunicorn.conf.py exporter.exporter:app"
    )

# metrics/storage.py
from datetime import datetime, timezone, timedelta
import threading
from flask import jsonify

metrics_storage = {}
_federated_cache_lock = threading.RLock()
_federated_cache = {"metrics": [], "refreshed_at": None}
_federate_max_age_seconds = 60


def set_federate_max_age_seconds(seconds: int):
    global _federate_max_age_seconds
    if isinstance(seconds, int) and seconds > 0:
        _federate_max_age_seconds = seconds


def prune_old_metrics(retention):
    if retention is None:
        return

    cutoff = datetime.now(timezone.utc) - retention
    keys_to_delete = []

    for key, entries in metrics_storage.items():
        kept = []
        for point in entries:
            try:
                ts = datetime.fromisoformat(point["timestamp"])
            except (TypeError, ValueError, KeyError):
                continue

            if ts >= cutoff:
                kept.append(point)

        if kept:
            metrics_storage[key] = kept
        else:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        metrics_storage.pop(key, None)


def _escape_label_value(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_labels(labels):
    if not labels:
        return ""
    parts = []
    for key in sorted(labels.keys()):
        val = _escape_label_value(str(labels[key]))
        parts.append(f'{key}="{val}"')
    return "{" + ",".join(parts) + "}"


def make_metric_key(name, labels=None):
    return name + format_labels(labels or {})


def parse_metric_key(key: str):
    if "{" not in key:
        return key, {}
    name, rest = key.split("{", 1)
    if not rest.endswith("}"):
        return key, {}
    inner = rest[:-1]
    labels = {}
    if not inner:
        return name, labels
    for part in inner.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        v = v.replace('\\\\', '\\').replace('\\"', '"')
        labels[k] = v
    return name, labels


def debug_populate():
    import random
    from datetime import datetime, timezone, timedelta

    names = ["cpu_usage", "memory_usage", "disk_io", "network_traffic"]
    now = datetime.now(timezone.utc)

    for name in names:
        entries = []
        for i in range(10):
            timestamp = (now - timedelta(minutes=10 - i)).isoformat()
            value = random.uniform(0, 100)
            entries.append({"timestamp": timestamp, "value": value})
        metrics_storage[name] = entries

# def return_metrics():
#     sorted_metrics = {}
#     for name, entries in metrics_storage.items():
#         sorted_entries = sorted(entries, key=lambda x: x['timestamp'])
#         sorted_metrics[name] = sorted_entries
#     return jsonify(sorted_metrics)

def return_metrics():
    return jsonify(metrics_storage)


def federate_metrics():
    with _federated_cache_lock:
        if _federated_cache["refreshed_at"] is None:
            refresh_federated_metrics_cache()
        return jsonify(dict(_federated_cache))


def refresh_federated_metrics_cache():
    federated = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=_federate_max_age_seconds)

    for key, entries in metrics_storage.items():
        if not entries:
            continue

        latest = max(entries, key=lambda e: datetime.fromisoformat(e["timestamp"]))
        latest_ts = datetime.fromisoformat(latest["timestamp"])
        if latest_ts < cutoff:
            continue

        name, labels = parse_metric_key(key)

        federated.append(
            {
                "name": name,
                "labels": labels,
                "value": latest.get("value"),
            }
        )

    snapshot = {
        "metrics": federated,
        "refreshed_at": now.isoformat(),
    }

    with _federated_cache_lock:
        _federated_cache["metrics"] = snapshot["metrics"]
        _federated_cache["refreshed_at"] = snapshot["refreshed_at"]

    return snapshot
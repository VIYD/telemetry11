# metrics/storage.py
from datetime import datetime, timezone, timedelta
from flask import jsonify

metrics_storage = {}


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
    federated = []

    for key, entries in metrics_storage.items():
        if not entries:
            continue

        latest = max(entries, key=lambda e: datetime.fromisoformat(e["timestamp"]))
        name, labels = parse_metric_key(key)

        federated.append(
            {
                "name": name,
                "labels": labels,
                "value": latest.get("value"),
            }
        )

    return jsonify({"metrics": federated})
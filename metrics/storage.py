# metrics/storage.py
from datetime import datetime, timezone, timedelta
from flask import jsonify

metrics_storage = {}

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
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=1)

    federated = {}
    for name, entries in metrics_storage.items():
        recent_entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= cutoff]
        if recent_entries:
            federated[name] = recent_entries

    return jsonify(federated)
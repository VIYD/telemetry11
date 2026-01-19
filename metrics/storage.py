# metrics/storage.py
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

def return_metrics(): #sorted by timestamp
    sorted_metrics = {}
    for name, entries in metrics_storage.items():
        sorted_entries = sorted(entries, key=lambda x: x['timestamp'])
        sorted_metrics[name] = sorted_entries
    return jsonify(sorted_metrics)
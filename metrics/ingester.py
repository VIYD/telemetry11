import psutil
from datetime import datetime, timezone
from metrics.storage import metrics_storage
from flask import jsonify

def ingest_metric(request):
    data = request.json
    if not data or "name" not in data or "value" not in data:
        return jsonify({"error": "Invalid payload"}), 400

    timestamp = datetime.now(timezone.utc).isoformat()
    storage_list = metrics_storage.setdefault(data["name"], [])
    storage_list.append({"timestamp": timestamp, "value": data["value"]})
    # storage_list.sort(key=lambda x: x['timestamp'])
    return jsonify({"status": "ok", "added": {"name": data["name"], "timestamp": timestamp, "value": data["value"]}}), 201

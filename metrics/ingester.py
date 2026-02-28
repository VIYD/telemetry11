import psutil
from datetime import datetime, timezone
from metrics.storage import metrics_storage, make_metric_key
from flask import jsonify


def ingest_metric(request):
    data = request.json
    if not data or "name" not in data or "value" not in data:
        return jsonify({"error": "Invalid payload"}), 400
    
    # Validate that name is a string and not empty
    if not isinstance(data["name"], str) or not data["name"].strip():
        return jsonify({"error": "Invalid metric name: must be a non-empty string"}), 400
    
    # Validate that value is numeric (int or float), but not boolean
    # Note: In Python, bool is a subclass of int, so we explicitly check for it
    if isinstance(data["value"], bool) or not isinstance(data["value"], (int, float)):
        return jsonify({"error": "Invalid metric value: must be a number (int or float)"}), 400

    labels = data.get("labels")
    if labels is not None and not isinstance(labels, dict):
        return jsonify({"error": "labels must be an object"}), 400

    metric_key = make_metric_key(data["name"], labels or {})

    timestamp = datetime.now(timezone.utc).isoformat()
    storage_list = metrics_storage.setdefault(metric_key, [])
    storage_list.append({"timestamp": timestamp, "value": data["value"]})
    # storage_list.sort(key=lambda x: x['timestamp'])
    return (
        jsonify(
            {
                "status": "ok",
                "added": {
                    "name": data["name"],
                    "labels": labels or {},
                    "timestamp": timestamp,
                    "value": data["value"],
                },
            }
        ),
        201,
    )

import psutil
from datetime import datetime, timezone
from metrics.storage import metrics_storage
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

    timestamp = datetime.now(timezone.utc).isoformat()
    storage_list = metrics_storage.setdefault(data["name"], [])
    storage_list.append({"timestamp": timestamp, "value": data["value"]})
    return jsonify({"status": "ok", "added": {"name": data["name"], "value": data["value"]}}), 201

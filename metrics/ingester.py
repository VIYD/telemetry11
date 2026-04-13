from datetime import datetime, timezone
from metrics.storage import metrics_storage, make_metric_key
from flask import jsonify


def add_metric(name, value, labels=None):
    merged_labels = dict(labels or {})
    metric_key = make_metric_key(name, merged_labels)

    timestamp = datetime.now(timezone.utc).isoformat()
    storage_list = metrics_storage.setdefault(metric_key, [])
    storage_list.append({"timestamp": timestamp, "value": value})

    return {
        "name": name,
        "labels": merged_labels,
        "timestamp": timestamp,
        "value": value,
    }


def ingest_metric(request, forced_labels=None):
    data = request.json
    if not data or "name" not in data or "value" not in data:
        return jsonify({"error": "Invalid payload"}), 400

    labels = data.get("labels")
    if labels is not None and not isinstance(labels, dict):
        return jsonify({"error": "labels must be an object"}), 400

    merged_labels = dict(labels or {})
    if forced_labels:
        merged_labels.update(forced_labels)

    added_metric = add_metric(data["name"], data["value"], merged_labels)

    return (
        jsonify(
            {
                "status": "ok",
                "added": added_metric,
            }
        ),
        201,
    )

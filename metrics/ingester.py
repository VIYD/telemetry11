from datetime import datetime, timezone
from metrics.storage import metrics_storage, make_metric_key
from flask import jsonify


INTERNAL_LABEL_KEY = "label"
INTERNAL_LABEL_VALUE = "internal"
INTERNAL_PREFIX = "internal_"
_internal_metrics_enabled = True


def set_internal_metrics_enabled(enabled: bool):
    global _internal_metrics_enabled
    _internal_metrics_enabled = bool(enabled)


def internal_labels(extra_labels=None):
    merged = dict(extra_labels or {})
    merged.setdefault(INTERNAL_LABEL_KEY, INTERNAL_LABEL_VALUE)
    return merged


def emit_internal_storage_stats():
    if not _internal_metrics_enabled:
        return
    total_series = len(metrics_storage)
    total_points = sum(len(entries) for entries in metrics_storage.values())
    add_metric(
        f"{INTERNAL_PREFIX}total_time_series",
        total_series,
        internal_labels(),
        emit_internal_stats=False,
    )
    add_metric(
        f"{INTERNAL_PREFIX}total_metrics",
        total_points,
        internal_labels(),
        emit_internal_stats=False,
    )


def add_metric(name, value, labels=None, emit_internal_stats=True):
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

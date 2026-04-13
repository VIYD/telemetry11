from datetime import datetime, timezone

from metrics.storage import parse_metric_key


def build_metrics_catalog(storage: dict):
    now = datetime.now(timezone.utc)
    by_name = {}

    for key, entries in storage.items():
        name, labels = parse_metric_key(key)
        item = by_name.setdefault(
            name,
            {
                "name": name,
                "series_count": 0,
                "points_count": 0,
                "label_keys": set(),
                "label_samples": [],
                "last_seen": None,
                "last_value": None,
                "freshness_seconds": None,
            },
        )

        item["series_count"] += 1
        item["points_count"] += len(entries)

        for lk in labels.keys():
            item["label_keys"].add(lk)

        if labels and len(item["label_samples"]) < 5:
            item["label_samples"].append(labels)

        if not entries:
            continue

        latest = max(entries, key=lambda e: datetime.fromisoformat(e["timestamp"]))
        latest_ts = datetime.fromisoformat(latest["timestamp"])

        if item["last_seen"] is None or latest_ts > item["last_seen"]:
            item["last_seen"] = latest_ts
            item["last_value"] = latest.get("value")

    result = []
    for item in by_name.values():
        if item["last_seen"] is not None:
            item["freshness_seconds"] = int((now - item["last_seen"]).total_seconds())
            item["last_seen"] = item["last_seen"].isoformat()
        item["label_keys"] = sorted(item["label_keys"])
        result.append(item)

    result.sort(key=lambda x: x["name"])
    return result

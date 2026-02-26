from datetime import datetime, timezone, timedelta
from metrics.storage import parse_metric_key

DEFAULT_RANGE_MINUTES = 15


def _labels_match(labels: dict, selector: dict | None) -> bool:
    if not selector:
        return True
    for k, v in selector.items():
        if labels.get(k) != v:
            return False
    return True


def _select_metric_keys(storage: dict, metric_selector: str):
    """Return list of storage keys matching the selector."""
    if metric_selector in storage:
        keys = [metric_selector]
    else:
        base_name, selector_labels = parse_metric_key(metric_selector)
        keys = []
        for key in storage.keys():
            name, labels = parse_metric_key(key)
            if name != base_name:
                continue
            if not _labels_match(labels, selector_labels):
                continue
            keys.append(key)

    return keys


def get_series_for_chart(storage: dict, metric_selector: str, minutes: int = DEFAULT_RANGE_MINUTES):
    """
    metric_selector can be:
      - exact key in storage, e.g. 'cpu{env="dev",host="laptop"}'
      - base name, e.g. 'cpu' (matches all label sets for that metric)
      - name with label filter, e.g. 'cpu{env="dev"}' (matches all series with env=dev)
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=minutes)

    series_list = []

    keys = _select_metric_keys(storage, metric_selector)

    for key in keys:
        points = []
        for point in storage.get(key, []):
            ts = datetime.fromisoformat(point["timestamp"])
            if ts >= start_time:
                points.append(
                    {
                        "x": int(ts.timestamp() * 1000),  # epoch ms
                        "y": point["value"],
                    }
                )
        if points:
            series_list.append({"name": key, "points": points})

    if not series_list:
        return None

    return {
        "series": series_list,
        "start": int(start_time.timestamp() * 1000),
        "end": int(now.timestamp() * 1000),
        "window_minutes": minutes,
    }


def get_series_for_api(storage: dict, metric_selector: str, minutes: int = DEFAULT_RANGE_MINUTES):
    """
    API-friendly representation:
      - decodes metric keys into name + labels
      - returns raw timestamps and values, not x/y points
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=minutes)

    keys = _select_metric_keys(storage, metric_selector)
    if not keys:
        return None

    series_list = []

    for key in keys:
        name, labels = parse_metric_key(key)
        points = []
        for point in storage.get(key, []):
            ts = datetime.fromisoformat(point["timestamp"])
            if ts >= start_time:
                points.append(
                    {
                        "timestamp": point["timestamp"],
                        "value": point["value"],
                    }
                )
        if points:
            series_list.append(
                {
                    "name": name,
                    "labels": labels,
                    "points": points,
                }
            )

    if not series_list:
        return None

    return {
        "metric": metric_selector,
        "series": series_list,
        "start": start_time.isoformat(),
        "end": now.isoformat(),
        "window_minutes": minutes,
    }

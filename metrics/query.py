from datetime import datetime, timezone, timedelta
from metrics.storage import parse_metric_key

DEFAULT_RANGE_MINUTES = 15


def parse_time_param(value: str | None, browser_tz_offset_minutes: int | None = None):
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        if browser_tz_offset_minutes is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            local_tz = timezone(timedelta(minutes=-browser_tz_offset_minutes))
            parsed = parsed.replace(tzinfo=local_tz).astimezone(timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _resolve_window(minutes: int, start_time=None, end_time=None):
    now = datetime.now(timezone.utc)
    resolved_end = end_time or now
    resolved_start = start_time or (resolved_end - timedelta(minutes=minutes))
    if resolved_start >= resolved_end:
        raise ValueError("start must be before end")

    span_minutes = max(1, int((resolved_end - resolved_start).total_seconds() // 60))
    return resolved_start, resolved_end, span_minutes


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


def get_series_for_chart(
    storage: dict,
    metric_selector: str,
    minutes: int = DEFAULT_RANGE_MINUTES,
    start_time=None,
    end_time=None,
):
    """
    metric_selector can be:
      - exact key in storage, e.g. 'cpu{env="dev",host="laptop"}'
      - base name, e.g. 'cpu' (matches all label sets for that metric)
      - name with label filter, e.g. 'cpu{env="dev"}' (matches all series with env=dev)
    """
    start_time, end_time, span_minutes = _resolve_window(minutes, start_time=start_time, end_time=end_time)

    series_list = []

    keys = _select_metric_keys(storage, metric_selector)

    for key in keys:
        points = []
        for point in storage.get(key, []):
            ts = datetime.fromisoformat(point["timestamp"])
            if start_time <= ts <= end_time:
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
        "end": int(end_time.timestamp() * 1000),
        "window_minutes": span_minutes,
    }


def get_series_for_api(
    storage: dict,
    metric_selector: str,
    minutes: int = DEFAULT_RANGE_MINUTES,
    start_time=None,
    end_time=None,
):
    """
    API-friendly representation:
      - decodes metric keys into name + labels
      - returns raw timestamps and values, not x/y points
    """
    start_time, end_time, span_minutes = _resolve_window(minutes, start_time=start_time, end_time=end_time)

    keys = _select_metric_keys(storage, metric_selector)
    if not keys:
        return None

    series_list = []

    for key in keys:
        name, labels = parse_metric_key(key)
        points = []
        for point in storage.get(key, []):
            ts = datetime.fromisoformat(point["timestamp"])
            if start_time <= ts <= end_time:
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
        "end": end_time.isoformat(),
        "window_minutes": span_minutes,
    }

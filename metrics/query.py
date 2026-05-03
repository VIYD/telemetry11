from datetime import datetime, timezone, timedelta
import time

import metrics.ingester
from metrics.storage import parse_metric_key

DEFAULT_RANGE_MINUTES = 15


def parse_duration_to_minutes(value: str | None):
    if value is None:
        return None
    raw = value.strip().lower()
    if not raw:
        return None
    if raw.isdigit():
        minutes = int(raw)
        if minutes <= 0:
            raise ValueError("duration must be > 0")
        return minutes

    unit = raw[-1]
    amount = raw[:-1]
    if not amount.isdigit():
        raise ValueError("duration must be a number optionally ending with 'm' or 'h'")

    numeric = int(amount)
    if numeric <= 0:
        raise ValueError("duration must be > 0")

    if unit == "m":
        return numeric
    if unit == "h":
        return numeric * 60

    raise ValueError("duration must end with 'm' or 'h'")


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


def _get_int_arg(args, key: str, default=None):
    if hasattr(args, "get"):
        try:
            return args.get(key, default, type=int)
        except TypeError:
            value = args.get(key, default)
        except ValueError:
            return None
    else:
        value = args.get(key, default) if args is not None else default

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_query_range(args):
    mode = ((args.get("mode") if args is not None else None) or "relative").strip().lower()
    if mode not in {"relative", "absolute"}:
        return {
            "error": "mode must be either 'relative' or 'absolute'",
            "status": 400,
        }

    duration_raw = args.get("duration") if args is not None else None
    start_raw = args.get("start") if args is not None else None
    end_raw = args.get("end") if args is not None else None
    timezone_mode = ((args.get("timezone") if args is not None else None) or "browser").strip().lower()
    if timezone_mode not in {"browser", "utc"}:
        timezone_mode = "browser"
    tz_offset_minutes = _get_int_arg(args, "tz_offset_minutes")

    minutes = _get_int_arg(args, "minutes", DEFAULT_RANGE_MINUTES)
    if minutes is None or minutes <= 0:
        return {
            "error": "minutes must be a positive integer",
            "status": 400,
        }

    if mode == "relative" and duration_raw:
        try:
            minutes = parse_duration_to_minutes(duration_raw)
        except ValueError as exc:
            return {
                "error": f"invalid duration: {exc}",
                "status": 400,
            }

    start_time = None
    end_time = None
    if mode == "absolute":
        if not start_raw or not end_raw:
            return {
                "error": "absolute mode requires both start and end",
                "status": 400,
            }
        try:
            browser_offset = tz_offset_minutes if timezone_mode == "browser" else None
            start_time = parse_time_param(start_raw, browser_tz_offset_minutes=browser_offset)
            end_time = parse_time_param(end_raw, browser_tz_offset_minutes=browser_offset)
        except ValueError as exc:
            return {
                "error": f"invalid time format: {exc}",
                "status": 400,
            }

    return {
        "mode": mode,
        "duration_raw": duration_raw,
        "start_raw": start_raw,
        "end_raw": end_raw,
        "timezone_mode": timezone_mode,
        "tz_offset_minutes": tz_offset_minutes,
        "minutes": minutes,
        "start_time": start_time,
        "end_time": end_time,
    }


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
    query_start = time.perf_counter()
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

    duration_ms = (time.perf_counter() - query_start) * 1000
    points_count = sum(len(series["points"]) for series in series_list)
    metrics.ingester.add_metric(
        f"{metrics.ingester.INTERNAL_PREFIX}query_duration_ms",
        round(duration_ms, 3),
        metrics.ingester.internal_labels({"query_type": "chart"}),
        emit_internal_stats=False,
    )
    metrics.ingester.add_metric(
        f"{metrics.ingester.INTERNAL_PREFIX}query_series_count",
        len(series_list),
        metrics.ingester.internal_labels({"query_type": "chart"}),
        emit_internal_stats=False,
    )
    metrics.ingester.add_metric(
        f"{metrics.ingester.INTERNAL_PREFIX}query_points_count",
        points_count,
        metrics.ingester.internal_labels({"query_type": "chart"}),
        emit_internal_stats=False,
    )

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
    query_start = time.perf_counter()
    start_time, end_time, span_minutes = _resolve_window(minutes, start_time=start_time, end_time=end_time)

    keys = _select_metric_keys(storage, metric_selector)
    if not keys:
        duration_ms = (time.perf_counter() - query_start) * 1000
        metrics.ingester.add_metric(
            f"{metrics.ingester.INTERNAL_PREFIX}query_duration_ms",
            round(duration_ms, 3),
            metrics.ingester.internal_labels({"query_type": "api"}),
            emit_internal_stats=False,
        )
        metrics.ingester.add_metric(
            f"{metrics.ingester.INTERNAL_PREFIX}query_series_count",
            0,
            metrics.ingester.internal_labels({"query_type": "api"}),
            emit_internal_stats=False,
        )
        metrics.ingester.add_metric(
            f"{metrics.ingester.INTERNAL_PREFIX}query_points_count",
            0,
            metrics.ingester.internal_labels({"query_type": "api"}),
            emit_internal_stats=False,
        )
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

    duration_ms = (time.perf_counter() - query_start) * 1000
    points_count = sum(len(series["points"]) for series in series_list)
    metrics.ingester.add_metric(
        f"{metrics.ingester.INTERNAL_PREFIX}query_duration_ms",
        round(duration_ms, 3),
        metrics.ingester.internal_labels({"query_type": "api"}),
        emit_internal_stats=False,
    )
    metrics.ingester.add_metric(
        f"{metrics.ingester.INTERNAL_PREFIX}query_series_count",
        len(series_list),
        metrics.ingester.internal_labels({"query_type": "api"}),
        emit_internal_stats=False,
    )
    metrics.ingester.add_metric(
        f"{metrics.ingester.INTERNAL_PREFIX}query_points_count",
        points_count,
        metrics.ingester.internal_labels({"query_type": "api"}),
        emit_internal_stats=False,
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

# metrics/query.py
from datetime import datetime, timezone, timedelta

DEFAULT_RANGE_MINUTES = 15


def get_series_for_chart(storage: dict, metric_name: str, minutes: int = DEFAULT_RANGE_MINUTES):
    if metric_name not in storage:
        return None

    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=minutes)

    series = []
    for point in storage[metric_name]:
        ts = datetime.fromisoformat(point["timestamp"])
        if ts >= start_time:
            series.append({
                "x": int(ts.timestamp() * 1000),  # epoch ms
                "y": point["value"]
            })

    return {
        "series": series,
        "start": int(start_time.timestamp() * 1000),
        "end": int(now.timestamp() * 1000),
    }

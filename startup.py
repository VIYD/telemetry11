from datetime import timedelta
from pathlib import Path
import json
import logging
import threading
import time
import urllib.error
import urllib.request

import yaml

import metrics.ingester
import metrics.storage


DEFAULT_RETENTION = timedelta(hours=12)

_scraper_started = False
_federate_refresher_started = False
_target_status_lock = threading.Lock()
_target_status = {}


def init_app_defaults(app):
    app.config["PUSH_API_ENABLED"] = True
    app.config["METRIC_RETENTION"] = DEFAULT_RETENTION
    app.config["RAW_CONFIG"] = {}
    app.config["CONFIG_PATH"] = None
    app.config["APP_PORT"] = 5000
    app.config["SCRAPE_ENDPOINT"] = None
    app.config["SCRAPE_INTERVAL_SECONDS"] = 15
    app.config["PULL_TARGETS"] = []
    app.config["FEDERATE_REFRESH_SECONDS"] = 60
    app.config["FEDERATE_MAX_AGE_SECONDS"] = 60
    app.config["LOG_LEVEL"] = "INFO"
    metrics.storage.set_federate_max_age_seconds(app.config["FEDERATE_REFRESH_SECONDS"])


def _now_utc_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _set_target_status(alias, **fields):
    with _target_status_lock:
        current = _target_status.get(alias, {})
        current.update(fields)
        _target_status[alias] = current


def snapshot_target_statuses(targets):
    with _target_status_lock:
        statuses = {k: dict(v) for k, v in _target_status.items()}

    rows = []
    for target in targets:
        alias = target["alias"]
        row = {
            "alias": alias,
            "endpoint": target["endpoint"],
            "interval": target["interval"],
            "status": "never",
            "last_scrape_at": None,
            "last_success_at": None,
            "last_error": None,
            "last_added_metrics": 0,
            "consecutive_failures": 0,
        }
        row.update(statuses.get(alias, {}))
        rows.append(row)
    return rows


def parse_metric_retention(value):
    if value is None:
        return DEFAULT_RETENTION

    if isinstance(value, int):
        if value <= 0:
            raise ValueError("Config key 'metric-retention' must be > 0")
        return timedelta(hours=value)

    if isinstance(value, str):
        raw = value.strip().lower()
        if len(raw) < 2:
            raise ValueError("Config key 'metric-retention' must be like '12h' or '30m'")

        unit = raw[-1]
        amount = raw[:-1]
        if not amount.isdigit():
            raise ValueError("Config key 'metric-retention' must be like '12h' or '30m'")

        numeric = int(amount)
        if numeric <= 0:
            raise ValueError("Config key 'metric-retention' must be > 0")

        if unit == "h":
            return timedelta(hours=numeric)
        if unit == "m":
            return timedelta(minutes=numeric)

    raise ValueError(
        "Config key 'metric-retention' must be an int (hours) or string like '12h'/'30m'"
    )


def format_retention(retention: timedelta) -> str:
    total_minutes = int(retention.total_seconds() // 60)
    if total_minutes % 60 == 0:
        return f"{total_minutes // 60}h"
    return f"{total_minutes}m"


def _parse_positive_int(value, key_name):
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Config key '{key_name}' must be a positive integer")
    return value


def _parse_log_level(value, key_name="log-level"):
    if value is None:
        return "INFO"
    if not isinstance(value, str):
        raise ValueError(f"Config key '{key_name}' must be a string")

    normalized = value.strip().upper()
    allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
    if normalized not in allowed:
        raise ValueError(
            f"Config key '{key_name}' must be one of: {', '.join(sorted(allowed))}"
        )
    return normalized


def configure_logging(level_name: str, logger):
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    # Suppress very noisy filesystem watcher logs when app runs with debug/reloader.
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("watchdog.observers.inotify_buffer").setLevel(logging.WARNING)
    logger.info("Logging configured at level=%s", level_name)


def _extract_pull_targets(parsed: dict):
    pull_cfg = parsed.get("pull")
    if pull_cfg is None:
        return []
    if not isinstance(pull_cfg, dict):
        raise ValueError("Config key 'pull' must be an object")

    default_interval = pull_cfg.get("scrape-interval-seconds")
    if default_interval is None:
        default_interval = 15
    default_interval = _parse_positive_int(default_interval, "pull.scrape-interval-seconds")

    targets = []

    # Backward-compatible single endpoint format.
    single_endpoint = pull_cfg.get("endpoint")
    if single_endpoint is not None:
        if not isinstance(single_endpoint, str):
            raise ValueError("Config key 'pull.endpoint' must be a string")
        alias = pull_cfg.get("alias", "default")
        if not isinstance(alias, str):
            raise ValueError("Config key 'pull.alias' must be a string")
        targets.append(
            {
                "alias": alias,
                "endpoint": single_endpoint,
                "interval": default_interval,
            }
        )

    # New multiple-endpoint format.
    endpoints = pull_cfg.get("endpoints")
    if endpoints is not None:
        if not isinstance(endpoints, list):
            raise ValueError("Config key 'pull.endpoints' must be an array")

        for i, item in enumerate(endpoints):
            if not isinstance(item, dict):
                raise ValueError(f"Config key 'pull.endpoints[{i}]' must be an object")

            endpoint = item.get("endpoint")
            if not isinstance(endpoint, str):
                raise ValueError(f"Config key 'pull.endpoints[{i}].endpoint' must be a string")

            alias = item.get("alias", f"endpoint-{i + 1}")
            if not isinstance(alias, str):
                raise ValueError(f"Config key 'pull.endpoints[{i}].alias' must be a string")

            interval = item.get("scrape-interval-seconds", default_interval)
            interval = _parse_positive_int(interval, f"pull.endpoints[{i}].scrape-interval-seconds")

            targets.append(
                {
                    "alias": alias,
                    "endpoint": endpoint,
                    "interval": interval,
                }
            )

    if not targets:
        return []

    # Ensure unique aliases for labels/logging readability.
    seen = set()
    for t in targets:
        base = t["alias"]
        current = base
        suffix = 2
        while current in seen:
            current = f"{base}-{suffix}"
            suffix += 1
        t["alias"] = current
        seen.add(current)

    return targets


def scrape_metrics_once(target: dict, logger):
    alias = target["alias"]
    endpoint = target["endpoint"]
    logger.debug("Scraping metrics alias=%s endpoint=%s", alias, endpoint)
    _set_target_status(alias, last_scrape_at=_now_utc_iso())
    with urllib.request.urlopen(endpoint, timeout=5) as response:
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)

    metrics_list = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(metrics_list, list):
        return 0

    added = 0
    for item in metrics_list:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}

        if not isinstance(name, str):
            continue

        merged_labels = dict(labels)
        merged_labels["method"] = "scrape"
        merged_labels["scrape_alias"] = alias
        metrics.ingester.add_metric(name=name, value=value, labels=merged_labels)
        added += 1

    _set_target_status(
        alias,
        status="up",
        last_success_at=_now_utc_iso(),
        last_error=None,
        last_added_metrics=added,
        consecutive_failures=0,
    )

    logger.info("Scrape complete alias=%s endpoint=%s added_metrics=%s", alias, endpoint, added)
    logger.debug("Scrape payload alias=%s endpoint=%s payload=%s", alias, endpoint, payload)
    return added


def _scrape_loop(target: dict, logger):
    alias = target["alias"]
    endpoint = target["endpoint"]
    interval = target["interval"]
    logger.info(
        "Background scraper loop started alias=%s endpoint=%s interval=%ss",
        alias,
        endpoint,
        interval,
    )
    while True:
        try:
            scrape_metrics_once(target, logger)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            with _target_status_lock:
                current = _target_status.get(alias, {})
                failures = current.get("consecutive_failures", 0)
            _set_target_status(
                alias,
                status="down",
                last_error=str(exc),
                consecutive_failures=failures + 1,
            )
            logger.warning("Scrape failed alias=%s endpoint=%s error=%s", alias, endpoint, exc)
        time.sleep(interval)


def start_scraper_if_configured(app, logger):
    global _scraper_started
    if _scraper_started:
        return

    targets = app.config.get("PULL_TARGETS") or []
    if not targets:
        logger.info("Scraper disabled (no pull targets configured)")
        return

    for target in targets:
        _set_target_status(
            target["alias"],
            status="starting",
            last_scrape_at=None,
            last_success_at=None,
            last_error=None,
            last_added_metrics=0,
            consecutive_failures=0,
        )
        thread = threading.Thread(target=_scrape_loop, args=(target, logger), daemon=True)
        thread.start()
        logger.info(
            "Scraper thread started alias=%s endpoint=%s interval=%ss",
            target["alias"],
            target["endpoint"],
            target["interval"],
        )

    _scraper_started = True


def _federate_refresh_loop(interval: int, logger):
    logger.info("Federate refresher started interval=%ss", interval)
    while True:
        try:
            snapshot = metrics.storage.refresh_federated_metrics_cache()
            logger.debug(
                "Federate cache refreshed metrics=%s refreshed_at=%s",
                len(snapshot.get("metrics", [])),
                snapshot.get("refreshed_at"),
            )
        except Exception as exc:
            logger.warning("Federate cache refresh failed: %s", exc)
        time.sleep(interval)


def start_federate_refresher(app, logger):
    global _federate_refresher_started
    if _federate_refresher_started:
        return

    interval = app.config.get("FEDERATE_REFRESH_SECONDS", 60)
    thread = threading.Thread(target=_federate_refresh_loop, args=(interval, logger), daemon=True)
    thread.start()
    _federate_refresher_started = True
    logger.info("Federate refresher thread started interval=%ss", interval)


def load_runtime_config(app, logger, config_path=None):
    init_app_defaults(app)
    app.config["CONFIG_PATH"] = config_path

    if not config_path:
        configure_logging(app.config["LOG_LEVEL"], logger)
        logger.info("No config path provided, using defaults")
        return

    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    with cfg_file.open("r", encoding="utf-8") as f:
        parsed = yaml.safe_load(f) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Config file root must be a YAML object")

    app.config["RAW_CONFIG"] = parsed

    app.config["LOG_LEVEL"] = _parse_log_level(parsed.get("log-level"), "log-level")
    configure_logging(app.config["LOG_LEVEL"], logger)
    logger.info("Loaded config file path=%s", config_path)

    push_api = parsed.get("push-api")
    if push_api is not None and not isinstance(push_api, bool):
        raise ValueError("Config key 'push-api' must be a boolean")
    if isinstance(push_api, bool):
        app.config["PUSH_API_ENABLED"] = push_api

    app.config["METRIC_RETENTION"] = parse_metric_retention(parsed.get("metric-retention"))

    app_port = parsed.get("app-port")
    if app_port is not None:
        app.config["APP_PORT"] = _parse_positive_int(app_port, "app-port")

    federate_refresh = parsed.get("federate-refresh-seconds")
    if federate_refresh is not None:
        app.config["FEDERATE_REFRESH_SECONDS"] = _parse_positive_int(
            federate_refresh, "federate-refresh-seconds"
        )

    targets = _extract_pull_targets(parsed)
    app.config["PULL_TARGETS"] = targets

    if parsed.get("federate-max-age-seconds") is not None:
        logger.warning(
            "Config key 'federate-max-age-seconds' is ignored; staleness now follows federate-refresh-seconds"
        )

    app.config["FEDERATE_MAX_AGE_SECONDS"] = app.config["FEDERATE_REFRESH_SECONDS"]
    metrics.storage.set_federate_max_age_seconds(app.config["FEDERATE_REFRESH_SECONDS"])

    # Keep backward-compat status keys populated from first target.
    if targets:
        app.config["SCRAPE_ENDPOINT"] = targets[0]["endpoint"]
        app.config["SCRAPE_INTERVAL_SECONDS"] = targets[0]["interval"]

    logger.info(
        "Effective config push_api=%s retention=%s app_port=%s scrape_targets=%s federate_refresh=%ss federate_age_window=%ss log_level=%s",
        app.config["PUSH_API_ENABLED"],
        format_retention(app.config["METRIC_RETENTION"]),
        app.config["APP_PORT"],
        len(app.config["PULL_TARGETS"]),
        app.config["FEDERATE_REFRESH_SECONDS"],
        app.config["FEDERATE_MAX_AGE_SECONDS"],
        app.config["LOG_LEVEL"],
    )

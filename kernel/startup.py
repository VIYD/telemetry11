from datetime import timedelta
from pathlib import Path
import copy
import logging

import yaml

import metrics.storage
import kernel.routines as routines


DEFAULT_RETENTION = timedelta(hours=12)

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


RUNTIME_CONFIG_KEYS = [
    "PUSH_API_ENABLED",
    "METRIC_RETENTION",
    "RAW_CONFIG",
    "CONFIG_PATH",
    "APP_PORT",
    "SCRAPE_ENDPOINT",
    "SCRAPE_INTERVAL_SECONDS",
    "PULL_TARGETS",
    "FEDERATE_REFRESH_SECONDS",
    "FEDERATE_MAX_AGE_SECONDS",
    "LOG_LEVEL",
]


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


def _default_runtime_config(config_path=None):
    return {
        "PUSH_API_ENABLED": True,
        "METRIC_RETENTION": DEFAULT_RETENTION,
        "RAW_CONFIG": {},
        "CONFIG_PATH": config_path,
        "APP_PORT": 5000,
        "SCRAPE_ENDPOINT": None,
        "SCRAPE_INTERVAL_SECONDS": 15,
        "PULL_TARGETS": [],
        "FEDERATE_REFRESH_SECONDS": 60,
        "FEDERATE_MAX_AGE_SECONDS": 60,
        "LOG_LEVEL": "INFO",
    }


def _load_parsed_config(config_path):
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    with cfg_file.open("r", encoding="utf-8") as f:
        parsed = yaml.safe_load(f) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Config file root must be a YAML object")

    return parsed


def _build_effective_runtime_config(parsed, config_path):
    effective = _default_runtime_config(config_path=config_path)
    warnings = []
    effective["RAW_CONFIG"] = parsed

    effective["LOG_LEVEL"] = _parse_log_level(parsed.get("log-level"), "log-level")

    push_api = parsed.get("push-api")
    if push_api is not None and not isinstance(push_api, bool):
        raise ValueError("Config key 'push-api' must be a boolean")
    if isinstance(push_api, bool):
        effective["PUSH_API_ENABLED"] = push_api

    effective["METRIC_RETENTION"] = parse_metric_retention(parsed.get("metric-retention"))

    app_port = parsed.get("app-port")
    if app_port is not None:
        effective["APP_PORT"] = _parse_positive_int(app_port, "app-port")

    federate_refresh = parsed.get("federate-refresh-seconds")
    if federate_refresh is not None:
        effective["FEDERATE_REFRESH_SECONDS"] = _parse_positive_int(
            federate_refresh, "federate-refresh-seconds"
        )

    targets = _extract_pull_targets(parsed)
    effective["PULL_TARGETS"] = targets

    if parsed.get("federate-max-age-seconds") is not None:
        warnings.append(
            "Config key 'federate-max-age-seconds' is ignored; staleness now follows federate-refresh-seconds"
        )

    effective["FEDERATE_MAX_AGE_SECONDS"] = effective["FEDERATE_REFRESH_SECONDS"]

    if targets:
        effective["SCRAPE_ENDPOINT"] = targets[0]["endpoint"]
        effective["SCRAPE_INTERVAL_SECONDS"] = targets[0]["interval"]

    return effective, warnings


def _snapshot_runtime_config(app):
    return {key: copy.deepcopy(app.config.get(key)) for key in RUNTIME_CONFIG_KEYS}


def _apply_effective_runtime_config(app, logger, effective, warnings=None):
    for key in RUNTIME_CONFIG_KEYS:
        app.config[key] = effective.get(key)

    metrics.storage.set_federate_max_age_seconds(app.config["FEDERATE_REFRESH_SECONDS"])
    configure_logging(app.config["LOG_LEVEL"], logger)

    for warning in warnings or []:
        logger.warning(warning)

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


def load_runtime_config(app, logger, config_path=None):
    if not config_path:
        effective = _default_runtime_config(config_path=None)
        _apply_effective_runtime_config(app, logger, effective)
        logger.info("No config path provided, using defaults")
        return

    parsed = _load_parsed_config(config_path)
    effective, warnings = _build_effective_runtime_config(parsed, config_path)
    _apply_effective_runtime_config(app, logger, effective, warnings=warnings)
    logger.info("Loaded config file path=%s", config_path)


def reload_runtime_config(app, logger):
    config_path = app.config.get("CONFIG_PATH")
    if not config_path:
        raise ValueError("Cannot reload: no config file path configured")

    previous = _snapshot_runtime_config(app)

    try:
        parsed = _load_parsed_config(config_path)
        effective, warnings = _build_effective_runtime_config(parsed, config_path)
        _apply_effective_runtime_config(app, logger, effective, warnings=warnings)
        # Ensure any new pull targets get worker threads.
        routines.start_scraper_if_configured(app, logger)
        return {
            "status": "ok",
            "config_path": config_path,
            "pull_targets": len(app.config.get("PULL_TARGETS") or []),
            "federate_refresh_seconds": app.config.get("FEDERATE_REFRESH_SECONDS"),
            "log_level": app.config.get("LOG_LEVEL"),
        }
    except Exception:
        _apply_effective_runtime_config(app, logger, previous)
        raise

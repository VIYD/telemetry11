import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

import metrics.ingester
import metrics.storage


_scraper_started = False
_federate_refresher_started = False
_scraper_aliases_started = set()
_target_status_lock = threading.Lock()
_target_status = {}


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


def _find_target_by_alias(targets, alias):
	for target in targets or []:
		if target.get("alias") == alias:
			return target
	return None


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


def _scrape_loop(app, alias: str, logger):
	target = _find_target_by_alias(app.config.get("PULL_TARGETS") or [], alias)
	endpoint = target["endpoint"] if target else "(dynamic)"
	interval = target["interval"] if target else 15
	logger.info(
		"Background scraper loop started alias=%s endpoint=%s interval=%ss",
		alias,
		endpoint,
		interval,
	)
	while True:
		target = _find_target_by_alias(app.config.get("PULL_TARGETS") or [], alias)
		if not target:
			_set_target_status(
				alias,
				status="disabled",
				last_error="target removed from runtime config",
			)
			time.sleep(1)
			continue

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
			logger.warning("Scrape failed alias=%s endpoint=%s error=%s", alias, target["endpoint"], exc)
		time.sleep(target["interval"])


def start_scraper_if_configured(app, logger):
	global _scraper_started, _scraper_aliases_started

	targets = app.config.get("PULL_TARGETS") or []
	if not targets:
		logger.info("Scraper disabled (no pull targets configured)")
		return

	for target in targets:
		if target["alias"] in _scraper_aliases_started:
			continue

		_set_target_status(
			target["alias"],
			status="starting",
			last_scrape_at=None,
			last_success_at=None,
			last_error=None,
			last_added_metrics=0,
			consecutive_failures=0,
		)
		thread = threading.Thread(target=_scrape_loop, args=(app, target["alias"], logger), daemon=True)
		thread.start()
		_scraper_aliases_started.add(target["alias"])
		logger.info(
			"Scraper thread started alias=%s endpoint=%s interval=%ss",
			target["alias"],
			target["endpoint"],
			target["interval"],
		)

	_scraper_started = True


def _federate_refresh_loop(app, logger):
	logger.info("Federate refresher started interval=%ss", app.config.get("FEDERATE_REFRESH_SECONDS", 60))
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
		interval = app.config.get("FEDERATE_REFRESH_SECONDS", 60)
		if not isinstance(interval, int) or interval <= 0:
			interval = 60
		time.sleep(interval)


def start_federate_refresher(app, logger):
	global _federate_refresher_started
	if _federate_refresher_started:
		return

	interval = app.config.get("FEDERATE_REFRESH_SECONDS", 60)
	thread = threading.Thread(target=_federate_refresh_loop, args=(app, logger), daemon=True)
	thread.start()
	_federate_refresher_started = True
	logger.info("Federate refresher thread started interval=%ss", interval)

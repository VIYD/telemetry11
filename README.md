# telemetry11

Lightweight telemetry collector.

Work in progress.

## Features
- Lightweight telemetry ingestion
- Basic metric indexing
- Metric retrieval
- Query chart page (`/query`, alias `/dashboard`)
- Status page (`/status`) showing loaded config values
- Pull-based scraping from external exporter endpoint

## Requirements
- Runtime: Python 3.10+

## Configuration

Application supports optional YAML config via `--config`.

Example (`config.yaml`):

```yaml
push-api: true
metric-retention: 12h
app-port: 5000
federate-refresh-seconds: 60
log-level: INFO
pull:
  scrape-interval-seconds: 10
	endpoints:
		- alias: "node-a"
			endpoint: "http://127.0.0.1:9100/metrics"
		- alias: "node-b"
			endpoint: "http://127.0.0.1:9101/metrics"
			scrape-interval-seconds: 5
```

- `push-api: true` — `/push` endpoint accepts metrics and ingests them.
- `push-api: false` — `/push` endpoint rejects requests with `503`.
- `metric-retention` — how long to keep metrics before auto-deletion (default: `12h`).
	- Supported formats:
		- string with unit: `12h`, `30m`
		- integer: treated as hours (for example `12` = `12h`)
- `app-port` — application HTTP port (default: `5000`).
- `federate-refresh-seconds` — how often `/federate` snapshot is refreshed (default: `60`).
- Federated staleness window is tied to `federate-refresh-seconds`; a series is exposed only if updated within that window.
- `federate-max-age-seconds` is deprecated and ignored if present.
- `log-level` — log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default: `INFO`).
- `pull.scrape-interval-seconds` — default scrape interval in seconds.
- `pull.endpoints` — list of scrape targets:
	- `endpoint` (required) — exporter endpoint URL.
	- `alias` (optional) — friendly target name used in logs and metric label.
	- `scrape-interval-seconds` (optional) — per-endpoint override interval.

Backward-compatible single-target format is still accepted:

```yaml
pull:
	endpoint: "http://127.0.0.1:9100/metrics"
	alias: "default"
	scrape-interval-seconds: 10
```

When metric is accepted through `/push`, label `method="push"` is automatically added.
When metric is scraped, labels `method="scrape"` and `scrape_alias="..."` are added.

`/federate` exposes one latest value per metric series (name + labels), from cached snapshot refreshed by `federate-refresh-seconds`.

## Exporter

System exporter is available under `exporter/`.

- Run exporter with `python exporter/exporter.py --config exporter/config.yaml`
- Exporter exposes `GET /metrics` with app-compatible payload.

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
- OpenAPI spec (`/openapi.json`) and Swagger UI (`/swagger`)

## Requirements
- Runtime: Python 3.10+

## Running

Main app (Gunicorn):

- `TELEMETRY_CONFIG=examples/config.example.yaml gunicorn -c gunicorn.conf.py app:app`
- `make run-prod` (uses `TELEMETRY_CONFIG=examples/config.example.yaml` by default)

Notes:

- Gunicorn imports `app:app` and uses `TELEMETRY_CONFIG` to load runtime config.
- Default Gunicorn config keeps `workers=1` because this app stores metrics in-process and starts background threads in-process.
- Direct `python3 app.py` execution is intentionally disabled.

## Configuration

Application loads YAML config from environment variable `TELEMETRY_CONFIG`.

Example (`config.yaml`):

```yaml
push-api: true
internal-metrics: true
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
- `internal-metrics: true` — enable internal application metrics (default: `true`).
- `internal-metrics: false` — disable internal metrics emission entirely.
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

## Internal metrics

The application can emit its own metrics (prefixed with `internal_` and labeled with `label="internal"`).
These are stored in the same in-memory storage and are visible in `/explorer` and `/query` like any other series.

Core internal metrics:

- `internal_total_time_series` — total distinct series in storage (emitted every 60s).
- `internal_total_metrics` — total data points stored (emitted every 60s).
- `internal_query_duration_ms` — time spent building a query response.
- `internal_query_series_count` — number of series returned by a query.
- `internal_query_points_count` — number of points returned by a query.
- `internal_scrape_targets_total` — total scrape attempts.
- `internal_scrape_targets_success` — successful scrape attempts.
- `internal_scrape_targets_fail` — failed scrape attempts.
- `internal_scrape_duration_ms` — most recent scrape duration.

`/query` and `GET /api/metrics` support custom time ranges via optional `start` and `end` (ISO 8601) query parameters; `minutes` is used as fallback window.

Range mode can be selected with `mode`:

- `mode=relative` — use `minutes`
- `mode=absolute` — use both `start` and `end`

`POST /api/reload` reloads configuration from the currently active `TELEMETRY_CONFIG` file. If reload fails (for example invalid YAML), previous runtime configuration remains active.

## Exporter

System exporter is available under `exporter/`.

- Run exporter with `EXPORTER_CONFIG=examples/exporter-config.example.yaml gunicorn -c exporter/gunicorn.conf.py exporter.exporter:app`
- Exporter exposes `GET /metrics` with app-compatible payload.

## Container

This repository includes a `Dockerfile` for running the main telemetry app in a container.

- Default config inside container: `examples/config.example.yaml`
- Override config by setting env var `TELEMETRY_CONFIG` and mounting your config file.
- Container exposes port `5000` (ensure your config `app-port` matches the mapped port).
- Container starts with Gunicorn by default.

Example build/run:

```bash
docker build -t telemetry11 .
docker run --rm -p 5000:5000 telemetry11
```

With custom config file:

```bash
docker run --rm -p 5000:5000 \
	-e TELEMETRY_CONFIG=/config/config.yaml \
	-v $(pwd)/examples/config.example.yaml:/config/config.yaml:ro \
	telemetry11
```

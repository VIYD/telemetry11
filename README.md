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
log-level: INFO
pull:
  endpoint: "http://127.0.0.1:9100/metrics"
  scrape-interval-seconds: 10
```

- `push-api: true` — `/push` endpoint accepts metrics and ingests them.
- `push-api: false` — `/push` endpoint rejects requests with `503`.
- `metric-retention` — how long to keep metrics before auto-deletion (default: `12h`).
	- Supported formats:
		- string with unit: `12h`, `30m`
		- integer: treated as hours (for example `12` = `12h`)
- `app-port` — application HTTP port (default: `5000`).
- `log-level` — log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default: `INFO`).
- `pull.endpoint` — exporter endpoint that returns federated metrics payload.
- `pull.scrape-interval-seconds` — scrape interval in seconds.

When metric is accepted through `/push`, label `method="push"` is automatically added.
When metric is scraped via `pull.endpoint`, label `method="scraped"` is added.

## Exporter

System exporter is available under `exporter/`.

- Run exporter with `python exporter/exporter.py --config exporter/config.yaml`
- Exporter exposes `GET /federate` with app-compatible payload.

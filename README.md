# telemetry11

Lightweight telemetry collector.

Work in progress.

## Features
- Lightweight telemetry ingestion
- Basic metric indexing
- Metric retrieval
- Query chart page (`/query`, alias `/dashboard`)
- Status page (`/status`) showing loaded config values

## Requirements
- Runtime: Python 3.10+

## Configuration

Application supports optional YAML config via `--config`.

Example (`config.yaml`):

```yaml
push-api: true
metric-retention: 12h
```

- `push-api: true` — `/push` endpoint accepts metrics and ingests them.
- `push-api: false` — `/push` endpoint rejects requests with `503`.
- `metric-retention` — how long to keep metrics before auto-deletion (default: `12h`).
	- Supported formats:
		- string with unit: `12h`, `30m`
		- integer: treated as hours (for example `12` = `12h`)

When metric is accepted through `/push`, label `method="push"` is automatically added.

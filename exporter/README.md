# Exporter

Simple system metrics exporter based on `psutil`.

## Config

`config.yaml` example:

```yaml
refresh-seconds: 5
port: 9100
log-level: INFO
```

- `refresh-seconds` — how often to refresh local system metrics.
- `port` — HTTP port for exporter server.
- `log-level` — exporter logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).

## Endpoints

- `GET /metrics` — returns latest metrics in app-compatible format:
  ```json
  {"metrics": [{"name": "...", "labels": {...}, "value": 0.0}]}
  ```
- `GET /health` — exporter health status.

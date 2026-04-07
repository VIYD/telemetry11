# Exporter

Simple system metrics exporter based on `psutil`.

## Config

`config.yaml` example:

```yaml
refresh-seconds: 5
port: 9100
```

- `refresh-seconds` — how often to refresh local system metrics.
- `port` — HTTP port for exporter server.

## Endpoints

- `GET /metrics` — returns latest metrics in app-compatible format:
  ```json
  {"metrics": [{"name": "...", "labels": {...}, "value": 0.0}]}
  ```
- `GET /health` — exporter health status.

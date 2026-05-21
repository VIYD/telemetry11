# Exporter

Simple system metrics exporter based on `psutil`.

## Config

`examples/configs/exporter.yaml` example:

```yaml
refresh-seconds: 5
port: 9100
log-level: INFO
labels:
  env: dev
  region: eu-central
```

- `refresh-seconds` — how often to refresh local system metrics.
- `port` — HTTP port for exporter server.
- `log-level` — exporter logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- `labels` — optional map of labels added to every metric.

## Running

- `EXPORTER_CONFIG=examples/configs/exporter.yaml gunicorn -c exporter/gunicorn.conf.py exporter.exporter:app`

Notes:

- Exporter config is loaded from `EXPORTER_CONFIG` (default: `examples/configs/exporter.yaml`).
- Use one worker by default (`exporter/gunicorn.conf.py`) because exporter keeps in-process state and collector thread.

## Endpoints

- `GET /metrics` — returns latest metrics in app-compatible format:
  ```json
  {"metrics": [{"name": "...", "labels": {...}, "value": 0.0}]}
  ```
- `GET /health` — exporter health status.

## Exposed metric families

Exporter now emits a wider psutil set (availability may vary by OS/kernel):

- CPU: `cpu_percent`, `cpu_count_logical`, `cpu_count_physical`,
  `loadavg_1m|5m|15m`, `cpu_freq_*`, `cpu_time_*_seconds`
- Memory: `memory_percent`, `memory_total_bytes`, `memory_used_bytes`,
  `memory_available_bytes`, `memory_free_bytes`, `memory_cached_bytes`,
  `memory_buffers_bytes`, `swap_*`
- Disk: `disk_root_*`, `disk_read_bytes_total`, `disk_write_bytes_total`,
  `disk_read_count_total`, `disk_write_count_total`
- Network: `network_bytes_*_total`, `network_packets_*_total`,
  `network_err*_total`, `network_drop*_total`
- System: `process_count`, `boot_time_unix`, `uptime_seconds`

All metrics include `host` label plus any `labels` configured in the exporter config.

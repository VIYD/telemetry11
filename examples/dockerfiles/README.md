# Service images with bundled exporter

These Dockerfiles build service images that also run the telemetry system exporter on port `9100`.
Each exporter adds a `service` label (`grafana`, `clickhouse`, or `postgres`) to help identify
metrics in the telemetry app.

## Build

```bash
docker build -f examples/configs/dockerfiles/Dockerfile.grafana -t telemetry11-grafana-exporter .
docker build -f examples/configs/dockerfiles/Dockerfile.clickhouse -t telemetry11-clickhouse-exporter .
docker build -f examples/configs/dockerfiles/Dockerfile.postgres -t telemetry11-postgres-exporter .
```

## Run

```bash
docker run --rm -p 3000:3000 -p 9100:9100 telemetry11-grafana-exporter
docker run --rm -p 8123:8123 -p 9000:9000 -p 9100:9100 telemetry11-clickhouse-exporter
docker run --rm -p 5432:5432 -p 9100:9100 telemetry11-postgres-exporter
```

## Exporter notes

- Exporter config lives in `/etc/telemetry/exporter.yaml` inside the images.
- Override with `-e EXPORTER_CONFIG=/path/to/config.yaml` and mount a custom file if needed.
- Exporter runs via `gunicorn` using `exporter/gunicorn.conf.py` from this repo.

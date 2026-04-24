.PHONY: run run-prod run-exporter run-docker-build run-docker

TELEMETRY_CONFIG ?= examples/config.example.yaml
EXPORTER_CONFIG ?= examples/exporter-config.example.yaml
IMAGE ?= telemetry11:latest

run:
	TELEMETRY_CONFIG=$(TELEMETRY_CONFIG) gunicorn -c gunicorn.conf.py app:app

run-prod: run

run-exporter:
	EXPORTER_CONFIG=$(EXPORTER_CONFIG) gunicorn -c exporter/gunicorn.conf.py exporter.exporter:app

run-docker-build:
	docker build -t $(IMAGE) .

run-docker:
	docker run --rm -p 5000:5000 $(IMAGE)
